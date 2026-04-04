from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from mmm_common import (
    ARCHIVE_INDEX_PATH,
    DRAFTS_DIR,
    SITE_PATH,
    TASTE_PROFILE_PATH,
    dump_json,
    load_json,
    slugify,
)

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



def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a weekly MMM draft")
    parser.add_argument("--date", dest="mix_date", help="ISO date for the mix, defaults to next Monday UTC")
    parser.add_argument("--mode", choices=["auto", "fallback"], default="auto")
    parser.add_argument("--force", action="store_true", help="Overwrite existing draft for the same slug")
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
    if requested == "fallback":
        return requested
    return "fallback"



def extract_genres(taste: dict[str, Any]) -> list[str]:
    if isinstance(taste.get("favorite_genres"), list):
        return [str(item) for item in taste["favorite_genres"]]
    if isinstance(taste.get("recurringDescriptors"), list):
        labels = [str(item.get("label")) for item in taste["recurringDescriptors"] if item.get("label")]
        if labels:
            return labels
    if isinstance(taste.get("eraHints"), list):
        labels = [str(item.get("label")) for item in taste["eraHints"] if item.get("label")]
        if labels:
            return labels
    return ["eclectic discovery"]



def extract_top_artists(taste: dict[str, Any]) -> list[str]:
    if isinstance(taste.get("recurring_artists"), list):
        return [str(item) for item in taste["recurring_artists"]]
    if isinstance(taste.get("topArtists"), list):
        names = [str(item.get("name")) for item in taste["topArtists"] if item.get("name")]
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



def generate_fallback_mix(mix_date: date, taste: dict[str, Any], site: dict[str, Any], archive: dict[str, Any]) -> dict[str, Any]:
    count = archive_count(archive)
    genres = extract_genres(taste)
    top_artists = extract_top_artists(taste)
    tone = taste.get("tone") or "warm and curious"
    start_index = count % len(FALLBACK_TRACKS)
    selected = [FALLBACK_TRACKS[(start_index + offset) % len(FALLBACK_TRACKS)] for offset in range(5)]

    title = f"MMM for {mix_date.isoformat()}"
    slug = slugify(title)
    summary = f"A {tone} set shaped by {genres[count % len(genres)]}."
    notes = (
        f"Generated in deterministic fallback mode using {site_title(site)} as context. "
        f"The sequencing nods to {' / '.join(top_artists[:3])}."
    )

    tracks = []
    for idx, (artist, track_title) in enumerate(selected, start=1):
        genre = genres[(count + idx - 1) % len(genres)]
        tracks.append(
            {
                "artist": artist,
                "title": track_title,
                "why_it_fits": f"Track {idx} reinforces the week's {genre} thread while keeping the pacing fluid.",
                "favorite": idx == 3,
            }
        )

    return {
        "slug": slug,
        "title": title,
        "date": mix_date.isoformat(),
        "status": "draft",
        "summary": summary,
        "notes": notes,
        "tags": ["weekly-draft", "local-generated"],
        "generation_mode": "fallback",
        "source_context": {
            "site_title": site_title(site),
            "archive_count": count,
            "taste_markers": genres[:3],
        },
        "tracks": tracks,
    }



def generate_weekly_draft(mix_date: date, mode: str = "auto", force: bool = False) -> Path:
    taste = load_json(TASTE_PROFILE_PATH)
    site = load_json(SITE_PATH)
    archive = load_json(ARCHIVE_INDEX_PATH)

    resolved_mode = choose_mode(mode)
    if resolved_mode != "fallback":
        raise ValueError(f"Unsupported generation mode: {resolved_mode}")

    mix = generate_fallback_mix(mix_date, taste, site, archive)

    output_path = DRAFTS_DIR / f"{mix['slug']}.json"
    if output_path.exists() and not force:
        raise FileExistsError(f"Draft already exists: {output_path}")

    dump_json(output_path, mix)
    return output_path



def main() -> int:
    args = parse_args()
    try:
        mix_date = resolve_mix_date(args.mix_date)
        output = generate_weekly_draft(mix_date, mode=args.mode, force=args.force)
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1

    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
