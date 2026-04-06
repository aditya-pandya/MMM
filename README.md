# MMM

Monday Music Mix rebuilt as a data-first static site with local-first import, authoring, validation, approval, publish, and GitHub Pages deploy.

## What's in here

- Static site build for:
  - `/`
  - `/archive/`
  - `/mixes/[slug]/`
  - `/about/`
  - `/notes/`
  - `/notes/[slug]/`
  - `/studio/`
- Tumblr/RSS import pipeline for old MMM mixes
- Taste-profile builder from imported history
- Local editorial tooling for:
  - weekly draft generation
  - AI weekly draft generation from the full 36-mix archive
  - AI draft artwork generation with local provenance capture
  - draft mix templates
  - note templates with notes-index updates
  - note scaffolds from published mixes
  - note coverage suggestions
  - aggregate index refresh helpers
  - latest route/file preview helpers
  - content validation and reporting
  - publish flow for approved mixes
- GitHub Actions for Pages deploy only

## Repo structure

- `data/`
  - `imported/` raw RSS + normalized imported mixes
  - `drafts/` generated or hand-edited unpublished mixes
  - `published/` published mix JSON
  - `notes/` editorial notes
  - `archive/` generated archive index
  - `media/` local artwork registry plus mix-specific asset workspaces
  - `youtube/` persisted per-track YouTube candidate + review state
  - `site.json`, `about.json`, `archive-index.json`, `notes-index.json`, `taste-profile.json`
  - `listening-provider-catalog.json` curated trust map for listening providers and embeds
- `schemas/`
  - JSON schemas for site, mixes, notes, archive, taste profile
- `scripts/`
  - `import_tumblr.py`
  - `build_taste_profile.py`
  - `generate_weekly_draft.py`
  - `create_content.py`
  - `validate_content.py`
  - `publish_mix.py`
  - `build.js`
  - `dev-server.js`
- `src/static/`
  - site CSS + small client-side discovery JS
- `tests/`
  - import, publish, generation, editorial tooling, and static build tests

## Local setup

```bash
python3 -m pip install -r requirements-dev.txt
npm run build
python3 -m pytest -q
```

## Local preview

```bash
npm run dev
```

Then open:
- http://localhost:3000/
- http://localhost:3000/archive/
- http://localhost:3000/notes/
- http://localhost:3000/notes/rebuilding-the-archive/
- http://localhost:3000/studio/

## Editorial commands

Validate all local content and report actionable issues:

```bash
python3 scripts/validate_content.py
npm run content:validate
```

Listening-specific operator notes:

- Treat `data/listening-provider-catalog.json` as the trust source for listening surfaces.
- Add explicit embed URLs only when the curated data genuinely supports inline playback.
- If validation warns that a listening surface is uncertain, the build will demote it instead of presenting it as a verified mirror.
- YouTube full-mix embeds now come only from `data/youtube/*.json` files with a fully resolved per-track queue. Ambiguous or low-confidence track matches stay blocked for review.
- The YouTube matcher now works against the canonical archive view: published plus imported mixes, deduped by slug and preferring published JSON when both exist.

Create a new draft mix template instead of starting from blank JSON:

```bash
python3 scripts/create_content.py draft-mix --date 2026-04-13
npm run draft:new -- --date 2026-04-13
```

Create a new note template and update `data/notes-index.json` automatically:

```bash
python3 scripts/create_content.py note --title "Why this mix lingers" --related-mix mix-036-thirtysixth
npm run note:new -- --title "Why this mix lingers" --related-mix mix-036-thirtysixth
```

Suggest published mixes that still do not have note coverage:

```bash
python3 scripts/create_content.py suggest-notes
npm run note:suggest
```

Scaffold a note directly from a published mix:

```bash
python3 scripts/create_content.py note-from-mix mix-036-thirtysixth
npm run note:new-from-mix -- mix-036-thirtysixth
```

Refresh aggregate note/archive indexes from canonical files:

```bash
python3 scripts/refresh_indexes.py
npm run content:refresh
```

Refresh imported/published Tumblr-derived fields from the saved `legacy.descriptionHtml` without re-fetching RSS:

```bash
python3 scripts/repair_legacy_imports.py
python3 scripts/repair_legacy_imports.py --dry-run data/imported/mixes data/published
```

Print local-safe previews for the latest draft, published mix, and note:

```bash
python3 scripts/preview_latest.py
npm run preview:latest
```

