from __future__ import annotations

import json
import sys
from argparse import Namespace
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import import_tumblr_archive
import mmm_common
import sync_tumblr_artwork


def write_archive_mix(path: Path, *, post_id: str, heading: str, mix_number: int, timestamp: str, image_src: str) -> None:
    path.write_text(
        f"""
<!DOCTYPE HTML>
<html>
  <body>
    <h1></h1>
    <h2>{heading}</h2>
    <p>Back after a while with another archive pull.</p>
    <p><strong>Monday Music Mix: {mix_number}</strong></p>
    <p><img src="{image_src}"/></p>
    <p>Album art featuring work by Archive Artist</p>
    <p>Tracklist:</p>
    <ol>
      <li>Artist One - Song One</li>
      <li><strong>Artist Two - Song Two</strong></li>
    </ol>
    <p><a href="https://example.com/download.zip">Download album</a></p>
    <div id="footer">
      <span id="timestamp">{timestamp}</span>
    </div>
  </body>
</html>
""".strip(),
        encoding="utf-8",
    )


def test_convert_html_file_to_mix_preserves_archive_context(tmp_path):
    archive_root = tmp_path / "archive"
    html_dir = archive_root / "posts" / "html"
    media_dir = archive_root / "media"
    html_dir.mkdir(parents=True)
    media_dir.mkdir(parents=True)

    html_path = html_dir / "43517668095.html"
    write_archive_mix(
        html_path,
        post_id="43517668095",
        heading="Thirtyfirst",
        mix_number=31,
        timestamp="February 4th, 2013 6:26pm",
        image_src="../../media/43517668095.jpg",
    )
    (media_dir / "43517668095.jpg").write_bytes(b"cover-bytes")

    mix = import_tumblr_archive.convert_html_file_to_mix(html_path, archive_root)

    assert mix is not None
    assert mix["slug"] == "mix-031-thirtyfirst"
    assert mix["source"]["feedType"] == "archive-html"
    assert mix["source"]["archiveExport"]["mediaPath"] == "media/43517668095.jpg"
    assert mix["source"]["archiveExport"]["timezoneAssumed"] == "+05:30"
    assert mix["publishedAt"] == "2013-02-04T12:56:00Z"
    assert mix["cover"]["imageUrl"] is None
    assert mix["legacy"]["archiveImageSource"] == "../../media/43517668095.jpg"
    assert mix["legacy"]["archiveTimestampText"] == "February 4th, 2013 6:26pm"


def test_archive_import_keeps_existing_rss_mix_but_syncs_archive_artwork(tmp_path, monkeypatch):
    archive_root = tmp_path / "archive"
    html_dir = archive_root / "posts" / "html"
    media_dir = archive_root / "media"
    imported_dir = tmp_path / "data" / "imported" / "mixes"
    published_dir = tmp_path / "data" / "published"
    tumblr_media_dir = tmp_path / "data" / "media" / "tumblr"
    html_dir.mkdir(parents=True)
    media_dir.mkdir(parents=True)
    imported_dir.mkdir(parents=True)
    published_dir.mkdir(parents=True)
    tumblr_media_dir.mkdir(parents=True)

    write_archive_mix(
        html_dir / "67441502817.html",
        post_id="67441502817",
        heading="Thirtysixth",
        mix_number=36,
        timestamp="November 19th, 2013 10:39am",
        image_src="https://64.media.tumblr.com/example/cover.jpg",
    )
    (media_dir / "67441502817_0.jpg").write_bytes(b"archive-cover")

    existing_payload = {
        "$schema": "schemas/mix.schema.json",
        "schemaVersion": "1.0",
        "id": "mix-036-thirtysixth",
        "slug": "mix-036-thirtysixth",
        "status": "published",
        "siteSection": "mixes",
        "source": {
            "platform": "tumblr",
            "feedType": "rss",
            "importedAt": "2026-04-04T00:41:14Z",
            "sourceUrl": "https://mondaymusicmix.tumblr.com/post/67441502817",
            "guid": "https://mondaymusicmix.tumblr.com/post/67441502817",
        },
        "title": "Monday Music Mix #36",
        "displayTitle": "Thirtysixth",
        "mixNumber": 36,
        "publishedAt": "2013-11-19T05:09:00Z",
        "summary": "Existing summary.",
        "intro": ["Existing intro."],
        "tags": [],
        "cover": {
            "imageUrl": "https://64.media.tumblr.com/example/cover.jpg",
            "alt": "Cover art for Thirtysixth",
            "credit": "Album art featuring work by Archive Artist",
        },
        "download": {"label": "Download mix", "url": "https://example.com/download.zip"},
        "tracks": [
            {"position": 1, "artist": "Artist One", "title": "Song One", "displayText": "Artist One - Song One", "isFavorite": False},
            {"position": 2, "artist": "Artist Two", "title": "Song Two", "displayText": "Artist Two - Song Two", "isFavorite": True},
        ],
        "stats": {"trackCount": 2, "favoriteCount": 1, "favoriteTracks": ["Artist Two - Song Two"], "topArtists": ["Artist One", "Artist Two"]},
        "legacy": {"descriptionHtml": "<p>Existing legacy html</p>"},
    }
    mmm_common.dump_json(imported_dir / "mix-036-thirtysixth.json", existing_payload)
    mmm_common.dump_json(published_dir / "mix-036-thirtysixth.json", existing_payload)

    monkeypatch.setattr(import_tumblr_archive, "ROOT", tmp_path)
    monkeypatch.setattr(sync_tumblr_artwork, "ROOT", tmp_path)
    monkeypatch.setattr(sync_tumblr_artwork, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(sync_tumblr_artwork, "PUBLISHED_DIR", published_dir)
    monkeypatch.setattr(sync_tumblr_artwork, "IMPORTED_DIR", imported_dir)
    monkeypatch.setattr(sync_tumblr_artwork, "MEDIA_TUMBLR_DIR", tumblr_media_dir)
    monkeypatch.setattr(sync_tumblr_artwork, "DEFAULT_ARCHIVE_ROOT", archive_root)
    monkeypatch.setattr(
        import_tumblr_archive,
        "parse_args",
        lambda: Namespace(
            mixes=[],
            archive_root=archive_root,
            output_dir=imported_dir,
            rewrite_existing=False,
            skip_artwork_sync=False,
        ),
    )

    assert import_tumblr_archive.main() == 0

    imported = json.loads((imported_dir / "mix-036-thirtysixth.json").read_text(encoding="utf-8"))
    published = json.loads((published_dir / "mix-036-thirtysixth.json").read_text(encoding="utf-8"))
    registry = json.loads((tmp_path / "data" / "media" / "artwork-registry.json").read_text(encoding="utf-8"))

    assert imported["summary"] == "Existing summary."
    assert imported["source"]["feedType"] == "rss"
    assert imported["cover"]["canonicalAssetPath"] == "data/media/tumblr/mix-036-thirtysixth/cover.jpg"
    assert published["cover"]["canonicalAssetPath"] == imported["cover"]["canonicalAssetPath"]
    assert (tmp_path / imported["cover"]["canonicalAssetPath"]).read_bytes() == b"archive-cover"
    assert registry["items"][0]["provenance"]["sourceUrl"].startswith("file://")
