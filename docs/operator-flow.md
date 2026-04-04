# MMM Operator Flow

## End-to-end workflow

1. Import
   - Bring source listening notes or imported historical mixes into the repository as JSON drafts under `data/drafts/`.
   - Each draft should follow the MMM mix shape used by `scripts/publish_mix.py`.

2. Review draft
   - Check title, date, summary, notes, and track ordering.
   - Confirm every track has `artist`, `title`, and `why_it_fits`.
   - Set `status` to `approved` once editorial review is complete.

3. Approve
   - Approval is represented in the draft JSON itself by `"status": "approved"`.
   - Optional: set `"featured": true` in the draft or pass `--feature` during publish.

4. Publish
   - Run `python3 scripts/publish_mix.py <slug-or-path>`.
   - The publisher validates the draft, requires approved status, converts it to `published`, writes it to `data/published/`, and refreshes `data/archive/index.json`.
   - Use `--validate-only` to verify a draft before changing repository state.

5. Deploy
   - Run `npm run build` locally if desired.
   - The static build emits `/notes/[slug]/` pages automatically and wires note-to-mix relationships into the homepage, notes index, archive, and mix detail pages.
   - Push to `main` to trigger the GitHub Pages deployment workflow.

## Weekly generation automation

- Local/manual: `python3 scripts/generate_weekly_draft.py --mode auto`
- Local/manual end-to-end: `./scripts/run_local_workflow.sh`
- Local scheduled: use `./scripts/run_local_workflow.sh --scheduled` via the LaunchAgent template in `ops/com.aditya.mmm.weekly.plist`
- Inputs read by the generator:
  - `data/taste-profile.json`
  - `data/site.json`
  - `data/archive/index.json`
- Output:
  - A new JSON draft in `data/drafts/`
  - A dated workflow log in `logs/run-local-workflow-YYYY-MM-DD.log`

Scheduled local runs:
- still execute the repo test suite first
- do not pass `--force` to draft generation
- do not run `npm run build` after writing the draft

## Notes

- Deterministic local generation is the default and only supported mode right now.
- The hosted GitHub workflow is for deployment, not editorial generation.
- Notes can be authored as standalone JSON files in `data/notes/` and indexed in `data/notes-index.json`; the build merges them by slug so short index metadata and full note bodies can evolve separately.
