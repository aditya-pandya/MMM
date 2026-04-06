from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import mmm_common
import approve_mix
import publish_mix


@pytest.fixture()
def temp_repo(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    drafts = data_dir / "drafts"
    published = data_dir / "published"
    archive_dir = data_dir / "archive"
    drafts.mkdir(parents=True)
    published.mkdir(parents=True)
    archive_dir.mkdir(parents=True)

    site_path = data_dir / "site.json"
    archive_path = archive_dir / "index.json"
    legacy_archive_path = data_dir / "archive-index.json"
    mixes_json_path = data_dir / "mixes.json"

    mmm_common.dump_json(site_path, {"name": "MMM", "featuredMixSlug": None})
    mmm_common.dump_json(archive_path, {"updated_at": None, "mixes": []})

    monkeypatch.setattr(mmm_common, "DRAFTS_DIR", drafts)
    monkeypatch.setattr(mmm_common, "PUBLISHED_DIR", published)
    monkeypatch.setattr(mmm_common, "ARCHIVE_INDEX_PATH", archive_path)
    monkeypatch.setattr(mmm_common, "LEGACY_ARCHIVE_INDEX_PATH", legacy_archive_path)
    monkeypatch.setattr(mmm_common, "MIXES_JSON_PATH", mixes_json_path)
    monkeypatch.setattr(mmm_common, "SITE_PATH", site_path)

    monkeypatch.setattr(publish_mix, "DRAFTS_DIR", drafts)
    monkeypatch.setattr(publish_mix, "PUBLISHED_DIR", published)
    monkeypatch.setattr(publish_mix, "ARCHIVE_INDEX_PATH", archive_path)
    monkeypatch.setattr(publish_mix, "LEGACY_ARCHIVE_INDEX_PATH", legacy_archive_path)
    monkeypatch.setattr(publish_mix, "MIXES_JSON_PATH", mixes_json_path)
    monkeypatch.setattr(publish_mix, "SITE_PATH", site_path)

    return tmp_path



def approved_mix(slug: str = "mmm-for-2026-04-06"):
    return {
        "slug": slug,
        "title": "MMM for 2026-04-06",
        "date": "2026-04-06",
        "status": "approved",
        "summary": "A test mix.",
        "notes": "Ready to publish.",
        "tracks": [
            {"artist": "Broadcast", "title": "Pendulum", "why_it_fits": "Sets the tone."},
            {"artist": "Air", "title": "All I Need", "why_it_fits": "Keeps things warm."},
            {"artist": "Stereolab", "title": "French Disko", "why_it_fits": "Adds momentum."},
        ],
        "approval": {
            "reviewedAt": "2026-04-06T10:00:00Z",
            "approvedAt": "2026-04-06T10:00:00Z",
            "reviewedBy": "Aditya",
            "approvedBy": "Aditya",
        },
    }



def test_publish_mix_updates_archive_and_feature(temp_repo):
    draft_path = temp_repo / "data" / "drafts" / "mmm-for-2026-04-06.json"
    mmm_common.dump_json(draft_path, approved_mix())

    result = publish_mix.publish_mix(draft_path, feature=True)

    assert result["published"] is True
    published_path = temp_repo / "data" / "published" / "mmm-for-2026-04-06.json"
    assert published_path.exists()
    published_mix = mmm_common.load_json(published_path)
    assert published_mix["status"] == "published"
    assert published_mix["publishedAt"] == "2026-04-06T12:00:00Z"
    archive = mmm_common.load_json(temp_repo / "data" / "archive" / "index.json")
    assert archive["mixes"][0]["slug"] == "mmm-for-2026-04-06"
    site = mmm_common.load_json(temp_repo / "data" / "site.json")
    assert site["featuredMixSlug"] == "mmm-for-2026-04-06"



def test_validate_only_allows_unapproved_draft(temp_repo):
    draft_path = temp_repo / "data" / "drafts" / "mmm-for-2026-04-06.json"
    mix = approved_mix()
    mix["status"] = "draft"
    mmm_common.dump_json(draft_path, mix)

    result = publish_mix.publish_mix(draft_path, validate_only=True)

    assert result["published"] is False
    assert result["status"] == "draft"



def test_publish_mix_requires_approved_status(temp_repo):
    draft_path = temp_repo / "data" / "drafts" / "mmm-for-2026-04-06.json"
    mix = approved_mix()
    mix["status"] = "draft"
    mmm_common.dump_json(draft_path, mix)

    with pytest.raises(mmm_common.ValidationError):
        publish_mix.publish_mix(draft_path)


def test_publish_mix_requires_approval_metadata_for_approved_draft(temp_repo):
    draft_path = temp_repo / "data" / "drafts" / "mmm-for-2026-04-06.json"
    mix = approved_mix()
    mix.pop("approval")
    mmm_common.dump_json(draft_path, mix)

    with pytest.raises(mmm_common.ValidationError, match="approval metadata"):
        publish_mix.publish_mix(draft_path)
