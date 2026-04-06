# MMM Operator Flow

## End-to-end editorial workflow

1. Validate the repo before touching content.
   - Run `python3 scripts/validate_content.py`.
   - Fix any actionable errors before creating or publishing anything.

2. Start with a template instead of blank JSON.
   - New draft mix: `python3 scripts/create_content.py draft-mix --date 2026-04-13`
   - New note: `python3 scripts/create_content.py note --title "A note title" --related-mix mix-036-thirtysixth`
   - Suggest uncovered published mixes: `python3 scripts/create_content.py suggest-notes`
   - Scaffold a note from a published mix: `python3 scripts/create_content.py note-from-mix mix-036-thirtysixth`
   - Note creation writes the note file and refreshes `data/notes-index.json` in one step.

3. Review and edit content.
   - Mix drafts live under `data/drafts/`.
   - Notes live under `data/notes/`.
   - Check title, date, summary, notes/body copy, tags, and relationships.
   - For mixes, confirm every track has `artist`, `title`, and `why_it_fits`.

4. Re-run validation.
   - Run `python3 scripts/validate_content.py` again after edits.
   - The validator checks site metadata, notes, drafts, published mixes, `data/archive/index.json`, `data/archive-index.json`, `data/mixes.json`, and `data/media/artwork-registry.json` when present.
   - Expected output before publish is `errors: 0`.
   - Warnings are non-blocking, but published mixes can now emit listening/provider warnings when a surface falls outside the curated trust rules in `data/listening-provider-catalog.json`.
   - Explicit embeds are required for inline playback. Trusted provider links alone stay link-only.
   - Use `/studio/` after a build for a quick local summary of note coverage gaps, orphan notes, and listening/provider warning counts.
   - If a Tumblr-imported mix still has messy intro/cover/favorite legacy fields, run `python3 scripts/repair_legacy_imports.py [file-or-dir]` to refresh those fields from the saved `legacy.descriptionHtml` snapshot without touching the network.
   - If you edited canonical note or published mix JSON directly, run `python3 scripts/refresh_indexes.py` to rebuild `data/notes-index.json`, `data/archive/index.json`, `data/archive-index.json`, and `data/mixes.json`.

5. Approve a mix.
   - Approval is represented in the draft JSON itself by `"status": "approved"`.
   - Optional: set `"featured": true` in the draft or pass `--feature` during publish.

6. Publish.
   - Run `python3 scripts/publish_mix.py <slug-or-path>`.
   - Use `--validate-only` to verify a draft before changing repository state.
   - The publisher validates the draft, requires approved status, converts it to `published`, writes it to `data/published/`, and refreshes the archive indexes.

7. Preview and deploy.
   - Run `npm run build` locally if desired.
   - `npm run dev` previews the static site.
   - `python3 scripts/preview_latest.py` or `npm run preview:latest` prints the latest draft/mix/note paths and local preview targets.
   - `python3 scripts/preview_latest.py --open` opens only local file previews or localhost routes.
   - Push to `main` to trigger the GitHub Pages deployment workflow.

## Local artwork workflow

- Scaffold a per-mix workspace: `python3 scripts/manage_artwork.py scaffold mix-036-thirtysixth`
- Keep raw ingredients in `source/`, exports in `exports/`, and quick process notes in `notes/`.
- Register a chosen asset in the canonical registry:
  - `python3 scripts/manage_artwork.py register mix-036-thirtysixth --asset-path data/media/workspaces/mix-036-thirtysixth/exports/cover.jpg --source-label "Local collage"`
- `data/media/artwork-registry.json` is the plain-JSON provenance source of truth.

## Weekly generation automation

- Local/manual generation: `python3 scripts/generate_weekly_draft.py --mode auto`
- Local/manual end-to-end: `./scripts/run_local_workflow.sh`
- Local scheduled: use `./scripts/run_local_workflow.sh --scheduled`
- Install the matching LaunchAgent with `python3 ops/install_launch_agent.py --install`
- Bootstrap immediately when wanted: `python3 ops/install_launch_agent.py --install --bootstrap --verify`
- Optional scheduled run with tests: `./scripts/run_local_workflow.sh --scheduled --run-tests`
- Skip aggregate refresh only when indexes are already known-good: `./scripts/run_local_workflow.sh --skip-refresh`
- Inputs read by the generator:
  - `data/taste-profile.json`
  - `data/site.json`
  - `data/archive/index.json`
- Optional local plugin input:
  - `--plugin-command "<local command>"`
  - `MMM_DRAFT_PLUGIN_COMMAND="<local command>"`
  - The command gets JSON context on stdin and may also use `{context_path}`, `{output_path}`, and `{repo_root}` placeholders.
- Output:
  - A new JSON draft in `data/drafts/`
  - A dated workflow log in `logs/run-local-workflow-YYYY-MM-DD.log`

Scheduled local runs:
- skip the repo test suite by default
- can opt back into tests with `--run-tests`
- do not pass `--force` to draft generation
- do not run `npm run build` after writing the draft
- still refresh aggregate indexes before generation unless `--skip-refresh` is passed

## Notes

- Deterministic local generation is the default mode.
- Local plugin refinement is optional and still must emit a valid editorial draft JSON object.
- The hosted GitHub workflow is for deployment, not editorial generation.
- `npm run content:validate`, `npm run draft:new`, and `npm run note:new` wrap the new editor-facing commands.
- `npm run note:suggest`, `npm run note:new-from-mix`, `npm run content:refresh`, and `npm run preview:latest` cover the new low-friction maintenance helpers.
- Notes are indexed through `data/notes-index.json`, but the detail files in `data/notes/` remain the primary authored source.
- Listening confidence is local-first and explicit: uncertain surfaces may still appear as leads, but the site will not style them like verified playback.