Generate the next weekly draft from local context:

```bash
python3 scripts/generate_weekly_draft.py --mode auto
npm run draft:generate
```

Notes:
- `--mode auto` is local-safe and currently resolves to deterministic local heuristics.
- `--mode ai` uses the canonical 36-mix archive window, taste profile, and notes, then asks OpenAI for strict JSON that still has to validate as an MMM editorial draft.
- Draft generation now pulls from local published mixes, archive summaries, taste-profile cues, and editorial notes before choosing tracks or writing copy.
- Covers, remixes, recurring artists, and bolded-favorite style signals can now show up in generated summary, notes, tags, and track rationale when that pattern already exists in local data.
- Optional local plugin hook: pass `--plugin-command` or set `MMM_DRAFT_PLUGIN_COMMAND` to a machine-local command. The command receives JSON context on stdin and can also use `{context_path}`, `{output_path}`, and `{repo_root}` placeholders.
- Plugin output still has to be a valid MMM editorial draft JSON object.
- Deterministic local generation remains the default. AI generation is opt-in and uses `MMM_OPENAI_API_KEY` or `OPENAI_API_KEY`.
- AI mode fails clearly if the model output does not validate; it does not silently fake a successful draft.
- `create_content.py note` writes the note file and refreshes the notes index entry in one step.
- `create_content.py note-from-mix` seeds a note slug, title, summary, related mix, and starter body from the published mix JSON.
- `create_content.py suggest-notes` still prints a clear zero-state when every published mix already has note coverage.
- `preview_latest.py --open` only opens local file previews or localhost routes.

Scaffold a local artwork workspace for a mix:

```bash
python3 scripts/manage_artwork.py scaffold mix-036-thirtysixth
npm run artwork:scaffold -- mix-036-thirtysixth
```

Register a local artwork file with provenance in the canonical registry:

```bash
python3 scripts/manage_artwork.py register mix-036-thirtysixth \
  --asset-path data/media/workspaces/mix-036-thirtysixth/exports/cover.jpg \
  --role cover-art \
  --source-type handmade \
  --source-label "Local collage pass" \
  --notes "Built from scans and local type."
```

Notes:
- `data/media/artwork-registry.json` is the canonical local artwork/provenance index.
- Keep registered asset paths inside `data/media/` so the registry stays local-safe and portable with the repo.
- AI artwork generation:

```bash
python3 scripts/generate_ai_artwork.py mmm-for-2026-04-13
npm run artwork:generate:ai -- mmm-for-2026-04-13
```

- AI artwork exports land in `data/media/workspaces/<slug>/exports/ai-cover.png`.
- Prompt, provider, and model provenance are saved under `data/media/workspaces/<slug>/notes/ai-artwork-generation.json` and summarized in the artwork registry.
- Use `python3 scripts/sync_tumblr_artwork.py mix-034-thirtyfourth mix-035-thirtyfifth` or `npm run artwork:sync:tumblr -- mix-034-thirtyfourth` to promote canonical Tumblr artwork into `data/media/tumblr/<mix-slug>/`.
- When a local Tumblr export is available at `/tmp/mmm-tumblr-archive`, the sync prefers those exact exported bytes and only falls back to downloading remote Tumblr-hosted bytes when no archive asset can be found.
- Tumblr artwork sync records SHA-256, byte size, media type, original source provenance, and the field that discovered the image.

Persist YouTube per-track candidate state locally:

```bash
python3 scripts/sync_youtube_matches.py mix-035-thirtyfifth
npm run youtube:match -- mix-035-thirtyfifth
```

Notes:
- Match state lives in `data/youtube/<mix-slug>.json`.
- The matcher scans the canonical archive, not only `data/published/`, and prefers published JSON when the same slug exists in both published and imported sources.
- The matcher stores the scored candidate set for each track and only auto-resolves clearly dominant hits.
- `pending-review`, `no-candidate`, and duplicate holdbacks are intentional human-review checkpoints.
- Do not manually bless a full-mix YouTube embed until every track has a reviewed `selectedVideoId`. The build will keep the embed blocked while any track is unresolved.
- If two good-looking candidates are close, or two tracks land on the same selected video, leave the state unresolved and review it explicitly instead of choosing silently.
- Once every track is explicitly resolved, the build renders an honest YouTube queue embed from explicit video IDs instead of a claimed playlist ID.

