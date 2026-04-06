from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from mmm_common import ValidationError, dump_json, load_json, now_iso, validate_mix
from publish_mix import resolve_draft
from validate_content import build_report

ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Approve an MMM draft mix with lightweight provenance")
    parser.add_argument("draft", help="Path to draft JSON or slug under data/drafts")
    parser.add_argument("--by", dest="approver", default=None, help="Reviewer/operator name to record")
    parser.add_argument(
        "--note",
        dest="approval_note",
        default=None,
        help="Optional short approval note to store in the draft approval metadata",
    )
    parser.add_argument(
        "--no-repo-validate",
        action="store_true",
        help="Skip the full repository validation preflight and validate only the target draft",
    )
    return parser.parse_args()


def default_approver() -> str | None:
    for key in ("MMM_APPROVER", "USER", "LOGNAME"):
        value = str(os.environ.get(key, "")).strip()
        if value:
            return value
    return None


def validate_repo_or_raise(repo_root: Path) -> dict[str, Any]:
    report = build_report(repo_root)
    if report["errors"]:
        raise ValidationError(
            f"repository validation failed with {report['errors']} error(s); run python3 scripts/validate_content.py"
        )
    return report


def apply_approval_metadata(
    mix: dict[str, Any],
    *,
    timestamp: str,
    approver: str | None,
    approval_note: str | None,
) -> dict[str, Any]:
    approval = mix.get("approval")
    if approval is not None and not isinstance(approval, dict):
        raise ValidationError("approval must be an object when present")

    updated = dict(approval or {})
    updated.setdefault("reviewedAt", timestamp)
    updated["approvedAt"] = timestamp

    if approver:
        updated.setdefault("reviewedBy", approver)
        updated["approvedBy"] = approver
    if approval_note:
        updated["notes"] = approval_note

    mix["status"] = "approved"
    mix["approval"] = updated
    return mix


def approve_mix(
    draft_path: Path,
    *,
    approver: str | None = None,
    approval_note: str | None = None,
    repo_root: Path = ROOT,
    validate_repo: bool = True,
) -> dict[str, Any]:
    if validate_repo:
        report = validate_repo_or_raise(repo_root)
    else:
        report = None

    payload = load_json(draft_path)
    result = validate_mix(payload)
    if result.flavor != "editorial":
        raise ValidationError("approval expects an editorial draft JSON")

    timestamp = now_iso()
    approver_name = approver or default_approver()
    approved_mix = apply_approval_metadata(
        result.mix,
        timestamp=timestamp,
        approver=approver_name,
        approval_note=approval_note,
    )
    validate_mix(approved_mix)
    dump_json(draft_path, approved_mix)

    return {
        "draft": str(draft_path),
        "slug": approved_mix["slug"],
        "status": approved_mix["status"],
        "approval": approved_mix["approval"],
        "warnings": result.warnings,
        "repo_validation": None
        if report is None
        else {"errors": report["errors"], "warnings": report["warnings"]},
    }


def main() -> int:
    args = parse_args()
    try:
        result = approve_mix(
            resolve_draft(args.draft),
            approver=args.approver,
            approval_note=args.approval_note,
            validate_repo=not args.no_repo_validate,
        )
    except (FileNotFoundError, ValidationError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
