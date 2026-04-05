from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from pathlib import Path
from urllib.parse import urlparse

from mmm_common import (
    DRAFTS_DIR,
    NOTES_DIR,
    PUBLISHED_DIR,
    ROOT,
    ValidationError,
    latest_item,
    load_notes,
    load_published_mixes,
    load_json,
    validate_mix,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Print or open local previews for the latest MMM content")
    parser.add_argument(
        "--kind",
        choices=["all", "draft", "mix", "note"],
        default="all",
        help="Limit output to one content type",
    )
    parser.add_argument("--host", default="http://localhost:3000", help="Local preview host for route URLs")
    parser.add_argument("--open", action="store_true", dest="open_targets", help="Open local previews after printing them")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable output")
    return parser.parse_args()


def load_drafts(drafts_dir: Path | None = None) -> list[dict]:
    drafts_dir = drafts_dir or DRAFTS_DIR
    drafts: list[dict] = []
    for path in sorted(drafts_dir.glob("*.json")):
        result = validate_mix(load_json(path))
        if result.flavor != "editorial":
            raise ValidationError(f"Expected draft/editorial mix content in {path}")
        payload = dict(result.mix)
        payload["_path"] = path
        drafts.append(payload)
    drafts.sort(key=lambda item: (item.get("date") or "", item["slug"]), reverse=True)
    return drafts


def build_preview_record(kind: str, payload: dict, host: str) -> dict:
    slug = payload["slug"]
    if kind == "draft":
        source_path = str(payload["_path"].resolve())
        return {
            "kind": kind,
            "slug": slug,
            "label": payload["title"],
            "sourcePath": source_path,
            "previewTarget": Path(source_path).as_uri(),
            "route": None,
            "distPath": None,
        }

    route = f"/mixes/{slug}/" if kind == "mix" else f"/notes/{slug}/"
    dist_path = (ROOT / "dist" / route.strip("/") / "index.html").resolve()
    preview_target = dist_path.as_uri() if dist_path.exists() else build_local_route_url(host, route)
    source_path = (PUBLISHED_DIR / f"{slug}.json").resolve() if kind == "mix" else (NOTES_DIR / f"{slug}.json").resolve()
    return {
        "kind": kind,
        "slug": slug,
        "label": payload["title"],
        "sourcePath": str(source_path),
        "previewTarget": preview_target,
        "route": route,
        "distPath": str(dist_path),
    }


def build_local_route_url(host: str, route: str) -> str:
    normalized_host = ensure_local_host(host)
    return f"{normalized_host.rstrip('/')}{route}"


def ensure_local_host(host: str) -> str:
    parsed = urlparse(host)
    if parsed.scheme not in {"http", "https"}:
        raise ValidationError("preview host must use http or https")
    hostname = parsed.hostname or ""
    if hostname not in {"localhost", "127.0.0.1"}:
        raise ValidationError("preview host must stay local (localhost or 127.0.0.1)")
    return host


def latest_previews(kind: str = "all", host: str = "http://localhost:3000") -> list[dict]:
    ensure_local_host(host)
    records: list[dict] = []

    if kind in {"all", "draft"}:
        draft = latest_item(load_drafts(), "date")
        if draft:
            records.append(build_preview_record("draft", draft, host))

    if kind in {"all", "mix"}:
        mix = latest_item(load_published_mixes(published_dir=PUBLISHED_DIR), "publishedAt", "date")
        if mix:
            records.append(build_preview_record("mix", mix, host))

    if kind in {"all", "note"}:
        note = latest_item(load_notes(notes_dir=NOTES_DIR), "publishedAt")
        if note:
            records.append(build_preview_record("note", note, host))

    return records


def render_preview_summary(records: list[dict]) -> str:
    if not records:
        return "No latest content found."

    lines = []
    for record in records:
        route = record["route"] or "n/a"
        dist_path = record["distPath"] or "n/a"
        lines.append(
            f"{record['kind']}: {record['slug']} | source={record['sourcePath']} | route={route} | preview={record['previewTarget']} | dist={dist_path}"
        )
    return "\n".join(lines)


def open_preview_targets(records: list[dict]) -> list[str]:
    opened = []
    for record in records:
        webbrowser.open(record["previewTarget"])
        opened.append(record["previewTarget"])
    return opened


def main() -> int:
    args = parse_args()
    try:
        records = latest_previews(kind=args.kind, host=args.host)
        if args.open_targets:
            open_preview_targets(records)
    except (ValidationError, ValueError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(records, indent=2))
    else:
        print(render_preview_summary(records))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
