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
    imported_dir = tmp_path / "data" / "imported" / "mixes"
    youtube_dir = tmp_path / "data" / "youtube"
    published_dir.mkdir(parents=True)
    imported_dir.mkdir(parents=True)
    youtube_dir.mkdir(parents=True)
    mix_path = published_dir / "mix-001-test.json"
    seed_mix(mix_path)

    monkeypatch.setattr(sync_youtube_matches, "ROOT", tmp_path)
    monkeypatch.setattr(sync_youtube_matches, "IMPORTED_MIXES_DIR", imported_dir)
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
    assert payload["summary"]["generatedEmbed"]["kind"] == "audio-first-queue"
    assert payload["summary"]["generatedEmbed"]["embedSupported"] is False
    written = json.loads((youtube_dir / "mix-001-test.json").read_text(encoding="utf-8"))
    assert written["tracks"][0]["resolution"]["status"] == "auto-resolved"


def test_sync_youtube_matches_holds_back_ambiguous_or_duplicate_results(tmp_path, monkeypatch):
    published_dir = tmp_path / "data" / "published"
    imported_dir = tmp_path / "data" / "imported" / "mixes"
    youtube_dir = tmp_path / "data" / "youtube"
    published_dir.mkdir(parents=True)
    imported_dir.mkdir(parents=True)
    youtube_dir.mkdir(parents=True)
    mix_path = published_dir / "mix-002-test.json"
    seed_mix(mix_path)

    monkeypatch.setattr(sync_youtube_matches, "ROOT", tmp_path)
    monkeypatch.setattr(sync_youtube_matches, "IMPORTED_MIXES_DIR", imported_dir)
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
    assert payload["tracks"][0]["resolution"]["holdbackReason"] in {"low-confidence-top-candidate", "possible-duplicate-video"}


def test_sync_youtube_matches_accepts_low_confidence_when_requested(tmp_path, monkeypatch):
    published_dir = tmp_path / "data" / "published"
    imported_dir = tmp_path / "data" / "imported" / "mixes"
    youtube_dir = tmp_path / "data" / "youtube"
    published_dir.mkdir(parents=True)
    imported_dir.mkdir(parents=True)
    youtube_dir.mkdir(parents=True)
    mix_path = published_dir / "mix-004-test.json"
    seed_mix(mix_path)

    monkeypatch.setattr(sync_youtube_matches, "ROOT", tmp_path)
    monkeypatch.setattr(sync_youtube_matches, "IMPORTED_MIXES_DIR", imported_dir)
    monkeypatch.setattr(sync_youtube_matches, "YOUTUBE_DIR", youtube_dir)

    def fake_search(_: str) -> list[dict[str, object]]:
        return [
            {
                "id": "video-a",
                "title": "Random upload clip",
                "url": "https://www.youtube.com/watch?v=video-a",
                "channel": "Unknown",
                "duration": 200,
            }
        ]

    monkeypatch.setattr(sync_youtube_matches, "search_youtube", fake_search)

    payload = sync_youtube_matches.sync_mix(mix_path, accept_low_confidence=True)

    assert payload["summary"]["requiresReview"] is False
    assert payload["summary"]["generatedEmbed"] is not None
    assert all(track["resolution"]["status"] == "auto-resolved" for track in payload["tracks"])
    assert all(track["resolution"]["selectedVideoId"] == "video-a" for track in payload["tracks"])
    assert all(track["resolution"]["holdbackReason"] in {None, "low-confidence-auto-selected"} for track in payload["tracks"])


def test_build_track_state_retries_with_cleaned_query(monkeypatch):
    queries: list[str] = []

    def fake_search(query: str) -> list[dict[str, object]]:
        queries.append(query)
        if "must listen" in query.lower():
            return []
        return [
            {
                "id": "video-clean",
                "title": "Adele - Set Fire To The Rain (feat. Gilbere Forte)",
                "url": "https://www.youtube.com/watch?v=video-clean",
                "channel": "Adele Topic",
                "duration": 240,
            }
        ]

    monkeypatch.setattr(sync_youtube_matches, "search_youtube", fake_search)

    track = {
        "position": 12,
        "artist": "Adele",
        "title": "Set Fire To The Rain (feat. Gilbere Forte) must listen - this isn’t the album version",
        "displayText": "Adele - Set Fire To The Rain (feat. Gilbere Forte) must listen - this isn’t the album version",
    }

    state = sync_youtube_matches.build_track_state(track, accept_low_confidence=True)

    assert len(queries) >= 2
    assert "must listen" not in state["query"].lower()
    assert state["resolution"]["selectedVideoId"] == "video-clean"


def test_sync_youtube_matches_prefers_audio_focused_result_over_music_video():
    track = {
        "artist": "Artist",
        "title": "Song",
        "displayText": "Artist - Song",
    }
    audio_candidate = sync_youtube_matches.score_candidate(
        track,
        {
            "id": "audio-1",
            "title": "Artist - Song [Official Audio]",
            "url": "https://www.youtube.com/watch?v=audio-1",
            "channel": "Artist Topic",
            "duration": 210,
        },
    )
    video_candidate = sync_youtube_matches.score_candidate(
        track,
        {
            "id": "video-1",
            "title": "Artist - Song (Official Video)",
            "url": "https://www.youtube.com/watch?v=video-1",
            "channel": "Artist",
            "duration": 210,
        },
    )

    assert audio_candidate.score > video_candidate.score
    assert "official-audio-preferred" in audio_candidate.signals


def test_resolve_mix_paths_prefers_published_when_slug_exists_in_both_sources(tmp_path, monkeypatch):
    published_dir = tmp_path / "data" / "published"
    imported_dir = tmp_path / "data" / "imported" / "mixes"
    youtube_dir = tmp_path / "data" / "youtube"
    published_dir.mkdir(parents=True)
    imported_dir.mkdir(parents=True)
    youtube_dir.mkdir(parents=True)

    published_mix_path = published_dir / "mix-003-test.json"
    imported_mix_path = imported_dir / "mix-003-test.json"
    seed_mix(published_mix_path)
    imported_payload = mmm_common.load_json(published_mix_path)
    imported_payload.pop("$schema", None)
    imported_payload.pop("schemaVersion", None)
    imported_payload.pop("siteSection", None)
    imported_payload.pop("publishedAt", None)
    imported_payload["date"] = "2026-04-06"
    imported_payload["status"] = "imported"
    imported_payload["notes"] = "Imported version"
    for track in imported_payload["tracks"]:
        track.pop("position", None)
        track.pop("displayText", None)
        track.pop("isFavorite", None)
        track["why_it_fits"] = "Imported context"
    mmm_common.dump_json(imported_mix_path, imported_payload)

    monkeypatch.setattr(sync_youtube_matches, "IMPORTED_MIXES_DIR", imported_dir)
    monkeypatch.setattr(mmm_common, "PUBLISHED_DIR", published_dir)

    resolved = sync_youtube_matches.resolve_mix_paths(["mix-003-test"])

    assert resolved == [published_mix_path]
