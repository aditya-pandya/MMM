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


def _published_mix(
    slug: str,
    title: str,
    published_at: str,
    summary: str,
    tracks: list[dict[str, object]],
    cover_tracks: list[str],
    remix_tracks: list[str],
) -> dict[str, object]:
    favorite_tracks = [track["displayText"] for track in tracks if track["isFavorite"]]
    top_artists = [track["artist"] for track in tracks[:5]]
    return {
        "$schema": "schemas/mix.schema.json",
        "schemaVersion": "1.0",
        "id": slug,
        "slug": slug,
        "status": "published",
        "siteSection": "mixes",
        "source": {
            "platform": "mmm",
            "feedType": "manual",
            "importedAt": "2026-04-05T12:00:00Z",
            "sourceUrl": f"https://example.invalid/{slug}",
            "guid": slug,
        },
        "title": title,
        "publishedAt": published_at,
        "summary": summary,
        "intro": [summary],
        "tags": [],
        "tracks": tracks,
        "stats": {
            "trackCount": len(tracks),
            "favoriteCount": len(favorite_tracks),
            "favoriteTracks": favorite_tracks,
            "topArtists": top_artists,
            "coverCount": len(cover_tracks),
            "coverTracks": cover_tracks,
            "remixCount": len(remix_tracks),
            "remixTracks": remix_tracks,
        },
    }


