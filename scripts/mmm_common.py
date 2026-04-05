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
NOTES_DIR = DATA_DIR / "notes"
ARCHIVE_DIR = DATA_DIR / "archive"
ARCHIVE_INDEX_PATH = ARCHIVE_DIR / "index.json"
LEGACY_ARCHIVE_INDEX_PATH = DATA_DIR / "archive-index.json"
MIXES_JSON_PATH = DATA_DIR / "mixes.json"
NOTES_INDEX_PATH = DATA_DIR / "notes-index.json"
SITE_PATH = DATA_DIR / "site.json"
TASTE_PROFILE_PATH = DATA_DIR / "taste-profile.json"

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
