#!/usr/bin/env python3
"""Refresh legacy-derived fields for imported or published Tumblr mix JSON."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.import_tumblr import refresh_mix_from_legacy_html
from scripts.mmm_common import dump_json, load_json


def iter_mix_paths(inputs: list[str]) -> list[Path]:
    paths: list[Path] = []
    for raw_input in inputs:
        path = Path(raw_input)
        if path.is_dir():
            paths.extend(sorted(path.glob("*.json")))
        elif path.suffix == ".json" and path.exists():
            paths.append(path)
    seen: set[Path] = set()
    unique_paths: list[Path] = []
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique_paths.append(path)
    return unique_paths


def repair_file(path: Path, dry_run: bool = False) -> bool:
    original = load_json(path)
    repaired = refresh_mix_from_legacy_html(original)
    if repaired == original:
        return False
    if not dry_run:
        dump_json(path, repaired)
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "inputs",
        nargs="*",
        default=["data/imported/mixes", "data/published"],
        help="JSON files or directories to repair",
    )
    parser.add_argument("--dry-run", action="store_true", help="Report files that would change without rewriting them")
    args = parser.parse_args(argv)

    paths = iter_mix_paths(args.inputs)
    changed_paths: list[Path] = []
    for path in paths:
        if repair_file(path, dry_run=args.dry_run):
            changed_paths.append(path)
            print(f"{'would update' if args.dry_run else 'updated'} {path}")

    print(
        f"Scanned {len(paths)} file(s); "
        f"{'would update' if args.dry_run else 'updated'} {len(changed_paths)} file(s)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
