# MMM

Monday Music Mix rebuilt as a data-first static site with import, draft generation, approval, publish, and GitHub Pages deploy.

What’s in here
- Static site build for:
  - /
  - /archive/
  - /mixes/[slug]/
  - /about/
  - /notes/
- Tumblr/RSS import pipeline for old MMM mixes
- Taste-profile builder from imported history
- Weekly draft generation for local-machine workflows
- Publish flow for approved mixes
- GitHub Actions for Pages deploy and scheduled draft generation

Repo structure
- data/
  - imported/ raw RSS + normalized imported mixes
  - drafts/ generated or hand-edited unpublished mixes
  - published/ published mix JSON
  - notes/ notes entries
  - archive/ generated archive index
  - site.json, archive-index.json, notes-index.json, taste-profile.json
- schemas/
  - JSON schemas for site, mixes, notes, archive, taste profile
- scripts/
  - import_tumblr.py
  - build_taste_profile.py
  - generate_weekly_draft.py
  - publish_mix.py
  - build.js
  - dev-server.js
- src/static/
  - site CSS
- tests/
  - import, publish, and generation tests

Local setup
```bash
python3 -m pip install -r requirements-dev.txt
npm run build
python3 -m pytest -q
```

Local preview
```bash
npm run dev
```
Then open:
- http://localhost:3000/
- http://localhost:3000/archive/
- http://localhost:3000/notes/

Import old Tumblr mixes
From RSS URL:
```bash
python3 scripts/import_tumblr.py --source https://mondaymusicmix.tumblr.com/rss --output data/imported/mixes
```

From a local file:
```bash
python3 scripts/import_tumblr.py --source data/imported/raw/mondaymusicmix-rss.xml --output data/imported/mixes
```

Rebuild taste profile
```bash
python3 scripts/build_taste_profile.py
```

Generate the next weekly draft
```bash
python3 scripts/generate_weekly_draft.py --mode auto
```

Notes:
- `--mode auto` is local-safe and currently resolves to deterministic generation.
- No OpenAI or hosted AI dependency is required for the site or the weekly workflow.

Run the local MMM workflow end-to-end
```bash
./scripts/run_local_workflow.sh
```

Optional macOS scheduling
- Load `ops/com.aditya.mmm.weekly.plist` as a LaunchAgent after editing paths if needed.
- That keeps weekly generation on this machine instead of GitHub Actions.

Approve + publish a mix
1. Open the draft JSON in `data/drafts/`
2. Edit copy, tracks, tags, art, notes
3. Change `status` from `draft` to `approved`
4. Publish it:

```bash
python3 scripts/publish_mix.py <slug-or-path> --feature
```

Useful commands:
```bash
python3 scripts/publish_mix.py <slug-or-path> --validate-only
python3 scripts/publish_mix.py <slug-or-path>
npm run build
```

What publish does
- validates the editorial draft
- writes schema-compatible published JSON into `data/published/`
- rebuilds:
  - `data/archive/index.json`
  - `data/archive-index.json`
  - `data/mixes.json`
- optionally updates `data/site.json` homepage feature

GitHub Actions
- `.github/workflows/deploy-pages.yml`
  - runs tests
  - builds the site
  - deploys `dist/` to GitHub Pages on push to main
- Weekly draft generation is intended to run locally on this machine.
- GitHub Actions is used for deploy only.

Current seeded content
- imported real mixes from the Monday Music Mix Tumblr RSS
- sample published mixes
- sample notes
- generated taste profile

Operational flow
1. Import archive
2. Build taste profile
3. Generate weekly draft
4. Review/edit draft
5. Mark approved
6. Publish
7. Push to main
8. GitHub Pages deploys the updated site
