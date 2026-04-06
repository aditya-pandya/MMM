from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from operator_workflow import OperatorService, atomic_dump_json
from test_approval_and_release import seed_repo


@pytest.fixture()
def service_repo(tmp_path):
    draft_path = seed_repo(tmp_path)
    youtube_dir = tmp_path / "data" / "youtube"
    youtube_dir.mkdir(parents=True, exist_ok=True)
    state_path = youtube_dir / "mix-001-test.json"
    state_path.write_text(
        json.dumps(
            {
                "$schema": "../../schemas/youtube-match.schema.json",
                "schemaVersion": "1.0",
                "mixSlug": "mix-001-test",
                "updatedAt": "2026-04-06T00:00:00Z",
                "sourceMixPath": "data/published/mix-001-test.json",
                "tracks": [
                    {
                        "position": 1,
                        "displayText": "Artist - Song",
                        "query": "Artist Song",
                        "resolution": {
                            "status": "pending-review",
                            "selectedVideoId": None,
                            "confidenceScore": 0.75,
                            "reason": "Needs review",
                            "holdbackReason": "ambiguous-top-candidates",
                        },
                        "candidates": [
                            {
                                "rank": 1,
                                "videoId": "video-a",
                                "title": "Artist - Song",
                                "url": "https://www.youtube.com/watch?v=video-a",
                                "channel": "Artist Topic",
                                "durationSeconds": 240,
                                "score": 0.99,
                                "signals": ["topic-channel"],
                            }
                        ],
                    }
                ],
                "summary": {
                    "totalTracks": 1,
                    "resolvedTracks": 0,
                    "unresolvedTracks": 1,
                    "requiresReview": True,
                    "generatedEmbed": None,
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return OperatorService(repo_root=tmp_path, preview_origin="http://127.0.0.1:3000"), draft_path, state_path


def test_atomic_dump_json_replaces_file_contents(tmp_path):
    path = tmp_path / "example.json"
    atomic_dump_json(path, {"hello": "world"})
    assert json.loads(path.read_text(encoding="utf-8")) == {"hello": "world"}


def test_save_draft_updates_editable_fields(service_repo):
    service, draft_path, _ = service_repo

    result = service.save_draft(
        "mmm-for-2026-04-13",
        {
            "title": "MMM for 2026-04-13 Revised",
            "summary": "A sharper summary.",
            "notes": "Operator-edited notes.",
            "tags": ["weekly-draft", "revised", "revised"],
            "featured": True,
            "tracks": [
                {"artist": "Broadcast", "title": "Pendulum", "why_it_fits": "Still opens well."},
                {"artist": "Air", "title": "All I Need", "why_it_fits": "Adds warmth."},
                {"artist": "Stereolab", "title": "French Disko", "why_it_fits": "Closes brighter."},
            ],
        },
    )

    written = json.loads(draft_path.read_text(encoding="utf-8"))
    assert result["title"] == "MMM for 2026-04-13 Revised"
    assert written["featured"] is True
    assert written["tags"] == ["weekly-draft", "revised"]
    assert written["tracks"][1]["why_it_fits"] == "Adds warmth."


def test_update_youtube_selections_generates_embed_when_resolved(service_repo):
    service, _, state_path = service_repo

    result = service.update_youtube_selections(
        "mix-001-test",
        [{"position": 1, "selectedVideoId": "video-a"}],
    )

    written = json.loads(state_path.read_text(encoding="utf-8"))
    assert result["state"]["summary"]["requiresReview"] is False
    assert written["tracks"][0]["resolution"]["status"] == "manual-selected"
    assert written["summary"]["generatedEmbed"]["videoIds"] == ["video-a"]


def test_bootstrap_surfaces_preview_routes_and_logs(service_repo):
    service, _, _ = service_repo
    service._log_action("validate-repo", service.validate_repo)

    payload = service.bootstrap()

    assert payload["counts"]["drafts"] >= 1
    assert payload["previewRoutes"]
    assert payload["logs"][0]["action"] == "validate-repo"
