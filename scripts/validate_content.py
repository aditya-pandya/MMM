from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from listening_confidence import load_provider_catalog, normalize_published_listening
from mmm_common import (
    ValidationError,
    ensure_iso8601_datetime,
    ensure_kebab_case_slug,
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

    drafts_by_slug = validate_mix_collection(data_dir / "drafts", "editorial", issues, "drafts", listening_catalog)
    published_by_slug = validate_mix_collection(data_dir / "published", "published", issues, "published", listening_catalog)
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
