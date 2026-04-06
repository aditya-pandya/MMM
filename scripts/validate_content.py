from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from listening_confidence import load_provider_catalog, normalize_published_listening
from mmm_common import (
    ARTWORK_REGISTRY_PATH,
    IMPORTED_MIXES_DIR,
    ValidationError,
    YOUTUBE_DIR,
    ensure_iso8601_datetime,
    ensure_kebab_case_slug,
    load_canonical_archive_mix_records,
    load_json,
    validate_mix,
    validate_note_payload,
)

ROOT = Path(__file__).resolve().parents[1]


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


def audit_published_listening(mix: dict[str, Any], catalog: dict[str, Any]) -> tuple[list[str], list[str]]:
    _, warnings = normalize_published_listening(mix, catalog)
    return [], warnings


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


def validate_about_section(section: dict[str, Any], label: str) -> None:
    require_non_empty_string(section, "label", f"{label} label")
    require_non_empty_string(section, "title", f"{label} title")

    summary = section.get("summary")
    if summary is not None:
        require_non_empty_string(section, "summary", f"{label} summary")

    body = section.get("body", [])
    if body is not None:
        if not isinstance(body, list):
            raise ValidationError(f"{label} body must be an array when present")
        for index, paragraph in enumerate(body, start=1):
            if not str(paragraph).strip():
                raise ValidationError(f"{label} body paragraph {index} must not be empty")

    items = section.get("items", [])
    if items is not None:
        if not isinstance(items, list):
            raise ValidationError(f"{label} items must be an array when present")
        for index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                raise ValidationError(f"{label} item {index} must be an object")
            require_non_empty_string(item, "label", f"{label} item {index} label")
            require_non_empty_string(item, "text", f"{label} item {index} text")

    links = section.get("links", [])
    if links is not None:
        if not isinstance(links, list):
            raise ValidationError(f"{label} links must be an array when present")
        for index, item in enumerate(links, start=1):
            if not isinstance(item, dict):
                raise ValidationError(f"{label} link {index} must be an object")
            require_non_empty_string(item, "label", f"{label} link {index} label")
            require_non_empty_string(item, "href", f"{label} link {index} href")
            if item.get("description") is not None:
                require_non_empty_string(item, "description", f"{label} link {index} description")


def validate_about_payload(about: dict[str, Any]) -> None:
    require_non_empty_string(about, "schemaVersion", "about schemaVersion")
    require_non_empty_string(about, "title", "about title")
    require_non_empty_string(about, "headline", "about headline")

    intro = about.get("intro")
    if not isinstance(intro, list) or not intro:
        raise ValidationError("about intro must be a non-empty array")
    for index, paragraph in enumerate(intro, start=1):
        if not str(paragraph).strip():
            raise ValidationError(f"about intro paragraph {index} must not be empty")

    editorial_note = about.get("editorialNote")
    if editorial_note is not None:
        if not isinstance(editorial_note, dict):
            raise ValidationError("about editorialNote must be an object when present")
        validate_about_section(editorial_note, "about editorialNote")

    sections = about.get("sections")
    if not isinstance(sections, list) or not sections:
        raise ValidationError("about sections must be a non-empty array")
    for index, section in enumerate(sections, start=1):
        if not isinstance(section, dict):
            raise ValidationError(f"about section {index} must be an object")
        validate_about_section(section, f"about section {index}")

    closing = about.get("closing")
    if closing is not None:
        if not isinstance(closing, dict):
            raise ValidationError("about closing must be an object when present")
        validate_about_section(closing, "about closing")


def load_json_with_issue(path: Path, issues: list[dict[str, str]], scope: str) -> Any | None:
    try:
        return load_json(path)
    except FileNotFoundError:
        add_issue(issues, "error", scope, path, "missing file")
    except json.JSONDecodeError as exc:
        add_issue(issues, "error", scope, path, f"invalid JSON: {exc}")
    return None


