from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
from pathlib import Path
from typing import Any

from mmm_common import (
    ARTWORK_REGISTRY_PATH,
    MEDIA_DIR,
    MEDIA_WORKSPACES_DIR,
    ROOT,
    ValidationError,
    dump_json,
    ensure_kebab_case_slug,
    ensure_non_empty_string,
    load_json,
    now_iso,
    slugify,
)

VALID_ROLES = {"cover-art", "cover-source", "social-card", "detail", "alternate"}
VALID_SOURCE_TYPES = {"handmade", "scan", "screenshot", "collage", "reference", "restoration", "tumblr-original", "unknown"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scaffold or register local MMM artwork and provenance.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scaffold = subparsers.add_parser("scaffold", help="Create a local workspace for a mix's artwork files.")
    scaffold.add_argument("mix_slug", help="Published or draft mix slug.")
    scaffold.add_argument(
        "--workspace-name",
        help="Optional workspace directory name. Defaults to the normalized mix slug.",
    )

    register = subparsers.add_parser("register", help="Register a local artwork file in the canonical registry.")
    register.add_argument("mix_slug", help="Published or draft mix slug.")
    register.add_argument("--asset-path", required=True, help="Path to a local asset file inside this repo.")
    register.add_argument("--role", default="cover-art", choices=sorted(VALID_ROLES))
    register.add_argument(
        "--source-type",
        default="handmade",
        choices=sorted(VALID_SOURCE_TYPES),
        help="Short provenance classification for the asset.",
    )
    register.add_argument("--source-label", required=True, help="Human-readable provenance label.")
    register.add_argument("--notes", default="", help="Optional provenance notes.")
    register.add_argument(
        "--workspace-path",
        help="Optional workspace path to associate with the asset. Defaults to data/media/workspaces/<mix-slug>.",
    )

    listing = subparsers.add_parser("list", help="Print the canonical artwork registry.")
    listing.add_argument("--json", action="store_true", help="Emit the full registry JSON.")
    return parser


def default_registry() -> dict[str, Any]:
    return {
        "$schema": "../../schemas/artwork-registry.schema.json",
        "schemaVersion": "1.0",
        "updatedAt": now_iso(),
        "items": [],
    }


def load_or_create_registry(path: Path | None = None) -> dict[str, Any]:
    path = path or ARTWORK_REGISTRY_PATH
    if not path.exists():
        registry = default_registry()
        dump_json(path, registry)
        return registry
    payload = load_json(path)
    if not isinstance(payload, dict):
        raise ValidationError("artwork registry must be a JSON object")
    payload.setdefault("$schema", "../../schemas/artwork-registry.schema.json")
    payload.setdefault("schemaVersion", "1.0")
    payload.setdefault("items", [])
    return payload


def path_relative_to_repo(path: Path, repo_root: Path | None = None) -> str:
    repo_root = repo_root or ROOT
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(repo_root.resolve())
    except ValueError as exc:
        raise ValidationError(f"path must stay inside the repo: {path}") from exc
    return relative.as_posix()


def ensure_media_relative_path(path_value: str, repo_root: Path | None = None) -> Path:
    repo_root = repo_root or ROOT
    normalized = ensure_non_empty_string(path_value, "media path")
    candidate = (repo_root / normalized).resolve()
    try:
        candidate.relative_to((repo_root / "data" / "media").resolve())
    except ValueError as exc:
        raise ValidationError("media paths must stay under data/media/") from exc
    return candidate


def scaffold_workspace(mix_slug: str, workspace_name: str | None = None) -> dict[str, str]:
    normalized_slug = ensure_kebab_case_slug(slugify(mix_slug), "mix slug")
    workspace_dir = MEDIA_WORKSPACES_DIR / (workspace_name or normalized_slug)
    source_dir = workspace_dir / "source"
    exports_dir = workspace_dir / "exports"
    notes_dir = workspace_dir / "notes"

    for path in (source_dir, exports_dir, notes_dir):
        path.mkdir(parents=True, exist_ok=True)

    readme_path = workspace_dir / "README.md"
    if not readme_path.exists():
        readme_path.write_text(
            "\n".join(
                [
                    f"# Artwork Workspace: {normalized_slug}",
                    "",
                    "- `source/` keeps scans, references, or raw local ingredients.",
                    "- `exports/` keeps candidate finals that can be registered into the artwork registry.",
                    "- `notes/` keeps process scraps, provenance notes, or quick captions.",
                    "",
                    "Keep everything local-safe and file-based.",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

    load_or_create_registry()
    return {
        "mix_slug": normalized_slug,
        "workspace": path_relative_to_repo(workspace_dir),
        "source": path_relative_to_repo(source_dir),
        "exports": path_relative_to_repo(exports_dir),
        "notes": path_relative_to_repo(notes_dir),
        "readme": path_relative_to_repo(readme_path),
    }


def build_registry_item(
    mix_slug: str,
    asset_path: Path,
    role: str,
    source_type: str,
    source_label: str,
    notes: str,
    workspace_path: Path,
) -> dict[str, Any]:
    normalized_mix_slug = ensure_kebab_case_slug(slugify(mix_slug), "mix slug")
    if role not in VALID_ROLES:
        raise ValidationError(f"unsupported artwork role: {role}")
    if source_type not in VALID_SOURCE_TYPES:
        raise ValidationError(f"unsupported artwork source type: {source_type}")
    if not asset_path.exists() or not asset_path.is_file():
        raise FileNotFoundError(f"asset file not found: {asset_path}")

    asset_relative = path_relative_to_repo(asset_path)
    workspace_relative = path_relative_to_repo(workspace_path)
    ensure_media_relative_path(asset_relative)
    ensure_media_relative_path(workspace_relative)

    item_id = slugify(f"{normalized_mix_slug}-{role}-{asset_path.stem}")
    file_bytes = asset_path.read_bytes()
    media_type = mimetypes.guess_type(asset_path.name)[0] or "application/octet-stream"
    return {
        "id": item_id,
        "mixSlug": normalized_mix_slug,
        "role": role,
        "assetPath": asset_relative,
        "workspacePath": workspace_relative,
        "registeredAt": now_iso(),
        "file": {
            "byteSize": len(file_bytes),
            "mediaType": media_type,
            "etag": None,
            "lastModified": None,
        },
        "checksum": {
            "algorithm": "sha256",
            "value": hashlib.sha256(file_bytes).hexdigest(),
        },
        "provenance": {
            "sourceType": source_type,
            "sourceLabel": ensure_non_empty_string(source_label, "source label"),
            "sourceUrl": "",
            "discoveredFrom": "manual-register",
            "notes": notes.strip(),
        },
    }


def register_artwork(
    mix_slug: str,
    asset_path_arg: str,
    role: str,
    source_type: str,
    source_label: str,
    notes: str = "",
    workspace_path_arg: str | None = None,
    registry_path: Path | None = None,
) -> dict[str, Any]:
    registry_path = registry_path or ARTWORK_REGISTRY_PATH
    normalized_mix_slug = ensure_kebab_case_slug(slugify(mix_slug), "mix slug")
    asset_path = (ROOT / asset_path_arg).resolve() if not Path(asset_path_arg).is_absolute() else Path(asset_path_arg).resolve()
    default_workspace = MEDIA_WORKSPACES_DIR / normalized_mix_slug
    workspace_path = (
        (ROOT / workspace_path_arg).resolve()
        if workspace_path_arg and not Path(workspace_path_arg).is_absolute()
        else Path(workspace_path_arg).resolve() if workspace_path_arg
        else default_workspace.resolve()
    )
    if not workspace_path.exists():
        raise FileNotFoundError(f"workspace path not found: {workspace_path}")

    registry = load_or_create_registry(registry_path)
    item = build_registry_item(
        normalized_mix_slug,
        asset_path,
        role,
        source_type,
        source_label,
        notes,
        workspace_path,
    )

    items = [existing for existing in registry.get("items", []) if existing.get("id") != item["id"]]
    items.append(item)
    items.sort(key=lambda entry: (entry.get("mixSlug", ""), entry.get("role", ""), entry.get("assetPath", "")))

    registry["schemaVersion"] = "1.0"
    registry["updatedAt"] = now_iso()
    registry["items"] = items
    dump_json(registry_path, registry)
    return item


def render_workspace_summary(summary: dict[str, str]) -> str:
    return "\n".join(
        [
            f"Artwork workspace ready for {summary['mix_slug']}",
            f"- workspace: {summary['workspace']}",
            f"- source: {summary['source']}",
            f"- exports: {summary['exports']}",
            f"- notes: {summary['notes']}",
            f"- readme: {summary['readme']}",
            f"- registry: {path_relative_to_repo(ARTWORK_REGISTRY_PATH)}",
        ]
    )


def render_registry_item(item: dict[str, Any]) -> str:
    provenance = item.get("provenance", {})
    return "\n".join(
        [
            f"Registered artwork: {item['id']}",
            f"- mix: {item['mixSlug']}",
            f"- role: {item['role']}",
            f"- asset: {item['assetPath']}",
            f"- workspace: {item['workspacePath']}",
            f"- source: {provenance.get('sourceType')} / {provenance.get('sourceLabel')}",
        ]
    )


def render_registry_listing(registry: dict[str, Any]) -> str:
    items = registry.get("items", [])
    lines = [f"Artwork registry items: {len(items)}"]
    for item in items:
        lines.append(f"- {item.get('id')}: {item.get('assetPath')} ({item.get('role')})")
    return "\n".join(lines)


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "scaffold":
            summary = scaffold_workspace(args.mix_slug, workspace_name=args.workspace_name)
            print(render_workspace_summary(summary))
            return 0
        if args.command == "register":
            item = register_artwork(
                args.mix_slug,
                args.asset_path,
                args.role,
                args.source_type,
                args.source_label,
                notes=args.notes,
                workspace_path_arg=args.workspace_path,
            )
            print(render_registry_item(item))
            return 0
        if args.command == "list":
            registry = load_or_create_registry()
            if args.json:
                print(json.dumps(registry, indent=2))
            else:
                print(render_registry_listing(registry))
            return 0
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
