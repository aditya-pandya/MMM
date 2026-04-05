#!/usr/bin/env python3
"""Import Tumblr RSS/XML content into structured MMM mix JSON files."""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import urlparse
from urllib.request import urlopen
import xml.etree.ElementTree as ET

SCHEMA_VERSION = "1.0"
DEFAULT_SITE = "Monday Music Mix"
IGNORED_TITLE_PATTERNS = [
    re.compile(r"\bask\b", re.IGNORECASE),
    re.compile(r"\bi[’']?m all tapped out\b", re.IGNORECASE),
]
ORDINAL_WORDS = {
    "first": 1,
    "second": 2,
    "third": 3,
    "fourth": 4,
    "fifth": 5,
    "sixth": 6,
    "seventh": 7,
    "eighth": 8,
    "ninth": 9,
    "tenth": 10,
    "eleventh": 11,
    "twelfth": 12,
    "thirteenth": 13,
    "fourteenth": 14,
    "fifteenth": 15,
    "sixteenth": 16,
    "seventeenth": 17,
    "eighteenth": 18,
    "nineteenth": 19,
    "twentieth": 20,
    "twentyfirst": 21,
    "twenty-first": 21,
    "twentysecond": 22,
    "twenty-second": 22,
    "twentythird": 23,
    "twenty-third": 23,
    "twentyfourth": 24,
    "twenty-fourth": 24,
    "twentyfifth": 25,
    "twenty-fifth": 25,
    "twentysixth": 26,
    "twenty-sixth": 26,
    "twentyseventh": 27,
    "twenty-seventh": 27,
    "twentyeighth": 28,
    "twenty-eighth": 28,
    "twentyninth": 29,
    "twenty-ninth": 29,
    "thirtieth": 30,
    "thirtyfirst": 31,
    "thirty-first": 31,
    "thirtysecond": 32,
    "thirty-second": 32,
    "thirtythird": 33,
    "thirty-third": 33,
    "thirtyfourth": 34,
    "thirty-fourth": 34,
    "thirtyfifth": 35,
    "thirty-fifth": 35,
    "thirtysixth": 36,
    "thirty-sixth": 36,
}


@dataclass
class Paragraph:
    text: str
    html: str


@dataclass
class TrackCandidate:
    text: str
    is_favorite: bool = False


@dataclass
class ParsedDescription:
    heading: Optional[str] = None
    paragraphs: list[Paragraph] = field(default_factory=list)
    track_candidates: list[TrackCandidate] = field(default_factory=list)
    download_links: list[str] = field(default_factory=list)
    images: list[str] = field(default_factory=list)


@dataclass
class IntroMetadata:
    summary: str
    intro: list[str]
    cover_credit: Optional[str] = None
    editorial_highlights: list[str] = field(default_factory=list)
    favorite_track_cue: Optional[str] = None


class TumblrDescriptionParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parsed = ParsedDescription()
        self._heading_parts: list[str] = []
        self._paragraph_parts: list[str] = []
        self._li_parts: list[str] = []
        self._tag_stack: list[str] = []
        self._in_heading = False
        self._in_paragraph = False
        self._in_li = False
        self._li_favorite = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        attr_map = dict(attrs)
        self._tag_stack.append(tag)
        if tag in {"h1", "h2", "h3"}:
            self._in_heading = True
            self._heading_parts = []
        elif tag == "p":
            self._in_paragraph = True
            self._paragraph_parts = []
        elif tag == "li":
            self._in_li = True
            self._li_parts = []
            self._li_favorite = False
        elif tag == "br":
            self._push_text("\n")
        elif tag == "strong" and self._in_li:
            self._li_favorite = True
        elif tag == "a":
            href = attr_map.get("href")
            if href and href not in self.parsed.download_links:
                lower = href.lower()
                if any(token in lower for token in ["download", "mega", "dropbox", "drive.google", "mediafire", "sendspace"]):
                    self.parsed.download_links.append(href)
        elif tag == "img":
            src = attr_map.get("src")
            if src and src not in self.parsed.images:
                self.parsed.images.append(src)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"h1", "h2", "h3"} and self._in_heading:
            heading = normalize_whitespace("".join(self._heading_parts))
            if heading:
                self.parsed.heading = heading
            self._in_heading = False
        elif tag == "p" and self._in_paragraph:
            raw = "".join(self._paragraph_parts)
            text = normalize_whitespace(raw)
            if text:
                self.parsed.paragraphs.append(Paragraph(text=text, html=raw.strip()))
            self._in_paragraph = False
        elif tag == "li" and self._in_li:
            text = normalize_whitespace("".join(self._li_parts))
            if text:
                self.parsed.track_candidates.append(TrackCandidate(text=text, is_favorite=self._li_favorite))
            self._in_li = False
            self._li_favorite = False
        if self._tag_stack:
            self._tag_stack.pop()

    def handle_data(self, data: str) -> None:
        self._push_text(data)

    def _push_text(self, text: str) -> None:
        if self._in_heading:
            self._heading_parts.append(text)
        if self._in_paragraph:
            self._paragraph_parts.append(text)
        if self._in_li:
            self._li_parts.append(text)