def validate_mix_collection(
    root: Path,
    directory: Path,
    expected_flavor: str,
    issues: list[dict[str, str]],
    scope: str,
    listening_catalog: dict[str, Any],
) -> dict[str, dict[str, Any]]:
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
            cover = result.mix.get("cover")
            if isinstance(cover, dict):
                canonical_asset = str(cover.get("canonicalAssetPath") or "").strip()
                if canonical_asset:
                    candidate = (root / canonical_asset).resolve()
                    try:
                        candidate.relative_to((root / "data" / "media").resolve())
                    except ValueError:
                        add_issue(issues, "error", scope, path, "cover.canonicalAssetPath must stay under data/media/")
                    else:
                        if not candidate.exists():
                            add_issue(issues, "warning", scope, path, f"cover.canonicalAssetPath is missing on disk: {canonical_asset}")
            listening_errors, listening_warnings = audit_published_listening(result.mix, listening_catalog)
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

    for slug, note_record in notes_by_slug.items():
        for related_note_slug in note_record["note"].get("relatedNoteSlugs", []):
            if related_note_slug not in notes_by_slug:
                add_issue(
                    issues,
                    "warning",
                    "notes",
                    Path(note_record["path"]),
                    f"related note slug '{related_note_slug}' does not exist under data/notes/",
                )

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
        for field in ("title", "summary", "publishedAt", "relatedMixSlugs", "relatedNoteSlugs", "series"):
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


def validate_artwork_registry(root: Path, issues: list[dict[str, str]]) -> int:
    path = root / ARTWORK_REGISTRY_PATH.relative_to(ROOT)
    if not path.exists():
        return 0

    registry = load_json_with_issue(path, issues, "artwork")
    if not isinstance(registry, dict):
        return 0

    try:
        require_non_empty_string(registry, "schemaVersion", "artwork schemaVersion")
        ensure_iso8601_datetime(registry.get("updatedAt"), "artwork updatedAt")
    except ValidationError as exc:
        add_issue(issues, "error", "artwork", path, str(exc))
        return 0

    items = registry.get("items")
    if not isinstance(items, list):
        add_issue(issues, "error", "artwork", path, "items must be an array")
        return 0

    seen_ids: set[str] = set()
    media_root = root / "data" / "media"

    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            add_issue(issues, "error", "artwork", path, f"item {index} must be an object")
            continue

        try:
            item_id = require_non_empty_string(item, "id", f"artwork item {index} id")
            mix_slug = ensure_kebab_case_slug(item.get("mixSlug"), f"artwork item {index} mixSlug")
            require_non_empty_string(item, "role", f"artwork item {index} role")
            ensure_iso8601_datetime(item.get("registeredAt"), f"artwork item {index} registeredAt")
            asset_path_value = require_non_empty_string(item, "assetPath", f"artwork item {index} assetPath")
            workspace_path_value = require_non_empty_string(item, "workspacePath", f"artwork item {index} workspacePath")
            provenance = item.get("provenance")
            if not isinstance(provenance, dict):
                raise ValidationError(f"artwork item {index} provenance must be an object")
            require_non_empty_string(provenance, "sourceType", f"artwork item {index} provenance.sourceType")
            require_non_empty_string(provenance, "sourceLabel", f"artwork item {index} provenance.sourceLabel")
            require_non_empty_string(provenance, "sourceUrl", f"artwork item {index} provenance.sourceUrl")
            require_non_empty_string(provenance, "discoveredFrom", f"artwork item {index} provenance.discoveredFrom")
            if provenance.get("notes") is None:
                raise ValidationError(f"artwork item {index} provenance.notes must be present")
            file_meta = item.get("file")
            if not isinstance(file_meta, dict):
                raise ValidationError(f"artwork item {index} file must be an object")
            if not isinstance(file_meta.get("byteSize"), int) or isinstance(file_meta.get("byteSize"), bool) or int(file_meta.get("byteSize")) < 0:
                raise ValidationError(f"artwork item {index} file.byteSize must be a non-negative integer")
            require_non_empty_string(file_meta, "mediaType", f"artwork item {index} file.mediaType")
            checksum = item.get("checksum")
            if not isinstance(checksum, dict):
                raise ValidationError(f"artwork item {index} checksum must be an object")
            if checksum.get("algorithm") != "sha256":
                raise ValidationError(f"artwork item {index} checksum.algorithm must be sha256")
            require_non_empty_string(checksum, "value", f"artwork item {index} checksum.value")
            if item_id in seen_ids:
                raise ValidationError(f"duplicate artwork id '{item_id}'")
            seen_ids.add(item_id)
        except ValidationError as exc:
            add_issue(issues, "error", "artwork", path, str(exc))
            continue

        for label, relative_value, must_be_file in (
            ("assetPath", asset_path_value, True),
            ("workspacePath", workspace_path_value, False),
        ):
            candidate = (root / relative_value).resolve()
            try:
                candidate.relative_to(media_root.resolve())
            except ValueError:
                add_issue(issues, "error", "artwork", path, f"{mix_slug} {label} must stay under data/media/")
                continue
            if must_be_file and not candidate.exists():
                add_issue(issues, "warning", "artwork", path, f"{mix_slug} assetPath is missing on disk: {relative_value}")
            if not must_be_file and not candidate.exists():
                add_issue(issues, "warning", "artwork", path, f"{mix_slug} workspacePath is missing on disk: {relative_value}")

    return len(items)


