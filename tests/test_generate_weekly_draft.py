from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import generate_weekly_draft
import mmm_common


@pytest.fixture()
def temp_repo(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    drafts = data_dir / "drafts"
    archive_dir = data_dir / "archive"
    drafts.mkdir(parents=True)
    archive_dir.mkdir(parents=True)

    site_path = data_dir / "site.json"
    taste_path = data_dir / "taste-profile.json"
    archive_path = archive_dir / "index.json"

    mmm_common.dump_json(site_path, {"site_title": "Monday Music Mix", "featured_mix_slug": None})
    mmm_common.dump_json(
        taste_path,
        {
            "curator": "Test Curator",
            "tone": "warm and curious",
            "favorite_genres": ["ambient", "dream pop", "indie rock"],
        },
    )
    mmm_common.dump_json(archive_path, {"updated_at": None, "mixes": [{"slug": "older-mix"}]})

    monkeypatch.setattr(mmm_common, "DRAFTS_DIR", drafts)
    monkeypatch.setattr(mmm_common, "SITE_PATH", site_path)
    monkeypatch.setattr(mmm_common, "TASTE_PROFILE_PATH", taste_path)
    monkeypatch.setattr(mmm_common, "ARCHIVE_INDEX_PATH", archive_path)

    monkeypatch.setattr(generate_weekly_draft, "DRAFTS_DIR", drafts)
    monkeypatch.setattr(generate_weekly_draft, "SITE_PATH", site_path)
    monkeypatch.setattr(generate_weekly_draft, "TASTE_PROFILE_PATH", taste_path)
    monkeypatch.setattr(generate_weekly_draft, "ARCHIVE_INDEX_PATH", archive_path)

    return tmp_path



def test_generate_weekly_draft_writes_deterministic_fallback_mix(temp_repo):
    output = generate_weekly_draft.generate_weekly_draft(
        generate_weekly_draft.resolve_mix_date("2026-04-13"), mode="fallback"
    )

    assert output.exists()
    mix = mmm_common.load_json(output)
    assert mix["slug"] == "mmm-for-2026-04-13"
    assert mix["generation_mode"] == "fallback"
    assert mix["status"] == "draft"
    assert len(mix["tracks"]) == 5



def test_auto_mode_resolves_to_local_fallback(temp_repo, monkeypatch):
    monkeypatch.setenv("MMM_OPENAI_API_KEY", "test-key")

    output = generate_weekly_draft.generate_weekly_draft(
        generate_weekly_draft.resolve_mix_date("2026-04-20"), mode="auto"
    )

    mix = mmm_common.load_json(output)
    assert mix["generation_mode"] == "fallback"
    assert "generation_fallback_reason" not in mix
    assert "local-generated" in mix["tags"]
