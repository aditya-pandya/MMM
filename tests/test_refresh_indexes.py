from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import mmm_common
import refresh_indexes


def test_refresh_indexes_rebuilds_notes_and_archive(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    notes_dir = data_dir / "notes"
    published_dir = data_dir / "published"
    archive_dir = data_dir / "archive"
    notes_dir.mkdir(parents=True)
    published_dir.mkdir(parents=True)
    archive_dir.mkdir(parents=True)

    notes_index_path = data_dir / "notes-index.json"
    archive_index_path = data_dir / "archive" / "index.json"
    legacy_archive_index_path = data_dir / "archive-index.json"
    mixes_json_path = data_dir / "mixes.json"

    mmm_common.dump_json(
        notes_dir / "fresh-note.json",
        {
            "$schema": "../../schemas/note.schema.json",
            "schemaVersion": "1.0",
            "id": "note-fresh-note",
            "slug": "fresh-note",
            "status": "draft",
            "title": "Fresh note",
            "publishedAt": "2026-04-05T12:00:00Z",
            "summary": "Freshly scaffolded note.",
            "body": ["First paragraph.", "Second paragraph."],
            "relatedMixSlugs": ["mix-001-test"],
            "tags": ["editorial-note"],
        },
    )
    mmm_common.dump_json(
        published_dir / "mix-001-test.json",
        {
            "$schema": "schemas/mix.schema.json",
            "schemaVersion": "1.0",
            "id": "mix-001-test",
            "slug": "mix-001-test",
            "status": "published",
            "siteSection": "mixes",
            "source": {"platform": "mmm", "feedType": "manual", "importedAt": "2026-04-05T12:00:00Z", "sourceUrl": "https://example.invalid/1", "guid": "mix-001-test"},
            "title": "Mix 001",
            "publishedAt": "2026-04-05T12:00:00Z",
            "summary": "Published mix summary.",
            "intro": ["Published mix summary."],
            "tags": ["test"],
            "tracks": [{"position": 1, "artist": "Broadcast", "title": "Pendulum", "displayText": "Broadcast - Pendulum", "isFavorite": False}],
            "stats": {"trackCount": 1, "favoriteCount": 0, "favoriteTracks": [], "topArtists": ["Broadcast"]},
        },
    )

    monkeypatch.setattr(refresh_indexes, "NOTES_DIR", notes_dir)
    monkeypatch.setattr(refresh_indexes, "NOTES_INDEX_PATH", notes_index_path)
    monkeypatch.setattr(refresh_indexes, "PUBLISHED_DIR", published_dir)
    monkeypatch.setattr(refresh_indexes, "ARCHIVE_INDEX_PATH", archive_index_path)
    monkeypatch.setattr(refresh_indexes, "LEGACY_ARCHIVE_INDEX_PATH", legacy_archive_index_path)
    monkeypatch.setattr(refresh_indexes, "MIXES_JSON_PATH", mixes_json_path)

    result = refresh_indexes.refresh_indexes()

    notes_index = mmm_common.load_json(notes_index_path)
    archive_index = mmm_common.load_json(legacy_archive_index_path)
    mixes_json = mmm_common.load_json(mixes_json_path)

    assert result["notes"]["count"] == 1
    assert result["archive"]["count"] == 1
    assert notes_index["items"][0]["slug"] == "fresh-note"
    assert archive_index["items"][0]["slug"] == "mix-001-test"
    assert mixes_json[0]["slug"] == "mix-001-test"


def test_render_refresh_summary_handles_scoped_result():
    summary = refresh_indexes.render_refresh_summary(
        {
            "scope": "notes",
            "notes": {"count": 2, "index": "data/notes-index.json"},
        }
    )

    assert "Refreshed aggregates: notes" in summary
    assert "notes: 2 notes -> data/notes-index.json" in summary
