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
    drafts_dir.mkdir(parents=True)
    notes_dir.mkdir(parents=True)
    notes_index_path = data_dir / "notes-index.json"
    return drafts_dir, notes_dir, notes_index_path


def test_create_draft_mix_writes_template(temp_paths):
    drafts_dir, _, _ = temp_paths

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
    _, notes_dir, notes_index_path = temp_paths

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


def test_create_draft_mix_rejects_existing_file_without_force(temp_paths):
    drafts_dir, _, _ = temp_paths
    create_content.create_draft_mix(mix_date="2026-04-13", drafts_dir=drafts_dir)

    with pytest.raises(FileExistsError):
        create_content.create_draft_mix(mix_date="2026-04-13", drafts_dir=drafts_dir)
