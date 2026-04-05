from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import mmm_common
import preview_latest


@pytest.fixture()
def preview_repo(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    drafts_dir = data_dir / "drafts"
    published_dir = data_dir / "published"
    notes_dir = data_dir / "notes"
    dist_dir = tmp_path / "dist"
    (dist_dir / "mixes" / "mix-002-test").mkdir(parents=True)
    (dist_dir / "notes" / "note-two").mkdir(parents=True)
    drafts_dir.mkdir(parents=True)
    published_dir.mkdir(parents=True)
    notes_dir.mkdir(parents=True)

    mmm_common.dump_json(
        drafts_dir / "mmm-for-2026-04-13.json",
        {
            "slug": "mmm-for-2026-04-13",
            "title": "MMM for 2026-04-13",
            "date": "2026-04-13",
            "status": "draft",
            "summary": "Draft summary.",
            "notes": "Draft notes.",
            "tracks": [
                {"artist": "Broadcast", "title": "Pendulum", "why_it_fits": "Sets the tone."},
                {"artist": "Air", "title": "All I Need", "why_it_fits": "Keeps the pace."},
                {"artist": "Stereolab", "title": "French Disko", "why_it_fits": "Adds lift."},
            ],
        },
    )
    for slug, published_at in (("mix-001-test", "2026-04-05T12:00:00Z"), ("mix-002-test", "2026-04-06T12:00:00Z")):
        mmm_common.dump_json(
            published_dir / f"{slug}.json",
            {
                "$schema": "schemas/mix.schema.json",
                "schemaVersion": "1.0",
                "id": slug,
                "slug": slug,
                "status": "published",
                "siteSection": "mixes",
                "source": {"platform": "mmm", "feedType": "manual", "importedAt": "2026-04-05T12:00:00Z", "sourceUrl": f"https://example.invalid/{slug}", "guid": slug},
                "title": slug,
                "publishedAt": published_at,
                "summary": "Published mix summary.",
                "intro": ["Published mix summary."],
                "tags": [],
                "tracks": [{"position": 1, "artist": "Broadcast", "title": "Pendulum", "displayText": "Broadcast - Pendulum", "isFavorite": False}],
                "stats": {"trackCount": 1, "favoriteCount": 0, "favoriteTracks": [], "topArtists": ["Broadcast"]},
            },
        )
    for slug, published_at in (("note-one", "2026-04-05T12:00:00Z"), ("note-two", "2026-04-06T15:00:00Z")):
        mmm_common.dump_json(
            notes_dir / f"{slug}.json",
            {
                "$schema": "../../schemas/note.schema.json",
                "schemaVersion": "1.0",
                "id": f"note-{slug}",
                "slug": slug,
                "status": "published",
                "title": slug,
                "publishedAt": published_at,
                "summary": "Note summary.",
                "body": ["One paragraph."],
                "relatedMixSlugs": ["mix-001-test"],
                "tags": ["editorial-note"],
            },
        )

    (dist_dir / "mixes" / "mix-002-test" / "index.html").write_text("<html></html>", encoding="utf-8")
    (dist_dir / "notes" / "note-two" / "index.html").write_text("<html></html>", encoding="utf-8")

    monkeypatch.setattr(preview_latest, "ROOT", tmp_path)
    monkeypatch.setattr(preview_latest, "DRAFTS_DIR", drafts_dir)
    monkeypatch.setattr(preview_latest, "PUBLISHED_DIR", published_dir)
    monkeypatch.setattr(preview_latest, "NOTES_DIR", notes_dir)
    return tmp_path


def test_latest_previews_selects_latest_local_content(preview_repo):
    records = preview_latest.latest_previews()

    kinds = {record["kind"]: record for record in records}
    assert kinds["draft"]["slug"] == "mmm-for-2026-04-13"
    assert kinds["mix"]["slug"] == "mix-002-test"
    assert kinds["note"]["slug"] == "note-two"
    assert kinds["mix"]["previewTarget"].startswith("file:")
    assert kinds["note"]["previewTarget"].startswith("file:")


def test_latest_previews_rejects_non_local_host():
    with pytest.raises(mmm_common.ValidationError, match="preview host must stay local"):
        preview_latest.latest_previews(host="https://example.com")


def test_open_preview_targets_uses_webbrowser(preview_repo, monkeypatch):
    opened = []
    records = preview_latest.latest_previews(kind="mix")

    monkeypatch.setattr(preview_latest.webbrowser, "open", lambda target: opened.append(target))
    result = preview_latest.open_preview_targets(records)

    assert result == opened
    assert len(opened) == 1


def test_render_preview_summary_handles_empty_state():
    assert preview_latest.render_preview_summary([]) == "No latest content found."