def normalize_whitespace(value: str) -> str:
    value = html.unescape(value or "")
    value = value.replace("\u00a0", " ")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def slugify(value: str) -> str:
    value = html.unescape(value or "")
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-+", "-", value)
    return value.strip("-") or "mix"


def title_case_mix_number(number: int) -> str:
    return f"Monday Music Mix #{number}"


def extract_mix_number(*candidates: Optional[str]) -> Optional[int]:
    for candidate in candidates:
        if not candidate:
            continue
        direct = re.search(r"(?:monday\s+music\s+mix\s*[:#-]?\s*)(\d{1,3})", candidate, re.IGNORECASE)
        if direct:
            return int(direct.group(1))
        plain_num = re.search(r"\b(\d{1,3})(?:st|nd|rd|th)?\b", candidate)
        if plain_num and "track" not in candidate.lower():
            return int(plain_num.group(1))
        collapsed = slugify(candidate).replace("-", "")
        for word in sorted(ORDINAL_WORDS, key=lambda value: len(value.replace("-", "")), reverse=True):
            if word.replace("-", "") in collapsed:
                return ORDINAL_WORDS[word]
    return None


def parse_pubdate(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    dt = parsedate_to_datetime(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def split_track_line(line: str) -> tuple[Optional[str], Optional[str]]:
    line = normalize_whitespace(line)
    if not line:
        return None, None
    line = re.sub(r"^\d+[.)-]?\s*", "", line)
    line = re.sub(r"^[•*-]\s*", "", line)
    parts = re.split(r"\s+[–—-]\s+", line, maxsplit=1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    if " - " in line:
        artist, title = line.split(" - ", 1)
        return artist.strip(), title.strip()
    return None, line


def parse_description(description_html: str) -> ParsedDescription:
    parser = TumblrDescriptionParser()
    parser.feed(description_html or "")
    return parser.parsed


def should_skip_item(title: str, description: str) -> bool:
    blob = f"{title}\n{description}"
    if "tracklist" not in blob.lower() and "monday music mix" not in blob.lower():
        return True
    return any(pattern.search(blob) for pattern in IGNORED_TITLE_PATTERNS)


def build_slug(mix_number: Optional[int], heading: Optional[str], title: str) -> str:
    if mix_number is not None:
        base = f"mix-{mix_number:03d}"
        if heading:
            return f"{base}-{slugify(heading)}"
        return base
    return slugify(heading or title)


FAVORITE_TRACK_CUE_RE = re.compile(
    r"^\*?\s*tracks?\s+in\s+(?P<style>[a-z0-9 #/_-]+)\s+indicate my favou?rites\b",
    re.IGNORECASE,
)
EDITORIAL_HIGHLIGHT_RE = re.compile(r"^(hat tip|h/t)\s*:", re.IGNORECASE)
TRACK_DOWNLOAD_LABEL_RE = re.compile(
    r"^(download album|part\s+\d+\b.*(?:\|\s*part\s+\d+\b.*)*)$",
    re.IGNORECASE,
)
TRACK_COVER_RE = re.compile(r"\([^)]*\bcover\b[^)]*\)", re.IGNORECASE)
TRACK_REMIX_RE = re.compile(r"\([^)]*\b(remix|mix)\b[^)]*\)", re.IGNORECASE)


def is_cover_credit_line(text: str) -> bool:
    lowered = normalize_whitespace(text).lower()
    return lowered.startswith(
        (
            "album art featuring",
            "album art by",
            "cover art featuring",
            "cover art by",
            "artwork by",
            "art by",
        )
    )


def paragraphs_to_intro_metadata(paragraphs: Iterable[Paragraph]) -> IntroMetadata:
    intro: list[str] = []
    editorial_highlights: list[str] = []
    cover_credit: Optional[str] = None
    favorite_track_cue: Optional[str] = None

    for paragraph in paragraphs:
        text = paragraph.text
        lowered = text.lower()
        if lowered.startswith("tracklist"):
            continue
        if text.startswith("Monday Music Mix:"):
            continue
        if TRACK_DOWNLOAD_LABEL_RE.fullmatch(text):
            continue
        if is_cover_credit_line(text):
            cover_credit = text
            continue
        if FAVORITE_TRACK_CUE_RE.match(text):
            favorite_track_cue = text
            continue
        if EDITORIAL_HIGHLIGHT_RE.match(text):
            editorial_highlights.append(text)
            continue
        intro.append(text)

    return IntroMetadata(
        summary=intro[0] if intro else "",
        intro=intro,
        cover_credit=cover_credit,
        editorial_highlights=editorial_highlights,
        favorite_track_cue=favorite_track_cue,
    )


def build_tracks_from_candidates(candidates: Iterable[TrackCandidate]) -> tuple[list[dict], Counter[str]]:
    tracks = []
    artist_counter: Counter[str] = Counter()
    for idx, candidate in enumerate(candidates, start=1):
        artist, track_title = split_track_line(candidate.text)
        primary_artist = artist or "Unknown Artist"
        artist_counter[primary_artist] += 1
        tracks.append(
            {
                "position": idx,
                "artist": primary_artist,
                "title": track_title or candidate.text,
                "displayText": candidate.text,
                "isFavorite": candidate.is_favorite,
            }
        )
    return tracks, artist_counter


def detect_track_mentions(tracks: Iterable[dict]) -> tuple[list[str], list[str]]:
    cover_tracks: list[str] = []
    remix_tracks: list[str] = []
    for track in tracks:
        display_text = normalize_whitespace(track.get("displayText") or f"{track.get('artist', '')} - {track.get('title', '')}")
        if TRACK_COVER_RE.search(display_text):
            cover_tracks.append(display_text)
        if TRACK_REMIX_RE.search(display_text):
            remix_tracks.append(display_text)
    return cover_tracks, remix_tracks


def build_track_stats(tracks: list[dict], top_artists: list[str] | None = None) -> dict:
    favorite_tracks = [track["displayText"] for track in tracks if track["isFavorite"]]
    cover_tracks, remix_tracks = detect_track_mentions(tracks)
    return {
        "trackCount": len(tracks),
        "favoriteCount": len(favorite_tracks),
        "favoriteTracks": favorite_tracks,
        "topArtists": (top_artists or [])[:5],
        "coverCount": len(cover_tracks),
        "coverTracks": cover_tracks,
        "remixCount": len(remix_tracks),
        "remixTracks": remix_tracks,
    }


def refresh_mix_from_legacy_html(mix: dict) -> dict:
    legacy = deepcopy(mix.get("legacy") or {})
    description_html = legacy.get("descriptionHtml")
    if not description_html:
        return deepcopy(mix)

    parsed = parse_description(description_html)
    intro_metadata = paragraphs_to_intro_metadata(parsed.paragraphs)

    updated = deepcopy(mix)
    heading = legacy.get("tumblrHeading") or parsed.heading or updated.get("displayTitle") or updated.get("title")

    if intro_metadata.summary:
        updated["summary"] = intro_metadata.summary
    if intro_metadata.intro:
        updated["intro"] = intro_metadata.intro

    tracks = deepcopy(updated.get("tracks") or [])
    parsed_tracks, artist_counter = build_tracks_from_candidates(parsed.track_candidates)
    if parsed_tracks and len(parsed_tracks) == len(tracks):
        for existing_track, parsed_track in zip(tracks, parsed_tracks):
            existing_track["isFavorite"] = parsed_track["isFavorite"]
            existing_track["displayText"] = parsed_track["displayText"]
    elif parsed_tracks and not tracks:
        tracks = parsed_tracks

    if tracks:
        top_artists = [name for name, _ in artist_counter.most_common(5)] if artist_counter else [
            track["artist"] for track in tracks if track.get("artist")
        ]
        deduped_top_artists: list[str] = []
        for artist in top_artists:
            if artist not in deduped_top_artists:
                deduped_top_artists.append(artist)
        updated["tracks"] = tracks
        updated["stats"] = build_track_stats(tracks, top_artists=deduped_top_artists)

    cover = deepcopy(updated.get("cover") or {})
    if parsed.images and not cover.get("imageUrl"):
        cover["imageUrl"] = parsed.images[0]
    if cover.get("imageUrl") and not cover.get("alt"):
        cover["alt"] = f"Cover art for {heading}"
    if intro_metadata.cover_credit is not None:
        cover["credit"] = intro_metadata.cover_credit
    if cover:
        updated["cover"] = {
            "imageUrl": cover.get("imageUrl"),
            "alt": cover.get("alt"),
            "credit": cover.get("credit"),
        }

    legacy["tumblrHeading"] = heading
    if intro_metadata.favorite_track_cue:
        legacy["favoriteTrackCue"] = intro_metadata.favorite_track_cue
    else:
        legacy.pop("favoriteTrackCue", None)
    if intro_metadata.editorial_highlights:
        legacy["editorialHighlights"] = intro_metadata.editorial_highlights
    else:
        legacy.pop("editorialHighlights", None)
    updated["legacy"] = legacy
    return updated


def convert_item_to_mix(item: ET.Element) -> Optional[dict]:
    title = normalize_whitespace(item.findtext("title", ""))
    description_html = item.findtext("description", "") or ""
    if should_skip_item(title, description_html):
        return None

    parsed = parse_description(description_html)
    heading = parsed.heading or title.splitlines()[0].strip()
    mix_number = extract_mix_number(title, heading, description_html)
    slug = build_slug(mix_number, heading, title)
    published_at = parse_pubdate(item.findtext("pubDate"))
    source_url = normalize_whitespace(item.findtext("link", ""))
    intro_metadata = paragraphs_to_intro_metadata(parsed.paragraphs)
    download_url = parsed.download_links[0] if parsed.download_links else None
    cover_image = parsed.images[0] if parsed.images else None

    tracks, artist_counter = build_tracks_from_candidates(parsed.track_candidates)

    if not tracks:
        return None

    tags = [normalize_whitespace(cat.text or "") for cat in item.findall("category") if normalize_whitespace(cat.text or "")]
    top_artists = [name for name, _ in artist_counter.most_common(5)]

    mix = {
        "$schema": "schemas/mix.schema.json",
        "schemaVersion": SCHEMA_VERSION,
        "id": slug,
        "slug": slug,
        "status": "published",
        "siteSection": "mixes",
        "source": {
            "platform": "tumblr",
            "feedType": "rss",
            "importedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "sourceUrl": source_url,
            "guid": normalize_whitespace(item.findtext("guid", "")) or source_url,
        },
        "title": title_case_mix_number(mix_number) if mix_number is not None else heading,
        "displayTitle": heading,
        "mixNumber": mix_number,
        "publishedAt": published_at,
        "summary": intro_metadata.summary,
        "intro": intro_metadata.intro,
        "tags": tags,
        "cover": {
            "imageUrl": cover_image,
            "alt": f"Cover art for {heading}" if cover_image else None,
            "credit": intro_metadata.cover_credit,
        },
        "download": {
            "label": "Download mix",
            "url": download_url,
        },
        "tracks": tracks,
        "stats": build_track_stats(tracks, top_artists=top_artists),
        "legacy": {
            "originalTitle": title,
            "tumblrHeading": heading,
            "descriptionHtml": description_html,
        },
    }
    if intro_metadata.favorite_track_cue:
        mix["legacy"]["favoriteTrackCue"] = intro_metadata.favorite_track_cue
    if intro_metadata.editorial_highlights:
        mix["legacy"]["editorialHighlights"] = intro_metadata.editorial_highlights
    return mix


def iter_feed_items(root: ET.Element) -> Iterable[ET.Element]:
    channel = root.find("channel")
    if channel is not None:
        yield from channel.findall("item")
        return
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    yield from root.findall("atom:entry", ns)


def load_xml(source: str) -> bytes:
    parsed = urlparse(source)
    if parsed.scheme in {"http", "https"}:
        with urlopen(source) as response:  # nosec - controlled CLI import helper
            return response.read()
    return Path(source).read_bytes()


def write_mix_json(mix: dict, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{mix['slug']}.json"
    path.write_text(json.dumps(mix, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def run_import(source: str, output_dir: str, limit: Optional[int] = None) -> list[Path]:
    payload = load_xml(source)
    root = ET.fromstring(payload)
    written: list[Path] = []
    for item in iter_feed_items(root):
        mix = convert_item_to_mix(item)
        if not mix:
            continue
        written.append(write_mix_json(mix, Path(output_dir)))
        if limit is not None and len(written) >= limit:
            break
    return written


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="RSS URL or local XML file")
    parser.add_argument("--output-dir", default="data/imported/mixes", help="Directory for generated mix JSON")
    parser.add_argument("--limit", type=int, default=None, help="Only import the first N matching mix posts")
    args = parser.parse_args(argv)

    written = run_import(args.source, args.output_dir, args.limit)
    if not written:
        print("No mix entries found", file=sys.stderr)
        return 1
    for path in written:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
