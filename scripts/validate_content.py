from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from mmm_common import (
    ValidationError,
    ensure_iso8601_datetime,
    ensure_kebab_case_slug,
    load_json,
    validate_mix,
    validate_note_payload,
)

ROOT = Path(__file__).resolve().parents[1]
SUPPORTED_LISTENING_KINDS = {"listen", "playlist", "album", "track", "set", "embed"}
KNOWN_PROVIDER_LABELS = {
    "applemusic": "Apple Music",
    "bandcamp": "Bandcamp",
    "mixcloud": "Mixcloud",
    "soundcloud": "SoundCloud",
    "spotify": "Spotify",
    "youtube": "YouTube",
}
PROVIDER_HOST_MATCHERS = {
    "applemusic": lambda host: host == "music.apple.com",
    "bandcamp": lambda host: host == "daily.bandcamp.com" or host.endswith(".bandcamp.com"),
    "mixcloud": lambda host: host.endswith("mixcloud.com"),
    "soundcloud": lambda host: host.endswith("soundcloud.com"),
    "spotify": lambda host: host == "open.spotify.com",
    "youtube": lambda host: host in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"},
}
EMBED_URL_MATCHERS = {
    "mixcloud": lambda host, path: host.endswith("mixcloud.com") and "/widget/" in path,
    "soundcloud": lambda host, path: host == "w.soundcloud.com" and path.startswith("/player"),
    "spotify": lambda host, path: host == "open.spotify.com" and "/embed/" in path,
    "youtube": lambda host, path: host.endswith("youtube.com") and "/embed/" in path,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate MMM editorial content and report issues")
    parser.add_argument("--root", type=Path, default=ROOT, help="Repository root to validate")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    return parser.parse_args()


def add_issue(issues: list[dict[str, str]], severity: str, scope: str, path: Path, message: str) -> None:
    issues.append(
        {
            "severity": severity,
            "scope": scope,
            "path": str(path),
            "message": message,
        }
    )


def require_non_empty_string(payload: dict[str, Any], key: str, label: str) -> str:
    value = str(payload.get(key, "")).strip()
    if not value:
        raise ValidationError(f"{label} must not be empty")
    return value


def normalize_listening_key(value: Any) -> str:
    return "".join(character for character in str(value or "").strip().lower() if character.isalnum())


def provider_label_from_key(value: Any) -> str:
    raw = str(value or "").strip()
    normalized = normalize_listening_key(raw)
    if not normalized:
        return ""
    if normalized in KNOWN_PROVIDER_LABELS:
        return KNOWN_PROVIDER_LABELS[normalized]
    return " ".join(part for part in raw.replace("_", " ").replace("-", " ").split() if part).title()


def is_http_url(value: Any) -> bool:
    raw = str(value or "").strip()
    parsed = urlparse(raw)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def parse_url_parts(value: Any) -> tuple[str, str]:
    parsed = urlparse(str(value or "").strip())
    return parsed.netloc.lower(), parsed.path.lower()


def infer_provider_from_url(value: Any) -> str:
    host, _ = parse_url_parts(value)
    if "spotify.com" in host:
        return "Spotify"
    if host == "music.apple.com":
        return "Apple Music"
    if "youtube.com" in host or host == "youtu.be":
        return "YouTube"
    if "bandcamp.com" in host:
        return "Bandcamp"
    if "soundcloud.com" in host:
        return "SoundCloud"
    if "mixcloud.com" in host:
        return "Mixcloud"
    return "Listening link"


def infer_provider_kind(value: Any) -> str:
    href = str(value or "").strip().lower()
    if not href:
        return "listen"
    if "/embed/" in href or "/embed?" in href or "youtube.com/embed/" in href or "/oembed" in href:
        return "embed"
    if "/playlist/" in href or "videoseries" in href:
        return "playlist"
    if "/album/" in href:
        return "album"
    if "/track/" in href or "/song/" in href:
        return "track"
    if "/sets/" in href:
        return "set"
    return "listen"


def youtube_list_id(value: Any) -> str:
    parsed = urlparse(str(value or "").strip())
    return str(parse_qs(parsed.query).get("list", [""])[0]).strip()


def collect_listening_entries(raw_entries: list[Any], mode: str = "provider", start_mode: str | None = None) -> tuple[list[dict[str, str]], list[str]]:
    items: list[dict[str, str]] = []
    warnings: list[str] = []
    provider_container_keys = {"providers", "links", "providerlinks", "streaming", "entries", "items", "sources"}
    embed_container_keys = {"embeds", "embed", "players", "iframes"}
    meta_keys = {"url", "href", "src", "provider", "label", "title", "kind", "note", "summary", "intro", "description"}
    start_mode = start_mode or mode

    def visit(value: Any, current_mode: str, provider_hint: str) -> None:
        if value is None:
            return

        if isinstance(value, list):
            for entry in value:
                visit(entry, current_mode, provider_hint)
            return

        if isinstance(value, str):
            url = value.strip()
            if not url:
                return
            if not is_http_url(url):
                warnings.append(f"{current_mode} entry uses a non-http(s) URL: {url}")
                return
            if current_mode == "embed":
                items.append(
                    {
                        "mode": current_mode,
                        "provider": provider_hint or infer_provider_from_url(url),
                        "title": "",
                        "url": url,
                        "kind": "embed",
                    }
                )
                return
            items.append(
                {
                    "mode": current_mode,
                    "provider": provider_hint or infer_provider_from_url(url),
                    "label": "",
                    "url": url,
                    "kind": infer_provider_kind(url),
                }
            )
            return

        if not isinstance(value, dict):
            warnings.append(f"{current_mode} entry should be an object, array, or URL string")
            return

        url = str(value.get("url") or value.get("href") or value.get("src") or "").strip()
        has_entry_shape = any(str(value.get(key, "")).strip() for key in ("provider", "label", "title", "kind", "note", "summary"))
        if url:
            if not is_http_url(url):
                warnings.append(f"{current_mode} entry uses a non-http(s) URL: {url}")
            elif current_mode == "embed":
                items.append(
                    {
                        "mode": current_mode,
                        "provider": str(value.get("provider") or provider_hint or infer_provider_from_url(url)).strip(),
                        "title": str(value.get("title") or value.get("label") or "").strip(),
                        "url": url,
                        "kind": "embed",
                    }
                )
            else:
                items.append(
                    {
                        "mode": current_mode,
                        "provider": str(value.get("provider") or provider_hint or infer_provider_from_url(url)).strip(),
                        "label": str(value.get("label") or value.get("title") or "").strip(),
                        "url": url,
                        "kind": str(value.get("kind") or infer_provider_kind(url)).strip(),
                    }
                )
        elif has_entry_shape:
            warnings.append(f"{current_mode} entry is missing a valid http(s) URL")

        for key, child in value.items():
            normalized_key = normalize_listening_key(key)
            if normalized_key in meta_keys or child is None:
                continue
            next_mode = "embed" if normalized_key in embed_container_keys else "provider" if normalized_key in provider_container_keys else current_mode
            next_hint = provider_hint if normalized_key in provider_container_keys | embed_container_keys else provider_label_from_key(key) or provider_hint
            visit(child, next_mode, next_hint)

    for entry in raw_entries:
        visit(entry, start_mode, "")

    deduped: dict[tuple[str, str, str], dict[str, str]] = {}
    for item in items:
        if item["mode"] != mode:
            continue
        provider = str(item.get("provider") or infer_provider_from_url(item.get("url"))).strip() or ("Embed" if mode == "embed" else "Listening link")
        url = str(item.get("url") or "").strip()
        kind = str(item.get("kind") or ("embed" if mode == "embed" else "listen")).strip()
        key = (provider, url, kind)
        deduped.setdefault(key, {**item, "provider": provider, "url": url, "kind": kind})

    return list(deduped.values()), warnings


def audit_published_listening(mix: dict[str, Any]) -> tuple[list[str], list[str]]:
    listening = mix.get("listening")
    errors: list[str] = []
    warnings: list[str] = []

    if listening is not None and not isinstance(listening, dict):
        errors.append("listening must be an object when present")
        return errors, warnings

    listening_obj = listening if isinstance(listening, dict) else {}
    provider_roots = [
        listening_obj.get("providers"),
        listening_obj.get("links"),
        mix.get("providers"),
        mix.get("providerLinks"),
        mix.get("streaming"),
    ]
    embed_roots = [
        listening_obj.get("embeds"),
        mix.get("embeds"),
    ]
    providers, provider_warnings = collect_listening_entries(provider_roots, "provider", "provider")
    embeds_from_providers, embed_from_provider_warnings = collect_listening_entries(provider_roots, "embed", "provider")
    embeds, embed_warnings = collect_listening_entries(embed_roots, "embed", "embed")
    warnings.extend(provider_warnings)
    warnings.extend(embed_from_provider_warnings)
    warnings.extend(embed_warnings)

    all_embeds = list({(entry["provider"], entry["url"]): entry for entry in [*embeds_from_providers, *embeds]}.values())
    provider_urls = {entry["url"] for entry in providers}

    for provider in providers:
        provider_name = str(provider.get("provider") or "").strip() or infer_provider_from_url(provider.get("url"))
        provider_key = normalize_listening_key(provider_name)
        url = str(provider.get("url") or "").strip()
        kind = str(provider.get("kind") or "listen").strip().lower()
        inferred_provider = infer_provider_from_url(url)
        if not is_http_url(url):
            warnings.append(f"provider '{provider_name}' is missing a valid http(s) URL")
            continue
        if kind not in SUPPORTED_LISTENING_KINDS - {"embed"}:
            warnings.append(f"provider '{provider_name}' uses unsupported kind '{provider.get('kind')}'")
        matcher = PROVIDER_HOST_MATCHERS.get(provider_key)
        host, _ = parse_url_parts(url)
        if matcher and not matcher(host):
            warnings.append(f"provider '{provider_name}' URL does not match the expected domain: {url}")
        elif inferred_provider != "Listening link" and provider_name and normalize_listening_key(inferred_provider) != provider_key:
            warnings.append(f"provider '{provider_name}' looks mismatched for URL: {url}")

    for embed in all_embeds:
        provider_name = str(embed.get("provider") or "").strip() or infer_provider_from_url(embed.get("url"))
        provider_key = normalize_listening_key(provider_name)
        url = str(embed.get("url") or "").strip()
        inferred_provider = infer_provider_from_url(url)
        if not is_http_url(url):
            warnings.append(f"embed '{provider_name}' is missing a valid http(s) URL")
            continue
        host, path = parse_url_parts(url)
        matcher = EMBED_URL_MATCHERS.get(provider_key)
        if not matcher or not matcher(host, path):
            warnings.append(f"embed '{provider_name}' is not using a trusted provider/embed URL pair: {url}")
        elif inferred_provider != "Listening link" and normalize_listening_key(inferred_provider) != provider_key:
            warnings.append(f"embed '{provider_name}' looks mismatched for URL: {url}")
        elif provider_key == "youtube":
            playlist_url = next((provider_url for provider_url in provider_urls if "youtube" in parse_url_parts(provider_url)[0] or parse_url_parts(provider_url)[0] == "youtu.be"), "")
            if provider_urls and playlist_url and youtube_list_id(url) and youtube_list_id(playlist_url) and youtube_list_id(url) != youtube_list_id(playlist_url):
                warnings.append(f"embed '{provider_name}' playlist does not match the published provider URL")

    deduped_warnings: list[str] = []
    seen: set[str] = set()
    for warning in warnings:
        if warning in seen:
            continue
        seen.add(warning)
        deduped_warnings.append(warning)

    return errors, deduped_warnings


def validate_site_payload(site: dict[str, Any]) -> None:
    require_non_empty_string(site, "schemaVersion", "site schemaVersion")
    require_non_empty_string(site, "name", "site name")
    require_non_empty_string(site, "tagline", "site tagline")
    require_non_empty_string(site, "description", "site description")
    require_non_empty_string(site, "baseUrl", "site baseUrl")
    author = site.get("author")
    if not isinstance(author, dict):
        raise ValidationError("site author must be an object")
    require_non_empty_string(author, "name", "site author.name")
    navigation = site.get("navigation")
    if not isinstance(navigation, list) or not navigation:
        raise ValidationError("site navigation must be a non-empty array")
    for index, item in enumerate(navigation, start=1):
        if not isinstance(item, dict):
            raise ValidationError(f"site navigation item {index} must be an object")
        require_non_empty_string(item, "label", f"site navigation item {index} label")
        require_non_empty_string(item, "path", f"site navigation item {index} path")


def load_json_with_issue(path: Path, issues: list[dict[str, str]], scope: str) -> Any | None:
    try:
        return load_json(path)
    except FileNotFoundError:
        add_issue(issues, "error", scope, path, "missing file")
    except json.JSONDecodeError as exc:
        add_issue(issues, "error", scope, path, f"invalid JSON: {exc}")
    return None


def validate_mix_collection(directory: Path, expected_flavor: str, issues: list[dict[str, str]], scope: str) -> dict[str, dict[str, Any]]:
    mixes_by_slug: dict[str, dict[str, Any]] = {}
    for path in sorted(directory.glob("*.json")):
        payload = load_json_with_issue(path, issues, scope)
        if payload is None:
            continue
        try:
            result = validate_mix(payload)
        except ValidationError as exc:
            add_issue(issues, "error", scope, path, str(exc))
            continue

        if result.flavor != expected_flavor:
            add_issue(issues, "error", scope, path, f"expected {expected_flavor} content but found {result.flavor}")
            continue

        slug = result.mix["slug"]
        if path.stem != slug:
            add_issue(issues, "warning", scope, path, f"filename should match slug '{slug}.json'")
        if slug in mixes_by_slug:
            add_issue(issues, "error", scope, path, f"duplicate slug also found in {mixes_by_slug[slug]['path']}")
            continue
        for warning in result.warnings:
            add_issue(issues, "warning", scope, path, warning)
        if expected_flavor == "published":
            listening_errors, listening_warnings = audit_published_listening(result.mix)
            for message in listening_errors:
                add_issue(issues, "error", scope, path, message)
            for message in listening_warnings:
                add_issue(issues, "warning", scope, path, message)

        mixes_by_slug[slug] = {"mix": result.mix, "path": str(path)}
    return mixes_by_slug


def validate_notes(notes_dir: Path, notes_index: dict[str, Any] | None, known_mix_slugs: set[str], issues: list[dict[str, str]]) -> dict[str, dict[str, Any]]:
    notes_by_slug: dict[str, dict[str, Any]] = {}
    for path in sorted(notes_dir.glob("*.json")):
        payload = load_json_with_issue(path, issues, "notes")
        if payload is None:
            continue
        try:
            validate_note_payload(payload)
        except ValidationError as exc:
            add_issue(issues, "error", "notes", path, str(exc))
            continue

        slug = str(payload["slug"])
        if path.stem != slug:
            add_issue(issues, "warning", "notes", path, f"filename should match slug '{slug}.json'")
        if slug in notes_by_slug:
            add_issue(issues, "error", "notes", path, f"duplicate note slug also found in {notes_by_slug[slug]['path']}")
            continue

        for related_slug in payload.get("relatedMixSlugs", []):
            if related_slug not in known_mix_slugs:
                add_issue(issues, "warning", "notes", path, f"related mix slug '{related_slug}' does not exist in drafts or published mixes")

        notes_by_slug[slug] = {"note": payload, "path": str(path)}

    if notes_index is None:
        return notes_by_slug

    items = notes_index.get("items")
    if not isinstance(items, list):
        add_issue(issues, "error", "notes-index", notes_dir.parent / "notes-index.json", "items must be an array")
        return notes_by_slug

    indexed_slugs: set[str] = set()
    for item in items:
        slug = str(item.get("slug", "")).strip()
        if not slug:
            add_issue(issues, "error", "notes-index", notes_dir.parent / "notes-index.json", "indexed note missing slug")
            continue
        if slug in indexed_slugs:
            add_issue(issues, "error", "notes-index", notes_dir.parent / "notes-index.json", f"duplicate indexed note slug '{slug}'")
        indexed_slugs.add(slug)

        note_record = notes_by_slug.get(slug)
        if note_record is None:
            add_issue(issues, "error", "notes-index", notes_dir.parent / "notes-index.json", f"indexed note '{slug}' has no file under data/notes/")
            continue
        expected_path = f"data/notes/{slug}.json"
        if item.get("path") != expected_path:
            add_issue(issues, "warning", "notes-index", notes_dir.parent / "notes-index.json", f"indexed note '{slug}' should point to {expected_path}")
        for field in ("title", "summary", "publishedAt"):
            if item.get(field) != note_record["note"].get(field):
                add_issue(issues, "warning", "notes-index", notes_dir.parent / "notes-index.json", f"indexed note '{slug}' field '{field}' is out of sync with note file")

    for slug in notes_by_slug:
        if slug not in indexed_slugs:
            add_issue(issues, "warning", "notes-index", notes_dir.parent / "notes-index.json", f"note '{slug}' is missing from data/notes-index.json")

    total_notes = notes_index.get("totalNotes")
    if total_notes != len(items):
        add_issue(issues, "warning", "notes-index", notes_dir.parent / "notes-index.json", f"totalNotes is {total_notes}, but items contains {len(items)} entries")

    return notes_by_slug


def validate_archive_indexes(
    root: Path,
    published_by_slug: dict[str, dict[str, Any]],
    issues: list[dict[str, str]],
) -> None:
    archive_path = root / "data" / "archive" / "index.json"
    legacy_path = root / "data" / "archive-index.json"
    mixes_json_path = root / "data" / "mixes.json"

    archive = load_json_with_issue(archive_path, issues, "archive")
    if isinstance(archive, dict):
        mixes = archive.get("mixes")
        if not isinstance(mixes, list):
            add_issue(issues, "error", "archive", archive_path, "mixes must be an array")
        else:
            archive_slugs = {item.get("slug") for item in mixes if isinstance(item, dict)}
            published_slugs = set(published_by_slug)
            if archive_slugs != published_slugs:
                missing = sorted(published_slugs - archive_slugs)
                extra = sorted(archive_slugs - published_slugs)
                if missing:
                    add_issue(issues, "error", "archive", archive_path, f"missing published slugs: {', '.join(missing)}")
                if extra:
                    add_issue(issues, "warning", "archive", archive_path, f"contains slugs not found in published/: {', '.join(extra)}")

    legacy = load_json_with_issue(legacy_path, issues, "archive-legacy")
    if isinstance(legacy, dict):
        items = legacy.get("items")
        if not isinstance(items, list):
            add_issue(issues, "error", "archive-legacy", legacy_path, "items must be an array")
        else:
            legacy_slugs = {item.get("slug") for item in items if isinstance(item, dict)}
            if legacy.get("totalMixes") != len(items):
                add_issue(issues, "warning", "archive-legacy", legacy_path, f"totalMixes is {legacy.get('totalMixes')}, but items contains {len(items)} entries")
            published_slugs = set(published_by_slug)
            if legacy_slugs != published_slugs:
                missing = sorted(published_slugs - legacy_slugs)
                extra = sorted(legacy_slugs - published_slugs)
                if missing:
                    add_issue(issues, "error", "archive-legacy", legacy_path, f"missing published slugs: {', '.join(missing)}")
                if extra:
                    add_issue(issues, "warning", "archive-legacy", legacy_path, f"contains slugs not found in published/: {', '.join(extra)}")

    mixes_json = load_json_with_issue(mixes_json_path, issues, "mixes-json")
    if mixes_json is not None:
        if not isinstance(mixes_json, list):
            add_issue(issues, "error", "mixes-json", mixes_json_path, "mixes.json must be an array")
        else:
            json_slugs = set()
            for index, item in enumerate(mixes_json, start=1):
                if not isinstance(item, dict):
                    add_issue(issues, "error", "mixes-json", mixes_json_path, f"mixes.json item {index} must be an object")
                    continue
                slug = item.get("slug")
                if slug:
                    json_slugs.add(slug)
            published_slugs = set(published_by_slug)
            if json_slugs != published_slugs:
                missing = sorted(published_slugs - json_slugs)
                extra = sorted(json_slugs - published_slugs)
                if missing:
                    add_issue(issues, "error", "mixes-json", mixes_json_path, f"missing published slugs: {', '.join(missing)}")
                if extra:
                    add_issue(issues, "warning", "mixes-json", mixes_json_path, f"contains slugs not found in published/: {', '.join(extra)}")


def build_report(root: Path) -> dict[str, Any]:
    data_dir = root / "data"
    issues: list[dict[str, str]] = []

    site_path = data_dir / "site.json"
    site = load_json_with_issue(site_path, issues, "site")
    if isinstance(site, dict):
        try:
            validate_site_payload(site)
        except ValidationError as exc:
            add_issue(issues, "error", "site", site_path, str(exc))

    drafts_by_slug = validate_mix_collection(data_dir / "drafts", "editorial", issues, "drafts")
    published_by_slug = validate_mix_collection(data_dir / "published", "published", issues, "published")
    known_mix_slugs = set(drafts_by_slug) | set(published_by_slug)

    if isinstance(site, dict):
        featured_slug = site.get("featuredMixSlug") or site.get("featured_mix_slug")
        if featured_slug and featured_slug not in published_by_slug:
            add_issue(issues, "error", "site", site_path, f"featured mix slug '{featured_slug}' is not present in data/published/")

    notes_index_path = data_dir / "notes-index.json"
    notes_index = load_json_with_issue(notes_index_path, issues, "notes-index")
    notes_by_slug = validate_notes(data_dir / "notes", notes_index if isinstance(notes_index, dict) else None, known_mix_slugs, issues)
    validate_archive_indexes(root, published_by_slug, issues)

    return {
        "root": str(root),
        "counts": {
            "drafts": len(drafts_by_slug),
            "published": len(published_by_slug),
            "notes": len(notes_by_slug),
        },
        "issues": issues,
        "errors": sum(1 for issue in issues if issue["severity"] == "error"),
        "warnings": sum(1 for issue in issues if issue["severity"] == "warning"),
    }


def render_text_report(report: dict[str, Any]) -> str:
    lines = [
        "MMM content validation report",
        f"root: {report['root']}",
        f"checked: {report['counts']['drafts']} drafts, {report['counts']['published']} published mixes, {report['counts']['notes']} notes",
        f"errors: {report['errors']}",
        f"warnings: {report['warnings']}",
    ]
    if report["issues"]:
        lines.append("")
        for issue in report["issues"]:
            lines.append(
                f"{issue['severity'].upper()} [{issue['scope']}] {issue['path']}: {issue['message']}"
            )
    else:
        lines.append("")
        lines.append("No issues found.")
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    report = build_report(args.root.resolve())
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(render_text_report(report))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
