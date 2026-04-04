from __future__ import annotations

import argparse
import sys
from pathlib import Path

from mmm_common import (
    ARCHIVE_INDEX_PATH,
    DRAFTS_DIR,
    LEGACY_ARCHIVE_INDEX_PATH,
    MIXES_JSON_PATH,
    PUBLISHED_DIR,
    SITE_PATH,
    ValidationError,
    dump_json,
    editorial_to_published_mix,
    load_json,
    update_archive_index,
    validate_mix,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate and publish MMM mixes")
    parser.add_argument("draft", help="Path to draft JSON or slug under data/drafts")
    parser.add_argument("--feature", action="store_true", help="Set this mix as the homepage feature")
    parser.add_argument("--validate-only", action="store_true", help="Validate without publishing")
    return parser.parse_args()



def resolve_draft(draft_arg: str) -> Path:
    candidate = Path(draft_arg)
    if candidate.exists():
        return candidate
    draft_path = DRAFTS_DIR / f"{draft_arg}.json"
    if draft_path.exists():
        return draft_path
    raise FileNotFoundError(f"Draft not found: {draft_arg}")



def publish_mix(draft_path: Path, feature: bool = False, validate_only: bool = False) -> dict:
    result = validate_mix(load_json(draft_path))
    mix = result.mix
    if result.flavor != "editorial":
        raise ValidationError("Publish flow expects an editorial draft JSON, not an already-published mix")

    if validate_only:
        return {
            "draft": str(draft_path),
            "slug": mix["slug"],
            "status": mix.get("status"),
            "warnings": result.warnings,
            "published": False,
        }

    if mix["status"] != "approved":
        raise ValidationError("Only mixes with status='approved' can be published")

    published_mix = editorial_to_published_mix(mix)
    published_path = PUBLISHED_DIR / f"{published_mix['slug']}.json"
    dump_json(published_path, published_mix)

    archive = update_archive_index(
        published_dir=PUBLISHED_DIR,
        index_path=ARCHIVE_INDEX_PATH,
        legacy_index_path=LEGACY_ARCHIVE_INDEX_PATH,
        mixes_json_path=MIXES_JSON_PATH,
    )

    if feature or mix.get("featured"):
        site = load_json(SITE_PATH)
        site["featuredMixSlug"] = published_mix["slug"]
        dump_json(SITE_PATH, site)

    return {
        "draft": str(draft_path),
        "published_path": str(published_path),
        "archive_index": str(ARCHIVE_INDEX_PATH),
        "legacy_archive_index": str(LEGACY_ARCHIVE_INDEX_PATH),
        "mixes_json": str(MIXES_JSON_PATH),
        "archive_count": len(archive["items"]),
        "warnings": result.warnings,
        "published": True,
    }



def main() -> int:
    args = parse_args()
    try:
        result = publish_mix(resolve_draft(args.draft), feature=args.feature, validate_only=args.validate_only)
    except (FileNotFoundError, ValidationError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
