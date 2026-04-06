# MMM Operator Flow

## End-to-end editorial workflow

Operator UI option:
- `npm run operator`
- With a token gate: `MMM_OPERATOR_TOKEN="choose-a-long-random-string" npm run operator`
- The UI stays local-first, edits draft JSON atomically, and can sit behind a private tunnel later if needed. See `docs/operator-ui.md`.

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
   - Tumblr-derived archive mixes can also emit YouTube review warnings when `data/youtube/<mix-slug>.json` is missing or still has unresolved tracks.
   - Explicit embeds are required for inline playback. Trusted provider links alone stay link-only.
   - Use `/studio/` after a build for a quick local summary of note coverage gaps, orphan notes, listening/provider warning counts, and blocked YouTube review queues.
   - To ingest the full Tumblr export, run `python3 scripts/import_tumblr_archive.py`. It reads `/tmp/mmm-tumblr-archive/posts/html`, skips non-mix asks, keeps the existing RSS-derived 33-36 JSON unless `--rewrite-existing` is passed, and syncs canonical local artwork from the archive bytes.
   - If a Tumblr-imported mix still has messy intro/cover/favorite legacy fields, run `python3 scripts/repair_legacy_imports.py [file-or-dir]` to refresh those fields from the saved `legacy.descriptionHtml` snapshot without touching the network.
   - If a Tumblr-derived mix still points at remote cover art only, run `python3 scripts/sync_tumblr_artwork.py <mix-slug>` to promote canonical local artwork. With the archive present, it prefers the exact exported media bytes and only downloads from Tumblr when no archive image exists.
   - If an archive mix needs a YouTube queue, run `python3 scripts/sync_youtube_matches.py <mix-slug>` and review `data/youtube/<mix-slug>.json` before trusting the embed. The matcher uses the canonical archive view, dedupes by slug, and prefers published JSON when a slug exists in both imported and published data.
   - Ambiguous, duplicate, or low-confidence candidates are expected to stay pending until a human selects the right video. Do not silently choose one.
   - If you edited canonical note or published mix JSON directly, run `python3 scripts/refresh_indexes.py` to rebuild `data/notes-index.json`, `data/archive/index.json`, `data/archive-index.json`, and `data/mixes.json`.

5. Approve a mix.
   - Run `python3 scripts/approve_mix.py mmm-for-2026-04-13 --by "Aditya"`.
   - Approval is still represented by `"status": "approved"` in the draft JSON, but the operator command also records lightweight provenance under `approval`.
   - Approved drafts must now include at least `approval.reviewedAt` and `approval.approvedAt`.
   - Optional: set `"featured": true` in the draft or pass `--feature` during publish.

6. Publish.
   - Preferred Monday path: `python3 scripts/release_weekly.py <slug-or-path>`.
   - Manual fallback: `python3 scripts/publish_mix.py <slug-or-path>`.
   - The release wrapper validates the repo, publishes the approved draft, validates again, runs `npm run build`, and prints the manual push/deploy reminder.
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
- Tumblr-exact local artwork sync:
  - `python3 scripts/sync_tumblr_artwork.py mix-034-thirtyfourth mix-035-thirtyfifth`
  - With `/tmp/mmm-tumblr-archive` available, this copies the exact exported media bytes into `data/media/tumblr/<mix-slug>/cover.<ext>`, updates the mix JSON with `cover.canonicalAssetPath`, and records SHA-256 plus source provenance in the registry.
  - Without a matching archive image, it falls back to downloading the exact Tumblr-hosted bytes.
- Published pages prefer `cover.canonicalAssetPath` when present and only fall back to the remote Tumblr URL when no canonical local asset exists yet.
- AI artwork option:
  - `python3 scripts/generate_ai_artwork.py mmm-for-2026-04-13`
  - This writes `data/media/workspaces/<slug>/exports/ai-cover.png`, saves prompt/model provenance to `notes/ai-artwork-generation.json`, and registers the asset in `data/media/artwork-registry.json`.

## YouTube queue workflow

- Generate candidate state:
  - `python3 scripts/sync_youtube_matches.py mix-035-thirtyfifth`
  - `python3 scripts/sync_youtube_matches.py` to refresh the full canonical archive set
- Review the saved JSON in `data/youtube/<mix-slug>.json`.
  - `auto-resolved` means the matcher found a clearly dominant hit.
  - `pending-review` means the stored candidates were too ambiguous, duplicate-prone, or low-confidence to pick safely.
  - `manual-selected` is the human-reviewed escape hatch once you have checked the candidate set.
- Do not force a mix-level embed while any track remains unresolved.
- If the same selected video lands on multiple tracks, keep the duplicate holdback in place until a person resolves it.
- Validation and `/studio/` keep surfacing unresolved YouTube review work until that last track is explicitly selected.
- When every track has a selected video ID, the build generates:
  - a queue-style YouTube embed from explicit video IDs
  - a queue-style watch URL from explicit video IDs
- The build never invents a playlist ID to make the embed look cleaner than the underlying data.

## Weekly generation automation

- Local/manual generation: `python3 scripts/generate_weekly_draft.py --mode auto`
- AI/manual generation: `python3 scripts/generate_weekly_draft.py --mode ai`
- Local/manual end-to-end: `./scripts/run_local_workflow.sh`
- AI end-to-end: `./scripts/run_local_workflow.sh --ai`
- AI end-to-end with artwork: `./scripts/run_local_workflow.sh --ai --with-ai-artwork`
- Local scheduled: use `./scripts/run_local_workflow.sh --scheduled`
- Install the matching LaunchAgent with `python3 ops/install_launch_agent.py --install`
- Bootstrap immediately when wanted: `python3 ops/install_launch_agent.py --install --bootstrap --verify`
- Customize schedule/flags locally when needed:
  - `python3 ops/install_launch_agent.py --install --weekday 2 --hour 9 --minute 30`
  - `python3 ops/install_launch_agent.py --install --ai --with-ai-artwork`
- Optional scheduled run with tests: `./scripts/run_local_workflow.sh --scheduled --run-tests`
- Skip aggregate refresh only when indexes are already known-good: `./scripts/run_local_workflow.sh --skip-refresh`
- Inputs read by the generator:
  - `data/taste-profile.json`
  - `data/site.json`
  - `data/archive/index.json`
- AI mode also reads the canonical archive window from `data/published/` plus `data/imported/mixes/`, deduped by slug and sorted newest first.
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
- still run content validation before generation and again after draft/artwork changes
- still refresh aggregate indexes before generation unless `--skip-refresh` is passed

## Notes

- Deterministic local generation is the default mode.
- AI draft generation is opt-in, uses the configured OpenAI key on the operator machine, and requires the model output to validate as MMM editorial JSON.
- AI artwork generation is also opt-in and records prompt/model provenance instead of pretending the cover was handmade.
- Local plugin refinement is optional and still must emit a valid editorial draft JSON object.
- The hosted GitHub workflow is for deployment, not editorial generation.
- `npm run content:validate`, `npm run draft:new`, `npm run draft:approve`, `npm run release:weekly`, and `npm run note:new` wrap the new editor-facing commands.
- `npm run note:suggest`, `npm run note:new-from-mix`, `npm run content:refresh`, and `npm run preview:latest` cover the new low-friction maintenance helpers.
- Notes are indexed through `data/notes-index.json`, but the detail files in `data/notes/` remain the primary authored source.
- Listening confidence is local-first and explicit: uncertain surfaces may still appear as leads, but the site will not style them like verified playback.
