from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import create_content
import mmm_common


@pytest.fixture()
def temp_paths(tmp_path):
    data_dir = tmp_path / "data"
    drafts_dir = data_dir / "drafts"
    notes_dir = data_dir / "notes"
    published_dir = data_dir / "published"
    drafts_dir.mkdir(parents=True)
    notes_dir.mkdir(parents=True)
    published_dir.mkdir(parents=True)
    notes_index_path = data_dir / "notes-index.json"
    return drafts_dir, notes_dir, published_dir, notes_index_path


def test_create_draft_mix_writes_template(temp_paths):
    drafts_dir, _, _, _ = temp_paths

    output = create_content.create_draft_mix(
        mix_date="2026-04-13",
        drafts_dir=drafts_dir,
    )

    assert output.name == "mmm-for-2026-04-13.json"
    payload = mmm_common.load_json(output)
    assert payload["status"] == "draft"
    assert payload["featured"] is False
    assert payload["tags"] == ["weekly-draft", "editorial-template"]
    assert len(payload["tracks"]) == 3


def test_create_note_writes_note_and_updates_index(temp_paths):
    _, notes_dir, _, notes_index_path = temp_paths

    output = create_content.create_note(
        title="Fresh archive note",
        summary="A note about the archive refresh.",
        related_mixes=["mix-036-thirtysixth"],
        published_at="2026-04-05T12:00:00Z",
        notes_dir=notes_dir,
        notes_index_path=notes_index_path,
    )

    note = mmm_common.load_json(output)
    index = mmm_common.load_json(notes_index_path)

    assert output.name == "fresh-archive-note.json"
    assert note["id"] == "note-fresh-archive-note"
    assert note["relatedMixSlugs"] == ["mix-036-thirtysixth"]
    assert index["totalNotes"] == 1
    assert index["items"][0]["path"] == "data/notes/fresh-archive-note.json"
    assert index["items"][0]["summary"] == "A note about the archive refresh."


def test_create_note_normalizes_and_deduplicates_related_mix_slugs(temp_paths):
    _, notes_dir, _, notes_index_path = temp_paths

    output = create_content.create_note(
        title="Normalized note",
        related_mixes=[" Mix 036 Thirtysixth ", "mix-036-thirtysixth", "MIX 035 THIRTYFIFTH"],
        published_at="2026-04-05T12:00:00Z",
        notes_dir=notes_dir,
        notes_index_path=notes_index_path,
    )

    note = mmm_common.load_json(output)

    assert note["relatedMixSlugs"] == ["mix-036-thirtysixth", "mix-035-thirtyfifth"]


def test_create_note_rejects_published_at_without_timezone(temp_paths):
    _, notes_dir, _, notes_index_path = temp_paths

    with pytest.raises(mmm_common.ValidationError, match="note publishedAt must be ISO-8601 date-time with timezone"):
        create_content.create_note(
            title="Bad timestamp",
            published_at="2026-04-05T12:00:00",
            notes_dir=notes_dir,
            notes_index_path=notes_index_path,
        )


def test_create_draft_mix_rejects_existing_file_without_force(temp_paths):
    drafts_dir, _, _, _ = temp_paths
    create_content.create_draft_mix(mix_date="2026-04-13", drafts_dir=drafts_dir)

    with pytest.raises(FileExistsError):
        create_content.create_draft_mix(mix_date="2026-04-13", drafts_dir=drafts_dir)


def test_create_note_from_mix_scaffolds_defaults_and_refreshes_index(temp_paths):
    _, notes_dir, published_dir, notes_index_path = temp_paths
    mix_path = published_dir / "mix-036-thirtysixth.json"
    mmm_common.dump_json(
        mix_path,
        {
            "$schema": "schemas/mix.schema.json",
            "schemaVersion": "1.0",
            "id": "mix-036-thirtysixth",
            "slug": "mix-036-thirtysixth",
            "status": "published",
            "siteSection": "mixes",
            "source": {"platform": "mmm", "feedType": "manual", "importedAt": "2026-04-05T12:00:00Z", "sourceUrl": "https://example.invalid/36", "guid": "mix-036-thirtysixth"},
            "title": "Monday Music Mix #36",
            "displayTitle": "Thirtysixth",
            "publishedAt": "2026-04-05T12:00:00Z",
            "summary": "A bright, late-night sequence.",
            "intro": ["A bright, late-night sequence."],
            "tags": [],
            "tracks": [
                {"position": 1, "artist": "Broadcast", "title": "Pendulum", "displayText": "Broadcast - Pendulum", "isFavorite": True},
                {"position": 2, "artist": "Air", "title": "All I Need", "displayText": "Air - All I Need", "isFavorite": False},
            ],
            "stats": {"trackCount": 2, "favoriteCount": 1, "favoriteTracks": ["Broadcast - Pendulum"], "topArtists": ["Broadcast", "Air"]},
        },
    )

    output = create_content.create_note_from_mix(
        mix_arg="mix-036-thirtysixth",
        notes_dir=notes_dir,
        notes_index_path=notes_index_path,
        published_dir=published_dir,
    )

    note = mmm_common.load_json(output)
    index = mmm_common.load_json(notes_index_path)

    assert output.name == "mix-036-thirtysixth-notes.json"
    assert note["title"] == "Notes on Thirtysixth"
    assert note["relatedMixSlugs"] == ["mix-036-thirtysixth"]
    assert note["tags"] == ["editorial-note", "mix-companion"]
    assert "Broadcast - Pendulum" in note["body"][1]
    assert index["items"][0]["slug"] == "mix-036-thirtysixth-notes"


def test_render_note_suggestions_reports_none_when_all_mixes_are_covered():
    rendered = create_content.render_note_suggestions([])
    payload = create_content.build_note_suggestions_payload([])

    assert rendered == "Published mixes without note coverage: 0\nnone"
    assert payload == {"count": 0, "items": []}
