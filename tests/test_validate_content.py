from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import mmm_common
import validate_content


def seed_repo(root: Path) -> None:
    data_dir = root / "data"
    (data_dir / "drafts").mkdir(parents=True)
    (data_dir / "published").mkdir(parents=True)
    (data_dir / "notes").mkdir(parents=True)
    (data_dir / "archive").mkdir(parents=True)

    mmm_common.dump_json(
        data_dir / "site.json",
        {
            "schemaVersion": "1.0",
            "name": "MMM",
            "tagline": "Weekly mixes",
            "description": "Data-first music archive.",
            "baseUrl": "https://example.com/MMM/",
            "featuredMixSlug": "mix-001-test",
            "author": {"name": "Aditya"},
            "navigation": [{"label": "Home", "path": "/"}],
        },
    )

    published_mix = {
        "$schema": "schemas/mix.schema.json",
        "schemaVersion": "1.0",
        "id": "mix-001-test",
        "slug": "mix-001-test",
        "status": "published",
        "siteSection": "mixes",
        "source": {
            "platform": "mmm",
            "feedType": "manual",
            "importedAt": "2026-04-03T12:00:00Z",
            "sourceUrl": "https://example.com/mix-001-test",
            "guid": "mix-001-test",
        },
        "title": "Mix 001",
        "publishedAt": "2026-04-03T12:00:00Z",
        "summary": "A published mix.",
        "intro": ["Intro paragraph."],
        "tags": ["seed"],
        "tracks": [
            {
                "position": 1,
                "artist": "Artist",
                "title": "Song",
                "displayText": "Artist - Song",
                "isFavorite": False,
            }
        ],
        "stats": {"trackCount": 1, "favoriteCount": 0},
    }
    mmm_common.dump_json(data_dir / "published" / "mix-001-test.json", published_mix)

    draft_mix = {
        "slug": "mmm-for-2026-04-13",
        "title": "MMM for 2026-04-13",
        "date": "2026-04-13",
        "status": "draft",
        "summary": "Draft summary.",
        "notes": "Draft notes.",
        "tracks": [
            {"artist": "Artist", "title": "Song", "why_it_fits": "It works."},
            {"artist": "Artist 2", "title": "Song 2", "why_it_fits": "It builds."},
            {"artist": "Artist 3", "title": "Song 3", "why_it_fits": "It closes."},
        ],
    }
    mmm_common.dump_json(data_dir / "drafts" / "mmm-for-2026-04-13.json", draft_mix)

    note = {
        "$schema": "../../schemas/note.schema.json",
        "schemaVersion": "1.0",
        "id": "note-seeded-note",
        "slug": "seeded-note",
        "status": "published",
        "title": "Seeded note",
        "publishedAt": "2026-04-03T13:00:00Z",
        "summary": "A seeded note.",
        "body": ["A note body."],
        "relatedMixSlugs": ["mix-001-test"],
        "tags": ["seed"],
    }
    mmm_common.dump_json(data_dir / "notes" / "seeded-note.json", note)
    mmm_common.dump_json(
        data_dir / "notes-index.json",
        {
            "$schema": "../schemas/notes-index.schema.json",
            "schemaVersion": "1.0",
            "generatedAt": "2026-04-03T13:05:00Z",
            "totalNotes": 1,
            "items": [
                {
                    "id": "note-seeded-note",
                    "slug": "seeded-note",
                    "title": "Seeded note",
                    "publishedAt": "2026-04-03T13:00:00Z",
                    "summary": "A seeded note.",
                    "path": "data/notes/seeded-note.json",
                    "tags": ["seed"],
                    "relatedMixSlugs": ["mix-001-test"],
                }
            ],
        },
    )

    mmm_common.dump_json(
        data_dir / "archive" / "index.json",
        {
            "updated_at": "2026-04-03T14:00:00Z",
            "mixes": [
                {
                    "slug": "mix-001-test",
                    "title": "Mix 001",
                    "date": "2026-04-03",
                    "summary": "A published mix.",
                    "track_count": 1,
                }
            ],
        },
    )
    mmm_common.dump_json(
        data_dir / "archive-index.json",
        {
            "$schema": "../schemas/archive-index.schema.json",
            "schemaVersion": "1.0",
            "generatedAt": "2026-04-03T14:00:00Z",
            "totalMixes": 1,
            "items": [
                {
                    "id": "mix-001-test",
                    "slug": "mix-001-test",
                    "title": "Mix 001",
                    "displayTitle": "Mix 001",
                    "publishedAt": "2026-04-03T12:00:00Z",
                    "summary": "A published mix.",
                    "trackCount": 1,
                    "path": "data/published/mix-001-test.json",
                }
            ],
        },
    )
    mmm_common.dump_json(data_dir / "mixes.json", [published_mix])


def test_validate_content_reports_clean_repo(tmp_path):
    seed_repo(tmp_path)

    report = validate_content.build_report(tmp_path)

    assert report["errors"] == 0
    assert report["warnings"] == 0
    assert report["counts"]["published"] == 1
    assert report["counts"]["drafts"] == 1
    assert report["counts"]["notes"] == 1


def test_validate_content_reports_actionable_mismatches(tmp_path):
    seed_repo(tmp_path)
    data_dir = tmp_path / "data"

    site = mmm_common.load_json(data_dir / "site.json")
    site["featuredMixSlug"] = "missing-mix"
    mmm_common.dump_json(data_dir / "site.json", site)

    notes_index = mmm_common.load_json(data_dir / "notes-index.json")
    notes_index["items"][0]["summary"] = "Out of sync summary."
    mmm_common.dump_json(data_dir / "notes-index.json", notes_index)

    report = validate_content.build_report(tmp_path)
    messages = [issue["message"] for issue in report["issues"]]

    assert report["errors"] == 1
    assert report["warnings"] >= 1
    assert any("featured mix slug 'missing-mix'" in message for message in messages)
    assert any("field 'summary' is out of sync" in message for message in messages)
