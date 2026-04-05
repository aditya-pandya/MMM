# MMM Operator Flow

## End-to-end editorial workflow

1. Validate the repo before touching content.
   - Run `python3 scripts/validate_content.py`.
   - Fix any actionable errors before creating or publishing anything.

2. Start with a template instead of blank JSON.
   - New draft mix: `python3 scripts/create_content.py draft-mix --date 2026-04-13`
   - New note: `python3 scripts/create_content.py note --title "A note title" --related-mix mix-036-thirtysixth`
   - Note creation writes the note file and refreshes `data/notes-index.json` in one step.

3. Review and edit content.
   - Mix drafts live under `data/drafts/`.
   - Notes live under `data/notes/`.
   - Check title, date, summary, notes/body copy, tags, and relationships.
   - For mixes, confirm every track has `artist`, `title`, and `why_it_fits`.

4. Re-run validation.
   - Run `python3 scripts/validate_content.py` again after edits.
   - The validator checks site metadata, notes, drafts, published mixes, `data/archive/index.json`, `data/archive-index.json`, and `data/mixes.json`.
   - Expected output is a clean report with `errors: 0`.

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
   - Push to `main` to trigger the GitHub Pages deployment workflow.

## Weekly generation automation

- Local/manual generation: `python3 scripts/generate_weekly_draft.py --mode auto`
- Local/manual end-to-end: `./scripts/run_local_workflow.sh`
- Local scheduled: use `./scripts/run_local_workflow.sh --scheduled`
- Install the matching LaunchAgent with `python3 ops/install_launch_agent.py`
- Optional scheduled run with tests: `./scripts/run_local_workflow.sh --scheduled --run-tests`
- Inputs read by the generator:
  - `data/taste-profile.json`
  - `data/site.json`
  - `data/archive/index.json`
- Output:
  - A new JSON draft in `data/drafts/`
  - A dated workflow log in `logs/run-local-workflow-YYYY-MM-DD.log`

Scheduled local runs:
- skip the repo test suite by default
- can opt back into tests with `--run-tests`
- do not pass `--force` to draft generation
- do not run `npm run build` after writing the draft

## Notes

- Deterministic local generation is the default and only supported mode right now.
- The hosted GitHub workflow is for deployment, not editorial generation.
- `npm run content:validate`, `npm run draft:new`, and `npm run note:new` wrap the new editor-facing commands.
- Notes are indexed through `data/notes-index.json`, but the detail files in `data/notes/` remain the primary authored source.
