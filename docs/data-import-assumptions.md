# MMM data/import assumptions

- Tumblr RSS is treated as the source of truth for legacy post text, links, and publication timestamps.
- The importer only emits structured mix JSON for posts that look like actual Monday Music Mix entries (it skips asks or non-tracklist posts).
- Mix numbers are inferred from explicit `Monday Music Mix: N` markers first, then from ordinal headings like `Thirtysixth`.
- Tracklists are parsed from ordered-list items and favorite tracks are inferred from bold text inside list entries.
- Cover art credits and download links are preserved when Tumblr exposes them in the post HTML.
- Imported JSON keeps the raw Tumblr HTML under `legacy.descriptionHtml` so future cleanup can be done without re-fetching the feed.
- The seeded `data/published/` entries were generated from a live fetch of the public Tumblr RSS snapshot saved to `data/imported/raw/mondaymusicmix-rss.xml`.
- `data/archive-index.json`, `data/notes-index.json`, and `data/taste-profile.json` are lightweight seed outputs meant to give the future site generator stable starter data.
- Notes are expected to live as full JSON entries under `data/notes/` and be referenced from `data/notes-index.json`; the static build merges those sources by slug and uses `relatedMixSlugs` to drive note detail pages and mix cross-links.
- Taste-profile derivation is heuristic rather than authoritative; it counts recurring artists and scans track text for cover/remix-era hints.
