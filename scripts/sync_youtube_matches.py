#!/usr/bin/env python3
"""Search YouTube per track and persist explicit match state for review."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib.parse import quote

from mmm_common import (
    IMPORTED_MIXES_DIR,
    ROOT,
    ValidationError,
    YOUTUBE_DIR,
    dump_json,
    ensure_kebab_case_slug,
    load_canonical_archive_mix_records,
    load_json,
    now_iso,
)

SCHEMA_VERSION = "1.0"
SEARCH_LIMIT = 5
AUTO_ACCEPT_SCORE = 0.80
NEGATIVE_VERSION_TERMS = {
    "live": ("live-version-penalty", 0.22),
    "remix": ("unexpected-remix-penalty", 0.12),
    "edit": ("unexpected-edit-penalty", 0.07),
    "acoustic": ("unexpected-acoustic-penalty", 0.08),
    "session": ("unexpected-session-penalty", 0.08),
    "karaoke": ("karaoke-penalty", 0.18),
    "instrumental": ("unexpected-instrumental-penalty", 0.08),
    "cover": ("unexpected-cover-penalty", 0.14),
    "lyrics": ("lyric-video-penalty", 0.08),
    "video": ("music-video-penalty", 0.10),
    "visualizer": ("visualizer-penalty", 0.05),
}
POSITIVE_AUDIO_TERMS = {
    "official audio": ("official-audio-preferred", 0.16),
    "audio only": ("audio-only-preferred", 0.12),
    "audio": ("audio-tag-preferred", 0.06),
}
EDITORIAL_TAIL_MARKERS = (
    "must listen",
    "this isn't",
    "this isn’t",
    "not the album version",
)
EMOJI_OR_ICON_PATTERN = re.compile(r"[\U0001F300-\U0001FAFF\u2600-\u27BF\ufe0f]")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Persist YouTube per-track match candidates for MMM mixes.")
    parser.add_argument("mixes", nargs="*", help="Canonical archive mix slugs to scan. Defaults to the full deduped archive.")
    parser.add_argument(
        "--accept-low-confidence",
        action="store_true",
        help="Auto-select each track's top candidate even below the normal score threshold, and skip duplicate holdbacks so every mix gets a complete starter queue for operator review.",
    )
    return parser.parse_args()


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", str(value or "").lower())).strip()


def tokenize(value: str) -> set[str]:
    return {part for part in normalize_text(value).split(" ") if part}


def overlaps_needed(track_text: str, candidate_text: str) -> float:
    expected = tokenize(track_text)
    if not expected:
        return 0.0
    present = expected.intersection(tokenize(candidate_text))
    return len(present) / len(expected)


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(a=normalize_text(a), b=normalize_text(b)).ratio()


def contains_phrase(text: str, phrase: str) -> bool:
    normalized_phrase = normalize_text(phrase)
    if not normalized_phrase:
        return False
    return normalized_phrase in normalize_text(text)


def strip_emoji_or_icon_symbols(value: str) -> str:
    without_icons = EMOJI_OR_ICON_PATTERN.sub("", str(value or ""))
    return re.sub(r"\s+", " ", without_icons).strip()


def strip_editorial_tail(value: str) -> str:
    raw = re.sub(r"\s+", " ", str(value or "")).strip()
    if not raw:
        return ""
    lowered = raw.lower()
    cut = len(raw)
    for marker in EDITORIAL_TAIL_MARKERS:
        index = lowered.find(marker)
        if index >= 0:
            cut = min(cut, index)
    cleaned = raw[:cut].strip(" -–—")
    return cleaned or raw


def build_track_queries(track: dict[str, Any]) -> list[str]:
    artist = str(track.get("artist") or "").strip()
    title = str(track.get("title") or "").strip()
    display = str(track.get("displayText") or "").strip()

    queries: list[str] = []

    def add(query: str) -> None:
        compact = re.sub(r"\s+", " ", str(query or "")).strip()
        if not compact:
            return
        if any(normalize_text(compact) == normalize_text(existing) for existing in queries):
            return
        queries.append(compact)

    add(" ".join(part for part in [artist, title] if part))
    add(display)
    cleaned_title = strip_editorial_tail(title)
    add(" ".join(part for part in [artist, cleaned_title] if part))
    add(strip_editorial_tail(display))

    return queries


@dataclass
class ScoredCandidate:
    video_id: str
    title: str
    url: str
    channel: str
    duration_seconds: float | None
    score: float
    signals: list[str]


def score_candidate(track: dict[str, Any], entry: dict[str, Any]) -> ScoredCandidate:
    artist = str(track.get("artist") or "").strip()
    title = str(track.get("title") or "").strip()
    display = str(track.get("displayText") or f"{artist} - {title}").strip()
    candidate_title = strip_emoji_or_icon_symbols(entry.get("title") or "")
    channel = strip_emoji_or_icon_symbols(entry.get("channel") or entry.get("uploader") or "")
    normalized_candidate = normalize_text(candidate_title)
    normalized_display = normalize_text(display)
    normalized_artist = normalize_text(artist)
    normalized_title = normalize_text(title)
    signals: list[str] = []
    score = 0.0

    overlap = overlaps_needed(display, candidate_title)
    if overlap >= 0.95:
      score += 0.42
      signals.append("candidate-title-covers-track-tokens")
    elif overlap >= 0.80:
      score += 0.30
      signals.append("candidate-title-covers-most-track-tokens")

    display_similarity = similarity(display, candidate_title)
    title_similarity = similarity(title, candidate_title)
    score += display_similarity * 0.30
    score += title_similarity * 0.18
    if display_similarity >= 0.90:
        signals.append("display-text-near-exact-match")
    if title_similarity >= 0.92:
        signals.append("song-title-near-exact-match")

    if normalized_artist and normalized_artist in normalized_candidate:
        score += 0.10
        signals.append("artist-name-in-title")
    if normalized_title and normalized_title in normalized_candidate:
        score += 0.08
        signals.append("song-title-in-title")

    normalized_channel = normalize_text(channel)
    if normalized_artist and normalized_artist in normalized_channel:
        score += 0.08
        signals.append("artist-name-in-channel")
    if normalized_channel.endswith(" topic"):
        score += 0.12
        signals.append("topic-channel")
    if contains_phrase(channel, "official artist channel"):
        score += 0.06
        signals.append("official-artist-channel")
    if "official" in normalized_candidate:
        score += 0.04
        signals.append("official-upload")
    for phrase, (signal, weight) in POSITIVE_AUDIO_TERMS.items():
        if contains_phrase(candidate_title, phrase):
            score += weight
            signals.append(signal)

    expected_title = f" {normalized_title} "
    candidate_terms = f" {normalized_candidate} "
    for term, (signal, penalty) in NEGATIVE_VERSION_TERMS.items():
        if f" {term} " not in candidate_terms:
            continue
        if f" {term} " in expected_title:
            continue
        score -= penalty
        signals.append(signal)

    return ScoredCandidate(
        video_id=str(entry.get("id") or "").strip(),
        title=candidate_title,
        url=str(entry.get("url") or f"https://www.youtube.com/watch?v={entry.get('id')}").strip(),
        channel=channel,
        duration_seconds=entry.get("duration"),
        score=max(0.0, min(score, 0.999)),
        signals=signals,
    )


def search_youtube(query: str) -> list[dict[str, Any]]:
    command = [
        "yt-dlp",
        "--flat-playlist",
        "--dump-single-json",
        f"ytsearch{SEARCH_LIMIT}:{query}",
    ]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f"yt-dlp failed for {query}")
    payload = json.loads(result.stdout)
    return payload.get("entries") or []


def derive_resolution(scored: list[ScoredCandidate], *, accept_low_confidence: bool = False) -> dict[str, Any]:
    if not scored:
        return {
            "status": "no-candidate",
            "selectedVideoId": None,
            "confidenceScore": 0.0,
            "reason": "No YouTube candidates were returned for this track query.",
            "holdbackReason": "no-candidates",
        }

    top = scored[0]
    if top.score > AUTO_ACCEPT_SCORE:
        return {
            "status": "auto-resolved",
            "selectedVideoId": top.video_id,
            "confidenceScore": round(top.score, 3),
            "reason": "Top YouTube candidate cleared MMM's auto-select threshold and best matched the track with audio-first signals.",
            "holdbackReason": None,
        }

    if accept_low_confidence:
        return {
            "status": "auto-resolved",
            "selectedVideoId": top.video_id,
            "confidenceScore": round(top.score, 3),
            "reason": "Top candidate auto-selected in low-confidence mode to seed a complete queue for operator review.",
            "holdbackReason": "low-confidence-auto-selected",
        }

    return {
        "status": "pending-review",
        "selectedVideoId": None,
        "confidenceScore": round(top.score, 3),
        "reason": "The best YouTube hit stayed at or below MMM's auto-select threshold, so a human review is still required.",
        "holdbackReason": "low-confidence-top-candidate",
    }


def apply_duplicate_holdbacks(tracks: list[dict[str, Any]]) -> None:
    seen: dict[str, list[dict[str, Any]]] = {}
    for track in tracks:
        resolution = track.get("resolution") or {}
        selected = str(resolution.get("selectedVideoId") or "").strip()
        if not selected:
            continue
        seen.setdefault(selected, []).append(track)

    for video_id, entries in seen.items():
        if len(entries) < 2:
            continue
        for track in entries:
            track["resolution"] = {
                **track["resolution"],
                "status": "pending-review",
                "selectedVideoId": None,
                "reason": "The same YouTube video landed on multiple tracks, so this needs a human duplicate check.",
                "holdbackReason": "possible-duplicate-video",
                "confidenceScore": min(float(track["resolution"].get("confidenceScore") or 0.0), 0.89),
            }


def build_generated_embed(mix: dict[str, Any], track_states: list[dict[str, Any]]) -> dict[str, Any] | None:
    video_ids = [str(track["resolution"].get("selectedVideoId") or "").strip() for track in track_states]
    if not video_ids or any(not video_id for video_id in video_ids):
        return None

    first_video = video_ids[0]
    remainder = video_ids[1:]
    embed_url = f"https://www.youtube.com/embed/{first_video}"
    if remainder:
        embed_url = f"{embed_url}?playlist={quote(','.join(remainder), safe=',')}"

    return {
        "provider": "YouTube",
        "kind": "audio-first-queue",
        "title": f"Full mix queue for {mix.get('displayTitle') or mix.get('title') or mix.get('slug')}",
        "embedUrl": embed_url,
        "watchUrl": f"https://www.youtube.com/watch_videos?video_ids={quote(','.join(video_ids), safe=',')}",
        "videoIds": video_ids,
        "presentation": "audio-first",
        "embedSupported": False,
        "embedLimitation": "YouTube does not expose a true audio-only iframe, so MMM surfaces this as an audio-first queue link instead of pretending the embed is audio-only.",
        "generatedAt": now_iso(),
    }


def build_track_state(
    track: dict[str, Any],
    existing_track: dict[str, Any] | None = None,
    *,
    accept_low_confidence: bool = False,
) -> dict[str, Any]:
    queries = build_track_queries(track)
    query = queries[0] if queries else str(track.get("displayText") or "").strip()
    existing_resolution = existing_track.get("resolution") if isinstance(existing_track, dict) else {}
    if isinstance(existing_resolution, dict) and existing_resolution.get("status") == "manual-selected":
        candidates = existing_track.get("candidates") if isinstance(existing_track.get("candidates"), list) else []
        return {
            "position": track["position"],
            "displayText": track["displayText"],
            "query": query,
            "resolution": existing_resolution,
            "candidates": candidates,
        }

    candidates: list[dict[str, Any]] = []
    for candidate_query in queries or [query]:
        query = candidate_query
        candidates = search_youtube(query)
        if candidates:
            break

    scored = sorted((score_candidate(track, candidate) for candidate in candidates if candidate.get("id")), key=lambda item: item.score, reverse=True)
    return {
        "position": track["position"],
        "displayText": track["displayText"],
        "query": query,
        "resolution": derive_resolution(scored, accept_low_confidence=accept_low_confidence),
        "candidates": [
            {
                "rank": index,
                "videoId": candidate.video_id,
                "title": candidate.title,
                "url": candidate.url,
                "channel": candidate.channel,
                "durationSeconds": candidate.duration_seconds,
                "score": round(candidate.score, 3),
                "signals": candidate.signals,
            }
            for index, candidate in enumerate(scored, start=1)
        ],
    }


def state_path_for_slug(slug: str) -> Path:
    return YOUTUBE_DIR / f"{slug}.json"


def load_existing_state(slug: str) -> dict[str, Any]:
    state_path = state_path_for_slug(slug)
    if not state_path.exists():
        return {}
    payload = load_json(state_path)
    return payload if isinstance(payload, dict) else {}


def sync_mix(path: Path, *, accept_low_confidence: bool = False) -> dict[str, Any]:
    mix = load_json(path)
    slug = ensure_kebab_case_slug(mix.get("slug"), "mix slug")
    tracks = mix.get("tracks")
    if not isinstance(tracks, list) or not tracks:
        raise ValidationError(f"{slug} has no published tracklist to search")

    existing = load_existing_state(slug)
    existing_by_position = {
        int(track.get("position")): track
        for track in existing.get("tracks", [])
        if isinstance(track, dict) and str(track.get("position") or "").isdigit()
    }

    track_states = [
        build_track_state(
            track,
            existing_by_position.get(int(track["position"])),
            accept_low_confidence=accept_low_confidence,
        )
        for track in tracks
    ]
    if not accept_low_confidence:
        apply_duplicate_holdbacks(track_states)
    resolved_tracks = sum(1 for track in track_states if track["resolution"]["status"] in {"auto-resolved", "manual-selected"} and track["resolution"].get("selectedVideoId"))
    unresolved_tracks = len(track_states) - resolved_tracks
    generated_embed = build_generated_embed(mix, track_states) if unresolved_tracks == 0 else None
    payload = {
        "$schema": "../../schemas/youtube-match.schema.json",
        "schemaVersion": SCHEMA_VERSION,
        "mixSlug": slug,
        "updatedAt": now_iso(),
        "sourceMixPath": path.relative_to(ROOT).as_posix(),
        "tracks": track_states,
        "summary": {
            "totalTracks": len(track_states),
            "resolvedTracks": resolved_tracks,
            "unresolvedTracks": unresolved_tracks,
            "requiresReview": unresolved_tracks > 0,
            "generatedEmbed": generated_embed,
        },
    }
    dump_json(state_path_for_slug(slug), payload)
    return payload


def resolve_mix_paths(slugs: list[str]) -> list[Path]:
    archive_records = load_canonical_archive_mix_records(imported_dir=IMPORTED_MIXES_DIR)
    if not slugs:
        return [record["path"] for record in archive_records]
    requested = {ensure_kebab_case_slug(slug, "mix slug") for slug in slugs}
    matches = [record["path"] for record in archive_records if record["slug"] in requested]
    missing = sorted(requested - {path.stem for path in matches})
    if missing:
        raise FileNotFoundError(f"Could not find canonical archive mix JSON for: {', '.join(missing)}")
    return matches


def main() -> int:
    args = parse_args()
    YOUTUBE_DIR.mkdir(parents=True, exist_ok=True)
    results = [sync_mix(path, accept_low_confidence=args.accept_low_confidence) for path in resolve_mix_paths(args.mixes)]
    for result in results:
        summary = result["summary"]
        print(
            f"{result['mixSlug']}: {summary['resolvedTracks']}/{summary['totalTracks']} resolved"
            + (" (review needed)" if summary["requiresReview"] else " (embed ready)")
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
