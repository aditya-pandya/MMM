from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import mmm_common
import sync_youtube_matches


def seed_mix(path: Path) -> None:
    mmm_common.dump_json(
        path,
        {
            "$schema": "schemas/mix.schema.json",
            "schemaVersion": "1.0",
            "id": path.stem,
            "slug": path.stem,
            "status": "published",
            "siteSection": "mixes",
            "source": {
                "platform": "tumblr",
                "feedType": "rss",
                "importedAt": "2026-04-06T00:00:00Z",
                "sourceUrl": "https://example.com/post",
                "guid": "guid-1",
            },
            "title": "Mix Test",
            "publishedAt": "2026-04-06T00:00:00Z",
            "summary": "Summary",
            "intro": ["Intro"],
            "tags": [],
            "tracks": [
                {"position": 1, "artist": "Chromeo", "title": "Over Your Shoulder", "displayText": "Chromeo - Over Your Shoulder", "isFavorite": False},
                {"position": 2, "artist": "White Denim", "title": "Pretty Green", "displayText": "White Denim - Pretty Green", "isFavorite": False},
            ],
            "stats": {"trackCount": 2, "favoriteCount": 0},
        },
    )


def test_sync_youtube_matches_generates_embed_when_all_tracks_are_clear(tmp_path, monkeypatch):
    published_dir = tmp_path / "data" / "published"
    youtube_dir = tmp_path / "data" / "youtube"
    published_dir.mkdir(parents=True)
    youtube_dir.mkdir(parents=True)
    mix_path = published_dir / "mix-001-test.json"
    seed_mix(mix_path)

    monkeypatch.setattr(sync_youtube_matches, "ROOT", tmp_path)
    monkeypatch.setattr(sync_youtube_matches, "PUBLISHED_DIR", published_dir)
    monkeypatch.setattr(sync_youtube_matches, "YOUTUBE_DIR", youtube_dir)

    def fake_search(query: str) -> list[dict[str, object]]:
        if "Chromeo" in query:
            return [
                {"id": "video-a", "title": "Chromeo - Over Your Shoulder [Official Audio]", "url": "https://www.youtube.com/watch?v=video-a", "channel": "Chromeo", "duration": 277},
                {"id": "video-b", "title": "Chromeo live", "url": "https://www.youtube.com/watch?v=video-b", "channel": "Someone Else", "duration": 300},
            ]
        return [
            {"id": "video-c", "title": "White Denim - Pretty Green", "url": "https://www.youtube.com/watch?v=video-c", "channel": "White Denim Topic", "duration": 220},
            {"id": "video-d", "title": "White Denim live", "url": "https://www.youtube.com/watch?v=video-d", "channel": "Fan Upload", "duration": 280},
        ]

    monkeypatch.setattr(sync_youtube_matches, "search_youtube", fake_search)

    payload = sync_youtube_matches.sync_mix(mix_path)

    assert payload["summary"]["requiresReview"] is False
    assert payload["summary"]["generatedEmbed"]["embedUrl"] == "https://www.youtube.com/embed/video-a?playlist=video-c"
    written = json.loads((youtube_dir / "mix-001-test.json").read_text(encoding="utf-8"))
    assert written["tracks"][0]["resolution"]["status"] == "auto-resolved"


def test_sync_youtube_matches_holds_back_ambiguous_or_duplicate_results(tmp_path, monkeypatch):
    published_dir = tmp_path / "data" / "published"
    youtube_dir = tmp_path / "data" / "youtube"
    published_dir.mkdir(parents=True)
    youtube_dir.mkdir(parents=True)
    mix_path = published_dir / "mix-002-test.json"
    seed_mix(mix_path)

    monkeypatch.setattr(sync_youtube_matches, "ROOT", tmp_path)
    monkeypatch.setattr(sync_youtube_matches, "PUBLISHED_DIR", published_dir)
    monkeypatch.setattr(sync_youtube_matches, "YOUTUBE_DIR", youtube_dir)

    def fake_search(query: str) -> list[dict[str, object]]:
        return [
            {"id": "video-a", "title": f"{query} official", "url": "https://www.youtube.com/watch?v=video-a", "channel": "Artist", "duration": 200},
            {"id": "video-a", "title": f"{query} mirror", "url": "https://www.youtube.com/watch?v=video-a", "channel": "Artist", "duration": 200},
        ]

    monkeypatch.setattr(sync_youtube_matches, "search_youtube", fake_search)

    payload = sync_youtube_matches.sync_mix(mix_path)

    assert payload["summary"]["requiresReview"] is True
    assert payload["summary"]["generatedEmbed"] is None
    assert payload["tracks"][0]["resolution"]["holdbackReason"] in {"ambiguous-top-candidates", "possible-duplicate-video"}
