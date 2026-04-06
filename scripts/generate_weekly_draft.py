from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from mmm_common import (
    ARCHIVE_INDEX_PATH,
    DRAFTS_DIR,
    IMPORTED_MIXES_DIR,
    NOTES_DIR,
    PUBLISHED_DIR,
    SITE_PATH,
    TASTE_PROFILE_PATH,
    ValidationError,
    dump_json,
    load_canonical_archive_mix_records,
    load_json,
    load_mix_payloads,
    mix_sort_value,
    now_iso,
    slugify,
    validate_mix,
)
from openai_common import post_openai_json

FALLBACK_TRACKS = [
    ("Broadcast", "Tears in the Typing Pool"),
    ("Khruangbin", "August 10"),
    ("Stereolab", "Miss Modular"),
    ("Mild High Club", "Homage"),
    ("Boards of Canada", "Dayvan Cowboy"),
    ("Air", "La Femme d'Argent"),
    ("Men I Trust", "Show Me How"),
    ("BADBADNOTGOOD", "Time Moves Slow"),
]

SUMMARY_SIGNAL_RULES = [
    ("late-night catch-up energy", ("late", "last hour", "tuesday", "absence", "not dead")),
    ("some-new-some-old reimagining", ("reimagined", "new", "old")),
    ("overflow-without-apology editing", ("left out", "rejects edition")),
    ("new-week reset momentum", ("new week", "prod me", "birdy")),
]
NOTE_SIGNAL_RULES = [
    ("blog-era indie", ("blog-era indie", "indie")),
    ("dreamy pop", ("dreamy pop", "dream pop")),
    ("left-field electronic drift", ("left-field electronic", "electronic")),
    ("cover-version pivots", ("cover version", "cover-heavy", "cover")),
    ("favorite-track cues", ("favorite", "bold")),
    ("remix release valves", ("remix", "remix-friendly")),
]
GENERIC_DESCRIPTOR_PREFIXES = ("2010s",)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a weekly MMM draft")
    parser.add_argument("--date", dest="mix_date", help="ISO date for the mix, defaults to next Monday UTC")
    parser.add_argument("--mode", choices=["auto", "local", "ai", "fallback"], default="auto")
    parser.add_argument("--force", action="store_true", help="Overwrite existing draft for the same slug")
    parser.add_argument(
        "--plugin-command",
        help="Optional local command that can refine or replace the deterministic draft using JSON context.",
    )
    parser.add_argument(
        "--archive-limit",
        type=int,
        default=36,
        help="How many canonical archive mixes to include in AI context. Defaults to 36.",
    )
    return parser.parse_args()


