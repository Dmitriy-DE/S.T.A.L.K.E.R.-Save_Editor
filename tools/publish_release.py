"""Prepare and publish identical release bytes to GitHub/R2 surfaces."""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import Request, urlopen

# CI and Make invoke this file directly.  Put the repository root on the path
# before importing sibling packages.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from editor.release_artifacts import artifact_names
from editor.update_manifest import DOWNLOAD_BASE_URL
from tools.build_release_manifest import build_release_manifest

STABLE_FILES = (
    "SaveEditor-windows-x86_64.zip",
    "SaveEditor-windows-x86_64-setup.exe",
    "SaveEditor-linux-x86_64.tar.gz",
    "stalker2-save-editor_amd64.deb",
    "latest.json",
    "SHA256SUMS",
)
_TARGETS = {
    "windows-x86_64": ("windows", "SaveEditor-windows-x86_64.zip"),
    "windows-installer-x86_64": ("windows", "SaveEditor-windows-x86_64-setup.exe"),
    "linux-x86_64": ("linux", "SaveEditor-linux-x86_64.tar.gz"),
    "linux-deb-amd64": ("linux", "stalker2-save-editor_amd64.deb"),
}
_CONTENT_TYPES = {
    ".zip": "application/zip",
    ".exe": "application/vnd.microsoft.portable-executable",
    ".gz": "application/gzip",
    ".deb": "application/vnd.debian.binary-package",
    ".json": "application/json; charset=utf-8",
}
_RELEASE_USER_AGENT = "SaveEditor-release-verifier/1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _reject_private_inputs(root: Path) -> None:
    rejected = [
        path
        for path in root.rglob("*")
        if path.is_file() and (path.suffix.casefold() in {".sav", ".bak", ".pem", ".key"} or ".git" in path.parts)
    ]
    if rejected:
        names = ", ".join(str(path.relative_to(root)) for path in rejected[:5])
        raise ValueError(f"release input contains private files: {names}")


def _locate(artifact_dir: Path, filename: str) -> Path:
    direct = artifact_dir / filename
    if direct.is_file():
        return direct
    matches = sorted(path for path in artifact_dir.rglob(filename) if path.is_file())
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise ValueError(f"release artifact missing: {filename}")
    raise ValueError(f"release artifact is ambiguous: {filename}")


def _versioned_paths(artifact_dir: Path, version: str) -> dict[str, Path]:
    windows_names = artifact_names(version, "windows")
    linux_names = artifact_names(version, "linux")
    names = windows_names + linux_names
    by_name = {name: _locate(artifact_dir, name) for name in names}
    return {
        "windows-x86_64": by_name[windows_names[0]],
        "windows-installer-x86_64": by_name[windows_names[1]],
        "linux-x86_64": by_name[linux_names[0]],
        "linux-deb-amd64": by_name[linux_names[1]],
    }


