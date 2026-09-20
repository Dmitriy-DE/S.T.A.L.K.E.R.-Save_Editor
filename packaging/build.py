"""Build reproducible standalone artifacts for the Qt editor.

The builder is intentionally stdlib-only.  PyInstaller, PySide6 and the
native decoder are build inputs, not imports required by this orchestration
module.  A build always runs on the target operating system: PyInstaller does
not cross-compile Windows executables from Linux (or the reverse).
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
import zipfile
from collections.abc import Iterable, Mapping
from pathlib import Path

from editor.release_artifacts import (
    APP_NAME,
    DEBIAN_NAME,
    artifact_names,
    debian_version as _debian_version,
)

SUPPORTED_TARGETS = frozenset({"linux", "windows"})
PRIVATE_NAMES = frozenset(
    {
        ".git",
        ".local",
        ".env",
        ".env.local",
        ".env.production",
        "credentials",
        "credentials.json",
        "token.json",
    }
)
PRIVATE_SUFFIXES = frozenset({".sav", ".bak"})


class BuildError(RuntimeError):
    """Raised when a package cannot be built or fails a safety gate."""


def repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def host_target(system: str | None = None) -> str:
    """Map a host OS name to the first-beta build target."""

    name = (platform.system() if system is None else system).strip().lower()
    if name == "linux":
        return "linux"
    if name == "windows":
        return "windows"
    raise BuildError(
        f"ОС {system or '<unknown>'} не поддерживается; нужны Linux или Windows x86_64"
    )


def resolve_target(requested: str, *, host: str | None = None) -> str:
    """Resolve ``auto`` and reject an unsafe cross-OS build request."""

    target = requested.strip().lower()
    if target == "auto":
        target = host_target(host)
    if target not in SUPPORTED_TARGETS:
        raise BuildError(f"Неизвестный target: {requested}")
    actual_host = host_target(host)
    if target != actual_host:
        raise BuildError(
            f"Нельзя собрать target={target} на host={actual_host}: "
            "PyInstaller не является cross-compiler; запустите builder на целевой ОС"
        )
    return target


def read_version(root: Path | None = None) -> str:
    root = root or repository_root()
    value = (root / "VERSION").read_text(encoding="utf-8").strip()
    if not value or any(ch.isspace() for ch in value):
        raise BuildError("VERSION пуст или содержит пробелы")
    return value


def _git_commit(root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return result.stdout.strip() or "unknown"


def _git_state(root: Path, *, ignore: Path | None = None) -> tuple[str, tuple[str, ...]]:
    """Return commit and working-tree paths so artifacts cannot hide edits.

    ``ignore`` drops one directory from the report: when the output directory
    sits inside the checkout, the build's own products would otherwise make
    every manifest claim the source was dirty.
    """

    commit = _git_commit(root)
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return commit, ()
    prefix: str | None = None
    if ignore is not None:
        try:
            prefix = ignore.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            prefix = None
    paths = tuple(
        entry
        for entry in (
            line[3:].strip()
            for line in result.stdout.splitlines()
            if len(line) >= 4 and line[3:].strip()
        )
        if prefix is None or not (entry == prefix or entry.startswith(f"{prefix}/"))
    )
    return commit, paths


def _version_or_missing(distribution: str) -> str:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return "missing"


def dependency_manifest(target: str) -> dict[str, str]:
    """Collect versions without making a missing optional dependency fatal."""

    return {
        "python": platform.python_version(),
        "pyinstaller": _version_or_missing("pyinstaller"),
        "pyside6": _version_or_missing("PySide6"),
        "pyooz": _version_or_missing("pyooz"),
        "target": target,
    }


# Debian dependency floor.  The bundle links against the glibc of the build
# host, so a hard-coded minimum silently under-declares the requirement as soon
# as the builder moves to a newer runner image.  2.35 (Ubuntu 22.04) is only the
# fallback for hosts where the version cannot be detected.
FALLBACK_LIBC_VERSION = "2.35"


def libc_requirement(host_version: str | None = None) -> str:
    """Return the libc6 minimum matching the host that produced the bundle."""

    if host_version is None:
        _, host_version = platform.libc_ver()
    parts = (host_version or "").split(".")
    if len(parts) >= 2 and all(part.isdigit() for part in parts[:2]):
        return f"{int(parts[0])}.{int(parts[1])}"
    return FALLBACK_LIBC_VERSION


def build_manifest(
    *, root: Path, target: str, version: str, output_dir: Path | None = None
) -> dict[str, object]:
    commit, dirty_paths = _git_state(root, ignore=output_dir)
    return {
        "application": APP_NAME,
        "version": version,
        "target": target,
        "architecture": "x86_64",
        "libc_minimum": libc_requirement() if target == "linux" else None,
        "source_commit": commit,
        "source_dirty": bool(dirty_paths),
        "dirty_paths": list(dirty_paths),
        "dependencies": dependency_manifest(target),
        "runtime_policy": {
            "core": "Python standard library",
            "decoder": "bundled pyooz==0.0.8 or Linux vendor fallback",
            "ui": "bundled PySide6==6.11.2",
            "steam_helper": "external executable; never bundled",
        },
    }


def _iter_tree(root: Path) -> Iterable[Path]:
    yield from sorted(root.rglob("*"), key=lambda item: item.as_posix())


def scan_package_tree(root: Path) -> None:
    """Reject private inputs and repository metadata before archive creation."""

    root = Path(root)
    if not root.is_dir():
        raise BuildError(f"Package tree отсутствует: {root}")
    rejected: list[str] = []
    for path in _iter_tree(root):
        relative = path.relative_to(root)
        if any(part.lower() in PRIVATE_NAMES for part in relative.parts):
            rejected.append(str(relative))
            continue
        if path.is_file() and (
            path.suffix.lower() in PRIVATE_SUFFIXES
            or path.suffix.lower() in {".pem", ".key"}
            or path.name.lower() in PRIVATE_NAMES
        ):
            rejected.append(str(relative))
    if rejected:
        details = ", ".join(sorted(rejected)[:8])
        suffix = "…" if len(rejected) > 8 else ""
        raise BuildError(f"Package содержит private input: {details}{suffix}")


def _write_json(path: Path, value: Mapping[str, object]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _copy_metadata(runtime: Path, manifest: Mapping[str, object]) -> None:
    _write_json(runtime / "BUILD_MANIFEST.json", manifest)
    (runtime / "SOURCE_COMMIT.txt").write_text(
        f"{manifest['source_commit']}\n", encoding="utf-8"
    )


def _run_pyinstaller(*, root: Path, target: str, work: Path, runtime_dist: Path) -> None:
    spec = root / "packaging" / "editor.spec"
    if not spec.is_file():
        raise BuildError(f"PyInstaller spec отсутствует: {spec}")
    work.mkdir(parents=True, exist_ok=True)
    runtime_dist.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(
        {
            "SAVE_EDITOR_ROOT": str(root),
            "SAVE_EDITOR_TARGET": target,
            "PYTHONHASHSEED": "0",
        }
    )
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--distpath",
        str(runtime_dist),
        "--workpath",
        str(work / "pyinstaller-work"),
        str(spec),
    ]
    try:
        subprocess.run(command, cwd=root, env=env, check=True)
    except FileNotFoundError as exc:
        raise BuildError(
            "PyInstaller не установлен. Установите requirements-build.txt в build environment"
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise BuildError(f"PyInstaller завершился с exit code {exc.returncode}") from exc


def _normalise_tar_info(info: tarfile.TarInfo) -> tarfile.TarInfo:
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mtime = 0
    return info


def _add_tar_entry(archive: tarfile.TarFile, path: Path, arcname: str) -> None:
    info = archive.gettarinfo(str(path), arcname=arcname)
    _normalise_tar_info(info)
    if info.isreg():
        with path.open("rb") as handle:
            archive.addfile(info, handle)
    else:
        archive.addfile(info)


def _make_tar(runtime: Path, destination: Path) -> None:
    with destination.open("wb") as raw_file:
        import gzip

        with (
            gzip.GzipFile(fileobj=raw_file, mode="wb", mtime=0) as gzip_file,
            tarfile.open(fileobj=gzip_file, mode="w") as archive,
        ):
                _add_tar_entry(archive, runtime, APP_NAME)
                for path in _iter_tree(runtime):
                    _add_tar_entry(archive, path, str(Path(APP_NAME) / path.relative_to(runtime)))


def _zip_info(name: str, *, mode: int, is_dir: bool = False) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name)
    info.date_time = (1980, 1, 1, 0, 0, 0)
    info.compress_type = zipfile.ZIP_DEFLATED
    permissions = stat.S_IMODE(mode) or (0o755 if is_dir else 0o644)
    info.external_attr = (permissions & 0xFFFF) << 16
    if is_dir:
        info.external_attr |= 0x10
    return info


def _make_zip(runtime: Path, destination: Path) -> None:
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        root_info = _zip_info(f"{APP_NAME}/", mode=0o755, is_dir=True)
        archive.writestr(root_info, b"")
        for path in _iter_tree(runtime):
            relative = Path(APP_NAME) / path.relative_to(runtime)
            if path.is_dir():
                archive.writestr(_zip_info(f"{relative.as_posix()}/", mode=path.stat().st_mode, is_dir=True), b"")
            else:
                archive.writestr(_zip_info(relative.as_posix(), mode=path.stat().st_mode), path.read_bytes())


def _desktop_entry() -> str:
    return """[Desktop Entry]
