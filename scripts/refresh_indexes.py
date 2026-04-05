from __future__ import annotations

import argparse
import json
import sys

from mmm_common import (
    ARCHIVE_INDEX_PATH,
    LEGACY_ARCHIVE_INDEX_PATH,
    MIXES_JSON_PATH,
    NOTES_DIR,
    NOTES_INDEX_PATH,
    PUBLISHED_DIR,
    ValidationError,
    refresh_notes_index,
    update_archive_index,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Refresh MMM aggregate indexes from canonical files")
    parser.add_argument(
        "--only",
        choices=["all", "archive", "notes"],
        default="all",
        help="Limit refresh to archive or notes aggregates",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable output")
    return parser.parse_args()


def refresh_indexes(scope: str = "all") -> dict:
    result: dict[str, object] = {"scope": scope}

    if scope in {"all", "archive"}:
        archive = update_archive_index(
            published_dir=PUBLISHED_DIR,
            index_path=ARCHIVE_INDEX_PATH,
            legacy_index_path=LEGACY_ARCHIVE_INDEX_PATH,
            mixes_json_path=MIXES_JSON_PATH,
        )
        result["archive"] = {
            "count": archive["totalMixes"],
            "index": str(ARCHIVE_INDEX_PATH),
            "legacyIndex": str(LEGACY_ARCHIVE_INDEX_PATH),
            "mixesJson": str(MIXES_JSON_PATH),
        }

    if scope in {"all", "notes"}:
        notes = refresh_notes_index(notes_dir=NOTES_DIR, notes_index_path=NOTES_INDEX_PATH)
        result["notes"] = {
            "count": notes["totalNotes"],
            "index": str(NOTES_INDEX_PATH),
        }

    return result


def render_refresh_summary(result: dict) -> str:
    lines = [f"Refreshed aggregates: {result['scope']}"]
    archive = result.get("archive")
    if archive:
        lines.append(
            f"- archive: {archive['count']} published mixes -> {archive['index']}, {archive['legacyIndex']}, {archive['mixesJson']}"
        )
    notes = result.get("notes")
    if notes:
        lines.append(f"- notes: {notes['count']} notes -> {notes['index']}")
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    try:
        result = refresh_indexes(scope=args.only)
    except (ValidationError, ValueError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(render_refresh_summary(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
