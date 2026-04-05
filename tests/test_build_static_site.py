from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def prepare_temp_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    shutil.copytree(REPO_ROOT / "scripts", repo / "scripts")
    shutil.copytree(REPO_ROOT / "data", repo / "data")
    shutil.copytree(REPO_ROOT / "src", repo / "src")
    return repo


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_static_build_emits_note_routes_and_relationships(tmp_path):
    repo = prepare_temp_repo(tmp_path)

    result = subprocess.run(
        ["node", "scripts/build.js"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout

    dist_dir = repo / "dist"
    home_html = read_text(dist_dir / "index.html")
    archive_html = read_text(dist_dir / "archive" / "index.html")
    notes_index_html = read_text(dist_dir / "notes" / "index.html")
    note_detail_html = read_text(dist_dir / "notes" / "rebuilding-the-archive" / "index.html")
    mix_detail_html = read_text(dist_dir / "mixes" / "mix-036-thirtysixth" / "index.html")
    mix_with_youtube_html = read_text(dist_dir / "mixes" / "mix-035-thirtyfifth" / "index.html")
    studio_html = read_text(dist_dir / "studio" / "index.html")
    site_js = read_text(dist_dir / "assets" / "site.js")

    assert "notes/rebuilding-the-archive/" in home_html
    assert "Notes related to Thirtysixth" in home_html
    assert "studio/" in home_html

    assert "Search archive" in archive_html
    assert 'data-discovery-filter="state:has-related"' in archive_html
    assert 'data-discovery-filter="state:has-highlights"' in archive_html
    assert 'data-discovery-filter="state:has-listening"' in archive_html
    assert 'data-discovery-filter="source:tumblr"' in archive_html
    assert 'data-discovery-filter="texture:covers"' in archive_html
    assert 'data-discovery-filter="texture:remixes"' in archive_html
    assert 'data-discovery-item' in archive_html
    assert 'data-discovery-tags="' in archive_html
    assert 'data-discovery-filters="' in archive_html
    assert 'data-discovery-search="' in archive_html
    assert "Rebuilding the archive" in archive_html
    assert "The Kite String Tangle - Tennis Court" in archive_html
    assert "Companion playlist on YouTube" in archive_html

    assert "./rebuilding-the-archive/" in notes_index_html
    assert "../mixes/mix-036-thirtysixth/" in notes_index_html
    assert "Related mixes:" in notes_index_html
    assert "Search notes" in notes_index_html
    assert 'data-discovery-filter="state:has-related"' in notes_index_html
    assert 'data-discovery-filter="tag:archive"' in notes_index_html
    assert 'data-discovery-item' in notes_index_html
    assert 'data-discovery-filters="' in notes_index_html
    assert "Dum Dum Girls" in notes_index_html

    assert "../../mixes/mix-034-thirtyfourth/" in note_detail_html
    assert "../../mixes/mix-036-thirtysixth/" in note_detail_html
    assert "Prev and next notes" in note_detail_html

    assert "Writing tied to this mix" in mix_detail_html
    assert "../../notes/rebuilding-the-archive/" in mix_detail_html
    assert "More mixes" in mix_detail_html
    assert "Full sequence" in mix_detail_html
    assert "Provenance" in mix_detail_html
    assert "Legacy download removed" in mix_detail_html
    assert "Listening" not in mix_detail_html
    assert "Imported Tumblr snapshot" not in mix_detail_html
    assert "Search YouTube" not in mix_detail_html
    assert "Legacy Tumblr artwork is preserved as source context" in mix_detail_html
    assert "https://mega.co.nz/" not in mix_detail_html

    assert "related note" in archive_html
    assert "highlighted track" in archive_html
    assert "Companion playlist on YouTube" in mix_with_youtube_html
    assert "Listening surfaces" in mix_with_youtube_html
    assert "Embedded preview" in mix_with_youtube_html
    assert "External links" in mix_with_youtube_html
    assert "youtube.com/embed/videoseries" in mix_with_youtube_html
    assert "Bandcamp starting point" not in mix_with_youtube_html
    assert "Local editorial state" in studio_html
    assert "Validation posture" in studio_html
    assert "Archive coverage" in studio_html
    assert "Recent routes" in studio_html
    assert "Recommended next actions" in studio_html
    assert "Local commands worth keeping close" in studio_html
    assert "updateDiscovery" in site_js


def test_static_build_normalizes_discovery_tags_for_notes_facets(tmp_path):
    repo = prepare_temp_repo(tmp_path)

    first_note_path = repo / "data" / "notes" / "how-the-mixes-are-read.json"
    first_note = json.loads(read_text(first_note_path))
    first_note["tags"] = ["Seed Data", "Late/Night", "Editorial Notes"]
    write_json(first_note_path, first_note)

    second_note_path = repo / "data" / "notes" / "rebuilding-the-archive.json"
    second_note = json.loads(read_text(second_note_path))
    second_note["tags"] = ["Seed Data", "Late/Night", "Editorial Notes"]
    write_json(second_note_path, second_note)

    result = subprocess.run(
        ["node", "scripts/build.js"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout

    notes_index_html = read_text(repo / "dist" / "notes" / "index.html")

    assert 'data-discovery-filter="tag:seed-data"' in notes_index_html
    assert 'data-discovery-filter="tag:late-night"' in notes_index_html
    assert 'data-discovery-filter="tag:editorial-notes"' in notes_index_html
    assert 'data-discovery-tags="seed-data|late-night|editorial-notes"' in notes_index_html


def test_static_build_recursively_flattens_nested_listening_provider_shapes(tmp_path):
    repo = prepare_temp_repo(tmp_path)
    mix_path = repo / "data" / "published" / "mix-035-thirtyfifth.json"
    mix = json.loads(read_text(mix_path))
    mix["listening"] = {
        "intro": "Nested listening data should still render without dropping providers or embeds.",
        "providers": {
            "playlistMirrors": [
                {
                    "provider": "YouTube",
                    "label": "Companion playlist on YouTube",
                    "url": "https://www.youtube.com/playlist?list=PL4fGSI1pDJn7gB0v9wN6Q8hX1QyQ1Z5wA",
                    "kind": "playlist",
                    "note": "Provider arrays can stay nested."
                }
            ],
            "editorial": {
                "bandcamp": {
                    "label": "Bandcamp starting point",
                    "url": "https://daily.bandcamp.com/best-of-2013",
                    "kind": "listen",
                    "note": "Provider maps should flatten recursively."
                },
                "embeds": [
                    {
                        "provider": "YouTube",
                        "title": "Thirtyfifth playlist embed",
                        "url": "https://www.youtube.com/embed/videoseries?list=PL4fGSI1pDJn7gB0v9wN6Q8hX1QyQ1Z5wA",
                        "note": "Nested embeds should survive too."
                    }
                ]
            }
        }
    }
    write_json(mix_path, mix)

    result = subprocess.run(
        ["node", "scripts/build.js"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout

    mix_html = read_text(repo / "dist" / "mixes" / "mix-035-thirtyfifth" / "index.html")

    assert "Companion playlist on YouTube" in mix_html
    assert "Bandcamp starting point" not in mix_html
    assert "Listening surfaces" in mix_html
    assert "Trusted link only" in mix_html
    assert "Trusted embed-ready" in mix_html
    assert "youtube.com/embed/videoseries" in mix_html

def test_static_build_requires_explicit_trusted_embed_data_before_rendering_preview(tmp_path):
    repo = prepare_temp_repo(tmp_path)

    youtube_mix_path = repo / "data" / "published" / "mix-035-thirtyfifth.json"
    youtube_mix = json.loads(read_text(youtube_mix_path))
    youtube_mix["listening"]["providers"]["editorial"]["embeds"] = []
    write_json(youtube_mix_path, youtube_mix)

    spotify_mix_path = repo / "data" / "published" / "mix-036-thirtysixth.json"
    spotify_mix = json.loads(read_text(spotify_mix_path))
    spotify_mix["listening"] = {
        "intro": "Explicit Spotify provider data should stay link-only.",
        "providers": [
            {
                "provider": "Spotify",
                "label": "Archive reconstruction playlist",
                "url": "https://open.spotify.com/playlist/37i9dQZF1DX4WYpdgoIcn6",
                "kind": "playlist",
                "note": "Useful as a direct playlist link, but not enough to claim embedded playback."
            }
        ]
    }
    write_json(spotify_mix_path, spotify_mix)

    result = subprocess.run(
        ["node", "scripts/build.js"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout

    youtube_mix_html = read_text(repo / "dist" / "mixes" / "mix-035-thirtyfifth" / "index.html")
    spotify_mix_html = read_text(repo / "dist" / "mixes" / "mix-036-thirtysixth" / "index.html")

    assert "youtube.com/embed/videoseries" not in youtube_mix_html
    assert "External links" in youtube_mix_html
    assert "Trusted link only" in spotify_mix_html
    assert "open.spotify.com/embed/playlist" not in spotify_mix_html


def test_static_build_demotes_uncertain_listening_data_on_mix_detail_pages(tmp_path):
    repo = prepare_temp_repo(tmp_path)

    mix_path = repo / "data" / "published" / "mix-036-thirtysixth.json"
    mix = json.loads(read_text(mix_path))
    mix["listening"] = {
        "intro": "These links should stay visibly tentative.",
        "providers": [
            {
                "provider": "YouTube",
                "label": "Questionable mirror",
                "url": "https://open.spotify.com/playlist/37i9dQZF1DX4WYpdgoIcn6",
                "kind": "mixtape"
            }
        ],
        "embeds": [
            {
                "provider": "Spotify",
                "title": "Untrusted preview",
                "url": "https://www.youtube.com/embed/videoseries?list=PL1234567890"
            }
        ]
    }
    write_json(mix_path, mix)

    result = subprocess.run(
        ["node", "scripts/build.js"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout

    mix_html = read_text(repo / "dist" / "mixes" / "mix-036-thirtysixth" / "index.html")

    assert "Uncertain leads" in mix_html
    assert "Questionable mirror" in mix_html
    assert "Inspect link" in mix_html
    assert "<iframe" not in mix_html
    assert "Trusted embed-ready" not in mix_html


def test_static_build_surfaces_listening_warnings_in_studio_health(tmp_path):
    repo = prepare_temp_repo(tmp_path)

    mix_path = repo / "data" / "published" / "mix-035-thirtyfifth.json"
    mix = json.loads(read_text(mix_path))
    mix["listening"] = {
        "intro": "Suspicious listening data should show up in studio health.",
        "providers": [
            {
                "provider": "YouTube",
                "label": "Broken provider mirror",
                "url": "https://open.spotify.com/playlist/37i9dQZF1DX4WYpdgoIcn6",
                "kind": "mixtape",
            }
        ],
        "embeds": [
            {
                "provider": "Spotify",
                "title": "Wrong embed host",
                "url": "https://www.youtube.com/embed/videoseries?list=PL1234567890",
            }
        ],
    }
    write_json(mix_path, mix)

    result = subprocess.run(
        ["node", "scripts/build.js"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout

    studio_html = read_text(repo / "dist" / "studio" / "index.html")

    assert "Listening warnings" in studio_html
    assert "Latest flagged: Thirtyfifth" in studio_html
    assert "Listening health" in studio_html
    assert "Review listening/provider payloads for Thirtyfifth" in studio_html
    assert "provider &quot;YouTube&quot; uses unsupported kind &quot;mixtape&quot;" in studio_html


def test_static_build_fails_loudly_on_malformed_canonical_note_json(tmp_path):
    repo = prepare_temp_repo(tmp_path)
    malformed_note_path = repo / "data" / "notes" / "rebuilding-the-archive.json"
    malformed_note_path.write_text("{\n  \"slug\": \"broken-note\",\n", encoding="utf-8")

    result = subprocess.run(
        ["node", "scripts/build.js"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "Could not parse data/notes/rebuilding-the-archive.json" in (result.stderr or result.stdout)
