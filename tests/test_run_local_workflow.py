from __future__ import annotations

import os
import shutil
import subprocess
from datetime import date
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def write_executable(path: Path, contents: str) -> None:
    path.write_text(contents, encoding="utf-8")
    path.chmod(0o755)


def prepare_temp_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    shutil.copytree(REPO_ROOT / "scripts", repo / "scripts")
    (repo / "bin").mkdir(parents=True)
    (repo / "data" / "drafts").mkdir(parents=True)
    return repo


def run_workflow(repo: Path, *args: str) -> tuple[subprocess.CompletedProcess[str], Path]:
    invocation_log = repo / "invocations.log"

    write_executable(
        repo / "bin" / "python3",
        """#!/bin/sh
echo "python3:$*" >> "$TEST_INVOCATIONS"
if [ "$1" = "scripts/generate_weekly_draft.py" ]; then
  mkdir -p data/drafts
  : > data/drafts/generated-from-test.json
fi
exit 0
""",
    )
    write_executable(
        repo / "bin" / "npm",
        """#!/bin/sh
echo "npm:$*" >> "$TEST_INVOCATIONS"
exit 0
""",
    )

    env = os.environ.copy()
    env["TEST_INVOCATIONS"] = str(invocation_log)

    result = subprocess.run(
        [str(repo / "scripts" / "run_local_workflow.sh"), *args],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    return result, invocation_log


def test_manual_run_forces_generation_and_builds(tmp_path):
    repo = prepare_temp_repo(tmp_path)

    result, invocation_log = run_workflow(repo)

    assert result.returncode == 0
    calls = invocation_log.read_text(encoding="utf-8").splitlines()
    assert "python3:-m pytest -q" in calls
    assert "python3:scripts/generate_weekly_draft.py --mode auto --force" in calls
    assert "npm:run build" in calls

    log_path = repo / "logs" / f"run-local-workflow-{date.today().isoformat()}.log"
    assert log_path.exists()
    assert "scheduled=false" in log_path.read_text(encoding="utf-8")


def test_scheduled_run_skips_force_and_build(tmp_path):
    repo = prepare_temp_repo(tmp_path)

    result, invocation_log = run_workflow(repo, "--scheduled")

    assert result.returncode == 0
    calls = invocation_log.read_text(encoding="utf-8").splitlines()
    assert "python3:-m pytest -q" in calls
    assert "python3:scripts/generate_weekly_draft.py --mode auto" in calls
    assert "python3:scripts/generate_weekly_draft.py --mode auto --force" not in calls
    assert not any(call == "npm:run build" for call in calls)

    log_files = list((repo / "logs").glob("run-local-workflow-*.log"))
    assert len(log_files) == 1
    assert "scheduled=true" in log_files[0].read_text(encoding="utf-8")
