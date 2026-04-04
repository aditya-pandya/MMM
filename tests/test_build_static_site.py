from __future__ import annotations

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

    assert "Writing that points back to this mix" in mix_detail_html
    assert "../../notes/rebuilding-the-archive/" in mix_detail_html
    assert "Prev and next mix links" in mix_detail_html
    assert "Provider links and embedded playback" in mix_detail_html
    assert "Reconstructed listening options for the archive build" in mix_detail_html
    assert "Archive reconstruction playlist" in mix_detail_html
    assert "Thirtysixth playlist embed" in mix_detail_html
    assert "open.spotify.com/embed/playlist" in mix_detail_html
    assert "Links, provenance, and source residue" in mix_detail_html
    assert "Imported Tumblr snapshot" in mix_detail_html
    assert "Favorite tracks marked in the source" in mix_detail_html
    assert "Search YouTube" in mix_detail_html
    assert "Search Spotify" in mix_detail_html
    assert "Legacy Tumblr artwork is preserved as source context" in mix_detail_html
    assert "https://mega.co.nz/" not in mix_detail_html

    assert "related note" in archive_html
    assert "highlighted track" in archive_html
    assert "Companion playlist on YouTube" in mix_with_youtube_html
    assert "This archived mix now carries a couple of modern listening mirrors" in mix_with_youtube_html
    assert "Thirtyfifth playlist embed" in mix_with_youtube_html
    assert "youtube.com/embed/videoseries" in mix_with_youtube_html
    assert "Local editorial state" in studio_html
    assert "Latest: MMM for 2026-04-06" in studio_html
    assert "Local commands worth keeping close" in studio_html
