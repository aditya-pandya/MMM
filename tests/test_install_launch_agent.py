from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_install_launch_agent_renders_repo_specific_paths(tmp_path):
    repo_root = tmp_path / "mmm-checkout"
    (repo_root / "scripts").mkdir(parents=True)
    (repo_root / "scripts" / "run_local_workflow.sh").write_text(
        "#!/bin/bash\n", encoding="utf-8"
    )
    output_path = tmp_path / "LaunchAgents" / "com.mmm.weekly.plist"

    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "ops" / "install_launch_agent.py"),
            "--repo-root",
            str(repo_root),
            "--output",
            str(output_path),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert output_path.exists()
    assert (repo_root / "logs").is_dir()

    rendered = output_path.read_text(encoding="utf-8")
    assert "<string>com.mmm.weekly</string>" in rendered
    assert str((repo_root / "scripts" / "run_local_workflow.sh").resolve()) in rendered
    assert f"<string>{repo_root.resolve()}</string>" in rendered
    assert (
        f"<string>{repo_root.resolve()}/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>"
        in rendered
    )
    assert str((repo_root / "logs" / "launchd-weekly.stdout.log").resolve()) in rendered
    assert str((repo_root / "logs" / "launchd-weekly.stderr.log").resolve()) in rendered
    assert "Weekday" in rendered
    assert "Hour" in rendered
    assert "Minute" in rendered

    assert f"Wrote LaunchAgent to {output_path}" in result.stdout
    assert "launchctl bootstrap gui/$(id -u)" in result.stdout
    assert "launchctl kickstart -k gui/$(id -u)/com.mmm.weekly" in result.stdout


def test_install_launch_agent_accepts_path_and_log_overrides(tmp_path):
    repo_root = tmp_path / "mmm-checkout"
    (repo_root / "scripts").mkdir(parents=True)
    (repo_root / "scripts" / "run_local_workflow.sh").write_text(
        "#!/bin/bash\n", encoding="utf-8"
    )
    output_path = tmp_path / "rendered.plist"
    stdout_log = tmp_path / "custom" / "mmm.stdout.log"
    stderr_log = tmp_path / "custom" / "mmm.stderr.log"
    path_value = "/custom/bin:/usr/bin:/bin"

    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "ops" / "install_launch_agent.py"),
            "--repo-root",
            str(repo_root),
            "--output",
            str(output_path),
            "--path-value",
            path_value,
            "--stdout-log",
            str(stdout_log),
            "--stderr-log",
            str(stderr_log),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    rendered = output_path.read_text(encoding="utf-8")
    assert f"<string>{path_value}</string>" in rendered
    assert str(stdout_log.resolve()) in rendered
    assert str(stderr_log.resolve()) in rendered
