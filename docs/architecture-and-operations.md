# MMM Architecture and Operations

## System overview

MMM is a static-site publishing system with local editorial tooling.

It is made of three major subsystems:

1. Data and schemas
2. Editorial tooling
3. Static rendering and deploy

## 1. Data and schemas

### Primary data directories
- `data/drafts/` — unpublished or approved draft mixes
- `data/published/` — published mixes rendered into the live archive
- `data/notes/` — note detail records
- `data/imported/` — imported Tumblr/RSS source and normalized mix records
- `data/archive/` — generated archive index
- `data/media/` — local artwork registry plus per-mix asset workspaces

### Aggregates and config
- `data/site.json`
- `data/mixes.json`
- `data/archive-index.json`
- `data/notes-index.json`
- `data/taste-profile.json`

### Schemas
Stored in `schemas/`.

These are not decorative. They define the expected contract for future agents.

## 2. Editorial tooling

All tooling lives under `scripts/`.

### Key scripts

`import_tumblr.py`
- imports historical Tumblr/RSS posts
- preserves provenance
- parses tracklists and favorites

`repair_legacy_imports.py`
- refreshes derived Tumblr legacy fields from saved `legacy.descriptionHtml`
- stays local-safe and file-based

`build_taste_profile.py`
- derives recurring artist/taste hints from imported material

`generate_weekly_draft.py`
- generates a local deterministic weekly draft
- can also run an opt-in AI mode against the canonical 36-mix archive window
- can optionally hand JSON context to a machine-local plugin command
- writes into `data/drafts/`

`manage_artwork.py`
- scaffolds local artwork workspaces per mix
- registers local asset paths plus provenance into canonical JSON

`generate_ai_artwork.py`
- generates AI artwork for a draft mix through OpenAI image generation
- saves the export under the mix workspace
- records prompt/model provenance alongside the registered asset

`create_content.py`
- creates new draft mix templates
- creates note templates and updates note index
- suggests published mixes with no note coverage
- can scaffold a note from a published mix

`approve_mix.py`
- validates the repo/draft and marks a reviewed draft approved
- stores lightweight review/approval provenance on the draft

`validate_content.py`
- validates content health across repo data
- should be run before publishing or handoff

`publish_mix.py`
- promotes approved draft mix to published state
- rebuilds aggregate files
- can update featured mix

`release_weekly.py`
- guarded release wrapper for an approved draft
- validates the repo before and after publish
- runs the static build and prints the manual deploy step

`refresh_indexes.py`
- regenerates notes/archive aggregate JSON from canonical note and published mix files

`preview_latest.py`
- prints or opens local-only previews for the latest draft, published mix, and note

`run_local_workflow.sh`
- convenience runner for scheduled/local editorial workflow
- manual runs execute pytest before generation
- scheduled runs skip pytest unless `--run-tests` is passed
- refreshes note/archive aggregates before generation unless `--skip-refresh` is passed
- runs content validation before generation and again after the draft/artwork step
- can opt into AI draft generation with `--ai`
- can opt into end-to-end AI draft plus AI artwork with `--with-ai-artwork`

## 3. Static rendering and deploy

`build.js`
- canonical static site generator
- reads data files
- writes HTML into `dist/`

`dev-server.js`
- local preview server helper

`src/static/site.css`
- global styles
- includes small UI affordances for discovery/filtering and dashboard surfaces

## Route map

Public/editorial routes emitted by the build:
- `/`
- `/archive/`
- `/mixes/[slug]/`
- `/about/`
- `/notes/`
- `/notes/[slug]/`
- `/studio/`

## Route purpose

### `/`
Homepage
- featured mix
- recent archive entries
- recent note relationships
- route into studio/dashboard

### `/archive/`
Published mix index
- searchable/filterable
- exposes tags and relationship hints

### `/mixes/[slug]/`
Mix detail page
- metadata
- tracklist
- listening fallback/provider area
- related notes
- previous/next mix links
- source/provenance

### `/notes/`
Notes index
- searchable/filterable
- links into note detail pages

