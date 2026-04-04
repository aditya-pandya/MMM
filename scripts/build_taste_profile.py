#!/usr/bin/env python3
"""Derive a taste profile from structured MMM mix JSON files."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

DEFAULT_INPUT_DIRS = ["data/published", "data/imported/mixes"]

DESCRIPTOR_PATTERNS = {
    "cover-heavy curation": re.compile(r"\bcover\b", re.IGNORECASE),
    "remix-friendly sequencing": re.compile(r"\bremix\b", re.IGNORECASE),
    "indie / alternative focus": re.compile(r"\bindie\b|\balternative\b", re.IGNORECASE),
    "late-night melancholy": re.compile(r"\bmelancholy\b|\bdark\b|\bghost\b|\bnight\b", re.IGNORECASE),
    "electronic pop crossover": re.compile(r"\belectro\b|\bsynth\b|\bpop\b", re.IGNORECASE),
}


def iter_mix_files(paths: Iterable[str]) -> Iterable[Path]:
    for source in paths:
        source_path = Path(source)
        if source_path.is_file() and source_path.suffix == ".json":
            yield source_path
        elif source_path.is_dir():
            yield from sorted(source_path.glob("*.json"))


def load_mix(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build_taste_profile(paths: Iterable[str]) -> dict:
    artist_counts: Counter[str] = Counter()
    tag_counts: Counter[str] = Counter()
    descriptor_counts: Counter[str] = Counter()
    publication_years: Counter[str] = Counter()
    sample_mixes: list[dict] = []

    for mix_path in iter_mix_files(paths):
        mix = load_mix(mix_path)
        if mix.get("siteSection") != "mixes":
            continue

        sample_mixes.append(
            {
                "id": mix.get("id"),
                "title": mix.get("title"),
                "slug": mix.get("slug"),
                "publishedAt": mix.get("publishedAt"),
            }
        )

        for track in mix.get("tracks", []):
            artist = track.get("artist")
            if artist:
                artist_counts[artist] += 1
            track_blob = f"{track.get('title', '')} {track.get('displayText', '')}"
            for label, pattern in DESCRIPTOR_PATTERNS.items():
                if pattern.search(track_blob):
                    descriptor_counts[label] += 1

        for tag in mix.get("tags", []):
            if tag:
                tag_counts[str(tag)] += 1

        mix_blob = " ".join(
            [mix.get("displayTitle", ""), mix.get("summary", ""), *mix.get("intro", [])]
        )
        for label, pattern in DESCRIPTOR_PATTERNS.items():
            if pattern.search(mix_blob):
                descriptor_counts[label] += 1

        published_at = mix.get("publishedAt")
        if published_at:
            publication_years[published_at[:4]] += 1

    dominant_year = publication_years.most_common(1)[0][0] if publication_years else None
    era_hints = []
    if dominant_year:
        decade = dominant_year[:3] + "0s"
        era_hints.append(
            {
                "label": f"{decade} blog-era discovery",
                "evidence": f"Most imported mixes were published around {dominant_year}.",
                "confidence": round(publication_years[dominant_year] / max(sum(publication_years.values()), 1), 2),
            }
        )
    if descriptor_counts["cover-heavy curation"]:
        era_hints.append(
            {
                "label": "Cover-blog sensibility",
                "evidence": "Multiple tracks are tagged as covers across the imported mixes.",
                "confidence": 0.72,
            }
        )
    if descriptor_counts["remix-friendly sequencing"]:
        era_hints.append(
            {
                "label": "Remix-era internet pop",
                "evidence": "Recurring remix mentions suggest a web-music discovery context.",
                "confidence": 0.64,
            }
        )

    return {
        "$schema": "../schemas/taste-profile.schema.json",
        "schemaVersion": "1.0",
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "sourceDirectories": list(paths),
        "mixCount": len(sample_mixes),
        "topArtists": [
            {"name": name, "count": count} for name, count in artist_counts.most_common(12)
        ],
        "topTags": [
            {"name": name, "count": count} for name, count in tag_counts.most_common(12)
        ],
        "recurringDescriptors": [
            {"label": label, "count": count} for label, count in descriptor_counts.most_common() if count > 0
        ],
        "eraHints": era_hints,
        "sampleMixes": sample_mixes[:10],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", default=DEFAULT_INPUT_DIRS, help="Mix JSON files or directories")
    parser.add_argument("--output", default="data/taste-profile.json", help="Output JSON path")
    args = parser.parse_args(argv)

    profile = build_taste_profile(args.paths)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(profile, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