Type=Application
Name=S.T.A.L.K.E.R. Save Editor
Comment=Inspect and edit local S.T.A.L.K.E.R. saves
Exec=stalker2-save-editor
Icon=stalker2-save-editor
Terminal=false
Categories=Utility;Game;
"""


def _build_deb(*, runtime: Path, destination: Path, work: Path, version: str) -> None:
    dpkg = shutil.which("dpkg-deb")
    if not dpkg:
        raise BuildError("dpkg-deb не найден; Debian package собирается на Debian/Ubuntu host")
    stage = work / "deb-root"
    if stage.exists():
        shutil.rmtree(stage)
    runtime_destination = stage / "usr" / "lib" / DEBIAN_NAME
    runtime_destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copytree(runtime, runtime_destination)
    except (OSError, shutil.Error) as exc:
        free = shutil.disk_usage(stage.parent).free
        raise BuildError(
            f"Не удалось скопировать runtime в Debian staging ({exc.__class__.__name__}); "
            f"свободно {free / 1024**3:.1f} GiB. Чаще всего это нехватка места: "
            "staging повторяет всё дерево PyInstaller."
        ) from exc
    wrapper = stage / "usr" / "bin" / "stalker2-save-editor"
    wrapper.parent.mkdir(parents=True, exist_ok=True)
    wrapper.write_text(
        "#!/bin/sh\nexec /usr/lib/stalker2-save-editor/SaveEditor \"$@\"\n",
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    desktop = stage / "usr" / "share" / "applications" / "stalker2-save-editor.desktop"
    desktop.parent.mkdir(parents=True, exist_ok=True)
    desktop.write_text(_desktop_entry(), encoding="utf-8")
    for size in (256, 128, 64):
        icon_src = repository_root() / "assets" / f"app_icon_{size}.png"
        if icon_src.is_file():
            icon_dst = (
                stage / "usr" / "share" / "icons" / "hicolor"
                / f"{size}x{size}" / "apps" / "stalker2-save-editor.png"
            )
            icon_dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(icon_src, icon_dst)
    control_dir = stage / "DEBIAN"
    control_dir.mkdir(parents=True, exist_ok=True)
    (control_dir / "control").write_text(
        f"""Package: stalker2-save-editor
