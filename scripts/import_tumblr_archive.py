#!/usr/bin/env python3
"""Import Tumblr archive HTML exports into structured MMM mix JSON files."""

from __future__ import annotations

import argparse
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from import_tumblr import (
    SCHEMA_VERSION,
    build_slug,
    build_track_stats,
    build_tracks_from_candidates,
    extract_mix_number,
    normalize_whitespace,
    paragraphs_to_intro_metadata,
    parse_description,
    should_skip_item,
    slugify,
    title_case_mix_number,
)
from mmm_common import DATA_DIR, ROOT, dump_json, load_json, now_iso
import sync_tumblr_artwork

DEFAULT_ARCHIVE_ROOT = Path("/tmp/mmm-tumblr-archive")
DEFAULT_OUTPUT_DIR = DATA_DIR / "imported" / "mixes"
ARCHIVE_TIMEZONE = timezone(timedelta(hours=5, minutes=30))
ARCHIVE_TIMEZONE_LABEL = "+05:30"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import Tumblr archive HTML exports into MMM JSON.")
    parser.add_argument("mixes", nargs="*", help="Optional mix slugs to import. Defaults to the full archive.")
    parser.add_argument("--archive-root", type=Path, default=DEFAULT_ARCHIVE_ROOT, help="Extracted Tumblr archive root.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Directory for imported mix JSON.")
    parser.add_argument(
        "--rewrite-existing",
        action="store_true",
        help="Rewrite already-imported archive mixes instead of skipping existing files.",
    )
    parser.add_argument(
        "--skip-artwork-sync",
        action="store_true",
        help="Only write JSON; do not copy canonical artwork bytes into data/media/tumblr/.",
    )
    return parser.parse_args()


def strip_ordinal_suffixes(value: str) -> str:
    return re.sub(r"(\d+)(st|nd|rd|th)\b", r"\1", value)


def parse_archive_timestamp(value: str) -> str:
    normalized = strip_ordinal_suffixes(normalize_whitespace(value))
    parsed = datetime.strptime(normalized, "%B %d, %Y %I:%M%p").replace(tzinfo=ARCHIVE_TIMEZONE)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def extract_body_fragment(document: str) -> str:
    body_match = re.search(r"<body>(.*?)(?:<div id=\"footer\">|</body>)", document, re.IGNORECASE | re.DOTALL)
    body = body_match.group(1) if body_match else document
    caption_match = re.search(r"<div class=\"caption\">(.*)</div>\s*$", body, re.IGNORECASE | re.DOTALL)
    if caption_match:
        return caption_match.group(1).strip()

    body = re.sub(r"^\s*<h1>\s*</h1>\s*", "", body, flags=re.IGNORECASE | re.DOTALL)
    return body.strip()


def extract_footer_timestamp(document: str) -> str:
    match = re.search(r"<span id=\"timestamp\">(.*?)</span>", document, re.IGNORECASE | re.DOTALL)
    return normalize_whitespace(match.group(1) if match else "")


def extract_tags(document: str) -> list[str]:
    tags = [normalize_whitespace(tag) for tag in re.findall(r"<span class=\"tag\">(.*?)</span>", document, re.IGNORECASE | re.DOTALL)]
    return [tag for tag in tags if tag and tag.lower() != "justmigrate"]


def resolve_archive_media_path(archive_root: Path, post_id: str) -> str | None:
    media_dir = archive_root / "media"
    for candidate in sorted(media_dir.glob(f"{post_id}*")):
        if candidate.is_file():
            return candidate.relative_to(archive_root).as_posix()
    return None


def build_source_url(post_id: str) -> str:
    return f"https://mondaymusicmix.tumblr.com/post/{post_id}"


