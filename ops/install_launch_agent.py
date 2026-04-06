#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path


DEFAULT_LABEL = "com.mmm.weekly"
DEFAULT_PATH = "{repo_root}/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parents[1]


def render_launch_agent(template_path: Path, repo_root: Path, path_value: str) -> str:
    repo_root = repo_root.resolve()
    logs_dir = repo_root / "logs"
    replacements = {
        "__RUN_SCRIPT__": str((repo_root / "scripts" / "run_local_workflow.sh").resolve()),
        "__REPO_ROOT__": str(repo_root),
        "__PATH__": path_value,
        "__STDOUT_LOG__": str((logs_dir / "launchd-weekly.stdout.log").resolve()),
        "__STDERR_LOG__": str((logs_dir / "launchd-weekly.stderr.log").resolve()),
    }

    rendered = template_path.read_text(encoding="utf-8")
    for placeholder, value in replacements.items():
        rendered = rendered.replace(placeholder, value)
    return rendered


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render or install the MMM LaunchAgent for this checkout."
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=repo_root_from_script(),
        help="Repository root to embed in the LaunchAgent. Defaults to this checkout.",
    )
    parser.add_argument(
        "--template",
        type=Path,
        default=repo_root_from_script() / "ops" / "com.mmm.weekly.plist.template",
        help="LaunchAgent template to render.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path.home() / "Library" / "LaunchAgents" / f"{DEFAULT_LABEL}.plist",
        help="Where to write the rendered LaunchAgent plist.",
    )
    parser.add_argument(
        "--path-value",
        default=None,
        help="PATH value for launchd. Defaults to the repo-local bin path plus system paths.",
    )
    parser.add_argument(
        "--stdout-log",
        type=Path,
        default=None,
        help="Override the stdout log path embedded in the rendered plist.",
    )
    parser.add_argument(
        "--stderr-log",
        type=Path,
        default=None,
        help="Override the stderr log path embedded in the rendered plist.",
    )
    parser.add_argument(
        "--print",
        action="store_true",
        help="Print the rendered plist after writing it.",
    )
    parser.add_argument(
        "--install",
        action="store_true",
        help="Write the plist in place and keep a timestamped backup if one already exists.",
    )
    parser.add_argument(
        "--bootstrap",
        action="store_true",
        help="Run launchctl bootstrap for the rendered plist after writing it.",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Run launchctl print for the agent label after writing or bootstrapping it.",
    )
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=None,
        help="Directory for timestamped plist backups. Defaults next to the output plist.",
    )
    parser.add_argument(
        "--launchctl-bin",
        default="launchctl",
        help="launchctl binary or shim to use for bootstrap/verify.",
    )
    return parser


def backup_existing_plist(output_path: Path, backup_dir: Path | None = None) -> Path | None:
    if not output_path.exists():
        return None

    stamp = str(int(output_path.stat().st_mtime))
    target_dir = (backup_dir or output_path.parent / "backups").expanduser()
    target_dir.mkdir(parents=True, exist_ok=True)
    backup_path = target_dir / f"{output_path.stem}.{stamp}.bak{output_path.suffix}"
    shutil.copy2(output_path, backup_path)
    return backup_path


def launchctl_target(label: str) -> str:
    return f"gui/{os.getuid()}/{label}"


def run_launchctl(launchctl_bin: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [launchctl_bin, *args],
        capture_output=True,
        text=True,
        check=False,
    )


def bootstrap_launch_agent(launchctl_bin: str, output_path: Path, label: str) -> None:
    target = launchctl_target(label)
    bootout = run_launchctl(launchctl_bin, "bootout", target)
    if bootout.returncode not in {0, 3, 36, 113} and "Could not find service" not in (bootout.stderr or ""):
        raise RuntimeError(bootout.stderr.strip() or bootout.stdout.strip() or "launchctl bootout failed")

    result = run_launchctl(launchctl_bin, "bootstrap", f"gui/{os.getuid()}", str(output_path))
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "launchctl bootstrap failed")


def verify_launch_agent(launchctl_bin: str, label: str) -> str:
    target = launchctl_target(label)
    result = run_launchctl(launchctl_bin, "print", target)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "launchctl print failed")
    return result.stdout.strip()


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    template_path = args.template.resolve()
    output_path = args.output.expanduser()
    logs_dir = repo_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    backup_path = backup_existing_plist(output_path, args.backup_dir)

    path_value = args.path_value or DEFAULT_PATH.format(repo_root=repo_root)
    rendered = render_launch_agent(template_path, repo_root, path_value)

    if args.stdout_log is not None:
        rendered = rendered.replace(
            str((logs_dir / "launchd-weekly.stdout.log").resolve()),
            str(args.stdout_log.expanduser().resolve()),
        )
    if args.stderr_log is not None:
        rendered = rendered.replace(
            str((logs_dir / "launchd-weekly.stderr.log").resolve()),
            str(args.stderr_log.expanduser().resolve()),
        )

    output_path.write_text(rendered, encoding="utf-8")
    print(f"Wrote LaunchAgent to {output_path}")
    if backup_path is not None:
        print(f"Backed up previous plist to {backup_path}")
    print("Load it with: launchctl bootstrap gui/$(id -u) " f"{output_path}")
    print("Kick it once with: launchctl kickstart -k gui/$(id -u)/" f"{DEFAULT_LABEL}")

    if args.bootstrap:
        bootstrap_launch_agent(args.launchctl_bin, output_path, DEFAULT_LABEL)
        print(f"Bootstrapped LaunchAgent: {launchctl_target(DEFAULT_LABEL)}")

    if args.verify:
        verification = verify_launch_agent(args.launchctl_bin, DEFAULT_LABEL)
        print(f"Verified LaunchAgent: {launchctl_target(DEFAULT_LABEL)}")
        if verification:
            print(verification)

    if args.print:
        print("")
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
