from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import generate_ai_artwork
import manage_artwork
import mmm_common


def test_generate_ai_artwork_saves_asset_and_registers_provenance(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    drafts_dir = data_dir / "drafts"
    media_dir = data_dir / "media"
    workspaces_dir = media_dir / "workspaces"
    registry_path = media_dir / "artwork-registry.json"
    drafts_dir.mkdir(parents=True)
    workspaces_dir.mkdir(parents=True)

    draft_path = drafts_dir / "mmm-for-2026-05-18.json"
    mmm_common.dump_json(
        draft_path,
        {
            "slug": "mmm-for-2026-05-18",
            "title": "MMM for 2026-05-18",
            "date": "2026-05-18",
            "status": "draft",
            "summary": "A soft-motion draft.",
            "notes": "Grounded in the archive and still a little airborne.",
            "tracks": [
                {"artist": "Goldroom", "title": "Embrace", "why_it_fits": "Warm opener."},
                {"artist": "Chromeo", "title": "Over Your Shoulder", "why_it_fits": "Playful builder."},
                {"artist": "Dum Dum Girls", "title": "Mine Tonight", "why_it_fits": "Anchor."},
            ],
        },
    )

    for module in (generate_ai_artwork, manage_artwork, mmm_common):
        monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(generate_ai_artwork, "DRAFTS_DIR", drafts_dir)
    monkeypatch.setattr(manage_artwork, "MEDIA_WORKSPACES_DIR", workspaces_dir)
    monkeypatch.setattr(manage_artwork, "ARTWORK_REGISTRY_PATH", registry_path)

    def fake_request(prompt: str) -> tuple[bytes, dict[str, object]]:
        assert "MMM for 2026-05-18" in prompt
        return b"png-bytes", {"provider": "openai", "model": "gpt-image-1", "response": {"data": []}}

    monkeypatch.setattr(generate_ai_artwork, "request_ai_artwork", fake_request)

    result = generate_ai_artwork.generate_ai_artwork("mmm-for-2026-05-18")

    asset_path = tmp_path / result["assetPath"]
    provenance_path = tmp_path / result["provenancePath"]
    registry = mmm_common.load_json(registry_path)

    assert asset_path.read_bytes() == b"png-bytes"
    assert provenance_path.exists()
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    assert provenance["model"] == "gpt-image-1"
    assert provenance["mixSlug"] == "mmm-for-2026-05-18"

    registry_item = registry["items"][0]
    assert registry_item["mixSlug"] == "mmm-for-2026-05-18"
    assert registry_item["provenance"]["sourceType"] == "ai-generated"
    assert registry_item["provenance"]["sourceUrl"] == "openai://images/generations"
    assert registry_item["provenance"]["discoveredFrom"] == "generate_ai_artwork.py"
    assert "ai-artwork-generation.json" in registry_item["provenance"]["notes"]
