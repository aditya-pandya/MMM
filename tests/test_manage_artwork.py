from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import manage_artwork
import mmm_common


@pytest.fixture()
def media_paths(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    media_dir = data_dir / "media"
    workspaces_dir = media_dir / "workspaces"
    registry_path = media_dir / "artwork-registry.json"
    workspaces_dir.mkdir(parents=True)

    monkeypatch.setattr(manage_artwork, "ROOT", tmp_path)
    monkeypatch.setattr(manage_artwork, "MEDIA_DIR", media_dir)
    monkeypatch.setattr(manage_artwork, "MEDIA_WORKSPACES_DIR", workspaces_dir)
    monkeypatch.setattr(manage_artwork, "ARTWORK_REGISTRY_PATH", registry_path)
    return tmp_path, media_dir, workspaces_dir, registry_path


def test_scaffold_workspace_creates_expected_directories(media_paths):
    _, _, workspaces_dir, registry_path = media_paths

    summary = manage_artwork.scaffold_workspace("mix-036-thirtysixth")

    workspace = workspaces_dir / "mix-036-thirtysixth"
    assert workspace.is_dir()
    assert (workspace / "source").is_dir()
    assert (workspace / "exports").is_dir()
    assert (workspace / "notes").is_dir()
    assert (workspace / "README.md").exists()
    assert registry_path.exists()
    assert summary["workspace"] == "data/media/workspaces/mix-036-thirtysixth"


def test_register_artwork_writes_canonical_registry_item(media_paths):
    _, _, workspaces_dir, registry_path = media_paths
    manage_artwork.scaffold_workspace("mix-036-thirtysixth")
    asset_path = workspaces_dir / "mix-036-thirtysixth" / "exports" / "cover.jpg"
    asset_path.write_text("cover", encoding="utf-8")

    item = manage_artwork.register_artwork(
        "mix-036-thirtysixth",
        "data/media/workspaces/mix-036-thirtysixth/exports/cover.jpg",
        role="cover-art",
        source_type="handmade",
        source_label="Local collage",
        notes="Built from local scans.",
    )

    registry = mmm_common.load_json(registry_path)
    assert item["mixSlug"] == "mix-036-thirtysixth"
    assert item["assetPath"] == "data/media/workspaces/mix-036-thirtysixth/exports/cover.jpg"
    assert registry["items"][0]["provenance"]["sourceLabel"] == "Local collage"
    assert registry["items"][0]["provenance"]["notes"] == "Built from local scans."