def next_monday(today: date | None = None) -> date:
    today = today or datetime.now(timezone.utc).date()
    days_ahead = (7 - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return today + timedelta(days=days_ahead)


def resolve_mix_date(explicit: str | None) -> date:
    return date.fromisoformat(explicit) if explicit else next_monday()


def choose_mode(requested: str) -> str:
    if requested in {"auto", "local", "fallback"}:
        return "local"
    if requested == "ai":
        return "ai"
    raise ValueError(f"Unsupported generation mode: {requested}")


def extract_genres(taste: dict[str, Any]) -> list[str]:
    if isinstance(taste.get("favorite_genres"), list):
        return [str(item).strip() for item in taste["favorite_genres"] if str(item).strip()]
    if isinstance(taste.get("recurringDescriptors"), list):
        labels = [str(item.get("label")).strip() for item in taste["recurringDescriptors"] if item.get("label")]
        if labels:
            return labels
    if isinstance(taste.get("eraHints"), list):
        labels = [str(item.get("label")).strip() for item in taste["eraHints"] if item.get("label")]
        if labels:
            return labels
    return ["eclectic discovery"]


def extract_top_artists(taste: dict[str, Any]) -> list[str]:
    if isinstance(taste.get("recurring_artists"), list):
        return [str(item).strip() for item in taste["recurring_artists"] if str(item).strip()]
    if isinstance(taste.get("topArtists"), list):
        names = [str(item.get("name")).strip() for item in taste["topArtists"] if item.get("name")]
        if names:
            return names
    return [artist for artist, _ in FALLBACK_TRACKS[:4]]


def archive_count(archive: dict[str, Any]) -> int:
    if isinstance(archive.get("mixes"), list):
        return len(archive["mixes"])
    if isinstance(archive.get("items"), list):
        return len(archive["items"])
    return 0


def site_title(site: dict[str, Any]) -> str:
    return str(site.get("site_title") or site.get("name") or "MMM")


def stable_score(value: str) -> int:
    return sum((index + 1) * ord(char) for index, char in enumerate(value))


def dedupe_preserving_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def track_display_text(track: dict[str, Any]) -> str:
    artist = str(track.get("artist") or "").strip()
    title = str(track.get("title") or "").strip()
    return str(track.get("displayText") or f"{artist} - {title}").strip()


def is_cover_track(track: dict[str, Any]) -> bool:
    return "cover" in str(track.get("title") or "").lower()


def is_remix_track(track: dict[str, Any]) -> bool:
    title = str(track.get("title") or "").lower()
    return "remix" in title or "edit" in title


def build_summary_tone(archive: dict[str, Any]) -> list[str]:
    summaries: list[str] = []
    for item in archive.get("mixes", []) or archive.get("items", []) or []:
        summary = str(item.get("summary") or "").strip().lower()
        if summary:
            summaries.append(summary)

    matches: list[tuple[int, int, str]] = []
    for label, keywords in SUMMARY_SIGNAL_RULES:
        count = sum(1 for summary in summaries if any(keyword in summary for keyword in keywords))
        if count:
            matches.append((-count, stable_score(label), label))
    if matches:
        return [label for _, _, label in sorted(matches)]
    return ["weekly reset energy"]


def build_note_signals(notes: list[dict[str, Any]]) -> list[str]:
    haystacks: list[str] = []
    for note in notes:
        haystacks.append(str(note.get("summary") or "").lower())
        for paragraph in note.get("body", []) if isinstance(note.get("body"), list) else []:
            haystacks.append(str(paragraph).lower())

    matches: list[tuple[int, int, str]] = []
    for label, keywords in NOTE_SIGNAL_RULES:
        count = sum(1 for haystack in haystacks if any(keyword in haystack for keyword in keywords))
        if count:
            matches.append((-count, stable_score(label), label))
    return [label for _, _, label in sorted(matches)]


def clean_descriptor(label: str) -> str:
    normalized = label.strip()
    for prefix in GENERIC_DESCRIPTOR_PREFIXES:
        if normalized.lower().startswith(prefix.lower() + " "):
            parts = normalized.split(" ", 1)
            if len(parts) == 2:
                return parts[1].strip()
    return normalized


def build_track_pool(published_mixes: list[dict[str, Any]], top_artist_names: list[str]) -> list[dict[str, Any]]:
    artist_occurrences: dict[str, int] = {}
    for mix in published_mixes:
        for track in mix.get("tracks", []):
            artist = str(track.get("artist") or "").strip()
            if artist:
                artist_occurrences[artist] = artist_occurrences.get(artist, 0) + 1

    top_artist_set = set(top_artist_names)
    pool: list[dict[str, Any]] = []
    for mix in published_mixes:
        stats = mix.get("stats") if isinstance(mix.get("stats"), dict) else {}
        for track in mix.get("tracks", []):
            artist = str(track.get("artist") or "").strip()
            title = str(track.get("title") or "").strip()
            if not artist or not title:
                continue
            display = track_display_text(track)
            pool.append(
                {
                    "artist": artist,
                    "title": title,
                    "display": display,
                    "position": int(track.get("position") or 0),
                    "is_favorite": bool(track.get("isFavorite")),
                    "is_cover": is_cover_track(track) or display in set(stats.get("coverTracks", [])),
                    "is_remix": is_remix_track(track) or display in set(stats.get("remixTracks", [])),
                    "artist_occurrences": artist_occurrences.get(artist, 1),
                    "top_artist": artist in top_artist_set,
                    "mix_slug": str(mix.get("slug") or ""),
                    "mix_title": str(mix.get("title") or ""),
                    "mix_summary": str(mix.get("summary") or "").strip(),
                }
            )
    return sorted(pool, key=lambda item: (item["mix_slug"], item["position"], item["display"]))


def choose_track_candidate(
    candidates: list[dict[str, Any]],
    selected_artists: set[str],
    slot_name: str,
    mix_date: date,
    predicate: Callable[[dict[str, Any]], bool],
    preferred: Callable[[dict[str, Any]], int],
) -> dict[str, Any] | None:
    viable = [candidate for candidate in candidates if predicate(candidate) and candidate["artist"] not in selected_artists]
    if not viable:
        viable = [candidate for candidate in candidates if candidate["artist"] not in selected_artists]
    if not viable:
        return None

    seed = f"{mix_date.isoformat()}::{slot_name}"
    return sorted(
        viable,
        key=lambda candidate: (
            -preferred(candidate),
            -candidate["artist_occurrences"],
            candidate["position"],
            stable_score(candidate["display"] + seed),
        ),
    )[0]


def infer_track_slots(
    candidates: list[dict[str, Any]],
    mix_date: date,
    wants_cover: bool,
    wants_remix: bool,
) -> list[tuple[str, dict[str, Any]]]:
    selected: list[tuple[str, dict[str, Any]]] = []
    selected_artists: set[str] = set()

    slot_plan: list[tuple[str, Callable[[dict[str, Any]], bool], Callable[[dict[str, Any]], int]]] = [
        (
            "opener",
            lambda candidate: candidate["position"] <= 4 and not candidate["is_cover"] and not candidate["is_remix"],
            lambda candidate: (5 if candidate["top_artist"] else 0) + candidate["artist_occurrences"] + (2 if candidate["is_favorite"] else 0),
        ),
        (
            "builder",
            lambda candidate: candidate["position"] <= 8 and not candidate["is_remix"],
            lambda candidate: candidate["artist_occurrences"] + (4 if candidate["is_favorite"] else 0),
        ),
    ]
    if wants_cover:
        slot_plan.append(
            (
                "cover-pivot",
                lambda candidate: candidate["is_cover"],
                lambda candidate: 8 + candidate["artist_occurrences"] + (4 if candidate["is_favorite"] else 0),
            )
        )
    slot_plan.append(
        (
            "favorite-anchor",
            lambda candidate: candidate["is_favorite"],
            lambda candidate: 8 + candidate["artist_occurrences"] + (3 if candidate["top_artist"] else 0),
        )
    )
    if wants_remix:
        slot_plan.append(
            (
                "remix-release",
                lambda candidate: candidate["is_remix"],
                lambda candidate: 9 + candidate["artist_occurrences"] + (3 if candidate["is_favorite"] else 0),
            )
        )
    else:
        slot_plan.append(
            (
                "closer",
                lambda candidate: candidate["position"] >= 10,
                lambda candidate: candidate["artist_occurrences"] + (4 if candidate["is_favorite"] else 0),
            )
        )

    for slot_name, predicate, preferred in slot_plan:
        chosen = choose_track_candidate(candidates, selected_artists, slot_name, mix_date, predicate, preferred)
        if chosen is None:
            continue
        selected.append((slot_name, chosen))
        selected_artists.add(chosen["artist"])

    while len(selected) < 5:
        slot_name = f"support-{len(selected) + 1}"
        chosen = choose_track_candidate(
            candidates,
            selected_artists,
            slot_name,
            mix_date,
            lambda candidate: True,
            lambda candidate: candidate["artist_occurrences"] + (4 if candidate["is_favorite"] else 0),
        )
        if chosen is None:
            break
        selected.append((slot_name, chosen))
        selected_artists.add(chosen["artist"])

    return selected[:5]


def build_track_reason(
    slot_name: str,
    track: dict[str, Any],
    summary_tone: list[str],
    note_signals: list[str],
) -> str:
    reasons: list[str] = []
    if slot_name == "opener":
        reasons.append(f"Opens with the archive's {summary_tone[0]} instead of starting from a blank template.")
    elif slot_name == "builder":
        reasons.append("Keeps the early run moving the way the archive usually stacks discovery tracks.")
    elif slot_name == "cover-pivot":
        reasons.append("Keeps the cover-heavy thread active because that recurrence shows up clearly in the local archive.")
    elif slot_name == "favorite-anchor":
        reasons.append("Reads like one of the bolded favorite moments the archive notes keep calling out.")
    elif slot_name == "remix-release":
        reasons.append("Lets the sequence exhale with the same late remix turn that already appears in local MMM history.")
    else:
        reasons.append("Supports the sequence without breaking the archive's pacing habits.")

    if track["artist_occurrences"] > 1:
        reasons.append(f"{track['artist']} is already a recurring archive artist.")
    if track["is_cover"] and "cover-heavy" not in reasons[0]:
        reasons.append("It also reinforces the archive's cover-version habit.")
    if track["is_remix"] and "remix" not in reasons[0]:
        reasons.append("It adds a remix cue instead of flattening the draft into one texture.")
    if note_signals:
        reasons.append(f"It fits the note-aware {note_signals[0]} lane already present in local data.")
    return " ".join(reasons[:3])


def build_local_tags(primary_descriptor: str, selected_tracks: list[dict[str, Any]], note_signals: list[str]) -> list[str]:
    tags = ["weekly-draft", "local-generated"]
    if primary_descriptor:
        tags.append(slugify(primary_descriptor))
    if any(track["is_cover"] for track in selected_tracks):
        tags.append("cover-thread")
    if any(track["is_remix"] for track in selected_tracks):
        tags.append("remix-thread")
    elif note_signals and any("favorite" in signal for signal in note_signals):
        tags.append("favorite-signals")
    return dedupe_preserving_order(tags[:5])


def build_local_summary(
    tone: str,
    primary_descriptor: str,
    summary_tone: list[str],
    note_signals: list[str],
    selected_tracks: list[dict[str, Any]],
) -> str:
    descriptor = clean_descriptor(primary_descriptor) if primary_descriptor else "local archive curation"
    clauses = [descriptor, summary_tone[0]]
    if note_signals:
        clauses.append(note_signals[0])

    ending = "a favorite-led late run"
    if any(track["is_cover"] for track in selected_tracks) and any(track["is_remix"] for track in selected_tracks):
        ending = "a cover pivot and a late remix release"
    elif any(track["is_cover"] for track in selected_tracks):
        ending = "a cover pivot that keeps the sequence from settling"
    elif any(track["is_remix"] for track in selected_tracks):
        ending = "a late remix release"

    return f"A {tone} draft shaped by {', '.join(clauses[:-1])}, and {clauses[-1]}, with {ending}."


def build_local_notes(
    site: dict[str, Any],
    archive: dict[str, Any],
    notes: list[dict[str, Any]],
    summary_tone: list[str],
    note_signals: list[str],
    top_artists: list[str],
    selected_tracks: list[dict[str, Any]],
) -> str:
    cover_count = sum(1 for track in selected_tracks if track["is_cover"])
    remix_count = sum(1 for track in selected_tracks if track["is_remix"])
    favorite_count = sum(1 for track in selected_tracks if track["is_favorite"])
    signal_bits = []
    if note_signals:
        signal_bits.append(f"note cues around {', '.join(note_signals[:2])}")
    if top_artists:
        signal_bits.append(f"recurring artists like {', '.join(top_artists[:3])}")
    signal_bits.append(f"{cover_count} cover turn{'s' if cover_count != 1 else ''}")
    signal_bits.append(f"{remix_count} remix release{'s' if remix_count != 1 else ''}")
    signal_bits.append(f"{favorite_count} bolded-favorite style peaks")

    return (
        f"Generated entirely from local {site_title(site)} data: {archive_count(archive)} archived mixes and {len(notes)} notes informed this pass. "
        f"It leans into {summary_tone[0]} while keeping {', '.join(signal_bits)} visible in the sequence."
    )


AI_DRAFT_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "mmm_weekly_draft",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["summary", "notes", "tags", "tracks"],
            "properties": {
                "summary": {"type": "string"},
                "notes": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "tracks": {
                    "type": "array",
                    "minItems": 5,
                    "maxItems": 5,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["artist", "title", "why_it_fits", "favorite", "sourceMixSlug"],
                        "properties": {
                            "artist": {"type": "string"},
                            "title": {"type": "string"},
                            "why_it_fits": {"type": "string"},
                            "favorite": {"type": "boolean"},
                            "sourceMixSlug": {"type": "string"},
                        },
                    },
                },
            },
        },
    },
}