def validate_youtube_match_data(root: Path, archive_by_slug: dict[str, dict[str, Any]], issues: list[dict[str, str]]) -> int:
    youtube_dir = root / YOUTUBE_DIR.relative_to(ROOT)
    if not youtube_dir.exists():
        for slug, record in archive_by_slug.items():
            source_platform = str(record["mix"].get("source", {}).get("platform") or "").strip().lower()
            if source_platform == "tumblr":
                add_issue(issues, "warning", "youtube", Path(record["path"]), "missing YouTube match state under data/youtube/")
        return 0

    count = 0
    seen_slugs: set[str] = set()
    for path in sorted(youtube_dir.glob("*.json")):
        payload = load_json_with_issue(path, issues, "youtube")
        if not isinstance(payload, dict):
            continue
        count += 1
        try:
            require_non_empty_string(payload, "schemaVersion", f"{path.name} schemaVersion")
            mix_slug = ensure_kebab_case_slug(payload.get("mixSlug"), f"{path.name} mixSlug")
            ensure_iso8601_datetime(payload.get("updatedAt"), f"{path.name} updatedAt")
            if mix_slug in seen_slugs:
                raise ValidationError(f"duplicate YouTube match state for '{mix_slug}'")
            seen_slugs.add(mix_slug)
            if mix_slug not in archive_by_slug:
                raise ValidationError(f"YouTube match state points to missing canonical archive mix '{mix_slug}'")
            tracks = payload.get("tracks")
            if not isinstance(tracks, list):
                raise ValidationError("tracks must be an array")
            summary = payload.get("summary")
            if not isinstance(summary, dict):
                raise ValidationError("summary must be an object")
        except ValidationError as exc:
            add_issue(issues, "error", "youtube", path, str(exc))
            continue

        selected_video_ids: list[str] = []
        for index, track in enumerate(tracks, start=1):
            if not isinstance(track, dict):
                add_issue(issues, "error", "youtube", path, f"track {index} must be an object")
                continue
            try:
                position = track.get("position")
                if not isinstance(position, int) or isinstance(position, bool) or position < 1:
                    raise ValidationError(f"track {index} position must be a positive integer")
                require_non_empty_string(track, "displayText", f"track {index} displayText")
                require_non_empty_string(track, "query", f"track {index} query")
                resolution = track.get("resolution")
                if not isinstance(resolution, dict):
                    raise ValidationError(f"track {index} resolution must be an object")
                status = require_non_empty_string(resolution, "status", f"track {index} resolution.status")
                if status not in {"auto-resolved", "manual-selected", "pending-review", "no-candidate"}:
                    raise ValidationError(f"track {index} resolution.status is invalid")
                selected_video_id = str(resolution.get("selectedVideoId") or "").strip()
                if status in {"auto-resolved", "manual-selected"} and not selected_video_id:
                    raise ValidationError(f"track {index} resolved status requires selectedVideoId")
                if selected_video_id:
                    selected_video_ids.append(selected_video_id)
                candidates = track.get("candidates")
                if not isinstance(candidates, list):
                    raise ValidationError(f"track {index} candidates must be an array")
            except ValidationError as exc:
                add_issue(issues, "error", "youtube", path, str(exc))

        generated_embed = summary.get("generatedEmbed")
        unresolved_tracks = summary.get("unresolvedTracks")
        if generated_embed is not None:
            if unresolved_tracks:
                add_issue(issues, "error", "youtube", path, "generatedEmbed must be absent while unresolved tracks remain")
            elif not isinstance(generated_embed, dict):
                add_issue(issues, "error", "youtube", path, "generatedEmbed must be an object when present")
            else:
                embed_ids = generated_embed.get("videoIds")
                if not isinstance(embed_ids, list) or not embed_ids or any(not str(value).strip() for value in embed_ids):
                    add_issue(issues, "error", "youtube", path, "generatedEmbed.videoIds must be a non-empty array")
                elif [str(value).strip() for value in embed_ids] != selected_video_ids:
                    add_issue(issues, "error", "youtube", path, "generatedEmbed.videoIds must match resolved track selections in order")
                embed_url = str(generated_embed.get("embedUrl") or "").strip()
                if not embed_url:
                    add_issue(issues, "error", "youtube", path, "generatedEmbed.embedUrl must not be empty")

        if unresolved_tracks:
            add_issue(issues, "warning", "youtube", path, f"{payload['mixSlug']} still has {unresolved_tracks} unresolved YouTube track match(es)")

    for slug, record in archive_by_slug.items():
        source_platform = str(record["mix"].get("source", {}).get("platform") or "").strip().lower()
        if source_platform == "tumblr" and slug not in seen_slugs:
            add_issue(issues, "warning", "youtube", Path(record["path"]), "missing YouTube match state under data/youtube/")

    return count