def convert_html_file_to_mix(path: Path, archive_root: Path) -> dict[str, Any] | None:
    document = path.read_text(encoding="utf-8")
    post_id = path.stem
    body_fragment = extract_body_fragment(document)
    if should_skip_item(path.name, body_fragment):
        return None

    parsed = parse_description(body_fragment)
    heading = parsed.heading or ""
    mix_number = extract_mix_number(heading, body_fragment, path.name)
    if mix_number is None:
        return None

    tracks, artist_counter = build_tracks_from_candidates(parsed.track_candidates)
    if not tracks:
        return None

    slug = build_slug(mix_number, heading, heading or path.name)
    intro_metadata = paragraphs_to_intro_metadata(parsed.paragraphs)
    footer_timestamp = extract_footer_timestamp(document)
    archive_media_path = resolve_archive_media_path(archive_root, post_id)
    cover_image = parsed.images[0] if parsed.images else ""
    source_url = build_source_url(post_id)
    top_artists = [name for name, _ in artist_counter.most_common(5)]

    legacy: dict[str, Any] = {
        "originalTitle": heading or path.name,
        "tumblrHeading": heading or None,
        "descriptionHtml": body_fragment,
        "archiveHtmlPath": path.relative_to(archive_root).as_posix(),
        "archiveTimestampText": footer_timestamp,
    }
    if archive_media_path:
        legacy["archiveMediaPath"] = archive_media_path
    if cover_image and not cover_image.lower().startswith(("http://", "https://")):
        legacy["archiveImageSource"] = cover_image
    if intro_metadata.favorite_track_cue:
        legacy["favoriteTrackCue"] = intro_metadata.favorite_track_cue
    if intro_metadata.editorial_highlights:
        legacy["editorialHighlights"] = intro_metadata.editorial_highlights

    archive_export: dict[str, Any] = {
        "postId": post_id,
        "htmlPath": path.relative_to(archive_root).as_posix(),
        "timestampText": footer_timestamp,
        "timezoneAssumed": ARCHIVE_TIMEZONE_LABEL,
        "timezoneInference": "Archive footer omits timezone; +05:30 inferred from mixes 33-36 that also survive in the RSS export.",
        "sourceUrlInferred": True,
    }
    if archive_media_path:
        archive_export["mediaPath"] = archive_media_path

    mix = {
        "$schema": "schemas/mix.schema.json",
        "schemaVersion": SCHEMA_VERSION,
        "id": slug,
        "slug": slug,
        "status": "published",
        "siteSection": "mixes",
        "source": {
            "platform": "tumblr",
            "feedType": "archive-html",
            "importedAt": now_iso(),
            "sourceUrl": source_url,
            "guid": source_url,
            "archiveExport": archive_export,
        },
        "title": title_case_mix_number(mix_number),
        "displayTitle": heading or title_case_mix_number(mix_number),
        "mixNumber": mix_number,
        "publishedAt": parse_archive_timestamp(footer_timestamp),
        "summary": intro_metadata.summary,
        "intro": intro_metadata.intro,
        "tags": extract_tags(document),
        "cover": {
            "imageUrl": cover_image if cover_image.lower().startswith(("http://", "https://")) else None,
            "alt": f"Cover art for {heading or title_case_mix_number(mix_number)}",
            "credit": intro_metadata.cover_credit,
        },
        "download": {
            "label": "Download mix",
            "url": parsed.download_links[0] if parsed.download_links else None,
        },
        "tracks": tracks,
        "stats": build_track_stats(tracks, top_artists=top_artists),
        "legacy": legacy,
    }
    return mix


def iter_archive_posts(archive_root: Path) -> list[Path]:
    html_dir = archive_root / "posts" / "html"
    return sorted(html_dir.glob("*.html"))


def should_process_slug(slug: str, requested: set[str]) -> bool:
    return not requested or slug in requested


def sync_slug_artwork(slug: str) -> dict[str, Any] | None:
    paths = sync_tumblr_artwork.resolve_target_paths([slug])
    if not paths:
        return None
    registry_path = ROOT / "data" / "media" / "artwork-registry.json"
    return sync_tumblr_artwork.sync_slug_artwork(paths, registry_path)


def main() -> int:
    args = parse_args()
    archive_root = args.archive_root.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    requested = {slugify(slug) for slug in args.mixes}
    imported = 0
    skipped_existing = 0
    synced_artwork = 0
    seen_mixes = 0

    for html_path in iter_archive_posts(archive_root):
        mix = convert_html_file_to_mix(html_path, archive_root)
        if mix is None:
            continue
        if not should_process_slug(mix["slug"], requested):
            continue

        seen_mixes += 1
        target_path = output_dir / f"{mix['slug']}.json"
        existing_payload = load_json(target_path) if target_path.exists() else None
        should_write = args.rewrite_existing or not target_path.exists()
        if isinstance(existing_payload, dict) and existing_payload.get("source", {}).get("feedType") == "rss" and not args.rewrite_existing:
            should_write = False

        if should_write:
            dump_json(target_path, mix)
            imported += 1
        else:
            skipped_existing += 1

        if not args.skip_artwork_sync:
            summary = sync_slug_artwork(mix["slug"])
            if summary is not None:
                synced_artwork += 1

    print(
        f"Imported Tumblr archive mixes: {imported} written, {skipped_existing} kept, "
        f"{synced_artwork} artwork syncs, {seen_mixes} mix posts scanned."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