Version: {_debian_version(version)}
Section: games
Priority: optional
Architecture: amd64
Maintainer: S.T.A.L.K.E.R. 2 Save Editor contributors
Depends: libc6 (>= {libc_requirement()})
Description: S.T.A.L.K.E.R. 2 save editor
 A local Qt editor with safe preview, backup and Steam Cloud workflows.
""",
        encoding="utf-8",
    )
    scan_package_tree(stage)
    env = os.environ.copy()
    env["SOURCE_DATE_EPOCH"] = "0"
    command = [dpkg, "--build", "--root-owner-group", str(stage), str(destination)]
    try:
        subprocess.run(command, cwd=work, env=env, check=True)
    except subprocess.CalledProcessError as exc:
        raise BuildError(f"dpkg-deb завершился с exit code {exc.returncode}") from exc


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_checksums(paths: Iterable[Path], destination: Path) -> None:
    lines = [f"{_sha256(path)}  {path.name}" for path in sorted(paths, key=lambda item: item.name)]
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")


# Rough working-set requirement for one Linux build: the PyInstaller onedir
# tree (Python runtime + Qt) plus the Debian staging copy of that same tree plus
# the compressed archive.  Measured at ~1.7 GB; the margin is deliberate.
MIN_FREE_BYTES = 3 * 1024**3


def _require_free_space(output_dir: Path) -> None:
    """Fail early and legibly when the output filesystem is too small.

    A build started into a small tmpfs fills it mid-copy, and the failure
    surfaces as a bare shutil.Error listing half-copied paths - which says
    nothing about the cause.  Check once, up front, in bytes the user can act on.
    """

    free = shutil.disk_usage(output_dir).free
    if free >= MIN_FREE_BYTES:
        return
    raise BuildError(
        f"Недостаточно места в {output_dir}: свободно {free / 1024**3:.1f} GiB, "
        f"нужно не менее {MIN_FREE_BYTES / 1024**3:.0f} GiB. "
        "Сборка PyInstaller разворачивает Python и Qt, затем копирует это дерево "
        "ещё раз для Debian staging. Выберите --output-dir на обычном диске "
        "(не на tmpfs вроде /tmp) и при необходимости задайте TMPDIR там же."
    )


def build(
    *,
    target: str,
    output_dir: Path,
    version: str | None = None,
    root: Path | None = None,
    allow_dirty: bool = False,
) -> tuple[Path, ...]:
    """Build artifacts and return their paths, including ``SHA256SUMS``."""

    root = (root or repository_root()).resolve()
    target = resolve_target(target)
    version = version or read_version(root)
    _, dirty_paths = _git_state(root)
    if dirty_paths and not allow_dirty:
        preview = ", ".join(dirty_paths[:5])
        suffix = "…" if len(dirty_paths) > 5 else ""
        raise BuildError(
            f"Рабочее дерево изменено ({preview}{suffix}); commit changes или "
            "передайте --allow-dirty для локального непубликуемого smoke"
        )
    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    _require_free_space(output_dir)
    work = output_dir / ".build" / target
    runtime_dist = work / "dist"
    if work.exists():
        shutil.rmtree(work)
    runtime_dist.mkdir(parents=True, exist_ok=True)

    _run_pyinstaller(root=root, target=target, work=work, runtime_dist=runtime_dist)
    runtime = runtime_dist / APP_NAME
    executable = runtime / ("SaveEditor.exe" if target == "windows" else "SaveEditor")
    if not executable.is_file():
        raise BuildError(f"PyInstaller output missing: {executable}")
    updater = runtime / ("SaveEditor-updater.exe" if target == "windows" else "SaveEditor-updater")
    if not updater.is_file():
        raise BuildError(f"PyInstaller updater output missing: {updater}")
    manifest = build_manifest(root=root, target=target, version=version, output_dir=output_dir)
    _copy_metadata(runtime, manifest)
    scan_package_tree(runtime)

    names = artifact_names(version, target)
    artifacts: list[Path] = []
    archive = output_dir / names[0]
    if target == "linux":
        _make_tar(runtime, archive)
        artifacts.append(archive)
        deb = output_dir / names[1]
        _build_deb(runtime=runtime, destination=deb, work=work, version=version)
        artifacts.append(deb)
    else:
        _make_zip(runtime, archive)
        artifacts.append(archive)
    checksums = output_dir / "SHA256SUMS"
    _write_checksums(artifacts, checksums)
    shutil.rmtree(work)
    return (*artifacts, checksums)


def plan(*, target: str, output_dir: Path, version: str | None = None) -> dict[str, object]:
    resolved = resolve_target(target)
    version = version or read_version()
    output = Path(output_dir).expanduser().resolve()
    return {
        "target": resolved,
        "host": host_target(),
        "version": version,
        "python": sys.executable,
        "spec": str(repository_root() / "packaging" / "editor.spec"),
        "output_dir": str(output),
        "artifacts": [str(output / name) for name in artifact_names(version, resolved)],
        "checksums": str(output / "SHA256SUMS"),
        "cross_compile": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build SaveEditor standalone artifacts")
    parser.add_argument("--target", choices=("auto", "linux", "windows"), default="auto")
    parser.add_argument("--output-dir", type=Path, default=repository_root() / "dist")
    parser.add_argument("--version")
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="разрешить локальную сборку из dirty tree; manifest отметит source_dirty",
    )
    parser.add_argument("--plan", action="store_true", help="print the build plan without running PyInstaller")
    args = parser.parse_args(argv)
    try:
        if args.plan:
            print(json.dumps(plan(target=args.target, output_dir=args.output_dir, version=args.version), ensure_ascii=False, indent=2))
            return 0
        artifacts = build(
            target=args.target,
            output_dir=args.output_dir,
            version=args.version,
            allow_dirty=args.allow_dirty,
        )
        for artifact in artifacts:
            print(artifact)
        return 0
    except BuildError as exc:
        print(f"Build error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