def build_report(root: Path) -> dict[str, Any]:
    data_dir = root / "data"
    issues: list[dict[str, str]] = []
    listening_catalog = load_provider_catalog(root)

    site_path = data_dir / "site.json"
    site = load_json_with_issue(site_path, issues, "site")
    if isinstance(site, dict):
        try:
            validate_site_payload(site)
        except ValidationError as exc:
            add_issue(issues, "error", "site", site_path, str(exc))

    about_path = data_dir / "about.json"
    about = load_json_with_issue(about_path, issues, "about")
    if isinstance(about, dict):
        try:
            validate_about_payload(about)
        except ValidationError as exc:
            add_issue(issues, "error", "about", about_path, str(exc))

    drafts_by_slug = validate_mix_collection(root, data_dir / "drafts", "editorial", issues, "drafts", listening_catalog)
    published_by_slug = validate_mix_collection(root, data_dir / "published", "published", issues, "published", listening_catalog)
    canonical_archive_records = load_canonical_archive_mix_records(
        published_dir=data_dir / "published",
        imported_dir=data_dir / "imported" / "mixes",
    )
    archive_by_slug = {
        record["slug"]: {"mix": record["mix"], "path": record["path"]}
        for record in canonical_archive_records
    }
    known_mix_slugs = set(drafts_by_slug) | set(published_by_slug)

    if isinstance(site, dict):
        featured_slug = site.get("featuredMixSlug") or site.get("featured_mix_slug")
        if featured_slug and featured_slug not in published_by_slug:
            add_issue(issues, "error", "site", site_path, f"featured mix slug '{featured_slug}' is not present in data/published/")

    notes_index_path = data_dir / "notes-index.json"
    notes_index = load_json_with_issue(notes_index_path, issues, "notes-index")
    notes_by_slug = validate_notes(data_dir / "notes", notes_index if isinstance(notes_index, dict) else None, known_mix_slugs, issues)
    validate_archive_indexes(root, published_by_slug, issues)
    artwork_count = validate_artwork_registry(root, issues)
    youtube_count = validate_youtube_match_data(root, archive_by_slug, issues)

    return {
        "root": str(root),
        "counts": {
            "drafts": len(drafts_by_slug),
            "published": len(published_by_slug),
            "notes": len(notes_by_slug),
            "artwork": artwork_count,
            "youtube": youtube_count,
        },
        "issues": issues,
        "errors": sum(1 for issue in issues if issue["severity"] == "error"),
        "warnings": sum(1 for issue in issues if issue["severity"] == "warning"),
    }


def render_text_report(report: dict[str, Any]) -> str:
    lines = [
        "MMM content validation report",
        f"root: {report['root']}",
        f"checked: {report['counts']['drafts']} drafts, {report['counts']['published']} published mixes, {report['counts']['notes']} notes, {report['counts'].get('artwork', 0)} artwork records, {report['counts'].get('youtube', 0)} YouTube match files",
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
