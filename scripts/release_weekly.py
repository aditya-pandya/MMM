from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from mmm_common import ValidationError
from publish_mix import publish_mix, resolve_draft
from validate_content import build_report

ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate, publish, and build the approved weekly MMM draft")
    parser.add_argument("draft", help="Path to draft JSON or slug under data/drafts")
    parser.add_argument("--feature", action="store_true", help="Set this mix as the homepage feature during publish")
    return parser.parse_args()


def validate_repo_or_raise(repo_root: Path, label: str) -> dict[str, Any]:
    report = build_report(repo_root)
    if report["errors"]:
        raise ValidationError(
            f"{label} validation failed with {report['errors']} error(s); run python3 scripts/validate_content.py"
        )
    return report


def run_command(command: list[str], repo_root: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f"command failed: {' '.join(command)}")
    return result


def release_mix(draft_path: Path, *, repo_root: Path = ROOT, feature: bool = False) -> dict[str, Any]:
    preflight_report = validate_repo_or_raise(repo_root, "Preflight")
    publish_result = publish_mix(draft_path, feature=feature, validate_only=False)
    post_publish_report = validate_repo_or_raise(repo_root, "Post-publish")
    build_result = run_command(["npm", "run", "build"], repo_root)

    return {
        "draft": str(draft_path),
        "published_path": publish_result["published_path"],
        "slug": Path(publish_result["published_path"]).stem,
        "validation": {
            "preflight": {"errors": preflight_report["errors"], "warnings": preflight_report["warnings"]},
            "post_publish": {"errors": post_publish_report["errors"], "warnings": post_publish_report["warnings"]},
        },
        "build": {
            "command": "npm run build",
            "stdout": build_result.stdout.strip(),
            "stderr": build_result.stderr.strip(),
        },
        "next_step": "Review the local build if desired, then push manually to trigger Pages deploy.",
    }


def main() -> int:
    args = parse_args()
    try:
        result = release_mix(resolve_draft(args.draft), feature=args.feature)
    except (FileNotFoundError, ValidationError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2))
    print("Next step: git push origin main")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