def build_ai_archive_context(archive_records: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    selected = archive_records[: max(limit, 0)]
    context: list[dict[str, Any]] = []
    for record in selected:
        mix = record["mix"]
        context.append(
            {
                "slug": mix.get("slug"),
                "title": mix.get("title"),
                "date": mix.get("publishedAt") or mix.get("date"),
                "summary": mix.get("summary"),
                "sourceName": record["sourceName"],
                "sourcePath": record["relativePath"],
                "tracks": [
                    {
                        "position": track.get("position"),
                        "artist": track.get("artist"),
                        "title": track.get("title"),
                        "displayText": track_display_text(track),
                        "isFavorite": bool(track.get("isFavorite") or track.get("favorite") or track.get("is_favorite")),
                    }
                    for track in mix.get("tracks", [])
                    if isinstance(track, dict)
                ],
            }
        )
    return context


def build_ai_generation_context(
    mix_date: date,
    site: dict[str, Any],
    taste: dict[str, Any],
    archive: dict[str, Any],
    archive_records: list[dict[str, Any]],
    notes: list[dict[str, Any]],
    archive_limit: int,
) -> dict[str, Any]:
    archive_context = build_ai_archive_context(archive_records, archive_limit)
    return {
        "mix_date": mix_date.isoformat(),
        "site": {
            "title": site_title(site),
        },
        "taste_profile": taste,
        "archive_summary": {
            "archive_index_count": archive_count(archive),
            "canonical_archive_mix_count": len(archive_records),
            "included_mix_count": len(archive_context),
            "mixes_are_sorted": "newest-first",
        },
        "notes": notes,
        "archive_mixes": archive_context,
        "instructions": {
            "track_source_rule": "Choose exactly 5 tracks and only use songs that appear in archive_mixes.",
            "why_it_fits_rule": "Ground each why_it_fits explanation in the provided archive, taste profile, and notes only.",
            "tone_rule": "Write like an honest MMM draft, not marketing copy.",
        },
    }


def build_ai_messages(context: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You are drafting the next Monday Music Mix using only the provided local archive context. "
                "Return strict JSON matching the schema. Do not invent songs outside the archive. "
                "Favor cohesion, recurrence, and honest reasoning over novelty theater."
            ),
        },
        {
            "role": "user",
            "content": (
                "Use the latest available archive mixes, taste profile, and notes to draft one new MMM entry. "
                "Pick exactly 5 tracks from the provided archive tracklists. "
                "Keep the draft compatible with the existing editorial JSON shape.\n\n"
                f"{json.dumps(context, indent=2, ensure_ascii=False)}"
            ),
        },
    ]


