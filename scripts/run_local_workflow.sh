#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export PATH="$ROOT/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/run-local-workflow-$(date '+%Y-%m-%d').log"
exec >> "$LOG_FILE" 2>&1

scheduled_run=false
run_tests=true
run_tests_override=false
refresh_indexes=true
generate_ai_artwork=false
generation_mode="auto"
forwarded_args=()

for arg in "$@"; do
  case "$arg" in
    --scheduled)
      scheduled_run=true
      ;;
    --run-tests)
      run_tests_override=true
      ;;
    --skip-refresh)
      refresh_indexes=false
      ;;
    --ai)
      generation_mode="ai"
      ;;
    --with-ai-artwork)
      generate_ai_artwork=true
      ;;
    *)
      forwarded_args+=("$arg")
      ;;
  esac
done

if [ "$scheduled_run" = true ] && [ "$run_tests_override" = false ]; then
  run_tests=false
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting local MMM workflow (scheduled=$scheduled_run, run_tests=$run_tests, refresh_indexes=$refresh_indexes, generation_mode=$generation_mode, ai_artwork=$generate_ai_artwork)"

if [ "$run_tests" = true ]; then
  python3 -m pytest -q
else
  echo "Skipping pytest for scheduled run."
fi

if [ "$refresh_indexes" = true ]; then
  python3 scripts/refresh_indexes.py
else
  echo "Skipping aggregate refresh."
fi

python3 scripts/validate_content.py

generate_args=(scripts/generate_weekly_draft.py --mode "$generation_mode")
if [ "$scheduled_run" = false ]; then
  generate_args+=(--force)
fi
if [ "${#forwarded_args[@]}" -gt 0 ]; then
  generate_args+=("${forwarded_args[@]}")
fi

generate_output=""
if ! generate_output=$(python3 "${generate_args[@]}" 2>&1); then
  printf '%s\n' "$generate_output"
  if [ "$scheduled_run" = true ] && printf '%s\n' "$generate_output" | grep -Fq "Draft already exists:"; then
    echo "Scheduled run found an existing draft; leaving it untouched."
  else
    exit 1
  fi
else
  printf '%s\n' "$generate_output"
fi

draft_output_path="$(printf '%s\n' "$generate_output" | awk 'NF{line=$0} END{print line}')"
if [ "$generate_ai_artwork" = true ]; then
  if [ -z "$draft_output_path" ]; then
    echo "ERROR: Could not determine generated draft path for AI artwork."
    exit 1
  fi
  python3 scripts/generate_ai_artwork.py "$draft_output_path" --force
fi

python3 scripts/validate_content.py

if [ "$scheduled_run" = false ]; then
  npm run build
fi

echo "Local MMM workflow complete."
echo "Workflow log: $LOG_FILE"
echo "Latest drafts:"
ls -1 data/drafts/*.json 2>/dev/null | tail -n 5 || true
