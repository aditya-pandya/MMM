from __future__ import annotations

import json
import re
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DRAFTS_DIR = DATA_DIR / "drafts"
PUBLISHED_DIR = DATA_DIR / "published"
IMPORTED_MIXES_DIR = DATA_DIR / "imported" / "mixes"
NOTES_DIR = DATA_DIR / "notes"
ARCHIVE_DIR = DATA_DIR / "archive"
MEDIA_DIR = DATA_DIR / "media"
MEDIA_WORKSPACES_DIR = MEDIA_DIR / "workspaces"
YOUTUBE_DIR = DATA_DIR / "youtube"
ARCHIVE_INDEX_PATH = ARCHIVE_DIR / "index.json"
LEGACY_ARCHIVE_INDEX_PATH = DATA_DIR / "archive-index.json"
MIXES_JSON_PATH = DATA_DIR / "mixes.json"
NOTES_INDEX_PATH = DATA_DIR / "notes-index.json"
SITE_PATH = DATA_DIR / "site.json"
TASTE_PROFILE_PATH = DATA_DIR / "taste-profile.json"
ARTWORK_REGISTRY_PATH = MEDIA_DIR / "artwork-registry.json"

EDITORIAL_REQUIRED_MIX_FIELDS = {
    "slug",
    "title",
    "date",
    "status",
    "summary",
    "notes",
    "tracks",
}
EDITORIAL_REQUIRED_TRACK_FIELDS = {"artist", "title", "why_it_fits"}
PUBLISHED_REQUIRED_MIX_FIELDS = {
    "schemaVersion",
    "id",
    "slug",
    "status",
    "siteSection",
    "source",
    "title",
    "publishedAt",
    "summary",
    "intro",
    "tags",
    "tracks",
    "stats",
}
PUBLISHED_REQUIRED_TRACK_FIELDS = {"position", "artist", "title", "displayText", "isFavorite"}
NOTE_REQUIRED_FIELDS = {
    "schemaVersion",
    "id",
    "slug",
    "status",
    "title",
    "publishedAt",
    "summary",
    "body",
    "tags",
}
VALID_STATUSES = {"draft", "approved", "published", "imported"}
NOTE_VALID_STATUSES = {"draft", "published"}
SLUG_PATTERN = r"[a-z0-9]+(?:-[a-z0-9]+)*"


class ValidationError(ValueError):
    pass


@dataclass
class ValidationResult:
    mix: dict[str, Any]
    warnings: list[str]
    flavor: str


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")



def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)



def dump_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")



def slugify(value: str) -> str:
    lowered = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return lowered or "mix"


def ensure_kebab_case_slug(slug: str, label: str = "slug") -> str:
    normalized = str(slug).strip()
    if not re.fullmatch(SLUG_PATTERN, normalized):
        raise ValidationError(f"{label} must be lowercase kebab-case")
    return normalized


