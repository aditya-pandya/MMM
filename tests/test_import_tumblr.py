import unittest
import xml.etree.ElementTree as ET

from scripts import import_tumblr


SAMPLE_ITEM = ET.fromstring(
    """
    <item>
      <title>Thirtysixth\nAlso known as the Tuesday music mix.</title>
      <description><![CDATA[
        <h2>Thirtysixth</h2>
        <p>Also known as the Tuesday music mix. One week and one day later than originally should've been out in the wild.</p>
        <p><strong>Monday Music Mix: 36</strong></p>
        <p>Tracklist:</p>
        <ol>
          <li>The Kite String Tangle - Tennis Court (Lorde cover)</li>
          <li><strong>Blood Orange - You're Not Good Enough</strong></li>
        </ol>
        <p><a href="https://example.com/download.zip">Download album</a></p>
      ]]></description>
      <link>https://mondaymusicmix.tumblr.com/post/67441502817</link>
      <guid>https://mondaymusicmix.tumblr.com/post/67441502817</guid>
      <pubDate>Tue, 19 Nov 2013 10:39:00 +0530</pubDate>
    </item>
    """
)

HAT_TIP_ITEM = ET.fromstring(
    """
    <item>
      <title>Thirtythird</title>
      <description><![CDATA[
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
      ]]></description>
      <link>https://mondaymusicmix.tumblr.com/post/54345905127</link>
      <guid>https://mondaymusicmix.tumblr.com/post/54345905127</guid>
      <pubDate>Mon, 01 Jul 2013 20:37:00 +0530</pubDate>
    </item>
    """
)


class ImportTumblrTests(unittest.TestCase):
    def test_slugify(self):
        self.assertEqual(import_tumblr.slugify("Monday Music Mix: 36!"), "monday-music-mix-36")

    def test_extract_mix_number_from_ordinal(self):
        self.assertEqual(import_tumblr.extract_mix_number("Thirtysixth"), 36)
        self.assertEqual(import_tumblr.extract_mix_number("Monday Music Mix: 12"), 12)

    def test_convert_item_to_mix(self):
        mix = import_tumblr.convert_item_to_mix(SAMPLE_ITEM)
        self.assertIsNotNone(mix)
        self.assertEqual(mix["mixNumber"], 36)
        self.assertEqual(mix["slug"], "mix-036-thirtysixth")
        self.assertEqual(mix["stats"]["trackCount"], 2)
        self.assertEqual(mix["tracks"][1]["isFavorite"], True)
        self.assertEqual(mix["download"]["url"], "https://example.com/download.zip")
        self.assertEqual(mix["publishedAt"], "2013-11-19T05:09:00Z")

    def test_convert_item_keeps_hat_tip_and_favorite_cue_out_of_intro(self):
        mix = import_tumblr.convert_item_to_mix(HAT_TIP_ITEM)
        self.assertIsNotNone(mix)
        self.assertEqual(
            mix["intro"],
            ["As always, back after a fairly long period of absence. MMM isn’t dead, not just yet."],
        )
        self.assertEqual(mix["cover"]["credit"], "Album art featuring work by Fernando Vincente")
        self.assertEqual(mix["legacy"]["editorialHighlights"], ["Hat tip: Rhea R for introducing me to Klingande"])
        self.assertEqual(mix["legacy"]["favoriteTrackCue"], "* Tracks in blue indicate my favourites")
        self.assertEqual(mix["stats"]["coverTracks"], ["Solid Gold - Danger Zone (Kenny Loggins cover)"])
        self.assertEqual(mix["stats"]["remixTracks"], ["Klingande - Jubel (Festival remix)"])


if __name__ == "__main__":
    unittest.main()
