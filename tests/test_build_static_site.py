from __future__ import annotations

import difflib
import json
import os
import re
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
STATIC_OUTPUT_FIXTURES = REPO_ROOT / "tests" / "fixtures" / "static_output"
UPDATE_STATIC_OUTPUT_FIXTURES = os.environ.get("MMM_UPDATE_STATIC_FIXTURES") == "1"


def prepare_temp_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    shutil.copytree(REPO_ROOT / "scripts", repo / "scripts")
    shutil.copytree(REPO_ROOT / "data", repo / "data")
    shutil.copytree(REPO_ROOT / "src", repo / "src")
    return repo


def stabilize_static_output_inputs(repo: Path) -> None:
    """Keep golden-route inputs pinned to the seeded editorial snapshot.

    The live repo can accumulate additional weekly draft files over time, but the
    static-output fixtures should only change when we intentionally update them.
    """
    drafts_dir = repo / "data" / "drafts"
    retained_draft = drafts_dir / "mmm-for-2026-04-06.json"

    for draft_path in drafts_dir.glob("*.json"):
        if draft_path != retained_draft:
            draft_path.unlink()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


class StaticOutputDigestParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.node_stack: list[dict[str, object]] = []
        self.capture_stack: list[dict[str, object]] = []
        self.lines: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        classes = set((attrs_dict.get("class") or "").split())
        self.node_stack.append({"tag": tag, "classes": classes})

        if self._should_capture(tag, classes):
            self.capture_stack.append(
                {
                    "tag": tag,
                    "classes": classes,
                    "chunks": [],
                    "track": self._within_class("tracklist"),
                }
            )

    def handle_endtag(self, tag: str) -> None:
        if self.capture_stack and self.capture_stack[-1]["tag"] == tag:
            capture = self.capture_stack.pop()
            text = self._normalize_text("".join(capture["chunks"]))
            if text:
                self.lines.append(f"{self._label_for_capture(capture)}: {text}")

        for index in range(len(self.node_stack) - 1, -1, -1):
            if self.node_stack[index]["tag"] == tag:
                del self.node_stack[index]
                break

    def handle_data(self, data: str) -> None:
        if self.capture_stack:
            self.capture_stack[-1]["chunks"].append(data)

    def _should_capture(self, tag: str, classes: set[str]) -> bool:
        if tag == "title":
            return True

        if not self._within_tag("main") or self._inside_ignored_context():
            return False

        if tag in {"h1", "h2", "h3", "code"}:
            return True

        if tag == "button" and "discovery-filter" in classes:
            return True

        if tag == "a" and classes.intersection({"button", "text-link"}):
            return True

        if tag == "li" and (self._within_class("tracklist") or self._within_class("tag-list")):
            return True

        return tag == "p"

    def _label_for_capture(self, capture: dict[str, object]) -> str:
        tag = str(capture["tag"])
        classes = set(capture["classes"])

        if tag == "title":
            return "TITLE"
        if tag in {"h1", "h2", "h3"}:
            return tag.upper()
        if tag == "code":
            return "COMMAND"
        if tag == "button":
            return "FILTER"
        if tag == "a":
            return "BUTTON" if "button" in classes else "LINK"
        if tag == "li":
            return "TRACK" if capture["track"] else "TAG"

        if "eyebrow" in classes or any(name.endswith("__eyebrow") for name in classes):
            return "EYEBROW"
        if classes.intersection({"hero-copy", "page-intro__copy", "page-intro__copy--large", "supporting-copy"}) or self._within_class("prose"):
            return "COPY"
        if any(
            name.endswith(suffix)
            for name in classes
            for suffix in ("__meta", "__submeta", "__label", "__link", "__credit")
        ):
            return "META"

        return "TEXT"

    def _inside_ignored_context(self) -> bool:
        return any(
            self._within_tag(tag)
            for tag in ("header", "footer", "nav", "script", "style")
        )

    def _within_tag(self, tag: str) -> bool:
        return any(entry["tag"] == tag for entry in self.node_stack)

    def _within_class(self, class_name: str) -> bool:
        return any(class_name in entry["classes"] for entry in self.node_stack)

    @staticmethod
    def _normalize_text(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip()


def build_static_output_digest(html: str) -> str:
    parser = StaticOutputDigestParser()
    parser.feed(html)
    return "\n".join(parser.lines) + "\n"


def assert_matches_static_output_fixture(
    *,
    html: str,
    fixture_name: str,
) -> None:
    fixture_path = STATIC_OUTPUT_FIXTURES / fixture_name
    digest = build_static_output_digest(html)

    if UPDATE_STATIC_OUTPUT_FIXTURES:
        fixture_path.parent.mkdir(parents=True, exist_ok=True)
        fixture_path.write_text(digest, encoding="utf-8")

    expected = fixture_path.read_text(encoding="utf-8")
    if digest != expected:
        diff = "".join(
            difflib.unified_diff(
                expected.splitlines(keepends=True),
                digest.splitlines(keepends=True),
                fromfile=str(fixture_path.relative_to(REPO_ROOT)),
                tofile=f"{fixture_path.relative_to(REPO_ROOT)} (actual)",
            )
        )
        raise AssertionError(
            f"Static output fixture mismatch for {fixture_name}.\n"
            f"Set MMM_UPDATE_STATIC_FIXTURES=1 to refresh intentional changes.\n"
            f"{diff}"
        )


def test_static_build_emits_note_routes_and_relationships(tmp_path):
    repo = prepare_temp_repo(tmp_path)

    result = subprocess.run(
        ["node", "scripts/build.js"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout

    dist_dir = repo / "dist"
    home_html = read_text(dist_dir / "index.html")
    archive_html = read_text(dist_dir / "archive" / "index.html")
    about_html = read_text(dist_dir / "about" / "index.html")
    notes_index_html = read_text(dist_dir / "notes" / "index.html")
    note_detail_html = read_text(dist_dir / "notes" / "rebuilding-the-archive" / "index.html")
    mix_detail_html = read_text(dist_dir / "mixes" / "mix-036-thirtysixth" / "index.html")
    mix_with_youtube_html = read_text(dist_dir / "mixes" / "mix-035-thirtyfifth" / "index.html")
    studio_html = read_text(dist_dir / "studio" / "index.html")
    site_js = read_text(dist_dir / "assets" / "site.js")

    assert "notes/rebuilding-the-archive/" in home_html
    assert "Notes related to Thirtysixth" in home_html
    assert "Read more about the project" in home_html

    assert "Search archive" in archive_html
    assert 'data-discovery-filter="state:has-related"' in archive_html
    assert 'data-discovery-filter="state:has-highlights"' in archive_html
    assert 'data-discovery-filter="state:has-listening"' in archive_html
    assert 'data-discovery-filter="source:tumblr"' in archive_html
    assert 'data-discovery-filter="texture:covers"' in archive_html
    assert 'data-discovery-filter="texture:remixes"' in archive_html
    assert 'data-discovery-item' in archive_html
    assert 'data-discovery-tags="' in archive_html
    assert 'data-discovery-filters="' in archive_html
    assert 'data-discovery-search="' in archive_html
    assert "Rebuilding the archive" in archive_html
    assert "The Kite String Tangle - Tennis Court" in archive_html
    assert "Listening surfaces" in archive_html

    assert "Built like an archive, not a content machine." in about_html
    assert "Browse the archive" in about_html
    assert "Read the notebook" in about_html

    assert "./rebuilding-the-archive/" in notes_index_html
    assert "../mixes/mix-036-thirtysixth/" in notes_index_html
    assert "Related mixes:" in notes_index_html
    assert "Search notes" in notes_index_html
    assert 'data-discovery-filter="state:has-related"' in notes_index_html
    assert 'data-discovery-filter="state:in-series"' in notes_index_html
    assert 'data-discovery-filter="state:has-note-links"' in notes_index_html
    assert 'data-discovery-filter="series:archive-notebook"' in notes_index_html
    assert 'data-discovery-filter="tag:archive"' in notes_index_html
    assert 'data-discovery-item' in notes_index_html
    assert 'data-discovery-filters="' in notes_index_html
    assert "Dum Dum Girls" in notes_index_html
    assert "Small runs of related notes" in notes_index_html
    assert "Nearby notes:" in notes_index_html

    assert "../../mixes/mix-034-thirtyfourth/" in note_detail_html
    assert "../../mixes/mix-036-thirtysixth/" in note_detail_html
    assert "Archive notebook" in note_detail_html
    assert "Nearby reading from the notebook" in note_detail_html
    assert "Prev and next notes" in note_detail_html

    assert "Writing tied to this mix" in mix_detail_html
    assert "../../notes/rebuilding-the-archive/" in mix_detail_html
    assert "More mixes" in mix_detail_html
    assert "Full sequence" in mix_detail_html
    assert "Provenance" in mix_detail_html
    assert "Original source" in mix_detail_html
    assert "Archive cleanup" in mix_detail_html
    assert "Preserved residue" in mix_detail_html
    assert "Imported from Tumblr RSS on April 4, 2026." in mix_detail_html
    assert "Open original post" in mix_detail_html
    assert "A legacy Mega download URL survives in the archived source data" in mix_detail_html
    assert "A sanitized copy of the original post HTML is kept for repair and import cleanup work." in mix_detail_html
    assert "Cover credit: Album art featuring work by Erik Jones." in mix_detail_html
    assert "Listening surfaces" in mix_detail_html
    assert "YouTube playback" in mix_detail_html
    assert "This queue is still being finalized" not in mix_detail_html
    assert 'data-queue-key="mix-036-thirtysixth"' in mix_detail_html
    assert "Imported Tumblr snapshot" not in mix_detail_html
    assert "Search YouTube" not in mix_detail_html
    assert "canonical cover slot" in mix_detail_html
    assert "https://mega.co.nz/" not in mix_detail_html

    assert "related note" in archive_html
    assert "highlighted track" in archive_html
    assert "YouTube playback" in mix_with_youtube_html
    assert "YouTube queue" in mix_with_youtube_html
    assert "Listening surfaces" in mix_with_youtube_html
    assert "Play here, or tap any track below to jump directly." in mix_with_youtube_html
    assert "Tap any marked row to play it above" in mix_with_youtube_html
    assert 'data-youtube-audio-player' in mix_with_youtube_html
    assert 'data-queue-key="mix-035-thirtyfifth"' in mix_with_youtube_html
    assert 'data-youtube-queue-tracklist="mix-035-thirtyfifth"' in mix_with_youtube_html
    assert 'data-youtube-queue-index="0"' in mix_with_youtube_html
    assert 'data-youtube-video-id="XYDg27tqXkI"' in mix_with_youtube_html
    assert 'data-youtube-track-trigger' in mix_with_youtube_html
    assert 'href="https://www.youtube.com/watch_videos?video_ids=' in mix_with_youtube_html
    assert "youtube.com/embed/ehpYg0NsGqA" not in mix_with_youtube_html
    assert mix_with_youtube_html.index("YouTube playback") < mix_with_youtube_html.index("Full sequence")
    assert "Bandcamp starting point" not in mix_with_youtube_html
    assert "Local editorial state" in studio_html
    assert "Validation posture" in studio_html
    assert "Archive coverage" in studio_html
    assert "Recent routes" in studio_html
    assert "Recommended next actions" in studio_html
    assert "Local commands worth keeping close" in studio_html
    assert "updateDiscovery" in site_js
    assert "youtube.com/iframe_api" in site_js
    assert "loadVideoById" in site_js
    assert "cuePlaylist" not in site_js


def test_static_build_matches_golden_route_digests(tmp_path):
    repo = prepare_temp_repo(tmp_path)
    stabilize_static_output_inputs(repo)

    result = subprocess.run(
        ["node", "scripts/build.js"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout

    route_fixtures = {
        repo / "dist" / "index.html": "home.txt",
        repo / "dist" / "archive" / "index.html": "archive.txt",
        repo / "dist" / "about" / "index.html": "about.txt",
        repo / "dist" / "mixes" / "mix-036-thirtysixth" / "index.html": "mix-036-thirtysixth.txt",
        repo / "dist" / "notes" / "index.html": "notes.txt",
        repo / "dist" / "studio" / "index.html": "studio.txt",
    }

    for route_path, fixture_name in route_fixtures.items():
        assert_matches_static_output_fixture(
            html=read_text(route_path),
            fixture_name=fixture_name,
        )


def test_static_build_normalizes_discovery_tags_for_notes_facets(tmp_path):
    repo = prepare_temp_repo(tmp_path)

    first_note_path = repo / "data" / "notes" / "how-the-mixes-are-read.json"
    first_note = json.loads(read_text(first_note_path))
    first_note["tags"] = ["Seed Data", "Late/Night", "Editorial Notes"]
    write_json(first_note_path, first_note)

    second_note_path = repo / "data" / "notes" / "rebuilding-the-archive.json"
    second_note = json.loads(read_text(second_note_path))
    second_note["tags"] = ["Seed Data", "Late/Night", "Editorial Notes"]
    write_json(second_note_path, second_note)

    result = subprocess.run(
        ["node", "scripts/build.js"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout

    notes_index_html = read_text(repo / "dist" / "notes" / "index.html")

    assert 'data-discovery-filter="tag:seed-data"' in notes_index_html
    assert 'data-discovery-filter="tag:late-night"' in notes_index_html
    assert 'data-discovery-filter="tag:editorial-notes"' in notes_index_html
    assert 'data-discovery-tags="seed-data|late-night|editorial-notes"' in notes_index_html


def test_static_build_recursively_flattens_nested_listening_provider_shapes(tmp_path):
    repo = prepare_temp_repo(tmp_path)
    mix_path = repo / "data" / "published" / "mix-035-thirtyfifth.json"
    mix = json.loads(read_text(mix_path))
    mix["listening"] = {
        "intro": "Nested listening data should still render without dropping providers or embeds.",
        "providers": {
            "playlistMirrors": [
                {
                    "provider": "YouTube",
                    "label": "Companion playlist on YouTube",
                    "url": "https://www.youtube.com/playlist?list=PL4fGSI1pDJn7gB0v9wN6Q8hX1QyQ1Z5wA",
                    "kind": "playlist",
                    "note": "Provider arrays can stay nested."
                }
            ],
            "editorial": {
                "bandcamp": {
                    "label": "Bandcamp starting point",
                    "url": "https://daily.bandcamp.com/best-of-2013",
                    "kind": "listen",
                    "note": "Provider maps should flatten recursively."
                },
                "embeds": [
                    {
                        "provider": "YouTube",
                        "title": "Thirtyfifth playlist embed",
                        "url": "https://www.youtube.com/embed/videoseries?list=PL4fGSI1pDJn7gB0v9wN6Q8hX1QyQ1Z5wA",
                        "note": "Nested embeds should survive too."
                    }
                ]
            }
        }
    }
    write_json(mix_path, mix)

    result = subprocess.run(
        ["node", "scripts/build.js"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout

    mix_html = read_text(repo / "dist" / "mixes" / "mix-035-thirtyfifth" / "index.html")

    assert "Companion playlist on YouTube" in mix_html
    assert "Bandcamp starting point" not in mix_html
    assert "Listening surfaces" in mix_html
    assert "Trusted link only" in mix_html
    assert "Trusted embed-ready" in mix_html
    assert "youtube.com/embed/videoseries" in mix_html


def test_static_build_prefers_canonical_tumblr_cover_asset_when_present(tmp_path):
    repo = prepare_temp_repo(tmp_path)

    result = subprocess.run(
        ["node", "scripts/build.js"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout

    mix_html = read_text(repo / "dist" / "mixes" / "mix-036-thirtysixth" / "index.html")

    assert "../../media/tumblr/mix-036-thirtysixth/cover.jpg" in mix_html


def test_static_build_requires_explicit_trusted_embed_data_before_rendering_preview(tmp_path):
    repo = prepare_temp_repo(tmp_path)

    youtube_mix_path = repo / "data" / "published" / "mix-035-thirtyfifth.json"
    youtube_mix = json.loads(read_text(youtube_mix_path))
    youtube_mix["listening"]["providers"]["editorial"]["embeds"] = []
    write_json(youtube_mix_path, youtube_mix)

    spotify_mix_path = repo / "data" / "published" / "mix-036-thirtysixth.json"
    spotify_mix = json.loads(read_text(spotify_mix_path))
    spotify_mix["listening"] = {
        "intro": "Explicit Spotify provider data should stay link-only.",
        "providers": [
            {
                "provider": "Spotify",
                "label": "Archive reconstruction playlist",
                "url": "https://open.spotify.com/playlist/37i9dQZF1DX4WYpdgoIcn6",
                "kind": "playlist",
                "note": "Useful as a direct playlist link, but not enough to claim embedded playback."
            }
        ]
    }
    write_json(spotify_mix_path, spotify_mix)

    result = subprocess.run(
        ["node", "scripts/build.js"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout

    youtube_mix_html = read_text(repo / "dist" / "mixes" / "mix-035-thirtyfifth" / "index.html")
    spotify_mix_html = read_text(repo / "dist" / "mixes" / "mix-036-thirtysixth" / "index.html")

    assert "youtube.com/embed/videoseries" not in youtube_mix_html
    assert "YouTube playback" in youtube_mix_html
    assert "Trusted link only" in spotify_mix_html
    assert "open.spotify.com/embed/playlist" not in spotify_mix_html


def test_static_build_demotes_uncertain_listening_data_on_mix_detail_pages(tmp_path):
    repo = prepare_temp_repo(tmp_path)

    mix_path = repo / "data" / "published" / "mix-036-thirtysixth.json"
    mix = json.loads(read_text(mix_path))
    mix["listening"] = {
        "intro": "These links should stay visibly tentative.",
        "providers": [
            {
                "provider": "YouTube",
                "label": "Questionable mirror",
                "url": "https://open.spotify.com/playlist/37i9dQZF1DX4WYpdgoIcn6",
                "kind": "mixtape"
            }
        ],
        "embeds": [
            {
                "provider": "Spotify",
                "title": "Untrusted preview",
                "url": "https://www.youtube.com/embed/videoseries?list=PL1234567890"
            }
        ]
    }
    write_json(mix_path, mix)

    result = subprocess.run(
        ["node", "scripts/build.js"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout

    mix_html = read_text(repo / "dist" / "mixes" / "mix-036-thirtysixth" / "index.html")

    assert "Uncertain leads" in mix_html
    assert "Questionable mirror" in mix_html
    assert "Inspect link" in mix_html
    assert "<iframe" not in mix_html
    assert "Trusted embed-ready" not in mix_html


def test_static_build_surfaces_listening_warnings_in_studio_health(tmp_path):
    repo = prepare_temp_repo(tmp_path)

    mix_path = repo / "data" / "published" / "mix-035-thirtyfifth.json"
    mix = json.loads(read_text(mix_path))
    mix["listening"] = {
        "intro": "Suspicious listening data should show up in studio health.",
        "providers": [
            {
                "provider": "YouTube",
                "label": "Broken provider mirror",
                "url": "https://open.spotify.com/playlist/37i9dQZF1DX4WYpdgoIcn6",
                "kind": "mixtape",
            }
        ],
        "embeds": [
            {
                "provider": "Spotify",
                "title": "Wrong embed host",
                "url": "https://www.youtube.com/embed/videoseries?list=PL1234567890",
            }
        ],
    }
    write_json(mix_path, mix)

    result = subprocess.run(
        ["node", "scripts/build.js"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout

    studio_html = read_text(repo / "dist" / "studio" / "index.html")

    assert "Listening warnings" in studio_html
    assert "Latest flagged: Thirtyfifth" in studio_html
    assert "Listening health" in studio_html
    assert "Review listening/provider payloads for Thirtyfifth" in studio_html
    assert "provider &quot;YouTube&quot; uses unsupported kind &quot;mixtape&quot;" in studio_html


def test_static_build_fails_loudly_on_malformed_canonical_note_json(tmp_path):
    repo = prepare_temp_repo(tmp_path)
    malformed_note_path = repo / "data" / "notes" / "rebuilding-the-archive.json"
    malformed_note_path.write_text("{\n  \"slug\": \"broken-note\",\n", encoding="utf-8")

    result = subprocess.run(
        ["node", "scripts/build.js"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "Could not parse data/notes/rebuilding-the-archive.json" in (result.stderr or result.stdout)


def test_static_build_emits_phosphor_queue_controls_and_no_legacy_glyphs(tmp_path):
    repo = prepare_temp_repo(tmp_path)

    result = subprocess.run(
        ["node", "scripts/build.js"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout

    mix_html = read_text(repo / "dist" / "mixes" / "mix-036-thirtysixth" / "index.html")

    assert "@phosphor-icons/web@2.1.1" in mix_html
    assert 'class="ph ph-skip-back"' in mix_html
    assert 'class="ph ph-play" data-youtube-player-toggle-icon' in mix_html
    assert 'class="ph ph-skip-forward"' in mix_html
    assert 'class="ph ph-speaker-high" data-youtube-player-mute-icon' in mix_html
    assert 'class="ph ph-play tracklist__affordance-icon"' in mix_html

    for legacy_marker in ("‹‹", "››", "▶", "❚❚", ">VOL<", ">MUT<"):
        assert legacy_marker not in mix_html


def test_site_js_keeps_mobile_playback_start_fallback_contract(tmp_path):
    repo = prepare_temp_repo(tmp_path)

    result = subprocess.run(
        ["node", "scripts/build.js"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout

    site_js = read_text(repo / "dist" / "assets" / "site.js")

    assert "shouldLoadWithinGesture" in site_js
    assert "window.YT.PlayerState.CUED" in site_js
    assert "window.YT.PlayerState.UNSTARTED" in site_js
    assert "window.YT.PlayerState.ENDED" in site_js
    assert "instance.player.loadVideoById(currentVideoId);" in site_js
    assert "instance.player.playVideo();" in site_js
    assert "instance.toggleIcon.className = `ph ${isPlaying ? 'ph-pause' : 'ph-play'}`;" in site_js
    assert "instance.muteIcon.className = `ph ${isMuted ? 'ph-speaker-slash' : 'ph-speaker-high'}`;" in site_js
    assert "if (Number.isInteger(instance.pendingIndex))" in site_js
    assert "instance.pendingIndex = nextIndex;" in site_js
    assert "instance.pendingIndex = 0;" in site_js
    assert "playYoutubeQueueIndex(instance, fallbackIndex, { autoplay: instance.shouldAutoplay });" in site_js


def test_site_css_keeps_youtube_iframe_offscreen_without_zero_clipping(tmp_path):
    repo = prepare_temp_repo(tmp_path)

    result = subprocess.run(
        ["node", "scripts/build.js"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout

    site_css = read_text(repo / "dist" / "assets" / "site.css")
    player_host_block = site_css.split('.youtube-player-host {', 1)[1].split('}', 1)[0]

    assert 'left: -9999px;' in player_host_block
    assert 'width: 220px;' in player_host_block
    assert 'height: 220px;' in player_host_block
    assert 'opacity: 0.01;' in player_host_block
    assert 'pointer-events: none;' in player_host_block
    assert 'clip-path:' not in player_host_block
    assert 'clip:' not in player_host_block


def test_static_build_renders_embed_ready_player_for_resolved_youtube_queues(tmp_path):
    repo = prepare_temp_repo(tmp_path)

    result = subprocess.run(
        ["node", "scripts/build.js"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout

    youtube_payloads = sorted((repo / "data" / "youtube").glob("*.json"))
    assert youtube_payloads, "Expected seeded YouTube match payloads"

    for payload_path in youtube_payloads:
        payload = json.loads(read_text(payload_path))
        summary = payload.get("summary") or {}
        generated_embed = payload.get("generatedEmbed") or {}
        unresolved_tracks = int(summary.get("unresolvedTracks") or 0)
        video_ids = [str(value).strip() for value in generated_embed.get("videoIds") or [] if str(value).strip()]
        mix_slug = str(payload.get("mixSlug") or payload_path.stem).strip()

        mix_route = repo / "dist" / "mixes" / mix_slug / "index.html"
        if not mix_route.exists() or not video_ids:
            continue

        mix_html = read_text(mix_route)

        if unresolved_tracks == 0:
            assert "This queue is still being finalized" not in mix_html
            assert "Playback is not ready yet while this mix's YouTube queue is being finalized" not in mix_html
            assert "data-youtube-audio-player" in mix_html
            assert f'data-queue-key="{mix_slug}"' in mix_html
