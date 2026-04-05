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
forwarded_args=()

for arg in "$@"; do
  case "$arg" in
    --scheduled)
      scheduled_run=true
      ;;
    --run-tests)
      run_tests_override=true
      ;;
    *)
      forwarded_args+=("$arg")
      ;;
  esac
done

if [ "$scheduled_run" = true ] && [ "$run_tests_override" = false ]; then
  run_tests=false
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting local MMM workflow (scheduled=$scheduled_run, run_tests=$run_tests)"

if [ "$run_tests" = true ]; then
  python3 -m pytest -q
else
  echo "Skipping pytest for scheduled run."
fi

generate_args=(scripts/generate_weekly_draft.py --mode auto)
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

if [ "$scheduled_run" = false ]; then
  npm run build
fi

echo "Local MMM workflow complete."
echo "Latest drafts:"
ls -1 data/drafts/*.json 2>/dev/null | tail -n 5 || true
