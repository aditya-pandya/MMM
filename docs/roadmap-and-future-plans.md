# MMM Roadmap and Future Plans

## Planning principle

Future work should make MMM:
- more useful
- more honest
- easier to operate locally
- richer as an archive

It should not make MMM:
- noisier
- more productized than necessary
- more dependent on remote services
- more complex than the content actually requires

## Current maturity level

MMM is beyond prototype stage.

It already has:
- a live deployed site
- archive and mix detail pages
- notes pages
- studio dashboard
- local editorial tooling
- validation and publish flow
- test coverage
- GitHub Pages deployment

That means future work should be iterative improvement, not greenfield reinvention.

## Priority 1: archive quality and editorial accuracy

### 1. Better note coverage
Goal:
- increase the number of published mixes with meaningful related notes

Why it matters:
- notes are what make the archive feel personal rather than just a track dump

Potential work:
- create more note templates for uncovered mixes
- add helper tooling that suggests published mixes without note coverage
- improve studio dashboard to spotlight note gaps more explicitly

### 2. Provider confidence improvements
Goal:
- make listening surfaces more trustworthy

Why it matters:
- low-confidence playback makes the site feel fake

Potential work:
- formalize confidence levels for listening/provider data
- only show embeds from trusted sources with explicit data
- add validation warnings for suspicious provider payloads

### 3. Legacy import cleanup
Goal:
- improve imported historical data quality

Potential work:
- fix known RSS/Tumblr text artifacts
- normalize cover credit extraction
- better detect and preserve favorite tracks / remixes / covers
- add repair scripts for imported JSON

## Priority 2: better discovery and local ops

### 4. Archive/notes discovery refinement
Goal:
- improve findability without turning the site into app sludge

Potential work:
- better tag normalization
- richer search blobs for discovery
- season/mood/era metadata if justified by real content
- compact archive faceting that stays editorial and quiet

### 5. Stronger studio dashboard
Goal:
- make `/studio/` more useful as the local operator page

Potential work:
- clearer validation summaries
- list of unpublished/approved drafts with route links
- stale-content reminders
- quick health sections for missing featured mix, orphan notes, missing note coverage, etc.

### 6. Better local maintenance helpers
Goal:
- reduce manual JSON fiddling

Potential work:
- regenerate notes/archive indexes from canonical files
- content repair helpers
- more guided content scaffolding
- route previews or “open latest draft/mix/note” helpers

## Priority 3: richer listening support

### 7. Real playlist mirror workflows
Goal:
- attach truly credible listening surfaces where possible

Potential work:
- support curated YouTube playlist URLs stored explicitly in mix JSON
- support other trusted providers only when real data exists
- add validation rules around allowed provider/embed shapes

Important rule:
- never fake playback certainty

### 8. Optional richer embeds
Goal:
- improve listening UX for mixes with trustworthy external playlists

Potential work:
- more polished provider cards
- explicit “play externally” vs “embedded preview” semantics
- embed support only for real trustworthy playlist URLs already curated into content

## Priority 4: content intelligence

### 9. Better taste-profile heuristics
Goal:
- make local draft generation more useful

Potential work:
- richer artist recurrence analysis
- stronger era/mood extraction from historical archive
- better sequencing heuristics
- note-aware draft suggestions

### 10. Smarter local draft generation
Goal:
- improve generated weekly draft quality without requiring hosted AI

Potential work:
- deterministic heuristics from archive/taste profile
- local recommendation logic based on note/tag/track signals
- optional future plug-in points for local or hosted models if explicitly desired

Important rule:
- hosted AI should stay optional, not foundational

## Lower-priority ideas

These are interesting but not urgent.

### 11. Better about page content model
- more structured about sections in data
- stronger long-form editorial framing

### 12. More nuanced source/provenance presentation
- separate “source”, “archive cleanup”, and “preserved residue” more elegantly
- improve legacy HTML cleanup further

### 13. Snapshot/test artifacts for design QA
- more explicit golden/static-output tests
- route-level regression fixtures

### 14. Optional local media workflows
Only if explicitly requested.
- local artwork generation/crafting pipeline
- local media asset management
- art provenance tracking

## Things future agents should probably NOT do

Unless explicitly told otherwise:
- do not migrate to a heavy framework
- do not add a backend
- do not add user auth
- do not build a CMS
- do not move editorial workflows into GitHub Actions
- do not add cloud dependence just because it seems “modern”
- do not turn the UI into a dashboard-first product

## Recommended next 3 concrete tasks

If another agent picks this up and wants the best next ROI, do these:

1. Add more note coverage for published mixes
- improves archive quality immediately
- low risk
- high editorial value

2. Tighten listening/provider validation heuristics
- reduces misleading playback UI
- increases trustworthiness

3. Improve `/studio/` with stronger local content health summaries
- helps the operator understand what to do next at a glance

## Suggested handoff sequencing for another agent

A future agent should tackle work in this order:

1. run validation/tests/build
2. inspect current content health and dashboard output
3. choose one bounded slice from Priority 1 or 2
4. make changes directly in data/scripts/build/tests/docs
5. rerun validation/tests/build
6. commit a clean, named slice
7. push and verify Pages deploy

## Definition of a good future change

A good MMM change should:
- make the archive more useful or more honest
- preserve local-first operations
- improve editorial clarity
- avoid unnecessary architectural sprawl
- leave behind tests and docs

If a future change cannot clear that bar, it probably should not be added.
