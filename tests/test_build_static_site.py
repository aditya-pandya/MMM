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

    assert "notes/rebuilding-the-archive/" in home_html
    assert "Notes related to Thirtysixth" in home_html
    assert "studio/" in home_html

    assert "./rebuilding-the-archive/" in notes_index_html
    assert "../mixes/mix-036-thirtysixth/" in notes_index_html
    assert "Related mixes:" in notes_index_html

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
    assert "Playlist" in mix_with_youtube_html
    assert "youtube.com/embed/videoseries" in mix_with_youtube_html
    assert "Bandcamp starting point" not in mix_with_youtube_html
    assert "Local editorial state" in studio_html
    assert "Latest: MMM for 2026-04-06" in studio_html
    assert "Local commands worth keeping close" in studio_html


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
    assert "Listening" in mix_html
    assert "youtube.com/embed/videoseries" in mix_html


def test_static_build_only_derives_youtube_playlist_embeds_from_real_playlist_data(tmp_path):
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
                "note": "Useful as a direct playlist link, but not enough to claim embed support."
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

    assert "youtube.com/embed/videoseries" in youtube_mix_html
    assert "open.spotify.com/embed/playlist" not in spotify_mix_html
