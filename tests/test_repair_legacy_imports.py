import copy
import tempfile
import unittest
from pathlib import Path

from scripts import repair_legacy_imports
from scripts.mmm_common import load_json


SAMPLE_MIX = {
    "$schema": "schemas/mix.schema.json",
    "schemaVersion": "1.0",
    "id": "mix-033-thirtythird",
    "slug": "mix-033-thirtythird",
    "status": "published",
    "siteSection": "mixes",
    "source": {
        "platform": "tumblr",
        "feedType": "rss",
        "importedAt": "2026-04-05T00:00:00Z",
        "sourceUrl": "https://mondaymusicmix.tumblr.com/post/54345905127",
        "guid": "https://mondaymusicmix.tumblr.com/post/54345905127",
    },
    "title": "Monday Music Mix #33",
    "displayTitle": "Thirtythird",
    "mixNumber": 33,
    "publishedAt": "2013-07-01T15:07:00Z",
    "summary": "Old summary",
    "intro": [
        "As always, back after a fairly long period of absence. MMM isn’t dead, not just yet.",
        "Album art featuring work by Fernando Vincente",
        "Hat tip: Rhea R for introducing me to Klingande",
    ],
    "tags": [],
    "cover": {
        "imageUrl": "https://example.com/cover.jpg",
        "alt": "Cover art for Thirtythird",
        "credit": None,
    },
    "download": {"label": "Download mix", "url": "https://example.com/download.zip"},
    "tracks": [
        {
            "position": 1,
            "artist": "Solid Gold",
            "title": "Danger Zone (Kenny Loggins cover)",
            "displayText": "Solid Gold - Danger Zone (Kenny Loggins cover)",
            "isFavorite": False,
        },
        {
            "position": 2,
            "artist": "Klingande",
            "title": "Jubel (Festival remix)",
            "displayText": "Klingande - Jubel (Festival remix)",
            "isFavorite": False,
        },
    ],
    "stats": {
        "trackCount": 2,
        "favoriteCount": 0,
        "favoriteTracks": [],
        "topArtists": ["Solid Gold", "Klingande"],
    },
    "legacy": {
        "originalTitle": "Thirtythird",
        "tumblrHeading": "Thirtythird",
        "descriptionHtml": """
            <h2>Thirtythird</h2>
            <p>As always, back after a fairly long period of absence. MMM isn’t dead, not just yet.</p>
            <p>Album art featuring work by <a href="https://example.com/artist">Fernando Vincente</a></p>
            <p>Tracklist:</p>
            <ol>
              <li>Solid Gold - Danger Zone (Kenny Loggins cover)</li>
              <li><strong>Klingande - Jubel (Festival remix)</strong></li>
            </ol>
            <p>* Tracks in blue indicate my favourites</p>
            <p>Hat tip: Rhea R for introducing me to Klingande</p>
        """,
    },
}


class RepairLegacyImportsTests(unittest.TestCase):
    def test_repair_file_refreshes_derived_fields(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "mix.json"
            path.write_text(__import__("json").dumps(SAMPLE_MIX, indent=2) + "\n", encoding="utf-8")

            changed = repair_legacy_imports.repair_file(path)

            self.assertTrue(changed)
            repaired = load_json(path)
            self.assertEqual(
                repaired["intro"],
                ["As always, back after a fairly long period of absence. MMM isn’t dead, not just yet."],
            )
            self.assertEqual(repaired["cover"]["credit"], "Album art featuring work by Fernando Vincente")
            self.assertEqual(
                repaired["legacy"]["editorialHighlights"],
                ["Hat tip: Rhea R for introducing me to Klingande"],
            )
            self.assertEqual(repaired["legacy"]["favoriteTrackCue"], "* Tracks in blue indicate my favourites")
            self.assertEqual(repaired["stats"]["favoriteCount"], 1)
            self.assertEqual(repaired["stats"]["favoriteTracks"], ["Klingande - Jubel (Festival remix)"])
            self.assertEqual(repaired["stats"]["coverTracks"], ["Solid Gold - Danger Zone (Kenny Loggins cover)"])
            self.assertEqual(repaired["stats"]["remixTracks"], ["Klingande - Jubel (Festival remix)"])

    def test_repair_file_is_noop_for_missing_legacy_html(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "mix.json"
            payload = copy.deepcopy(SAMPLE_MIX)
            payload["legacy"].pop("descriptionHtml")
            path.write_text(__import__("json").dumps(payload, indent=2) + "\n", encoding="utf-8")

            changed = repair_legacy_imports.repair_file(path)

            self.assertFalse(changed)


if __name__ == "__main__":
    unittest.main()