Run the weekly workflow end to end:

```bash
./scripts/run_local_workflow.sh
./scripts/run_local_workflow.sh --ai
./scripts/run_local_workflow.sh --ai --with-ai-artwork
npm run workflow:weekly:ai-art
```

Notes:
- Default workflow behavior stays deterministic and local-first.
- `--ai` switches draft generation to OpenAI-backed structured output.
- `--with-ai-artwork` adds AI cover generation for the draft that was just created.

## Local editorial workflow

1. Validate the repository state.

```bash
python3 scripts/validate_content.py
```

2. Start from a template.

```bash
python3 scripts/create_content.py draft-mix --date 2026-04-13
python3 scripts/create_content.py note --title "A note title"
python3 scripts/create_content.py suggest-notes
python3 scripts/create_content.py note-from-mix mix-036-thirtysixth
```

3. Edit the new JSON under `data/drafts/` or `data/notes/`.
   Optional note metadata:
   - `series` can group a restrained run of related notes with `slug`, `title`, optional `description`, and optional `order`.
   - `relatedNoteSlugs` can link directly to other real note files when a local reading path is worth surfacing.
4. Re-run validation and fix anything it reports.
5. Refresh generated aggregates if you hand-edited canonical files directly.

```bash
python3 scripts/refresh_indexes.py
```

6. Change a mix `status` from `draft` to `approved` once editorial review is complete.
7. Publish the approved mix.

```bash
python3 scripts/publish_mix.py <slug-or-path> --feature
```

8. Build the static site and preview it locally.

```bash
npm run build
npm run dev
npm run preview:latest
```

## Import old Tumblr mixes

From RSS URL:

```bash
python3 scripts/import_tumblr.py https://mondaymusicmix.tumblr.com/rss --output-dir data/imported/mixes
```

From a local file:

```bash
python3 scripts/import_tumblr.py data/imported/raw/mondaymusicmix-rss.xml --output-dir data/imported/mixes
```

From the extracted Tumblr archive HTML export:

```bash
python3 scripts/import_tumblr_archive.py
npm run tumblr:archive:import
```

Notes:
- The archive importer reads `/tmp/mmm-tumblr-archive/posts/html`, skips non-mix asks, and safely fills `data/imported/mixes/` without rewriting the existing RSS-derived 33-36 files unless `--rewrite-existing` is passed.
- Archive footer timestamps omit timezone. The importer currently assumes `+05:30` because mixes 33-36 overlap with the RSS export and match that local clock exactly; the raw footer timestamp is also preserved in the JSON.
- Archive-derived mixes use the exact exported `media/*.jpg` bytes as canonical local artwork and record that provenance in `data/media/artwork-registry.json`.

Repair existing imported or published mix JSON from the preserved legacy HTML snapshot:

```bash
python3 scripts/repair_legacy_imports.py
python3 scripts/repair_legacy_imports.py data/imported/mixes/mix-033-thirtythird.json
```

Download Tumblr-hosted cover art into the repo and promote it to canonical local artwork:

```bash
python3 scripts/sync_tumblr_artwork.py mix-034-thirtyfourth mix-035-thirtyfifth mix-036-thirtysixth
```

Generate persisted YouTube candidate/match state for published mixes:

```bash
python3 scripts/sync_youtube_matches.py mix-035-thirtyfifth mix-036-thirtysixth
```

Review rule:
- ambiguous, duplicate, or low-confidence matches stay pending on purpose
- the site only renders a full-mix YouTube embed when every track is resolved
- validation and `/studio/` call out blocked YouTube review work explicitly

## Rebuild taste profile

```bash
python3 scripts/build_taste_profile.py
```

## Run the local MMM workflow end-to-end

```bash
./scripts/run_local_workflow.sh
npm run workflow:weekly
```

Scheduled local run without overwrite/build:

```bash
./scripts/run_local_workflow.sh --scheduled
npm run workflow:weekly:scheduled
```

Scheduled local run with tests enabled:

```bash
./scripts/run_local_workflow.sh --scheduled --run-tests
```

