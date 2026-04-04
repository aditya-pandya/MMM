from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from mmm_common import DRAFTS_DIR, NOTES_DIR, NOTES_INDEX_PATH, ValidationError, dump_json, load_json, now_iso, slugify


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

    return parser.parse_args()


def ensure_slug(value: str) -> str:
    slug = slugify(value)
    if not slug:
        raise ValidationError("slug must not be empty")
    return slug


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
    return {
        "$schema": "../../schemas/note.schema.json",
        "schemaVersion": "1.0",
        "id": f"note-{resolved_slug}",
        "slug": resolved_slug,
        "status": "draft",
        "title": resolved_title,
        "publishedAt": published_at or now_iso(),
        "summary": summary or "A short editorial summary for notes index and previews.",
        "body": [
            "Start with the editorial context or question that prompted this note.",
            "Add one paragraph on what changed in the archive, mix, or listening thread.",
            "Close with the detail worth remembering when returning to this later.",
        ],
        "relatedMixSlugs": [ensure_slug(item) for item in (related_mixes or [])],
        "tags": ["editorial-note"],
    }


def upsert_note_index(note: dict, notes_index_path: Path = NOTES_INDEX_PATH) -> dict:
    if notes_index_path.exists():
        payload = load_json(notes_index_path)
        items = [item for item in payload.get("items", []) if item.get("slug") != note["slug"]]
    else:
        payload = {
            "$schema": "../schemas/notes-index.schema.json",
            "schemaVersion": "1.0",
            "generatedAt": now_iso(),
            "totalNotes": 0,
            "items": [],
        }
        items = []

    items.append(
        {
            "id": note["id"],
            "slug": note["slug"],
            "title": note["title"],
            "publishedAt": note["publishedAt"],
            "summary": note["summary"],
            "path": f"data/notes/{note['slug']}.json",
            "tags": note["tags"],
            "relatedMixSlugs": note["relatedMixSlugs"],
        }
    )
    items.sort(key=lambda item: (item["publishedAt"], item["slug"]), reverse=True)

    payload["generatedAt"] = now_iso()
    payload["totalNotes"] = len(items)
    payload["items"] = items
    dump_json(notes_index_path, payload)
    return payload


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
    upsert_note_index(payload, notes_index_path=notes_index_path)
    return output_path


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
        else:
            output_path = create_note(
                title=args.title,
                slug=args.slug,
                summary=args.summary,
                related_mixes=args.related_mixes,
                published_at=args.published_at,
                force=args.force,
            )
    except (ValidationError, ValueError, FileExistsError) as exc:
        print(f"ERROR: {exc}")
        return 1

    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
