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
  - `site.json`, `archive-index.json`, `notes-index.json`, `taste-profile.json`
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
- `--mode auto` is local-safe and currently resolves to deterministic generation.
- No OpenAI or hosted AI dependency is required for the site or the weekly workflow.
- `create_content.py note` writes the note file and refreshes the notes index entry in one step.
- `create_content.py note-from-mix` seeds a note slug, title, summary, related mix, and starter body from the published mix JSON.
- `create_content.py suggest-notes` still prints a clear zero-state when every published mix already has note coverage.
- `preview_latest.py --open` only opens local file previews or localhost routes.

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

Repair existing imported or published mix JSON from the preserved legacy HTML snapshot:

```bash
python3 scripts/repair_legacy_imports.py
python3 scripts/repair_legacy_imports.py data/imported/mixes/mix-033-thirtythird.json
```

## Rebuild taste profile

```bash
python3 scripts/build_taste_profile.py
```

## Run the local MMM workflow end-to-end

```bash
./scripts/run_local_workflow.sh
```

Scheduled local run without overwrite/build:

```bash
./scripts/run_local_workflow.sh --scheduled
```

Scheduled local run with tests enabled:

```bash
./scripts/run_local_workflow.sh --scheduled --run-tests
```

Optional macOS scheduling:
- Render and install a machine-local LaunchAgent with `python3 ops/install_launch_agent.py`.
- By default this writes `~/Library/LaunchAgents/com.mmm.weekly.plist` with the current repo root, workflow script path, and `logs/launchd-weekly.*.log` paths embedded automatically.
- Load it with `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.mmm.weekly.plist`.
- Re-run it on demand with `launchctl kickstart -k gui/$(id -u)/com.mmm.weekly`.
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

- Notes are loaded from `data/notes-index.json` plus matching files in `data/notes/`, with `data/notes.json` still supported as a fallback.
- Note detail pages are emitted at `/notes/[slug]/`.
- Mix detail pages expose previous/next archive links, related notes, highlighted tracks, and source/embed metadata when present in the JSON.
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