def prepare_release(
    *,
    artifact_dir: Path,
    output_dir: Path,
    version: str,
    commit: str,
    published_at: str,
) -> dict[str, Path]:
    """Copy exact versioned build outputs to stable names and create metadata."""

    artifact_dir = Path(artifact_dir).expanduser().resolve()
    output_dir = Path(output_dir).expanduser().resolve()
    if not artifact_dir.is_dir():
        raise ValueError(f"artifact directory missing: {artifact_dir}")
    _reject_private_inputs(artifact_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    source_paths = _versioned_paths(artifact_dir, version)
    stable_paths: dict[str, Path] = {}
    for target, (_, filename) in _TARGETS.items():
        destination = output_dir / filename
        shutil.copyfile(source_paths[target], destination)
        stable_paths[target] = destination
    manifest_path = output_dir / "latest.json"
    build_release_manifest(
        version=version,
        commit=commit,
        artifacts=stable_paths,
        output=manifest_path,
        published_at=published_at,
    )
    checksum_lines = [
        f"{_sha256(stable_paths[target])}  {stable_paths[target].name}"
        for target in (
            "windows-x86_64",
            "windows-installer-x86_64",
            "linux-x86_64",
            "linux-deb-amd64",
        )
    ]
    (output_dir / "SHA256SUMS").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")
    return {"manifest": manifest_path, **stable_paths}


def _content_type(path: Path) -> str:
    if path.name == "SHA256SUMS":
        return "text/plain; charset=utf-8"
    if path.name.endswith(".tar.gz"):
        return "application/gzip"
    return _CONTENT_TYPES.get(path.suffix.casefold(), "application/octet-stream")


def _validate_prepared_release(output_dir: Path) -> Path:
    output_dir = Path(output_dir).expanduser().resolve()
    if not output_dir.is_dir():
        raise ValueError(f"prepared release directory missing: {output_dir}")
    for filename in STABLE_FILES:
        path = output_dir / filename
        if not path.is_file():
            raise ValueError(f"prepared release file missing: {path}")
    return output_dir


def publish_r2(
    output_dir: Path,
    *,
    runner: str = "npx",
    wrangler_version: str = "4",
    bucket: str = "save-editor-downloads",
) -> None:
    """Upload stable files; credentials are supplied by Wrangler's environment."""

    output_dir = Path(output_dir).resolve()
    for filename in STABLE_FILES:
        path = output_dir / filename
        if not path.is_file():
            raise ValueError(f"prepared release file missing: {path}")
        command = [
            runner,
            "--yes",
            f"wrangler@{wrangler_version}",
            "r2",
            "object",
            "put",
            f"{bucket}/{filename}",
            "--file",
            str(path),
            "--remote",
            "--content-type",
            _content_type(path),
        ]
        if filename == "latest.json":
            command.extend(["--cache-control", "public, max-age=60, must-revalidate"])
        else:
            command.extend(
                [
                    "--cache-control",
                    "public, max-age=31536000, immutable",
                    "--content-disposition",
                    f'attachment; filename="{filename}"',
                ]
            )
        subprocess.run(command, check=True)


def verify_public_r2(
    output_dir: Path,
    *,
    base_url: str = DOWNLOAD_BASE_URL,
    timeout: float = 30.0,
) -> None:
    """Read every public object back and compare bytes and advertised length."""

    output_dir = Path(output_dir).resolve()
    base_url = base_url.rstrip("/")
    for filename in STABLE_FILES:
        local = output_dir / filename
        if not local.is_file():
            raise ValueError(f"prepared release file missing: {local}")
        request = Request(
            f"{base_url}/{filename}?readback={int(time.time())}",
            headers={"User-Agent": _RELEASE_USER_AGENT},
            method="GET",
        )
        with urlopen(request, timeout=timeout) as response:
            body = response.read()
            status = getattr(response, "status", 200)
            if status != 200:
                raise ValueError(f"R2 read-back failed for {filename}: HTTP {status}")
            advertised = response.headers.get("Content-Length")
        if advertised is not None and int(advertised) != len(body):
            raise ValueError(f"R2 size mismatch for {filename}")
        if body != local.read_bytes():
            raise ValueError(f"R2 SHA-256 mismatch for {filename}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path)
    parser.add_argument("--version")
    parser.add_argument("--commit")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--prepared",
        action="store_true",
        help="publish an existing prepared output directory without rebuilding it",
    )
    parser.add_argument(
        "--published-at",
        default=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    )
    parser.add_argument("--publish-r2", action="store_true")
    parser.add_argument("--verify-r2", action="store_true")
    parser.add_argument("--r2-base-url", default=DOWNLOAD_BASE_URL)
    args = parser.parse_args(argv)
    try:
        if args.prepared:
            if args.artifacts is not None or args.version is not None or args.commit is not None:
                parser.error("--prepared cannot be combined with --artifacts, --version, or --commit")
            output_dir = _validate_prepared_release(args.output)
        else:
            missing = [
                option
                for option, value in (
                    ("--artifacts", args.artifacts),
                    ("--version", args.version),
                    ("--commit", args.commit),
                )
                if value is None
            ]
            if missing:
                parser.error(f"the following arguments are required: {', '.join(missing)}")
            prepare_release(
                artifact_dir=args.artifacts,
                output_dir=args.output,
                version=args.version,
                commit=args.commit,
                published_at=args.published_at,
            )
            output_dir = args.output.resolve()
        if args.publish_r2:
            publish_r2(output_dir)
        if args.verify_r2:
            verify_public_r2(output_dir, base_url=args.r2_base_url)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        parser.error(str(exc))
    print(output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
