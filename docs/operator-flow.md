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
   - Push to `main` to trigger the GitHub Pages deployment workflow.

## Weekly generation automation

- Local/manual: `python3 scripts/generate_weekly_draft.py --mode auto`
- Scheduled: `.github/workflows/weekly-draft.yml`
- Inputs read by the generator:
  - `data/taste-profile.json`
  - `data/site.json`
  - `data/archive/index.json`
- Output:
  - A new JSON draft in `data/drafts/`

## Notes

- Deterministic fallback mode is the default safe path and does not require secrets.
- AI mode is intentionally optional. If an API key is present but AI generation is not configured or fails, the generator falls back to deterministic mode and records the fallback reason in the draft JSON.