@pytest.fixture()
def temp_repo(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    drafts = data_dir / "drafts"
    archive_dir = data_dir / "archive"
    published_dir = data_dir / "published"
    notes_dir = data_dir / "notes"
    drafts.mkdir(parents=True)
    archive_dir.mkdir(parents=True)
    published_dir.mkdir(parents=True)
    notes_dir.mkdir(parents=True)

    site_path = data_dir / "site.json"
    taste_path = data_dir / "taste-profile.json"
    archive_path = archive_dir / "index.json"

    mmm_common.dump_json(site_path, {"site_title": "Monday Music Mix", "featured_mix_slug": None})
    mmm_common.dump_json(
        taste_path,
        {
            "curator": "Test Curator",
            "tone": "warm and curious",
            "favorite_genres": ["dream pop", "indie rock", "left-field electronic"],
            "recurringDescriptors": [
                {"label": "cover-heavy curation", "count": 4},
                {"label": "remix-friendly sequencing", "count": 1},
            ],
            "eraHints": [{"label": "2010s blog-era discovery", "confidence": 1.0}],
            "topArtists": [
                {"name": "Dum Dum Girls", "count": 2},
                {"name": "Goldroom", "count": 1},
            ],
        },
    )
    mmm_common.dump_json(
        archive_path,
        {
            "updated_at": None,
            "mixes": [
                {
                    "slug": "mix-034-thirtyfourth",
                    "title": "Monday Music Mix #34",
                    "date": "2013-08-12",
                    "summary": "New week, new mix. A little birdy from the mountains had to prod me to post this today.",
                    "track_count": 15,
                },
                {
                    "slug": "mix-035-thirtyfifth",
                    "title": "Monday Music Mix #35",
                    "date": "2013-09-23",
                    "summary": "A bit late given this is going up in the last hour of Monday but it still counts, right?",
                    "track_count": 15,
                },
                {
                    "slug": "mix-036-thirtysixth",
                    "title": "Monday Music Mix #36",
                    "date": "2013-11-19",
                    "summary": "Some new, some old and reimagined.",
                    "track_count": 14,
                },
            ],
        },
    )

    mmm_common.dump_json(
        published_dir / "mix-034-thirtyfourth.json",
        _published_mix(
            slug="mix-034-thirtyfourth",
            title="Monday Music Mix #34",
            published_at="2013-08-12T12:42:00Z",
            summary="New week, new mix. A little birdy from the mountains had to prod me to post this today.",
            tracks=[
                {"position": 1, "artist": "Dum Dum Girls", "title": "Mine Tonight", "displayText": "Dum Dum Girls - Mine Tonight", "isFavorite": False},
                {"position": 3, "artist": "Haim", "title": "The Wire", "displayText": "Haim - The Wire", "isFavorite": True},
                {"position": 11, "artist": "Happy Hollows", "title": "Endless", "displayText": "Happy Hollows - Endless", "isFavorite": True},
            ],
            cover_tracks=[],
            remix_tracks=[],
        ),
    )
    mmm_common.dump_json(
        published_dir / "mix-035-thirtyfifth.json",
        _published_mix(
            slug="mix-035-thirtyfifth",
            title="Monday Music Mix #35",
            published_at="2013-09-23T17:32:30Z",
            summary="A bit late given this is going up in the last hour of Monday but it still counts, right?",
            tracks=[
                {"position": 2, "artist": "Goldroom", "title": "Embrace", "displayText": "Goldroom - Embrace", "isFavorite": True},
                {"position": 8, "artist": "Chromeo", "title": "Over Your Shoulder", "displayText": "Chromeo - Over Your Shoulder", "isFavorite": False},
                {"position": 14, "artist": "Oh Land", "title": "Love You Better (John Dillinger remix)", "displayText": "Oh Land - Love You Better (John Dillinger remix)", "isFavorite": True},
            ],
            cover_tracks=[],
            remix_tracks=["Oh Land - Love You Better (John Dillinger remix)"],
        ),
    )
    mmm_common.dump_json(
        published_dir / "mix-036-thirtysixth.json",
        _published_mix(
            slug="mix-036-thirtysixth",
            title="Monday Music Mix #36",
            published_at="2013-11-19T05:09:00Z",
            summary="Some new, some old and reimagined.",
            tracks=[
                {"position": 1, "artist": "The Kite String Tangle", "title": "Tennis Court (Lorde cover)", "displayText": "The Kite String Tangle - Tennis Court (Lorde cover)", "isFavorite": False},
                {"position": 4, "artist": "Dum Dum Girls", "title": "Lost Boys and Girls Club", "displayText": "Dum Dum Girls - Lost Boys and Girls Club", "isFavorite": False},
                {"position": 12, "artist": "Angel Haze", "title": "Summer Time Sadness (Lana Del Rey cover)", "displayText": "Angel Haze - Summer Time Sadness (Lana Del Rey cover)", "isFavorite": True},
            ],
            cover_tracks=[
                "The Kite String Tangle - Tennis Court (Lorde cover)",
                "Angel Haze - Summer Time Sadness (Lana Del Rey cover)",
            ],
            remix_tracks=[],
        ),
    )

    mmm_common.dump_json(
        notes_dir / "how-the-mixes-are-read.json",
        {
            "$schema": "../../schemas/note.schema.json",
            "schemaVersion": "1.0",
            "id": "note-how-the-mixes-are-read",
            "slug": "how-the-mixes-are-read",
            "status": "published",
            "title": "How the mixes are read",
            "publishedAt": "2026-04-03T20:05:00Z",
            "summary": "A lightweight editorial note on what stands out in the seeded 2013 mixes.",
            "body": [
                "The seeded mixes lean toward blog-era indie, dreamy pop, left-field electronic tracks, and the occasional big cover version that changes the mood of the whole sequence.",
                "The Tumblr posts also signal favorites in bold, which the importer preserves as a first-class boolean field on each track.",
                "That structure makes it easy to surface recurring artists, covers, remixes, and other taste signals without rewriting the original posts.",
            ],
            "relatedMixSlugs": ["mix-035-thirtyfifth", "mix-036-thirtysixth"],
            "tags": ["editorial", "taste", "seed-data"],
        },
    )

    monkeypatch.setattr(mmm_common, "DRAFTS_DIR", drafts)
    monkeypatch.setattr(mmm_common, "SITE_PATH", site_path)
    monkeypatch.setattr(mmm_common, "TASTE_PROFILE_PATH", taste_path)
    monkeypatch.setattr(mmm_common, "ARCHIVE_INDEX_PATH", archive_path)
    monkeypatch.setattr(mmm_common, "PUBLISHED_DIR", published_dir)
    monkeypatch.setattr(mmm_common, "NOTES_DIR", notes_dir)

    monkeypatch.setattr(generate_weekly_draft, "DRAFTS_DIR", drafts)
    monkeypatch.setattr(generate_weekly_draft, "SITE_PATH", site_path)
    monkeypatch.setattr(generate_weekly_draft, "TASTE_PROFILE_PATH", taste_path)
    monkeypatch.setattr(generate_weekly_draft, "ARCHIVE_INDEX_PATH", archive_path)
    monkeypatch.setattr(generate_weekly_draft, "PUBLISHED_DIR", published_dir)
    monkeypatch.setattr(generate_weekly_draft, "NOTES_DIR", notes_dir)

    return tmp_path


def test_generate_weekly_draft_uses_archive_informed_local_heuristics(temp_repo):
    output = generate_weekly_draft.generate_weekly_draft(
        generate_weekly_draft.resolve_mix_date("2026-04-13"), mode="local"
    )

    assert output.exists()
    mix = mmm_common.load_json(output)

    assert mix["slug"] == "mmm-for-2026-04-13"
    assert mix["generation_mode"] == "local"
    assert mix["status"] == "draft"
    assert mix["tags"] == [
        "weekly-draft",
        "local-generated",
        "dream-pop",
        "cover-thread",
        "remix-thread",
    ]
    assert any(phrase in mix["summary"] for phrase in ["blog-era indie", "cover-version pivots", "dream pop"])
    assert "local Monday Music Mix data" in mix["notes"]
    assert "cover turn" in mix["notes"]
    assert "remix release" in mix["notes"]
    assert len(mix["tracks"]) == 5

    titles = [track["title"] for track in mix["tracks"]]
    assert any("cover" in title.lower() for title in titles)
    assert any("remix" in title.lower() for title in titles)
    assert "Dum Dum Girls" in mix["source_context"]["top_artists"]
    assert any(
        phrase in track["why_it_fits"]
        for track in mix["tracks"]
        for phrase in ["recurring archive artist", "bolded favorite moments", "note-aware"]
    )
    assert any("cover-heavy thread" in track["why_it_fits"] for track in mix["tracks"])
    assert any("remix turn" in track["why_it_fits"] or "remix cue" in track["why_it_fits"] for track in mix["tracks"])


def test_auto_mode_stays_local_even_with_hosted_key_present(temp_repo, monkeypatch):
    monkeypatch.setenv("MMM_OPENAI_API_KEY", "test-key")

    output = generate_weekly_draft.generate_weekly_draft(
        generate_weekly_draft.resolve_mix_date("2026-04-20"), mode="auto"
    )

    mix = mmm_common.load_json(output)
    assert mix["generation_mode"] == "local"
    assert "generation_fallback_reason" not in mix
    assert mix["source_context"]["published_mix_count"] == 3
    assert mix["source_context"]["note_count"] == 1
    assert "local-generated" in mix["tags"]
