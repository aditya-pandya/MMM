from __future__ import annotations

import email.message
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import mmm_common
import sync_tumblr_artwork


class FakeResponse:
    def __init__(self, body: bytes) -> None:
        self._body = body
        self.headers = email.message.Message()
        self.headers["Content-Type"] = "image/jpeg"
        self.headers["ETag"] = "\"etag-123\""
        self.headers["Last-Modified"] = "Tue, 01 Jan 2013 00:00:00 GMT"

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def seed_mix(path: Path, *, with_cover_url: bool) -> None:
    payload = {
        "$schema": "schemas/mix.schema.json",
        "schemaVersion": "1.0",
        "id": path.stem,
        "slug": path.stem,
        "status": "published",
        "siteSection": "mixes",
        "source": {
            "platform": "tumblr",
            "feedType": "rss",
            "importedAt": "2026-04-06T00:00:00Z",
            "sourceUrl": "https://example.com/post",
            "guid": "guid-1",
        },
        "title": "Test Mix",
        "publishedAt": "2026-04-06T00:00:00Z",
        "summary": "Summary",
        "intro": ["Intro"],
        "tags": [],
        "cover": {
            "imageUrl": "https://64.media.tumblr.com/example/image.jpg" if with_cover_url else None,
            "alt": "Alt",
            "credit": "Credit",
        },
        "tracks": [{"position": 1, "artist": "Artist", "title": "Song", "displayText": "Artist - Song", "isFavorite": False}],
        "stats": {"trackCount": 1, "favoriteCount": 0},
        "legacy": {
            "descriptionHtml": '<figure><img src="https://64.media.tumblr.com/fallback/image.jpg"/></figure>'
        },
    }
    mmm_common.dump_json(path, payload)


def test_sync_tumblr_artwork_downloads_and_promotes_canonical_asset(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    published_dir = data_dir / "published"
    imported_dir = data_dir / "imported" / "mixes"
    media_dir = data_dir / "media"
    published_dir.mkdir(parents=True)
    imported_dir.mkdir(parents=True)
    (media_dir / "tumblr").mkdir(parents=True)

    published_path = published_dir / "mix-001-test.json"
    imported_path = imported_dir / "mix-001-test.json"
    seed_mix(published_path, with_cover_url=True)
    seed_mix(imported_path, with_cover_url=False)

    monkeypatch.setattr(sync_tumblr_artwork, "ROOT", tmp_path)
    monkeypatch.setattr(sync_tumblr_artwork, "DATA_DIR", data_dir)
    monkeypatch.setattr(sync_tumblr_artwork, "PUBLISHED_DIR", published_dir)
    monkeypatch.setattr(sync_tumblr_artwork, "IMPORTED_DIR", imported_dir)
    monkeypatch.setattr(sync_tumblr_artwork, "MEDIA_TUMBLR_DIR", media_dir / "tumblr")
    monkeypatch.setattr(sync_tumblr_artwork, "urlopen", lambda request, timeout=30: FakeResponse(b"jpeg-bytes"))

    summary = sync_tumblr_artwork.sync_slug_artwork([published_path, imported_path], media_dir / "artwork-registry.json")

    published = json.loads(published_path.read_text(encoding="utf-8"))
    imported = json.loads(imported_path.read_text(encoding="utf-8"))
    registry = json.loads((media_dir / "artwork-registry.json").read_text(encoding="utf-8"))
    asset_path = tmp_path / published["cover"]["canonicalAssetPath"]

    assert summary["mixSlug"] == "mix-001-test"
    assert asset_path.exists()
    assert asset_path.read_bytes() == b"jpeg-bytes"
    assert published["cover"]["canonicalAssetPath"] == imported["cover"]["canonicalAssetPath"]
    assert registry["items"][0]["provenance"]["sourceType"] == "tumblr-original"
    assert registry["items"][0]["provenance"]["discoveredFrom"] == "cover.imageUrl"
    assert registry["items"][0]["file"]["etag"] == "\"etag-123\""


def test_sync_tumblr_artwork_uses_legacy_html_when_cover_url_missing(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    published_dir = data_dir / "published"
    media_dir = data_dir / "media"
    published_dir.mkdir(parents=True)
    (media_dir / "tumblr").mkdir(parents=True)

    published_path = published_dir / "mix-002-test.json"
    seed_mix(published_path, with_cover_url=False)

    monkeypatch.setattr(sync_tumblr_artwork, "ROOT", tmp_path)
    monkeypatch.setattr(sync_tumblr_artwork, "DATA_DIR", data_dir)
    monkeypatch.setattr(sync_tumblr_artwork, "PUBLISHED_DIR", published_dir)
    monkeypatch.setattr(sync_tumblr_artwork, "IMPORTED_DIR", data_dir / "imported" / "mixes")
    monkeypatch.setattr(sync_tumblr_artwork, "MEDIA_TUMBLR_DIR", media_dir / "tumblr")
    monkeypatch.setattr(sync_tumblr_artwork, "urlopen", lambda request, timeout=30: FakeResponse(b"jpeg-bytes"))

    summary = sync_tumblr_artwork.sync_mix_artwork(published_path, media_dir / "artwork-registry.json")

    assert summary["discoveredFrom"] == "legacy.descriptionHtml img"
