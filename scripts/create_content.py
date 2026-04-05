from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from mmm_common import (
    DRAFTS_DIR,
    NOTES_DIR,
    NOTES_INDEX_PATH,
    PUBLISHED_DIR,
    ValidationError,
    dump_json,
    ensure_iso8601_datetime,
    find_published_mix,
    now_iso,
    published_mixes_without_note_coverage,
    refresh_notes_index,
    slugify,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create MMM draft mix and note templates")
    subparsers = parser.add_subparsers(dest="command", required=True)

    draft_mix = subparsers.add_parser("draft-mix", help="Create a new draft mix template")
    draft_mix.add_argument("--date", required=True, help="ISO date for the draft mix")
    draft_mix.add_argument("--title", help="Optional mix title")
    draft_mix.add_argument("--slug", help="Optional mix slug")
    draft_mix.add_argument("--force", action="store_true", help="Overwrite an existing file")

    note = subparsers.add_parser("note", help="Create a new editorial note template")
    note.add_argument("--title", required=True, help="Title for the note")
    note.add_argument("--slug", help="Optional note slug")
    note.add_argument("--summary", help="Optional one-line note summary")
    note.add_argument(
        "--related-mix",
        dest="related_mixes",
        action="append",
        default=[],
        help="Related published mix slug; pass multiple times for more than one",
    )
    note.add_argument("--published-at", help="Optional publishedAt timestamp; defaults to now")
    note.add_argument("--force", action="store_true", help="Overwrite an existing file")

    note_from_mix = subparsers.add_parser(
        "note-from-mix",
        help="Scaffold a note from an existing published mix",
    )
    note_from_mix.add_argument("mix", help="Published mix slug or path under data/published")
    note_from_mix.add_argument("--title", help="Optional note title override")
    note_from_mix.add_argument("--slug", help="Optional note slug override")
    note_from_mix.add_argument("--summary", help="Optional one-line note summary override")
    note_from_mix.add_argument("--published-at", help="Optional publishedAt timestamp; defaults to now")
    note_from_mix.add_argument("--force", action="store_true", help="Overwrite an existing file")

    suggest_notes = subparsers.add_parser(
        "suggest-notes",
        help="List published mixes that do not have note coverage yet",
    )
    suggest_notes.add_argument("--json", action="store_true", help="Emit machine-readable output")

    return parser.parse_args()


def ensure_slug(value: str) -> str:
    slug = slugify(value)
    if not slug:
        raise ValidationError("slug must not be empty")
    return slug


def normalize_related_mix_slugs(related_mixes: list[str] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for item in related_mixes or []:
        slug = ensure_slug(item)
        if slug in seen:
            continue
        seen.add(slug)
        normalized.append(slug)
    return normalized


def build_draft_mix_template(mix_date: str, title: str | None = None, slug: str | None = None) -> dict:
    date.fromisoformat(mix_date)
    resolved_title = title.strip() if title else f"MMM for {mix_date}"
    resolved_slug = ensure_slug(slug or slugify(resolved_title))
    return {
        "slug": resolved_slug,
        "title": resolved_title,
        "date": mix_date,
        "status": "draft",
        "summary": "A short summary of the week's arc, mood, or through-line.",
        "notes": "Open with the context for this mix, then explain the sequencing or recurring thread.",
        "tags": ["weekly-draft", "editorial-template"],
        "featured": False,
        "tracks": [
            {
                "artist": "Artist name",
                "title": "Track title",
                "why_it_fits": "Why this opener belongs in the sequence.",
            },
            {
                "artist": "Second artist",
                "title": "Second track",
                "why_it_fits": "What this changes or deepens in the mix.",
            },
            {
                "artist": "Third artist",
                "title": "Third track",
                "why_it_fits": "Why this track earns its place in the back half.",
            },
        ],
    }


def create_draft_mix(
    mix_date: str,
    title: str | None = None,
    slug: str | None = None,
    force: bool = False,
    drafts_dir: Path = DRAFTS_DIR,
) -> Path:
    payload = build_draft_mix_template(mix_date=mix_date, title=title, slug=slug)
    output_path = drafts_dir / f"{payload['slug']}.json"
    if output_path.exists() and not force:
        raise FileExistsError(f"Draft already exists: {output_path}")
    dump_json(output_path, payload)
    return output_path


def build_note_template(
    title: str,
    slug: str | None = None,
    summary: str | None = None,
    related_mixes: list[str] | None = None,
    published_at: str | None = None,
) -> dict:
    resolved_title = title.strip()
    if not resolved_title:
        raise ValidationError("note title must not be empty")
    resolved_slug = ensure_slug(slug or slugify(resolved_title))
    resolved_published_at = ensure_iso8601_datetime(published_at or now_iso(), "note publishedAt")
    return {
        "$schema": "../../schemas/note.schema.json",
        "schemaVersion": "1.0",
        "id": f"note-{resolved_slug}",
        "slug": resolved_slug,
        "status": "draft",
        "title": resolved_title,
        "publishedAt": resolved_published_at,
        "summary": summary or "A short editorial summary for notes index and previews.",
        "body": [
            "Start with the editorial context or question that prompted this note.",
            "Add one paragraph on what changed in the archive, mix, or listening thread.",
            "Close with the detail worth remembering when returning to this later.",
        ],
        "relatedMixSlugs": normalize_related_mix_slugs(related_mixes),
        "tags": ["editorial-note"],
    }


def create_note(
    title: str,
    slug: str | None = None,
    summary: str | None = None,
    related_mixes: list[str] | None = None,
    published_at: str | None = None,
    force: bool = False,
    notes_dir: Path = NOTES_DIR,
    notes_index_path: Path = NOTES_INDEX_PATH,
) -> Path:
    payload = build_note_template(
        title=title,
        slug=slug,
        summary=summary,
        related_mixes=related_mixes,
        published_at=published_at,
    )
    output_path = notes_dir / f"{payload['slug']}.json"
    if output_path.exists() and not force:
        raise FileExistsError(f"Note already exists: {output_path}")
    dump_json(output_path, payload)
    refresh_notes_index(notes_dir=notes_dir, notes_index_path=notes_index_path)
    return output_path


def build_note_from_mix_template(
    mix: dict,
    title: str | None = None,
    slug: str | None = None,
    summary: str | None = None,
    published_at: str | None = None,
) -> dict:
    mix_label = str(mix.get("displayTitle") or mix["title"]).strip()
    favorite_tracks = [track["displayText"] for track in mix.get("tracks", []) if track.get("isFavorite")]
    notable_track = favorite_tracks[0] if favorite_tracks else mix.get("tracks", [{}])[0].get("displayText", "the key turn")
    payload = build_note_template(
        title=title or f"Notes on {mix_label}",
        slug=slug or f"{mix['slug']}-notes",
        summary=summary
        or f"Editorial notes for {mix['title']}, including sequencing cues and archive context worth keeping.",
        related_mixes=[mix["slug"]],
        published_at=published_at,
    )
    payload["body"] = [
        f"Start with what still feels true about {mix['title']}: {mix['summary']}",
        f"Track the arc across {len(mix.get('tracks', []))} songs and call out the pivot points, especially {notable_track}.",
        "Add any archival context, listening mirrors, or details that would help future-you understand why this mix still matters.",
    ]
    payload["tags"] = ["editorial-note", "mix-companion"]
    return payload


def create_note_from_mix(
    mix_arg: str,
    title: str | None = None,
    slug: str | None = None,
    summary: str | None = None,
    published_at: str | None = None,
    force: bool = False,
    published_dir: Path = PUBLISHED_DIR,
    notes_dir: Path = NOTES_DIR,
    notes_index_path: Path = NOTES_INDEX_PATH,
) -> Path:
    mix = find_published_mix(mix_arg, published_dir=published_dir)
    payload = build_note_from_mix_template(
        mix=mix,
        title=title,
        slug=slug,
        summary=summary,
        published_at=published_at,
    )
    output_path = notes_dir / f"{payload['slug']}.json"
    if output_path.exists() and not force:
        raise FileExistsError(f"Note already exists: {output_path}")
    dump_json(output_path, payload)
    refresh_notes_index(notes_dir=notes_dir, notes_index_path=notes_index_path)
    return output_path


def suggest_notes_without_coverage(
    published_dir: Path = PUBLISHED_DIR,
    notes_dir: Path = NOTES_DIR,
) -> list[dict]:
    return published_mixes_without_note_coverage(published_dir=published_dir, notes_dir=notes_dir)


def render_note_suggestions(suggestions: list[dict]) -> str:
    lines = [f"Published mixes without note coverage: {len(suggestions)}"]
    if not suggestions:
        lines.append("none")
        return "\n".join(lines)

    for mix in suggestions:
        lines.append(f"- {mix['slug']} | {mix['publishedAt']} | {mix['title']}")
    return "\n".join(lines)


def build_note_suggestions_payload(suggestions: list[dict]) -> dict:
    return {
        "count": len(suggestions),
        "items": [
            {
                "slug": mix["slug"],
                "title": mix["title"],
                "publishedAt": mix["publishedAt"],
                "path": f"data/published/{mix['slug']}.json",
            }
            for mix in suggestions
        ],
    }


def main() -> int:
    args = parse_args()
    try:
        if args.command == "draft-mix":
            output_path = create_draft_mix(
                mix_date=args.date,
                title=args.title,
                slug=args.slug,
                force=args.force,
            )
        elif args.command == "note":
            output_path = create_note(
                title=args.title,
                slug=args.slug,
                summary=args.summary,
                related_mixes=args.related_mixes,
                published_at=args.published_at,
                force=args.force,
            )
        elif args.command == "note-from-mix":
            output_path = create_note_from_mix(
                mix_arg=args.mix,
                title=args.title,
                slug=args.slug,
                summary=args.summary,
                published_at=args.published_at,
                force=args.force,
            )
        else:
            suggestions = suggest_notes_without_coverage()
            if args.json:
                print(json.dumps(build_note_suggestions_payload(suggestions), indent=2))
            else:
                print(render_note_suggestions(suggestions))
            return 0
    except (ValidationError, ValueError, FileExistsError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}")
        return 1

    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