def extract_chat_completion_text(response_payload: dict[str, Any]) -> str:
    choices = response_payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValidationError("OpenAI draft response did not include choices")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        raise ValidationError("OpenAI draft response did not include a message")
    refusal = str(message.get("refusal") or "").strip()
    if refusal:
        raise RuntimeError(f"OpenAI draft generation refused the request: {refusal}")
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") in {"output_text", "text"}:
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        if parts:
            return "".join(parts)
    raise ValidationError("OpenAI draft response did not include JSON text content")


def normalize_ai_draft_payload(
    payload: dict[str, Any],
    mix_date: date,
    context: dict[str, Any],
    model: str,
) -> dict[str, Any]:
    title = f"MMM for {mix_date.isoformat()}"
    slug = slugify(title)
    archive_lookup = {
        str(item.get("slug") or "").strip(): item
        for item in context.get("archive_mixes", [])
        if str(item.get("slug") or "").strip()
    }

    tags = dedupe_preserving_order(
        [
            "weekly-draft",
            "ai-generated",
            *[str(tag).strip() for tag in payload.get("tags", []) if str(tag).strip()],
        ]
    )[:6]

    normalized_tracks: list[dict[str, Any]] = []
    for track in payload.get("tracks", []):
        source_mix_slug = str(track.get("sourceMixSlug") or "").strip()
        if source_mix_slug not in archive_lookup:
            raise ValidationError(f"AI track references unknown sourceMixSlug '{source_mix_slug}'")
        artist = str(track.get("artist") or "").strip()
        title_value = str(track.get("title") or "").strip()
        matches_archive = any(
            artist == str(source_track.get("artist") or "").strip()
            and title_value == str(source_track.get("title") or "").strip()
            for source_track in archive_lookup[source_mix_slug].get("tracks", [])
        )
        if not matches_archive:
            raise ValidationError(
                f"AI track '{artist} - {title_value}' does not exist in archive mix '{source_mix_slug}'"
            )
        normalized_tracks.append(
            {
                "artist": artist,
                "title": title_value,
                "why_it_fits": str(track.get("why_it_fits") or "").strip(),
                "favorite": bool(track.get("favorite")),
                "sourceMixSlug": source_mix_slug,
            }
        )

    candidate = {
        "slug": slug,
        "title": title,
        "date": mix_date.isoformat(),
        "status": "draft",
        "summary": str(payload.get("summary") or "").strip(),
        "notes": str(payload.get("notes") or "").strip(),
        "tags": tags,
        "generation_mode": "ai",
        "generatedAt": now_iso(),
        "ai_source": {
            "provider": "openai",
            "model": model,
            "archiveMixCount": len(context.get("archive_mixes", [])),
        },
        "source_context": {
            "site_title": context.get("site", {}).get("title"),
            "archive_count": context.get("archive_summary", {}).get("canonical_archive_mix_count"),
            "note_count": len(context.get("notes", [])),
            "archive_window": "canonical-archive-deduped",
            "archive_mix_slugs": [item.get("slug") for item in context.get("archive_mixes", [])[:10]],
        },
        "tracks": normalized_tracks,
    }
    result = validate_mix(candidate)
    if result.flavor != "editorial":
        raise ValidationError("AI draft payload must validate as editorial content")
    return result.mix


