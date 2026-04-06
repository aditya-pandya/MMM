#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
from typing import Any

from manage_artwork import register_artwork, scaffold_workspace
from mmm_common import DRAFTS_DIR, ROOT, ValidationError, dump_json, load_json, now_iso, slugify
from openai_common import post_openai_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate AI artwork for an MMM draft mix and register it locally.")
    parser.add_argument("draft", help="Draft mix slug or path under data/drafts/")
    parser.add_argument("--prompt", help="Optional explicit image prompt override.")
    parser.add_argument("--force", action="store_true", help="Overwrite the default export filename if it exists.")
    return parser.parse_args()


def resolve_draft_path(draft_arg: str) -> Path:
    candidate = Path(draft_arg)
    if candidate.exists():
        return candidate.resolve()
    draft_path = DRAFTS_DIR / f"{draft_arg}.json"
    if draft_path.exists():
        return draft_path.resolve()
    raise FileNotFoundError(f"Draft mix not found: {draft_arg}")


def build_artwork_prompt(mix: dict[str, Any]) -> str:
    summary = str(mix.get("summary") or "").strip()
    notes = str(mix.get("notes") or "").strip()
    track_lines = [
        f"{track.get('artist')} - {track.get('title')}"
        for track in mix.get("tracks", [])
        if isinstance(track, dict)
    ]
    compact_notes = " ".join(notes.split())[:500]
    return (
        "Create square album artwork for Monday Music Mix. "
        "Make it feel editorial, musical, and intentional rather than photoreal or generic. "
        "Avoid legible typography, artist portraits, interface chrome, and watermarks. "
        f"Mix title context: {mix.get('title')}. "
        f"Summary: {summary}. "
        f"Notes context: {compact_notes}. "
        f"Track cues: {', '.join(track_lines[:5])}."
    ).strip()


def request_ai_artwork(prompt: str) -> tuple[bytes, dict[str, Any]]:
    model = "gpt-image-1"
    response_payload = post_openai_json(
        "/images/generations",
        {
            "model": model,
            "size": "1024x1024",
            "response_format": "b64_json",
            "prompt": prompt,
        },
        timeout_seconds=300,
    )
    data = response_payload.get("data")
    if not isinstance(data, list) or not data or not isinstance(data[0], dict):
        raise ValidationError("OpenAI image response did not include image data")
    encoded = str(data[0].get("b64_json") or "").strip()
    if not encoded:
        raise ValidationError("OpenAI image response did not include b64_json")
    return base64.b64decode(encoded), {"provider": "openai", "model": model, "response": response_payload}


def generate_ai_artwork(
    draft_arg: str,
    *,
    prompt_override: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    draft_path = resolve_draft_path(draft_arg)
    mix = load_json(draft_path)
    if not isinstance(mix, dict):
        raise ValidationError("Draft payload must be a JSON object")

    mix_slug = str(mix.get("slug") or "").strip()
    if not mix_slug:
        raise ValidationError("Draft mix slug is required")

    workspace = scaffold_workspace(mix_slug)
    workspace_dir = ROOT / workspace["workspace"]
    notes_dir = workspace_dir / "notes"
    exports_dir = workspace_dir / "exports"

    prompt = prompt_override.strip() if prompt_override and prompt_override.strip() else build_artwork_prompt(mix)
    image_bytes, generation_meta = request_ai_artwork(prompt)

    asset_path = exports_dir / "ai-cover.png"
    if asset_path.exists() and not force:
        raise FileExistsError(f"Artwork asset already exists: {asset_path}")
    asset_path.write_bytes(image_bytes)

    provenance_path = notes_dir / "ai-artwork-generation.json"
    provenance_payload = {
        "generatedAt": now_iso(),
        "draftPath": draft_path.relative_to(ROOT).as_posix(),
        "mixSlug": mix_slug,
        "prompt": prompt,
        "provider": generation_meta["provider"],
        "model": generation_meta["model"],
    }
    dump_json(provenance_path, provenance_payload)

    item = register_artwork(
        mix_slug,
        asset_path.relative_to(ROOT).as_posix(),
        role="cover-art",
        source_type="ai-generated",
        source_label="OpenAI-generated album artwork",
        source_url="openai://images/generations",
        discovered_from="generate_ai_artwork.py",
        notes=(
            f"AI-generated artwork. Model={generation_meta['model']}. "
            f"Prompt and generation metadata saved in {provenance_path.relative_to(ROOT).as_posix()}."
        ),
        workspace_path_arg=workspace["workspace"],
    )

    return {
        "mixSlug": mix_slug,
        "draftPath": draft_path.relative_to(ROOT).as_posix(),
        "assetPath": asset_path.relative_to(ROOT).as_posix(),
        "provenancePath": provenance_path.relative_to(ROOT).as_posix(),
        "registryItemId": item["id"],
        "prompt": prompt,
        "model": generation_meta["model"],
    }


def main() -> int:
    args = parse_args()
    try:
        result = generate_ai_artwork(args.draft, prompt_override=args.prompt, force=args.force)
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