Optional macOS scheduling:
- Render and install a machine-local LaunchAgent with `python3 ops/install_launch_agent.py`.
- `./scripts/run_local_workflow.sh` now refreshes note/archive aggregates before draft generation unless `--skip-refresh` is passed.
- By default this writes `~/Library/LaunchAgents/com.mmm.weekly.plist` with the current repo root, workflow script path, and `logs/launchd-weekly.*.log` paths embedded automatically.
- Safe install + verify in one command: `python3 ops/install_launch_agent.py --install --verify`
- Install + bootstrap + verify immediately: `python3 ops/install_launch_agent.py --install --bootstrap --verify`
- Load it with `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.mmm.weekly.plist`.
- Re-run it on demand with `launchctl kickstart -k gui/$(id -u)/com.mmm.weekly`.
- Re-installs keep a timestamped backup under `~/Library/LaunchAgents/backups/` unless `--backup-dir` is overridden.
- That keeps weekly generation on this machine instead of GitHub Actions.
- Local workflow logs are written to `logs/run-local-workflow-YYYY-MM-DD.log`.

## Approve + publish a mix

1. Open the draft JSON in `data/drafts/`.
2. Edit copy, tracks, tags, art, notes.
3. Change `status` from `draft` to `approved`.
4. Validate the repo again.
5. Publish it:

```bash
python3 scripts/publish_mix.py <slug-or-path> --feature
```

Useful commands:

```bash
python3 scripts/publish_mix.py <slug-or-path> --validate-only
python3 scripts/validate_content.py
npm run build
```

## What publish does

- validates the editorial draft
- writes schema-compatible published JSON into `data/published/`
- rebuilds:
  - `data/archive/index.json`
  - `data/archive-index.json`
  - `data/mixes.json`
- optionally updates `data/site.json` homepage feature

## GitHub Actions

- `.github/workflows/deploy-pages.yml`
  - runs tests
  - builds the site
  - deploys `dist/` to GitHub Pages on push to main
- Weekly draft generation is intended to run locally on this machine.
- GitHub Actions is used for deploy only.

## Handoff and deep project docs

For another agent or developer, start here:
- `docs/handoff-spec.md`
- `docs/architecture-and-operations.md`
- `docs/roadmap-and-future-plans.md`
- `docs/operator-flow.md`
- `docs/data-import-assumptions.md`

These documents cover:
- product intent and non-goals
- architecture and route model
- editorial/local operations
- current requirements
- future roadmap and safe extension areas

## Current seeded content

- imported real mixes from the Monday Music Mix Tumblr RSS
- sample published mixes
- sample notes
- generated taste profile

## Static build behavior

- The About page now reads from `data/about.json` when present, with structured intro/editorial/section content and a restrained fallback only when that file is absent.
- Notes are loaded from `data/notes-index.json` plus matching files in `data/notes/`, with `data/notes.json` still supported as a fallback.
- Note relationships stay data-backed: `relatedMixSlugs` links notes to mixes, while optional `series` and `relatedNoteSlugs` organize nearby reading without inventing synthetic graph data.
- Note detail pages are emitted at `/notes/[slug]/`.
- Mix detail pages expose previous/next archive links, related notes, highlighted tracks, and provenance grouped into original source, archive cleanup decisions, and preserved residue when that context exists in the JSON.
- Dedicated listening sections render automatically when mix JSON includes provider links or embeds under `listening`, including nested provider maps and embedded-player groups.
- Listening confidence is derived from `data/listening-provider-catalog.json`, so verified previews require an explicit curated embed URL and verified links stay clearly separate from uncertain leads.
- `/archive/` and `/notes/` include lightweight client-side search and filter controls driven by the metadata already rendered into each page.
- Discovery now normalizes tag variants at build time and folds real mix/note context into each page's search blob, so archive queries can match track names, related note titles, provider labels, and linked mix context without inventing extra metadata.
- Archive facets stay small on purpose: they only surface content-backed states such as related notes, listening surfaces, Tumblr source provenance, covers, remixes, and the few tags already present in the data.
- `/studio/` is generated from local JSON and now summarizes draft count, published count, notes count, featured mix state, note coverage gaps, listening/provider warning counts, validation posture, recent routes, and recommended next actions.
- Tumblr-imported archive mixes fall back to typographic cover placeholders and track-level search helpers when the only artwork/download data is legacy Tumblr residue.
- Home, archive, and notes pages surface mix-note relationships so the writing is visible without having to guess where it lives.

## Operational flow

1. Import archive.
2. Build taste profile.
3. Validate content.
4. Generate or create draft content.
5. Review and edit.
6. Approve.
7. Publish.
8. Build locally.
9. Push to `main`.
10. GitHub Pages deploys the updated site.
