"""Console entry point for replacing a closed portable installation."""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

from editor.updater import (
    InstallationInfo,
    replace_installation,
    stage_archive,
    wait_for_process_exit,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent-pid", type=int, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--target", choices=("windows", "linux"), required=True)
    parser.add_argument("--kind", choices=("portable", "package"), required=True)
    parser.add_argument("--launch", type=Path, required=True)
    parser.add_argument("--wait-timeout", type=float, default=30.0)
    args = parser.parse_args(argv)
    installation = InstallationInfo(
        args.target,
        "x86_64",
        args.kind,
        args.installation.resolve(),
        args.launch.resolve(),
    )
    staging_root = installation.root.parent / f".{installation.root.name}.update-staging"
    try:
        wait_for_process_exit(args.parent_pid, timeout=args.wait_timeout)
        staged = stage_archive(args.archive, installation, staging_root)

        def launch(executable: Path) -> None:
            subprocess.Popen([str(executable)], cwd=executable.parent, start_new_session=True)

        replace_installation(staged, installation, launcher=launch)
        Path(args.archive).unlink(missing_ok=True)
        return 0
    except Exception as exc:
        print(f"Updater error: {type(exc).__name__}: {exc}")
        shutil.rmtree(staging_root, ignore_errors=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