def request_ai_draft(
    mix_date: date,
    site: dict[str, Any],
    taste: dict[str, Any],
    archive: dict[str, Any],
    archive_records: list[dict[str, Any]],
    notes: list[dict[str, Any]],
    archive_limit: int,
) -> dict[str, Any]:
    model = os.environ.get("MMM_OPENAI_DRAFT_MODEL", "gpt-5-mini").strip() or "gpt-5-mini"
    context = build_ai_generation_context(
        mix_date,
        site,
        taste,
        archive,
        archive_records,
        notes,
        archive_limit,
    )
    response_payload = post_openai_json(
        "/chat/completions",
        {
            "model": model,
            "messages": build_ai_messages(context),
            "response_format": AI_DRAFT_RESPONSE_FORMAT,
        },
    )
    raw_content = extract_chat_completion_text(response_payload)
    try:
        parsed = json.loads(raw_content)
    except json.JSONDecodeError as exc:
        raise ValidationError("AI draft response was not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise ValidationError("AI draft response must be a JSON object")
    return normalize_ai_draft_payload(parsed, mix_date, context, model)


def generate_archive_informed_mix(
    mix_date: date,
    taste: dict[str, Any],
    site: dict[str, Any],
    archive: dict[str, Any],
    published_mixes: list[dict[str, Any]],
    notes: list[dict[str, Any]],
) -> dict[str, Any]:
    top_artists = extract_top_artists(taste)
    primary_descriptor = extract_genres(taste)[0]
    tone = str(taste.get("tone") or "warm and curious").strip()
    summary_tone = build_summary_tone(archive)
    note_signals = build_note_signals(notes)
    track_pool = build_track_pool(published_mixes, top_artists)

    title = f"MMM for {mix_date.isoformat()}"
    slug = slugify(title)

    if not track_pool:
        count = archive_count(archive)
        selected = [FALLBACK_TRACKS[(count + offset) % len(FALLBACK_TRACKS)] for offset in range(5)]
        tracks = []
        for index, (artist, track_title) in enumerate(selected, start=1):
            tracks.append(
                {
                    "artist": artist,
                    "title": track_title,
                    "why_it_fits": "Falls back to the local emergency list because no published track archive is available yet.",
                    "favorite": index in {3, 5},
                }
            )
        return {
            "slug": slug,
            "title": title,
            "date": mix_date.isoformat(),
            "status": "draft",
            "summary": f"A {tone} draft preserved in local-only mode while the archive track pool is still empty.",
            "notes": "Generated without hosted AI and without published track history; once local mixes exist this will become archive-informed automatically.",
            "tags": ["weekly-draft", "local-generated", "archive-bootstrap"],
            "generation_mode": "local",
            "source_context": {
                "site_title": site_title(site),
                "archive_count": count,
                "published_mix_count": 0,
                "note_count": len(notes),
                "primary_descriptor": primary_descriptor,
            },
            "tracks": tracks,
        }

    cover_occurrences = sum(1 for track in track_pool if track["is_cover"])
    remix_occurrences = sum(1 for track in track_pool if track["is_remix"])
    wants_cover = cover_occurrences > 0
    wants_remix = remix_occurrences > 0

    selected_slots = infer_track_slots(track_pool, mix_date, wants_cover=wants_cover, wants_remix=wants_remix)
    selected_tracks: list[dict[str, Any]] = []
    for slot_name, candidate in selected_slots:
        selected_tracks.append(
            {
                "artist": candidate["artist"],
                "title": candidate["title"],
                "why_it_fits": build_track_reason(slot_name, candidate, summary_tone, note_signals),
                "favorite": slot_name in {"favorite-anchor", "remix-release"} or candidate["is_favorite"],
                "is_favorite": slot_name in {"favorite-anchor", "remix-release"} or candidate["is_favorite"],
                "is_cover": candidate["is_cover"],
                "is_remix": candidate["is_remix"],
            }
        )

    editorial_tracks = [
        {
            "artist": track["artist"],
            "title": track["title"],
            "why_it_fits": track["why_it_fits"],
            "favorite": track["favorite"],
        }
        for track in selected_tracks
    ]

    return {
        "slug": slug,
        "title": title,
        "date": mix_date.isoformat(),
        "status": "draft",
        "summary": build_local_summary(tone, primary_descriptor, summary_tone, note_signals, selected_tracks),
        "notes": build_local_notes(site, archive, notes, summary_tone, note_signals, top_artists, selected_tracks),
        "tags": build_local_tags(primary_descriptor, selected_tracks, note_signals),
        "generation_mode": "local",
        "source_context": {
            "site_title": site_title(site),
            "archive_count": archive_count(archive),
            "published_mix_count": len(published_mixes),
            "note_count": len(notes),
            "primary_descriptor": primary_descriptor,
            "summary_tone": summary_tone[:2],
            "note_signals": note_signals[:3],
            "top_artists": top_artists[:5],
        },
        "tracks": editorial_tracks,
    }


def build_plugin_context(
    mix_date: date,
    mode: str,
    site: dict[str, Any],
    taste: dict[str, Any],
    archive: dict[str, Any],
    published_mixes: list[dict[str, Any]],
    notes: list[dict[str, Any]],
    baseline_mix: dict[str, Any],
) -> dict[str, Any]:
    return {
        "version": "1.0",
        "mix_date": mix_date.isoformat(),
        "requested_mode": mode,
        "site": {
            "title": site_title(site),
            "featured_mix_slug": site.get("featuredMixSlug") or site.get("featured_mix_slug"),
        },
        "taste_profile": {
            "tone": taste.get("tone"),
            "favorite_genres": extract_genres(taste),
            "top_artists": extract_top_artists(taste),
        },
        "archive_summary": {
            "mix_count": archive_count(archive),
            "summary_tone": build_summary_tone(archive),
            "published_mix_count": len(published_mixes),
            "note_count": len(notes),
            "recent_mix_slugs": [str(mix.get("slug") or "") for mix in published_mixes[:5]],
            "note_signals": build_note_signals(notes)[:5],
        },
        "published_mixes": published_mixes,
        "notes": notes,
        "baseline_draft": baseline_mix,
        "instructions": {
            "local_only": True,
            "hosted_ai_not_required": True,
            "expected_output": "Return one editorial draft JSON object compatible with MMM validate_mix().",
            "stdin_supported": True,
        },
    }


def resolve_plugin_command(explicit_command: str | None) -> str | None:
    if explicit_command and explicit_command.strip():
        return explicit_command.strip()
    env_value = os.environ.get("MMM_DRAFT_PLUGIN_COMMAND", "").strip()
    return env_value or None


def _load_plugin_output(stdout: str, output_path: Path) -> dict[str, Any]:
    if output_path.exists():
        payload = load_json(output_path)
        if not isinstance(payload, dict):
            raise ValidationError("plugin output file must contain a JSON object")
        return payload

    if not stdout.strip():
        raise ValidationError("plugin produced no JSON output")
    payload = json.loads(stdout)
    if not isinstance(payload, dict):
        raise ValidationError("plugin stdout must be a JSON object")
    return payload


def run_plugin_command(
    plugin_command: str,
    context: dict[str, Any],
    repo_root: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    with tempfile.TemporaryDirectory(prefix="mmm-draft-plugin-") as temp_dir:
        temp_root = Path(temp_dir)
        context_path = temp_root / "draft-context.json"
        output_path = temp_root / "draft-output.json"
        dump_json(context_path, context)

        formatted_command = plugin_command.format(
            context_path=str(context_path),
            output_path=str(output_path),
            repo_root=str(repo_root),
        )
        command_parts = shlex.split(formatted_command)
        if not command_parts:
            raise ValueError("plugin command resolved to an empty command")

        completed = subprocess.run(
            command_parts,
            cwd=repo_root,
            input=json.dumps(context, indent=2),
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            stderr = completed.stderr.strip()
            stdout = completed.stdout.strip()
            detail = stderr or stdout or f"exit code {completed.returncode}"
            raise RuntimeError(f"plugin command failed: {detail}")

        payload = _load_plugin_output(completed.stdout, output_path)
        result = validate_mix(payload)
        if result.flavor != "editorial":
            raise ValidationError("plugin command must return an editorial draft payload")

        metadata = {
            "command": formatted_command,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
        }
        return result.mix, metadata


def apply_plugin_hook(
    mix_date: date,
    mode: str,
    site: dict[str, Any],
    taste: dict[str, Any],
    archive: dict[str, Any],
    published_mixes: list[dict[str, Any]],
    notes: list[dict[str, Any]],
    baseline_mix: dict[str, Any],
    plugin_command: str | None,
) -> dict[str, Any]:
    resolved_command = resolve_plugin_command(plugin_command)
    if not resolved_command:
        return baseline_mix

    context = build_plugin_context(
        mix_date,
        mode,
        site,
        taste,
        archive,
        published_mixes,
        notes,
        baseline_mix,
    )
    plugin_mix, plugin_metadata = run_plugin_command(resolved_command, context, Path(__file__).resolve().parents[1])

    plugin_source = dict(plugin_mix.get("plugin_source") or {})
    plugin_source.update(
        {
            "type": "local-command",
            "command": plugin_metadata["command"],
        }
    )

    plugin_mix = dict(plugin_mix)
    plugin_mix["generation_mode"] = "local-plugin"
    plugin_mix["plugin_source"] = plugin_source

    source_context = dict(plugin_mix.get("source_context") or {})
    if "baseline_generation_mode" not in source_context:
        source_context["baseline_generation_mode"] = baseline_mix.get("generation_mode", "local")
    source_context["plugin_enabled"] = True
    plugin_mix["source_context"] = source_context
    return plugin_mix


def generate_weekly_draft(
    mix_date: date,
    mode: str = "auto",
    force: bool = False,
    plugin_command: str | None = None,
    archive_limit: int = 36,
) -> Path:
    taste = load_json(TASTE_PROFILE_PATH)
    site = load_json(SITE_PATH)
    archive = load_json(ARCHIVE_INDEX_PATH)
    published_mixes = sorted(load_mix_payloads(PUBLISHED_DIR), key=mix_sort_value, reverse=True)
    notes = load_mix_payloads(NOTES_DIR)

    resolved_mode = choose_mode(mode)
    if resolved_mode == "local":
        baseline_mix = generate_archive_informed_mix(mix_date, taste, site, archive, published_mixes, notes)
        mix = apply_plugin_hook(
            mix_date,
            resolved_mode,
            site,
            taste,
            archive,
            published_mixes,
            notes,
            baseline_mix,
            plugin_command,
        )
    elif resolved_mode == "ai":
        archive_records = load_canonical_archive_mix_records(
            published_dir=PUBLISHED_DIR,
            imported_dir=IMPORTED_MIXES_DIR,
        )
        mix = request_ai_draft(
            mix_date,
            site,
            taste,
            archive,
            archive_records,
            notes,
            archive_limit,
        )
    else:
        raise ValueError(f"Unsupported generation mode: {resolved_mode}")

    output_path = DRAFTS_DIR / f"{mix['slug']}.json"
    if output_path.exists() and not force:
        raise FileExistsError(f"Draft already exists: {output_path}")

    dump_json(output_path, mix)
    return output_path


def main() -> int:
    args = parse_args()
    try:
        mix_date = resolve_mix_date(args.mix_date)
        output = generate_weekly_draft(
            mix_date,
            mode=args.mode,
            force=args.force,
            plugin_command=args.plugin_command,
            archive_limit=args.archive_limit,
        )
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1

    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