def ensure_non_empty_string(value: Any, label: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValidationError(f"{label} must not be empty")
    return normalized


def ensure_iso8601_datetime(value: Any, label: str) -> str:
    normalized = ensure_non_empty_string(value, label)
    if "T" not in normalized:
        raise ValidationError(f"{label} must be ISO-8601 date-time")

    candidate = normalized.replace("Z", "+00:00")
    parsed: datetime
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ValidationError(f"{label} must be ISO-8601 date-time") from exc

    if parsed.tzinfo is None:
        raise ValidationError(f"{label} must be ISO-8601 date-time with timezone")
    return normalized


def normalize_mix_approval(approval: Any, *, required: bool) -> dict[str, Any] | None:
    if approval is None:
        if required:
            raise ValidationError("approved mixes must include approval metadata")
        return None

    if not isinstance(approval, dict):
        raise ValidationError("approval must be an object when present")

    normalized: dict[str, Any] = {}
    reviewed_at = approval.get("reviewedAt")
    approved_at = approval.get("approvedAt")

    if required:
        normalized["reviewedAt"] = ensure_iso8601_datetime(reviewed_at, "approval.reviewedAt")
        normalized["approvedAt"] = ensure_iso8601_datetime(approved_at, "approval.approvedAt")
    else:
        if reviewed_at is not None:
            normalized["reviewedAt"] = ensure_iso8601_datetime(reviewed_at, "approval.reviewedAt")
        if approved_at is not None:
            normalized["approvedAt"] = ensure_iso8601_datetime(approved_at, "approval.approvedAt")

    for field in ("reviewedBy", "approvedBy", "notes"):
        value = approval.get(field)
        if value is not None:
            normalized[field] = ensure_non_empty_string(value, f"approval.{field}")

    return normalized


def validate_note_payload(note: dict[str, Any]) -> dict[str, Any]:
    missing = NOTE_REQUIRED_FIELDS - set(note)
    if missing:
        raise ValidationError(f"note missing field: {', '.join(sorted(missing))}")

    status = str(note.get("status", "")).strip()
    if status not in NOTE_VALID_STATUSES:
        raise ValidationError("note status must be draft or published")

    slug = ensure_kebab_case_slug(note.get("slug"), "note slug")
    note_id = ensure_non_empty_string(note.get("id"), "note id")
    title = ensure_non_empty_string(note.get("title"), "note title")
    published_at = ensure_iso8601_datetime(note.get("publishedAt"), "note publishedAt")
    summary = ensure_non_empty_string(note.get("summary"), "note summary")

    body = note.get("body")
    if not isinstance(body, list) or not body:
        raise ValidationError("note body must be a non-empty array")
    normalized_body: list[str] = []
    for index, paragraph in enumerate(body, start=1):
        normalized_paragraph = ensure_non_empty_string(paragraph, f"note body paragraph {index}")
        normalized_body.append(normalized_paragraph)

    tags = note.get("tags")
    if not isinstance(tags, list):
        raise ValidationError("note tags must be an array")

    related = note.get("relatedMixSlugs", [])
    if related is not None and not isinstance(related, list):
        raise ValidationError("note relatedMixSlugs must be an array when present")

    normalized_related: list[str] = []
    seen_related: set[str] = set()
    for index, related_slug in enumerate(related or [], start=1):
        normalized_related_slug = ensure_kebab_case_slug(related_slug, f"note relatedMixSlugs[{index}]")
        if normalized_related_slug in seen_related:
            raise ValidationError("note relatedMixSlugs must not contain duplicates")
        seen_related.add(normalized_related_slug)
        normalized_related.append(normalized_related_slug)

    related_notes = note.get("relatedNoteSlugs", [])
    if related_notes is not None and not isinstance(related_notes, list):
        raise ValidationError("note relatedNoteSlugs must be an array when present")

    normalized_related_notes: list[str] = []
    seen_related_notes: set[str] = set()
    for index, related_note_slug in enumerate(related_notes or [], start=1):
        normalized_related_note_slug = ensure_kebab_case_slug(
            related_note_slug,
            f"note relatedNoteSlugs[{index}]",
        )
        if normalized_related_note_slug == slug:
            raise ValidationError("note relatedNoteSlugs must not include the note slug itself")
        if normalized_related_note_slug in seen_related_notes:
            raise ValidationError("note relatedNoteSlugs must not contain duplicates")
        seen_related_notes.add(normalized_related_note_slug)
        normalized_related_notes.append(normalized_related_note_slug)

    series = note.get("series")
    normalized_series: dict[str, Any] | None = None
    if series is not None:
        if not isinstance(series, dict):
            raise ValidationError("note series must be an object when present")

        series_slug = ensure_kebab_case_slug(series.get("slug"), "note series.slug")
        series_title = ensure_non_empty_string(series.get("title"), "note series.title")
        series_description = series.get("description")
        if series_description is not None:
            series_description = ensure_non_empty_string(series_description, "note series.description")

        series_order = series.get("order")
        if series_order is not None:
            if not isinstance(series_order, int) or isinstance(series_order, bool) or series_order < 1:
                raise ValidationError("note series.order must be a positive integer when present")

        normalized_series = {
            "slug": series_slug,
            "title": series_title,
        }
        if series_description is not None:
            normalized_series["description"] = series_description
        if series_order is not None:
            normalized_series["order"] = series_order

    normalized = deepcopy(note)
    normalized["status"] = status
    normalized["slug"] = slug
    normalized["id"] = note_id
    normalized["title"] = title
    normalized["publishedAt"] = published_at
    normalized["summary"] = summary
    normalized["body"] = normalized_body
    normalized["relatedMixSlugs"] = normalized_related
    normalized["relatedNoteSlugs"] = normalized_related_notes
    normalized["series"] = normalized_series
    return normalized



def _validate_editorial_mix(mix: dict[str, Any]) -> ValidationResult:
    missing = EDITORIAL_REQUIRED_MIX_FIELDS - set(mix)
    if missing:
        raise ValidationError(f"Missing required fields: {', '.join(sorted(missing))}")

    slug = ensure_kebab_case_slug(mix["slug"])

    status = str(mix["status"]).strip()
    if status not in VALID_STATUSES:
        raise ValidationError(f"status must be one of: {', '.join(sorted(VALID_STATUSES))}")

    try:
        date.fromisoformat(str(mix["date"]))
    except ValueError as exc:
        raise ValidationError("date must be ISO-8601 YYYY-MM-DD") from exc

    title = ensure_non_empty_string(mix["title"], "title")
    summary = ensure_non_empty_string(mix["summary"], "summary")
    notes = ensure_non_empty_string(mix["notes"], "notes")
    approval = normalize_mix_approval(mix.get("approval"), required=status == "approved")

    tracks = mix["tracks"]
    if not isinstance(tracks, list) or not tracks:
        raise ValidationError("tracks must be a non-empty array")

    warnings: list[str] = []
    if len(tracks) < 3:
        warnings.append("mix has fewer than 3 tracks")

    cleaned_tracks = []
    for index, track in enumerate(tracks, start=1):
        if not isinstance(track, dict):
            raise ValidationError(f"track {index} must be an object")
        track_missing = EDITORIAL_REQUIRED_TRACK_FIELDS - set(track)
        if track_missing:
            raise ValidationError(
                f"track {index} missing fields: {', '.join(sorted(track_missing))}"
            )
        artist = ensure_non_empty_string(track["artist"], f"track {index} artist")
        title_ = ensure_non_empty_string(track["title"], f"track {index} title")
        why = ensure_non_empty_string(track["why_it_fits"], f"track {index} why_it_fits")
        cleaned_track = deepcopy(track)
        cleaned_track["artist"] = artist
        cleaned_track["title"] = title_
        cleaned_track["why_it_fits"] = why
        cleaned_tracks.append(cleaned_track)

    normalized = deepcopy(mix)
    normalized["slug"] = slug
    normalized["title"] = title
    normalized["summary"] = summary
    normalized["notes"] = notes
    normalized["status"] = status
    normalized["tracks"] = cleaned_tracks
    normalized["approval"] = approval
    normalized.setdefault("featured", False)
    return ValidationResult(mix=normalized, warnings=warnings, flavor="editorial")



def _validate_published_mix(mix: dict[str, Any]) -> ValidationResult:
    missing = PUBLISHED_REQUIRED_MIX_FIELDS - set(mix)
    if missing:
        raise ValidationError(f"Missing published fields: {', '.join(sorted(missing))}")

    slug = str(mix["slug"]).strip()
    status = str(mix["status"]).strip()
    ensure_kebab_case_slug(slug)
    if status not in VALID_STATUSES:
        raise ValidationError(f"status must be one of: {', '.join(sorted(VALID_STATUSES))}")
    ensure_iso8601_datetime(mix["publishedAt"], "publishedAt")

    cover = mix.get("cover")
    if cover is not None:
        if not isinstance(cover, dict):
            raise ValidationError("cover must be an object when present")
        for key in ("imageUrl", "alt", "credit", "canonicalAssetPath"):
            if key in cover and cover[key] is not None and not str(cover[key]).strip():
                raise ValidationError(f"cover.{key} must not be empty when present")

    tracks = mix["tracks"]
    if not isinstance(tracks, list) or not tracks:
        raise ValidationError("tracks must be a non-empty array")
    for index, track in enumerate(tracks, start=1):
        if not isinstance(track, dict):
            raise ValidationError(f"track {index} must be an object")
        track_missing = PUBLISHED_REQUIRED_TRACK_FIELDS - set(track)
        if track_missing:
            raise ValidationError(
                f"track {index} missing published fields: {', '.join(sorted(track_missing))}"
            )
    return ValidationResult(mix=deepcopy(mix), warnings=[], flavor="published")



def validate_mix(mix: dict[str, Any]) -> ValidationResult:
    if "publishedAt" in mix or "schemaVersion" in mix or "siteSection" in mix:
        return _validate_published_mix(mix)
    return _validate_editorial_mix(mix)


def mix_sort_value(mix: dict[str, Any]) -> tuple[str, str]:
    return str(mix.get("publishedAt") or mix.get("date") or "").strip(), str(mix.get("slug") or mix.get("id") or "").strip()


def load_mix_payloads(directory: Path) -> list[dict[str, Any]]:
    if not directory.exists():
        return []

    payloads: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        payload = load_json(path)
        if isinstance(payload, dict):
            payloads.append(payload)
    return payloads


def load_canonical_archive_mix_records(
    published_dir: Path | None = None,
    imported_dir: Path | None = None,
) -> list[dict[str, Any]]:
    published_dir = published_dir or PUBLISHED_DIR
    imported_dir = imported_dir or IMPORTED_MIXES_DIR

    records_by_slug: dict[str, dict[str, Any]] = {}
    for source_name, directory in (("imported", imported_dir), ("published", published_dir)):
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.json")):
            result = validate_mix(load_json(path))
            slug = result.mix["slug"]
            try:
                relative_path = path.relative_to(ROOT).as_posix()
            except ValueError:
                relative_path = path.as_posix()
            candidate = {
                "slug": slug,
                "mix": result.mix,
                "path": path,
                "relativePath": relative_path,
                "flavor": result.flavor,
                "sourceName": source_name,
                "warnings": list(result.warnings),
            }
            existing = records_by_slug.get(slug)
            if existing is None or source_name == "published":
                records_by_slug[slug] = candidate

    return sorted(
        records_by_slug.values(),
        key=lambda item: mix_sort_value(item["mix"]),
        reverse=True,
    )


def load_canonical_archive_mixes(
    published_dir: Path | None = None,
    imported_dir: Path | None = None,
) -> list[dict[str, Any]]:
    return [record["mix"] for record in load_canonical_archive_mix_records(published_dir=published_dir, imported_dir=imported_dir)]



def editorial_to_published_mix(mix: dict[str, Any]) -> dict[str, Any]:
    result = _validate_editorial_mix(mix)
    editorial = result.mix
    published_at = editorial.get("published_at") or f"{editorial['date']}T12:00:00Z"
    favorite_tracks = [
        f"{track['artist']} - {track['title']}"
        for track in editorial["tracks"]
        if track.get("favorite") or track.get("is_favorite")
    ]
    top_artists: list[str] = []
    for track in editorial["tracks"]:
        artist = track["artist"]
        if artist not in top_artists:
            top_artists.append(artist)

    return {
        "$schema": "schemas/mix.schema.json",
        "schemaVersion": "1.0",
        "id": editorial.get("id", editorial["slug"]),
        "slug": editorial["slug"],
        "status": "published",
        "siteSection": "mixes",
        "source": editorial.get(
            "source",
            {
                "platform": "mmm",
                "feedType": "manual",
                "importedAt": now_iso(),
                "sourceUrl": editorial.get("source_url", "https://example.invalid/mmm/manual"),
                "guid": editorial.get("guid", editorial["slug"]),
            },
        ),
        "title": editorial["title"],
        "displayTitle": editorial.get("displayTitle") or editorial["title"],
        "mixNumber": editorial.get("mixNumber"),
        "publishedAt": published_at,
        "summary": editorial["summary"],
        "intro": editorial.get("intro") or [editorial["notes"]],
        "tags": editorial.get("tags", []),
        "cover": editorial.get("cover", {"imageUrl": None, "alt": None, "credit": None}),
        "download": editorial.get("download", {"label": "", "url": None}),
        "tracks": [
            {
                "position": index,
                "artist": track["artist"],
                "title": track["title"],
                "displayText": f"{track['artist']} - {track['title']}",
                "isFavorite": bool(track.get("favorite") or track.get("is_favorite")),
            }
            for index, track in enumerate(editorial["tracks"], start=1)
        ],
        "stats": {
            "trackCount": len(editorial["tracks"]),
            "favoriteCount": len(favorite_tracks),
            "favoriteTracks": favorite_tracks,
            "topArtists": top_artists[:5],
        },
        "legacy": editorial.get("legacy", {"originalTitle": editorial["title"], "descriptionHtml": editorial["notes"]}),
        "published_at": now_iso(),
        "date": editorial["date"],
        "notes": editorial["notes"],
        "excerpt": editorial["summary"],
        "tracklist": [
            {
                "position": index,
                "artist": track["artist"],
                "title": track["title"],
                "why_it_fits": track["why_it_fits"],
            }
            for index, track in enumerate(editorial["tracks"], start=1)
        ],
    }



def build_archive_entry(mix: dict[str, Any]) -> dict[str, Any]:
    if "publishedAt" in mix:
        return {
            "id": mix.get("id", mix["slug"]),
            "slug": mix["slug"],
            "title": mix["title"],
            "displayTitle": mix.get("displayTitle"),
            "publishedAt": mix["publishedAt"],
            "summary": mix["summary"],
            "trackCount": len(mix.get("tracks", [])),
            "favoriteCount": mix.get("stats", {}).get("favoriteCount", 0),
            "path": f"data/published/{mix['slug']}.json",
            "tags": mix.get("tags", []),
        }

    return {
        "id": mix.get("id", mix["slug"]),
        "slug": mix["slug"],
        "title": mix["title"],
        "displayTitle": mix.get("displayTitle", mix["title"]),
        "publishedAt": f"{mix['date']}T12:00:00Z",
        "summary": mix["summary"],
        "trackCount": len(mix["tracks"]),
        "favoriteCount": 0,
        "path": f"data/published/{mix['slug']}.json",
        "tags": mix.get("tags", []),
    }



def update_archive_index(
    published_dir: Path | None = None,
    index_path: Path | None = None,
    legacy_index_path: Path | None = None,
    mixes_json_path: Path | None = None,
) -> dict[str, Any]:
    published_dir = published_dir or PUBLISHED_DIR
    index_path = index_path or ARCHIVE_INDEX_PATH
    legacy_index_path = legacy_index_path or LEGACY_ARCHIVE_INDEX_PATH
    mixes_json_path = mixes_json_path or MIXES_JSON_PATH

    archive_entries: list[dict[str, Any]] = []
    mixes_for_build: list[dict[str, Any]] = []

    for path in sorted(published_dir.glob("*.json")):
        mix = load_json(path)
        result = validate_mix(mix)
        if result.mix.get("status") != "published":
            continue
        archive_entries.append(build_archive_entry(result.mix))
        mixes_for_build.append(result.mix)

    archive_entries.sort(key=lambda item: (item["publishedAt"], item["slug"]), reverse=True)
    mixes_for_build.sort(
        key=lambda item: (item.get("publishedAt") or item.get("date") or "", item["slug"]), reverse=True
    )

    lightweight_archive = {
        "updated_at": now_iso(),
        "mixes": [
            {
                "slug": item["slug"],
                "title": item["title"],
                "date": item["publishedAt"][:10],
                "summary": item["summary"],
                "track_count": item["trackCount"],
            }
            for item in archive_entries
        ],
    }
    legacy_archive = {
        "$schema": "../schemas/archive-index.schema.json",
        "schemaVersion": "1.0",
        "generatedAt": now_iso(),
        "totalMixes": len(archive_entries),
        "items": archive_entries,
    }

    dump_json(index_path, lightweight_archive)
    dump_json(legacy_index_path, legacy_archive)
    dump_json(mixes_json_path, mixes_for_build)
    return legacy_archive


def load_published_mixes(published_dir: Path | None = None) -> list[dict[str, Any]]:
    published_dir = published_dir or PUBLISHED_DIR
    mixes: list[dict[str, Any]] = []
    for path in sorted(published_dir.glob("*.json")):
        result = validate_mix(load_json(path))
        if result.flavor != "published":
            raise ValidationError(f"Expected published mix content in {path}")
        if result.mix.get("status") != "published":
            continue
        mixes.append(result.mix)
    mixes.sort(key=lambda item: (item.get("publishedAt") or item.get("date") or "", item["slug"]), reverse=True)
    return mixes


def build_note_index_entry(note: dict[str, Any]) -> dict[str, Any]:
    validated = validate_note_payload(note)
    entry = {
        "id": validated["id"],
        "slug": validated["slug"],
        "title": validated["title"],
        "publishedAt": validated["publishedAt"],
        "summary": validated["summary"],
        "path": f"data/notes/{validated['slug']}.json",
        "tags": validated["tags"],
        "relatedMixSlugs": validated["relatedMixSlugs"],
    }
    if validated["relatedNoteSlugs"]:
        entry["relatedNoteSlugs"] = validated["relatedNoteSlugs"]
    if validated["series"]:
        entry["series"] = validated["series"]
    return entry


def refresh_notes_index(
    notes_dir: Path | None = None,
    notes_index_path: Path | None = None,
) -> dict[str, Any]:
    notes_dir = notes_dir or NOTES_DIR
    notes_index_path = notes_index_path or NOTES_INDEX_PATH

    items = []
    for path in sorted(notes_dir.glob("*.json")):
        note = validate_note_payload(load_json(path))
        items.append(build_note_index_entry(note))

    items.sort(key=lambda item: (item["publishedAt"], item["slug"]), reverse=True)
    payload = {
        "$schema": "../schemas/notes-index.schema.json",
        "schemaVersion": "1.0",
        "generatedAt": now_iso(),
        "totalNotes": len(items),
        "items": items,
    }
    dump_json(notes_index_path, payload)
    return payload


def load_notes(notes_dir: Path | None = None) -> list[dict[str, Any]]:
    notes_dir = notes_dir or NOTES_DIR
    notes = []
    for path in sorted(notes_dir.glob("*.json")):
        notes.append(validate_note_payload(load_json(path)))
    notes.sort(key=lambda item: (item["publishedAt"], item["slug"]), reverse=True)
    return notes


def published_mixes_without_note_coverage(
    published_dir: Path | None = None,
    notes_dir: Path | None = None,
) -> list[dict[str, Any]]:
    published_mixes = load_published_mixes(published_dir=published_dir)
    notes = load_notes(notes_dir=notes_dir)
    covered_mix_slugs = {
        related_slug
        for note in notes
        for related_slug in note.get("relatedMixSlugs", [])
    }
    return [mix for mix in published_mixes if mix["slug"] not in covered_mix_slugs]


def find_published_mix(slug_or_path: str, published_dir: Path | None = None) -> dict[str, Any]:
    published_dir = published_dir or PUBLISHED_DIR
    candidate = Path(slug_or_path)
    if candidate.exists():
        result = validate_mix(load_json(candidate))
        if result.flavor != "published":
            raise ValidationError(f"Expected a published mix JSON, got {result.flavor}")
        return result.mix

    target_path = published_dir / f"{slug_or_path}.json"
    if not target_path.exists():
        raise FileNotFoundError(f"Published mix not found: {slug_or_path}")
    result = validate_mix(load_json(target_path))
    if result.flavor != "published":
        raise ValidationError(f"Expected a published mix JSON, got {result.flavor}")
    return result.mix


def latest_item(items: list[dict[str, Any]], *date_fields: str) -> dict[str, Any] | None:
    if not items:
        return None

    def sort_key(item: dict[str, Any]) -> tuple[str, str]:
        for field in date_fields:
            value = str(item.get(field) or "").strip()
            if value:
                return value, str(item.get("slug") or item.get("id") or "")
        return "", str(item.get("slug") or item.get("id") or "")

    return max(items, key=sort_key)