### `/notes/[slug]/`
Note detail page
- note body
- related mixes
- prev/next notes

### `/studio/`
Local/editorial orientation route
- content counts
- recent draft/published/note state
- featured mix state
- validation posture copy
- recommended next actions

## Build-time data flow

1. load raw site metadata
2. load mixes from aggregate/generated/published/imported sources
3. normalize mix structures
4. load notes from notes index + note detail files
5. attach note-to-mix and mix-to-note relationships
6. load drafts
7. render all routes
8. emit `dist/`

## Publish-time data flow

1. read draft JSON
2. validate draft shape/content
3. require approved status
4. transform to published mix shape
5. write to `data/published/`
6. rebuild aggregate indexes/files
7. optionally update featured mix in `data/site.json`

## Local operations model

### Expected operator flow
1. validate repo content
2. create/generate draft
3. edit content JSON
4. refresh generated aggregates if canonical files were edited directly
5. validate again
6. approve mix explicitly and capture lightweight provenance
7. run the guarded release wrapper or publish manually
8. build preview
9. push to `main`
10. GitHub deploys Pages

### Why local-first matters
This project intentionally keeps editorial decisions and generation on the local machine.

Reasons:
- avoids hidden hosted state
- avoids fragile CI-as-editor patterns
- matches Aditya’s preference for local ops
- keeps the deployed site dumb and stable
- keeps machine-specific LaunchAgent paths out of tracked files by rendering them locally via `ops/install_launch_agent.py`
- keeps artwork provenance visible in canonical JSON instead of scattered across untracked folders

## GitHub Actions role

GitHub Actions should remain deploy/test oriented only.

Allowed responsibilities:
- install dependencies needed for test/build
- run tests
- build the site
- deploy Pages

Disallowed responsibilities unless explicitly requested later:
- generate editorial drafts
- publish content automatically
- mutate editorial content as part of CI

## Listening and provenance rules

These matter because future agents may get too clever.

### Good behavior
- show real provider/embed data when trustworthy
- derive listening confidence from the curated provider catalog instead of URL wishfulness
- require explicit embed URLs before rendering inline playback
- show track-first search helpers when provider confidence is low
- keep YouTube matches unresolved when the best candidate is ambiguous, duplicate-prone, or low-confidence
- preserve Tumblr source links as provenance
- preserve AI artwork provenance honestly, including prompt/model context
- separate original source, cleanup choices, and preserved residue instead of flattening them into one metadata block
- suppress dead Mega links from primary listening UI

### Bad behavior
- fabricate “official” listening paths from weak evidence
- infer embed readiness just because a provider usually supports embeds
- present legacy Tumblr artwork as definitive album art when it is only archival source art
- hide provenance because it looks messy

## Design source material

The live app does not depend on Stitch prototype files.

Reference material is stored only under:
- `docs/reference-design/stitch/`

Those files are for inspiration and audit, not runtime usage.

## Testing strategy

Current tests cover:
- Tumblr import parsing
- draft generation
- publish flow
- local workflow behavior
- static build output
- content creation helpers
- content validation

Any future major feature should add tests in one of these categories:
- tooling behavior
- static build output
- data validation contract

## Change-management guidance

When changing MMM, future agents should prefer this order:
1. update schemas/data expectations if needed
2. update generators/validators
3. update build/rendering
4. update tests
5. update docs

## Safe extension areas

These are good places to keep building:
- content creation helpers
- archive discovery
- better studio summaries
- note/mix relationship quality
- local editorial helpers
- provider confidence heuristics
- imported legacy cleanup tools

## Dangerous extension areas

These are where agents are likely to overbuild or regress the product:
- turning `/studio/` into a gross admin app
- turning CI into an editorial runtime
- adding server-side state
- introducing framework migration churn without benefit
- inventing too much fake metadata for legacy archive content

## Operator sanity checks

Before handoff or deploy, the system should satisfy:
- `python3 scripts/validate_content.py` → no errors
- `python3 -m pytest -q` → green
- `npm run build` → green
- `git status` → clean unless intentionally in progress

If those hold, the repo is in good operational shape.
