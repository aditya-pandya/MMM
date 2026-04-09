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


def build_static_site(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["node", "scripts/build.js"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )


def evaluate_site_js_asset(repo: Path, scenario: str) -> object:
    site_js = read_text(repo / "dist" / "assets" / "site.js")
    script = "\n".join(
        [
            "const vm = require('vm');",
            f"const siteJs = {json.dumps(site_js)};",
            "const context = {",
            "  module: { exports: {} },",
            "  exports: {},",
            "  console,",
            "  Date,",
            "  JSON,",
            "  Set,",
            "  Map,",
            "  Math,",
            "  Number,",
            "  String,",
            "  Boolean,",
            "  Array,",
            "  Object,",
            "  Promise,",
            "};",
            "context.window = {",
            "  setTimeout: () => 1,",
            "  clearTimeout() {},",
            "  setInterval: () => 1,",
            "  clearInterval() {},",
            "  YT: {",
            "    PlayerState: {",
            "      UNSTARTED: -1,",
            "      ENDED: 0,",
            "      PLAYING: 1,",
            "      PAUSED: 2,",
            "      BUFFERING: 3,",
            "      CUED: 5,",
            "    },",
            "  },",
            "};",
            "context.document = {",
            "  addEventListener() {},",
            "  querySelector() { return null; },",
            "  querySelectorAll() { return []; },",
            "  createElement() { return { async: true, onerror: null }; },",
            "  head: { append() {} },",
            "};",
            "vm.createContext(context);",
            "vm.runInContext(siteJs + '\\nmodule.exports = { syncYoutubeAudioPlayerUi, recoverStalledYoutubePlayback, requestYoutubePlayback, STALLED_AUTOPLAY_MS, STALLED_RECOVERY_SKIP_MS };', context);",
            "const exported = context.module.exports;",
            "const result = (() => {",
            scenario,
            "})();",
            "console.log(JSON.stringify(result));",
        ]
    )
    result = subprocess.run(
        ["node", "-e", script],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    return json.loads(result.stdout)


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
    mix_detail_html = read_text(dist_dir / "mixes" / "mix-036-thirtysixth" / "index.html")
    mix_with_youtube_html = read_text(dist_dir / "mixes" / "mix-035-thirtyfifth" / "index.html")
    site_js = read_text(dist_dir / "assets" / "site.js")

    assert "Read more about Monday Music Mix" in home_html
    assert "From the notebook" not in home_html
    assert "Notes related to Thirtysixth" not in home_html
    assert 'href="./notes/"' not in home_html
    assert ">Notes<" not in home_html

    assert "Search archive" in archive_html
    assert 'data-discovery-filter="state:has-related"' not in archive_html
    assert 'data-discovery-filter="state:has-highlights"' in archive_html
    assert 'data-discovery-filter="state:has-listening"' in archive_html
    assert 'data-discovery-filter="texture:covers"' in archive_html
    assert 'data-discovery-filter="texture:remixes"' in archive_html
    assert 'data-discovery-item' in archive_html
    assert 'data-discovery-tags="' in archive_html
    assert 'data-discovery-filters="' in archive_html
    assert 'data-discovery-search="' in archive_html
    assert "The Kite String Tangle - Tennis Court" in archive_html
    assert "Playable" in archive_html

    assert "A personal archive, kept with care." in about_html
    assert "A weekly habit that kept leaving a trace." in about_html
    assert "Because music remembers things differently." in about_html
    assert "Read the notebook" not in about_html

    assert not (dist_dir / "notes").exists()
    assert not (dist_dir / "studio").exists()

    assert "Writing tied to this mix" not in mix_detail_html
    assert "../../notes/rebuilding-the-archive/" not in mix_detail_html
    assert "More mixes" in mix_detail_html
    assert "Full sequence" in mix_detail_html
    assert '<p class="eyebrow">Source</p>' not in mix_detail_html
    assert "Provenance" not in mix_detail_html
    assert "Original source" not in mix_detail_html
    assert "Original post" not in mix_detail_html
    assert "Archive cleanup" not in mix_detail_html
    assert "Cleanup choices" not in mix_detail_html
    assert "Preserved residue" not in mix_detail_html
    assert "Legacy snapshot" not in mix_detail_html
    assert "Imported from Tumblr RSS on April 4, 2026." not in mix_detail_html
    assert "Open original post" not in mix_detail_html
    assert "A legacy Mega download URL survives in the archived source data" not in mix_detail_html
    assert "A sanitized copy of the original post HTML is kept for repair and import cleanup work." not in mix_detail_html
    assert "canonical cover slot" not in mix_detail_html
    assert "Cover credit: Album art featuring work by Erik Jones." not in mix_detail_html
    assert "Listen" in mix_detail_html
    assert "Play this mix" in mix_detail_html
    assert "This queue is still being finalized" not in mix_detail_html
    assert 'data-queue-key="mix-036-thirtysixth"' in mix_detail_html
    assert "Imported Tumblr snapshot" not in mix_detail_html
    assert "Search YouTube" not in mix_detail_html
    assert "https://mega.co.nz/" not in mix_detail_html
    assert "1 YouTube queue" not in mix_detail_html
    assert '<p class="provider-card__eyebrow">YouTube queue</p>' not in mix_detail_html
    assert ">Full mix<" in mix_detail_html
    assert "Tap play or choose a track below." not in mix_detail_html
    assert "tracklist stays in sync" not in mix_detail_html
    assert "tracklist below stays in sync" not in mix_detail_html
    assert "Open Thirtysixth on YouTube" not in mix_detail_html
    assert ">Open on YouTube<" in mix_detail_html

    assert "highlighted track" in archive_html
    assert "Play this mix" in mix_with_youtube_html
    assert ">Full mix<" in mix_with_youtube_html
    assert "Listen" in mix_with_youtube_html
    assert "Provenance" not in mix_with_youtube_html
    assert "Original source" not in mix_with_youtube_html
    assert "Tap play or choose a track below." not in mix_with_youtube_html
    assert "Tap any marked row to play it above" not in mix_with_youtube_html
    assert 'data-youtube-audio-player' in mix_with_youtube_html
    assert 'data-queue-key="mix-035-thirtyfifth"' in mix_with_youtube_html
    assert 'data-youtube-queue-tracklist="mix-035-thirtyfifth"' in mix_with_youtube_html
    assert 'data-youtube-queue-index="0"' in mix_with_youtube_html
    assert 'data-youtube-video-id="XYDg27tqXkI"' in mix_with_youtube_html
    assert 'data-youtube-track-trigger' in mix_with_youtube_html
    assert 'href="https://www.youtube.com/watch_videos?video_ids=' in mix_with_youtube_html
    assert "youtube.com/embed/ehpYg0NsGqA" not in mix_with_youtube_html
    assert mix_with_youtube_html.index("Play this mix") < mix_with_youtube_html.index("Full sequence")
    assert "Bandcamp starting point" not in mix_with_youtube_html
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
    }

    for route_path, fixture_name in route_fixtures.items():
        assert_matches_static_output_fixture(
            html=read_text(route_path),
            fixture_name=fixture_name,
        )


def test_static_build_does_not_emit_public_note_routes(tmp_path):
    repo = prepare_temp_repo(tmp_path)

    result = subprocess.run(
        ["node", "scripts/build.js"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert not (repo / "dist" / "notes").exists()


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
    assert "Listen" in mix_html
    assert "Listen elsewhere" in mix_html
    assert "Preview" in mix_html
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
    assert "Play this mix" in youtube_mix_html
    assert "Listen elsewhere" in spotify_mix_html
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

    assert "Other links" in mix_html
    assert "Questionable mirror" in mix_html
    assert "Open link" in mix_html
    assert "<iframe" not in mix_html
    assert "Trusted embed-ready" not in mix_html


def test_static_build_does_not_emit_public_studio_route(tmp_path):
    repo = prepare_temp_repo(tmp_path)

    mix_path = repo / "data" / "published" / "mix-035-thirtyfifth.json"
    mix = json.loads(read_text(mix_path))
    mix["listening"] = {
        "intro": "Suspicious listening data should not create a public studio route.",
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
    assert not (repo / "dist" / "studio").exists()


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
    assert 'tracklist__affordance-icon' not in mix_html

    for legacy_marker in ("‹‹", "››", "▶", "❚❚", ">VOL<", ">MUT<"):
        assert legacy_marker not in mix_html


def test_site_js_preserves_cued_autoplay_recovery_timers_until_playback_stabilizes(tmp_path):
    repo = prepare_temp_repo(tmp_path)

    result = build_static_site(repo)

    assert result.returncode == 0, result.stderr or result.stdout

    runtime = evaluate_site_js_asset(
        repo,
        """
const stateClassList = {
  active: false,
  toggle(_name, value) { this.active = Boolean(value); },
  remove() { this.active = false; },
};
let loadCalls = 0;
const realNow = Date.now;
Date.now = () => 5000;
const instance = {
  player: {
    getCurrentTime: () => 0,
    getDuration: () => 0,
    getPlayerState: () => context.window.YT.PlayerState.CUED,
    getVideoData: () => ({ title: 'Track A' }),
    isMuted: () => false,
    getVolume: () => 88,
    loadVideoById: () => { loadCalls += 1; },
  },
  isReady: true,
  isScrubbing: false,
  videoIds: ['abc123'],
  trackLabels: ['Track A'],
  trackItems: [{
    dataset: { youtubeQueueIndex: '0' },
    classList: { add() {}, remove() {}, toggle() {} },
    element: { setAttribute() {} },
    trigger: { setAttribute() {} },
  }],
  currentIndex: 0,
  pendingIndex: 0,
  shouldAutoplay: true,
  autoplayRequestedAt: 2000,
  lastRecoveryAttemptAt: 0,
  failedIndexes: new Set(),
  statusOverride: null,
  state: { textContent: '', classList: stateClassList },
  track: { textContent: '' },
  meta: { textContent: '' },
  elapsed: { textContent: '' },
  duration: { textContent: '' },
  previous: { disabled: false },
  next: { disabled: false },
  mute: { disabled: false, setAttribute() {} },
  volume: { disabled: false, value: '100' },
  toggle: { disabled: false, setAttribute() {} },
  progress: { disabled: false, value: '0' },
  toggleIcon: { className: '' },
  toggleLabel: { textContent: '' },
  muteIcon: { className: '' },
  muteLabel: { textContent: '' },
};
exported.syncYoutubeAudioPlayerUi(instance);
exported.recoverStalledYoutubePlayback(instance);
Date.now = realNow;
return {
  autoplayRequestedAt: instance.autoplayRequestedAt,
  lastRecoveryAttemptAt: instance.lastRecoveryAttemptAt,
  loadCalls,
  state: instance.state.textContent,
};
""",
    )

    assert runtime["autoplayRequestedAt"] == 2000
    assert runtime["lastRecoveryAttemptAt"] == 5000
    assert runtime["loadCalls"] == 1
    assert runtime["state"] == "Ready"


def test_site_js_request_playback_does_not_force_unmute_before_start(tmp_path):
    repo = prepare_temp_repo(tmp_path)

    result = build_static_site(repo)

    assert result.returncode == 0, result.stderr or result.stdout

    runtime = evaluate_site_js_asset(
        repo,
        """
let loadCalls = 0;
let playCalls = 0;
let unmuteCalls = 0;
context.window.setTimeout = () => 1;
const instance = {
  player: {
    getPlayerState: () => context.window.YT.PlayerState.CUED,
    loadVideoById: () => { loadCalls += 1; },
    playVideo: () => { playCalls += 1; },
    unMute: () => { unmuteCalls += 1; },
  },
  isReady: true,
  shouldAutoplay: true,
  autoplayRequestedAt: 0,
  lastRecoveryAttemptAt: 99,
  currentIndex: 0,
  videoIds: ['abc123'],
  statusOverride: { stateText: 'Unavailable', metaText: 'retry me' },
};
exported.requestYoutubePlayback(instance);
return {
  loadCalls,
  playCalls,
  unmuteCalls,
  autoplayRequestedAt: instance.autoplayRequestedAt > 0,
  lastRecoveryAttemptAt: instance.lastRecoveryAttemptAt,
  statusOverride: instance.statusOverride,
};
""",
    )

    assert runtime["loadCalls"] == 1
    assert runtime["playCalls"] == 0
    assert runtime["unmuteCalls"] == 0
    assert runtime["autoplayRequestedAt"] is True
    assert runtime["lastRecoveryAttemptAt"] == 0
    assert runtime["statusOverride"] is None


def test_site_css_keeps_youtube_iframe_in_card_viewport_for_mobile_playback(tmp_path):
    repo = prepare_temp_repo(tmp_path)

    result = build_static_site(repo)

    assert result.returncode == 0, result.stderr or result.stdout

    site_css = read_text(repo / "dist" / "assets" / "site.css")
    player_card_block = site_css.split('.provider-card--player,', 1)[1].split('}', 1)[0]
    player_host_block = site_css.split('.youtube-player-host {', 1)[1].split('}', 1)[0]

    assert 'position: relative;' in player_card_block
    assert '> :not(.youtube-player-host)' in site_css
    assert 'top: 0;' in player_host_block
    assert 'right: 0;' in player_host_block
    assert 'left:' not in player_host_block
    assert 'width: 220px;' in player_host_block
    assert 'height: 220px;' in player_host_block
    assert 'min-width: 220px;' in player_host_block
    assert 'min-height: 220px;' in player_host_block
    assert 'opacity: 0.01;' in player_host_block
    assert 'pointer-events: none;' in player_host_block
    assert 'transform:' not in player_host_block
    assert 'z-index: 0;' in player_host_block
    assert 'clip-path:' not in player_host_block
    assert 'clip:' not in player_host_block
    assert 'translate' not in player_host_block
    assert 'scale' not in player_host_block


def test_site_js_terminal_stall_state_overrides_loading_forever(tmp_path):
    repo = prepare_temp_repo(tmp_path)

    result = build_static_site(repo)

    assert result.returncode == 0, result.stderr or result.stdout

    runtime = evaluate_site_js_asset(
        repo,
        """
const stateClassList = {
  active: false,
  toggle(_name, value) { this.active = Boolean(value); },
  remove() { this.active = false; },
};
const realNow = Date.now;
Date.now = () => 10000;
const instance = {
  player: {
    getCurrentTime: () => 0,
    getDuration: () => 0,
    getPlayerState: () => context.window.YT.PlayerState.UNSTARTED,
    getVideoData: () => ({ title: 'Track A' }),
    isMuted: () => false,
    getVolume: () => 75,
    loadVideoById: () => {},
  },
  isReady: true,
  isScrubbing: false,
  videoIds: ['abc123'],
  trackLabels: ['Track A'],
  trackItems: [],
  currentIndex: 0,
  pendingIndex: 0,
  shouldAutoplay: true,
  autoplayRequestedAt: 10000 - exported.STALLED_RECOVERY_SKIP_MS - 50,
  lastRecoveryAttemptAt: 0,
  failedIndexes: new Set(),
  statusOverride: null,
  state: { textContent: '', classList: stateClassList },
  track: { textContent: '' },
  meta: { textContent: '' },
  elapsed: { textContent: '' },
  duration: { textContent: '' },
  previous: { disabled: false },
  next: { disabled: false },
  mute: { disabled: false, setAttribute() {} },
  volume: { disabled: false, value: '100' },
  toggle: { disabled: false, setAttribute() {} },
  progress: { disabled: false, value: '0' },
  toggleIcon: { className: '' },
  toggleLabel: { textContent: '' },
  muteIcon: { className: '' },
  muteLabel: { textContent: '' },
};
exported.syncYoutubeAudioPlayerUi(instance);
const beforeRecovery = instance.state.textContent;
exported.recoverStalledYoutubePlayback(instance);
exported.syncYoutubeAudioPlayerUi(instance);
Date.now = realNow;
return {
  beforeRecovery,
  afterRecovery: instance.state.textContent,
  meta: instance.meta.textContent,
  shouldAutoplay: instance.shouldAutoplay,
  autoplayRequestedAt: instance.autoplayRequestedAt,
  lastRecoveryAttemptAt: instance.lastRecoveryAttemptAt,
  failedIndexes: Array.from(instance.failedIndexes),
};
""",
    )

    assert runtime["beforeRecovery"] == "Loading"
    assert runtime["afterRecovery"] == "Unavailable"
    assert runtime["meta"] == "Playback is unavailable here. Open it on YouTube instead."
    assert runtime["shouldAutoplay"] is False
    assert runtime["autoplayRequestedAt"] == 0
    assert runtime["lastRecoveryAttemptAt"] == 0
    assert runtime["failedIndexes"] == [0]


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
