#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

python3 -m pytest -q
python3 scripts/generate_weekly_draft.py --mode auto --force "$@"
npm run build

echo "Local MMM workflow complete."
echo "Latest drafts:"
ls -1 data/drafts/*.json 2>/dev/null | tail -n 5 || true
