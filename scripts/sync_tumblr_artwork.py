#!/usr/bin/env python3
"""Download exact Tumblr-hosted mix artwork into the local archive."""

from __future__ import annotations

import argparse
import hashlib
import mimetypes
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from manage_artwork import load_or_create_registry
from mmm_common import DATA_DIR, ROOT, ValidationError, dump_json, ensure_kebab_case_slug, load_json, now_iso

PUBLISHED_DIR = DATA_DIR / "published"
IMPORTED_DIR = DATA_DIR / "imported" / "mixes"
MEDIA_TUMBLR_DIR = DATA_DIR / "media" / "tumblr"


class LegacyImageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.images: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "img":
            return
        src = dict(attrs).get("src")
        if src and src not in self.images:
            self.images.append(src)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync Tumblr cover art into data/media/tumblr/")
    parser.add_argument("mixes", nargs="*", help="Mix slugs to sync. Defaults to every Tumblr-derived published/imported mix.")
    return parser.parse_args()


def iter_mix_paths() -> list[Path]:
    return sorted([*PUBLISHED_DIR.glob("*.json"), *IMPORTED_DIR.glob("*.json")])


def resolve_target_paths(slugs: list[str]) -> list[Path]:
    if not slugs:
        return iter_mix_paths()

    requested = {ensure_kebab_case_slug(slug, "mix slug") for slug in slugs}
    matches = [path for path in iter_mix_paths() if path.stem in requested]
    missing = sorted(requested - {path.stem for path in matches})
    if missing:
        raise FileNotFoundError(f"Could not find mix JSON for: {', '.join(missing)}")
    return matches


def extract_legacy_image(description_html: str) -> str:
    parser = LegacyImageParser()
    parser.feed(str(description_html or ""))
    return parser.images[0] if parser.images else ""


def resolve_cover_url(mix: dict[str, Any]) -> tuple[str, str]:
    cover = mix.get("cover") if isinstance(mix.get("cover"), dict) else {}
    image_url = str(cover.get("imageUrl") or "").strip()
    if image_url:
        return image_url, "cover.imageUrl"

    legacy_html = str(mix.get("legacy", {}).get("descriptionHtml") or "").strip()
    if legacy_html:
        fallback = extract_legacy_image(legacy_html)
        if fallback:
            return fallback, "legacy.descriptionHtml img"

    raise ValidationError(f"{mix.get('slug') or 'mix'} is missing Tumblr cover.imageUrl and legacy HTML fallback")


def download_bytes(url: str) -> tuple[bytes, dict[str, str | None]]:
    request = Request(url, headers={"User-Agent": "MMM artwork sync/1.0"})
    with urlopen(request, timeout=30) as response:
        body = response.read()
        metadata = {
            "mediaType": response.headers.get_content_type(),
            "etag": response.headers.get("ETag"),
            "lastModified": response.headers.get("Last-Modified"),
        }
    return body, metadata


def determine_extension(url: str, media_type: str | None) -> str:
    guessed = mimetypes.guess_extension(media_type or "", strict=False)
    if guessed:
        return guessed
    suffix = Path(urlparse(url).path).suffix
    return suffix or ".bin"


def sync_mix_artwork(path: Path, registry_path: Path) -> dict[str, Any]:
    mix = load_json(path)
    source = mix.get("source") if isinstance(mix.get("source"), dict) else {}
    if str(source.get("platform") or "").strip().lower() != "tumblr":
        raise ValidationError(f"{path.name} is not marked as a Tumblr-derived mix")

    url, discovered_from = resolve_cover_url(mix)
    body, remote_meta = download_bytes(url)
    extension = determine_extension(url, remote_meta.get("mediaType"))
    destination_dir = MEDIA_TUMBLR_DIR / mix["slug"]
    destination_dir.mkdir(parents=True, exist_ok=True)
    asset_path = destination_dir / f"cover{extension}"
    asset_path.write_bytes(body)

    asset_relative = asset_path.relative_to(ROOT).as_posix()
    cover = mix.get("cover") if isinstance(mix.get("cover"), dict) else {}
    cover["imageUrl"] = cover.get("imageUrl") or url
    cover["canonicalAssetPath"] = asset_relative
    mix["cover"] = cover
    dump_json(path, mix)

    registry = load_or_create_registry(registry_path)
    item = {
        "id": f"{mix['slug']}-cover-art-tumblr-original",
        "mixSlug": mix["slug"],
        "role": "cover-art",
        "assetPath": asset_relative,
        "workspacePath": destination_dir.relative_to(ROOT).as_posix(),
        "registeredAt": now_iso(),
        "file": {
            "byteSize": len(body),
            "mediaType": remote_meta.get("mediaType") or "application/octet-stream",
            "etag": remote_meta.get("etag"),
            "lastModified": remote_meta.get("lastModified"),
        },
        "checksum": {
            "algorithm": "sha256",
            "value": hashlib.sha256(body).hexdigest(),
        },
        "provenance": {
            "sourceType": "tumblr-original",
            "sourceLabel": "Exact Tumblr-hosted cover image bytes",
            "sourceUrl": url,
            "discoveredFrom": discovered_from,
            "notes": f"Downloaded from Tumblr for {path.relative_to(ROOT).as_posix()} and promoted to canonical local artwork.",
        },
    }
    registry["schemaVersion"] = "1.0"
    registry["updatedAt"] = now_iso()
    registry_items = [entry for entry in registry.get("items", []) if entry.get("id") != item["id"]]
    registry_items.append(item)
    registry_items.sort(key=lambda entry: (entry.get("mixSlug", ""), entry.get("role", ""), entry.get("assetPath", "")))
    registry["items"] = registry_items
    dump_json(registry_path, registry)

    return {
        "mixSlug": mix["slug"],
        "mixPath": path.relative_to(ROOT).as_posix(),
        "assetPath": asset_relative,
        "checksum": item["checksum"]["value"],
        "discoveredFrom": discovered_from,
    }


def sync_slug_artwork(paths: list[Path], registry_path: Path) -> dict[str, Any]:
    primary = sync_mix_artwork(paths[0], registry_path)
    primary_mix = load_json(paths[0])
    canonical_asset = primary_mix["cover"]["canonicalAssetPath"]
    source_url = primary_mix["cover"]["imageUrl"]

    for extra_path in paths[1:]:
        extra_mix = load_json(extra_path)
        cover = extra_mix.get("cover") if isinstance(extra_mix.get("cover"), dict) else {}
        cover["imageUrl"] = cover.get("imageUrl") or source_url
        cover["canonicalAssetPath"] = canonical_asset
        extra_mix["cover"] = cover
        dump_json(extra_path, extra_mix)

    return primary


def main() -> int:
    args = parse_args()
    synced: list[dict[str, Any]] = []
    registry_path = ROOT / "data" / "media" / "artwork-registry.json"
    grouped_paths: dict[str, list[Path]] = {}
    for path in resolve_target_paths(args.mixes):
        grouped_paths.setdefault(path.stem, []).append(path)
    for slug in sorted(grouped_paths):
        synced.append(sync_slug_artwork(grouped_paths[slug], registry_path))

    for item in synced:
        print(f"{item['mixSlug']}: {item['assetPath']} ({item['discoveredFrom']}) sha256={item['checksum']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
