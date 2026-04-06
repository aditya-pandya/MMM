from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import approve_mix
import mmm_common
import publish_mix
import release_weekly


def seed_repo(root: Path) -> Path:
    data_dir = root / "data"
    (data_dir / "drafts").mkdir(parents=True)
    (data_dir / "published").mkdir(parents=True)
    (data_dir / "notes").mkdir(parents=True)
    (data_dir / "archive").mkdir(parents=True)

    mmm_common.dump_json(
        data_dir / "listening-provider-catalog.json",
        mmm_common.load_json(REPO_ROOT / "data" / "listening-provider-catalog.json"),
    )
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
    mmm_common.dump_json(
        data_dir / "about.json",
        {
            "$schema": "../schemas/about.schema.json",
            "schemaVersion": "1.0",
            "title": "About MMM",
            "headline": "A data-first music archive.",
            "intro": ["A short introduction."],
            "sections": [{"label": "Scope", "title": "What is here", "body": ["Mixes and notes."]}],
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
            {"position": 1, "artist": "Artist", "title": "Song", "displayText": "Artist - Song", "isFavorite": False}
        ],
        "stats": {
            "trackCount": 1,
            "favoriteCount": 0,
            "favoriteTracks": [],
            "topArtists": ["Artist"],
        },
    }
    mmm_common.dump_json(data_dir / "published" / "mix-001-test.json", published_mix)

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
        "relatedNoteSlugs": [],
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
                    "relatedNoteSlugs": [],
                    "series": None,
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

    draft_path = data_dir / "drafts" / "mmm-for-2026-04-13.json"
    mmm_common.dump_json(
        draft_path,
        {
            "slug": "mmm-for-2026-04-13",
            "title": "MMM for 2026-04-13",
            "date": "2026-04-13",
            "status": "draft",
            "summary": "A weekly draft.",
            "notes": "Ready for review.",
            "tracks": [
                {"artist": "Broadcast", "title": "Pendulum", "why_it_fits": "Sets the tone."},
                {"artist": "Air", "title": "All I Need", "why_it_fits": "Keeps things warm."},
                {"artist": "Stereolab", "title": "French Disko", "why_it_fits": "Adds momentum."},
            ],
        },
    )
    return draft_path


@pytest.fixture()
def temp_repo(tmp_path, monkeypatch):
    draft_path = seed_repo(tmp_path)
    data_dir = tmp_path / "data"

    monkeypatch.setattr(mmm_common, "DRAFTS_DIR", data_dir / "drafts")
    monkeypatch.setattr(mmm_common, "PUBLISHED_DIR", data_dir / "published")
    monkeypatch.setattr(mmm_common, "ARCHIVE_INDEX_PATH", data_dir / "archive" / "index.json")
    monkeypatch.setattr(mmm_common, "LEGACY_ARCHIVE_INDEX_PATH", data_dir / "archive-index.json")
    monkeypatch.setattr(mmm_common, "MIXES_JSON_PATH", data_dir / "mixes.json")
    monkeypatch.setattr(mmm_common, "SITE_PATH", data_dir / "site.json")

    monkeypatch.setattr(publish_mix, "PUBLISHED_DIR", data_dir / "published")
    monkeypatch.setattr(publish_mix, "ARCHIVE_INDEX_PATH", data_dir / "archive" / "index.json")
    monkeypatch.setattr(publish_mix, "LEGACY_ARCHIVE_INDEX_PATH", data_dir / "archive-index.json")
    monkeypatch.setattr(publish_mix, "MIXES_JSON_PATH", data_dir / "mixes.json")
    monkeypatch.setattr(publish_mix, "SITE_PATH", data_dir / "site.json")

    return tmp_path, draft_path


def test_approve_mix_adds_lightweight_provenance(temp_repo):
    repo_root, draft_path = temp_repo

    result = approve_mix.approve_mix(
        draft_path,
        approver="Aditya",
        approval_note="Reviewed locally.",
        repo_root=repo_root,
    )

    draft = mmm_common.load_json(draft_path)
    assert result["status"] == "approved"
    assert draft["status"] == "approved"
    assert draft["approval"]["reviewedBy"] == "Aditya"
    assert draft["approval"]["approvedBy"] == "Aditya"
    assert draft["approval"]["notes"] == "Reviewed locally."
    assert draft["approval"]["reviewedAt"].endswith("Z")
    assert draft["approval"]["approvedAt"].endswith("Z")


def test_release_weekly_covers_approval_publish_and_build(temp_repo, monkeypatch):
    repo_root, draft_path = temp_repo
    approve_mix.approve_mix(draft_path, approver="Aditya", repo_root=repo_root)

    commands: list[list[str]] = []

    def fake_run_command(command: list[str], working_root: Path):
        commands.append(command)
        (working_root / "dist").mkdir(parents=True, exist_ok=True)
        (working_root / "dist" / "index.html").write_text("<html></html>", encoding="utf-8")

        class Result:
            stdout = "build ok"
            stderr = ""

        return Result()

    monkeypatch.setattr(release_weekly, "run_command", fake_run_command)

    result = release_weekly.release_mix(draft_path, repo_root=repo_root, feature=True)

    published_path = repo_root / "data" / "published" / "mmm-for-2026-04-13.json"
    assert published_path.exists()
    published = mmm_common.load_json(published_path)
    assert published["status"] == "published"
    assert result["validation"]["preflight"]["errors"] == 0
    assert result["validation"]["post_publish"]["errors"] == 0
    assert commands == [["npm", "run", "build"]]
    assert (repo_root / "dist" / "index.html").exists()
    assert "push manually" in result["next_step"]

    site = mmm_common.load_json(repo_root / "data" / "site.json")
    assert site["featuredMixSlug"] == "mmm-for-2026-04-13"
