"""Build reproducible standalone artifacts for the Qt editor.

The builder is intentionally stdlib-only.  PyInstaller, PySide6 and the
native decoder are build inputs, not imports required by this orchestration
module.  A build always runs on the target operating system: PyInstaller does
not cross-compile Windows executables from Linux (or the reverse).
"""

from __future__ import annotations

import argparse
import datetime
import gzip
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
import time
import zipfile
from collections.abc import Iterable, Mapping
from pathlib import Path

# ``python packaging/build.py`` is the documented CI/Make entry point.  Python
# otherwise puts only ``packaging/`` on ``sys.path`` and cannot see the sibling
# ``editor`` package.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from editor.release_artifacts import (
    APP_NAME,
    DEBIAN_NAME,
    artifact_names,
)
from editor.release_artifacts import debian_version as _debian_version

SUPPORTED_TARGETS = frozenset({"linux", "windows", "macos"})
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
    """Map a host OS name to a supported native build target."""

    name = (platform.system() if system is None else system).strip().lower()
    if name == "linux":
        return "linux"
    if name == "windows":
        return "windows"
    if name == "darwin":
        return "macos"
    raise BuildError(
        f"ОС {system or '<unknown>'} не поддерживается; нужны Linux, Windows x86_64 "
        "или macOS arm64"
    )


def resolve_target(
    requested: str, *, host: str | None = None, machine: str | None = None
) -> str:
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
    if target == "macos":
        actual_machine = (platform.machine() if machine is None else machine).strip().lower()
        if actual_machine not in {"arm64", "aarch64"}:
            raise BuildError(
                f"Сборка macOS поддерживает только arm64, обнаружено {actual_machine or '<unknown>'}"
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


def _source_date_epoch(root: Path | None = None) -> int:
    """Return a stable, non-ancient timestamp for package metadata."""

    override = os.environ.get("SOURCE_DATE_EPOCH", "").strip()
    if override.isdigit() and int(override) > 0:
        return int(override)
    try:
        result = subprocess.run(
            ["git", "show", "-s", "--format=%ct", "HEAD"],
            cwd=root or repository_root(),
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return int(time.time())
    value = result.stdout.strip()
    return int(value) if value.isdigit() and int(value) > 0 else int(time.time())


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
SUPPORTED_GLIBC_BASELINE = "2.35"
FALLBACK_LIBC_VERSION = SUPPORTED_GLIBC_BASELINE
DESKTOP_ID = "com.github.dmitriyde.stalker2saveeditor"
DEBIAN_RUNTIME_DEPENDENCIES = (
    "libegl1",
    "libglib2.0-0",
    "libdbus-1-3",
    "libxkbcommon0",
    "libxkbcommon-x11-0",
    "libxcb-cursor0",
    "libxcb-icccm4",
    "libxcb-image0",
    "libxcb-keysyms1",
    "libxcb-render-util0",
)


def libc_requirement(host_version: str | None = None) -> str:
    """Return the libc6 minimum matching the host that produced the bundle."""

    if host_version is None:
        _, host_version = platform.libc_ver()
    parts = (host_version or "").split(".")
    if len(parts) >= 2 and all(part.isdigit() for part in parts[:2]):
        return f"{int(parts[0])}.{int(parts[1])}"
    return FALLBACK_LIBC_VERSION


def release_libc_requirement() -> str:
    """Return the glibc floor used by public Linux release builds."""

    return SUPPORTED_GLIBC_BASELINE


def require_release_glibc(host_version: str | None = None) -> str:
    """Fail unless the current build host is the declared release baseline."""

    detected = libc_requirement(host_version)
    if detected != SUPPORTED_GLIBC_BASELINE:
        raise BuildError(
            "Публичный Linux release должен собираться на glibc baseline "
            f"{SUPPORTED_GLIBC_BASELINE}, обнаружено {detected}; "
            "используйте Ubuntu 22.04-compatible build environment"
        )
    return SUPPORTED_GLIBC_BASELINE


def build_manifest(
    *, root: Path, target: str, version: str, output_dir: Path | None = None
) -> dict[str, object]:
    commit, dirty_paths = _git_state(root, ignore=output_dir)
    return {
        "application": APP_NAME,
        "version": version,
        "target": target,
        "architecture": "arm64" if target == "macos" else "x86_64",
        "libc_minimum": libc_requirement() if target == "linux" else None,
        "source_commit": commit,
        "source_dirty": bool(dirty_paths),
        "dirty_paths": list(dirty_paths),
        "dependencies": dependency_manifest(target),
        "runtime_policy": {
            "core": "Python standard library",
            "decoder": "bundled pyooz==0.0.8 or Linux vendor fallback",
            "encoder": "bundled native ooz_encoder; required for changed compressed saves",
            "ui": "bundled PySide6==6.11.2",
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


def stage_macos_bundle_metadata(
    work: Path, manifest: Mapping[str, object]
) -> Path:
    """Prepare bundle metadata before PyInstaller signs the macOS app."""

    metadata_dir = Path(work) / "bundle-metadata"
    if metadata_dir.exists():
        shutil.rmtree(metadata_dir)
    metadata_dir.mkdir(parents=True)
    _copy_metadata(metadata_dir, manifest)
    return metadata_dir


def _run_pyinstaller(
    *,
    root: Path,
    target: str,
    work: Path,
    runtime_dist: Path,
    encoder_dir: Path,
    app_icon: Path | None = None,
    app_metadata_dir: Path | None = None,
) -> None:
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
            "SAVE_EDITOR_ENCODER_DIR": str(encoder_dir),
            "PYTHONHASHSEED": "0",
        }
    )
    if app_icon is not None:
        env["SAVE_EDITOR_APP_ICON"] = str(app_icon)
    if app_metadata_dir is not None:
        env["SAVE_EDITOR_BUILD_METADATA_DIR"] = str(app_metadata_dir)
    pythonpath = [str(encoder_dir), str(root)]
    if env.get("PYTHONPATH"):
        pythonpath.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(pythonpath)
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


def _generate_macos_icon(source: Path, destination: Path) -> Path:
    """Convert the checked-in PNG artwork into the ICNS file used by BUNDLE."""

    source = Path(source)
    destination = Path(destination)
    if not source.is_file():
        raise BuildError(f"Исходная иконка macOS отсутствует: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            ["sips", "-s", "format", "icns", str(source), "--out", str(destination)],
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise BuildError(f"Не удалось сгенерировать SaveEditor.icns через sips: {exc}") from exc
    if not destination.is_file():
        raise BuildError(f"sips не создал иконку macOS: {destination}")
    return destination


def _make_macos_zip(bundle: Path, destination: Path) -> None:
    """Archive an app bundle with Apple's metadata and symlinks preserved."""

    try:
        subprocess.run(
            [
                "ditto",
                "-c",
                "-k",
                "--sequesterRsrc",
                "--keepParent",
                str(bundle),
                str(destination),
            ],
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise BuildError(f"Не удалось создать macOS ZIP через ditto: {exc}") from exc
    if not destination.is_file():
        raise BuildError(f"ditto не создал macOS ZIP: {destination}")


def _make_macos_dmg(bundle: Path, destination: Path, *, version: str) -> None:
    """Create a compressed read-only disk image containing the app bundle."""

    try:
        subprocess.run(
            [
                "hdiutil",
                "create",
                "-volname",
                f"{APP_NAME} {version}",
                "-srcfolder",
                str(bundle),
                "-ov",
                "-format",
                "UDZO",
                str(destination),
            ],
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise BuildError(f"Не удалось создать macOS DMG через hdiutil: {exc}") from exc
    if not destination.is_file():
        raise BuildError(f"hdiutil не создал macOS DMG: {destination}")


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


def _windows_installer_script() -> str:
    """Return the Inno Setup script used for the Windows installer artifact."""

    return r'''#define AppName "S.T.A.L.K.E.R. Save Editor"
#define AppVersion GetEnv('SAVE_EDITOR_VERSION')
#define RuntimeDir GetEnv('SAVE_EDITOR_RUNTIME')
#define OutputDir GetEnv('SAVE_EDITOR_OUTPUT')
#define OutputBaseName GetEnv('SAVE_EDITOR_OUTPUT_NAME')

[Setup]
AppId={{B5B1C7A0-9D5B-4D99-9D30-8A4DF0E6AC91}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Save Editor contributors
DefaultDirName={autopf}\S.T.A.L.K.E.R. Save Editor
DefaultGroupName={#AppName}
UninstallDisplayIcon={app}\SaveEditor.exe
OutputDir={#OutputDir}
OutputBaseFilename={#OutputBaseName}
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
CloseApplications=yes
RestartApplications=no
WizardStyle=modern

[Files]
Source: "{#RuntimeDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\SaveEditor.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\SaveEditor.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[Run]
Filename: "{app}\SaveEditor.exe"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: files; Name: "{app}\INSTALLER_MARKER"

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    SaveStringToFile(ExpandConstant('{app}\INSTALLER_MARKER'), 'installed-by-save-editor-installer' + #13#10, False);
end;
'''


def _find_inno_compiler() -> Path:
    """Locate the native Inno Setup compiler on a Windows build host."""

    for command in ("ISCC.exe", "iscc"):
        found = shutil.which(command)
        if found:
            return Path(found)
    for variable in ("ProgramFiles(x86)", "ProgramFiles"):
        root = os.environ.get(variable)
        if root:
            candidate = Path(root) / "Inno Setup 6" / "ISCC.exe"
            if candidate.is_file():
                return candidate
    raise BuildError(
        "Inno Setup не найден; установите Inno Setup 6 на Windows build host"
    )


def _build_windows_installer(
    *, runtime: Path, destination: Path, work: Path, version: str
) -> Path:
    """Build a separately installable Windows executable from the runtime tree."""

    compiler = _find_inno_compiler()
    work.mkdir(parents=True, exist_ok=True)
    script = work / "windows-installer.iss"
    script.write_text(_windows_installer_script(), encoding="utf-8")
    environment = os.environ.copy()
    environment.update(
        {
            "SAVE_EDITOR_VERSION": version,
            "SAVE_EDITOR_RUNTIME": str(runtime),
            "SAVE_EDITOR_OUTPUT": str(destination.parent),
            "SAVE_EDITOR_OUTPUT_NAME": destination.stem,
        }
    )
    try:
        subprocess.run(
            [str(compiler), "/Q", str(script)],
            cwd=work,
            env=environment,
            check=True,
        )
    except FileNotFoundError as exc:
        raise BuildError("Inno Setup compiler не найден") from exc
    except subprocess.CalledProcessError as exc:
        raise BuildError(f"Inno Setup завершился с exit code {exc.returncode}") from exc
    if not destination.is_file():
        raise BuildError(f"Windows installer output missing: {destination}")
    return destination


def _desktop_entry() -> str:
    return f"""[Desktop Entry]
Type=Application
Name=S.T.A.L.K.E.R. Save Editor
Comment=Inspect and edit local S.T.A.L.K.E.R. saves
Exec=stalker2-save-editor
Icon={DESKTOP_ID}
Terminal=false
Categories=Utility;Game;
Keywords=save;editor;S.T.A.L.K.E.R.;game;
StartupNotify=true
"""


def _installed_size_kib(stage: Path) -> int:
    """Return Debian's Installed-Size approximation for the staged payload."""

    total = 0
    for path in stage.rglob("*"):
        if path.is_file() and "DEBIAN" not in path.relative_to(stage).parts:
            total += (path.stat().st_size + 1023) // 1024
    return max(1, total)


def _debian_copyright() -> str:
    return (
        "Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/\n"
        "Upstream-Name: S.T.A.L.K.E.R. Save Editor\n"
        "Source: https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor\n\n"
        "Files: *\n"
        "Copyright: 2026 Dmitriy-DE and contributors\n"
        "License: GPL-3+\n"
        " The full text is available in /usr/share/common-licenses/GPL-3.\n"
    )


def _debian_manpage() -> str:
    return r""".TH STALKER2-SAVE-EDITOR 1 "2026-09-21" "S.T.A.L.K.E.R. Save Editor" "User Commands"
.SH NAME
stalker2-save-editor \- inspect and edit supported S.T.A.L.K.E.R. save files
.SH SYNOPSIS
.B stalker2-save-editor
.RI [ options ]
.SH DESCRIPTION
Launches the desktop S.T.A.L.K.E.R. Save Editor. Save writes are protected by
preview, backup, checksum and atomic replacement guards.
"""


def _debian_changelog(version: str, source_date_epoch: int) -> str:
    date = datetime.datetime.fromtimestamp(source_date_epoch, datetime.UTC)
    formatted_date = date.strftime("%a, %d %b %Y %H:%M:%S +0000")
    return f"""stalker2-save-editor ({_debian_version(version)}) stable; urgency=medium

  * Release the standalone desktop editor with protected save operations.

 -- S.T.A.L.K.E.R. Save Editor contributors <save-editor@users.noreply.github.com>  {formatted_date}
"""


def _debian_lintian_overrides() -> str:
    """Document checks that cannot understand a self-contained PyInstaller tree."""

    return """# The PyInstaller runtime intentionally carries its Qt/Python shared libraries.
stalker2-save-editor: embedded-library
stalker2-save-editor: shared-library-lacks-prerequisites
stalker2-save-editor: library-not-linked-against-libc
# PyInstaller bootloaders are prebuilt non-PIE ELF executables.
stalker2-save-editor: hardening-no-pie
# The upstream provenance archive is retained in the runtime for license/source traceability.
stalker2-save-editor: package-contains-timestamped-gzip
# The UI loads its own copy of Liberation Sans Narrow from the bundle so its
# layout never depends on which system fonts happen to be installed.
stalker2-save-editor: duplicate-font-file
"""


def _is_shared_library(path: Path) -> bool:
    name = path.name
    return name.endswith(".so") or ".so." in name


def _normalise_runtime_libraries(runtime: Path) -> None:
    """Make bundled shared libraries non-executable and remove symbol baggage."""

    strip = shutil.which("strip")
    if strip is None:
        raise BuildError("binutils/strip не найден; Debian package требует stripped shared libraries")
    for path in runtime.rglob("*"):
        if not path.is_file() or not _is_shared_library(path):
            continue
        path.chmod(path.stat().st_mode & ~0o111)
        try:
            subprocess.run(
                [strip, "--strip-unneeded", "--preserve-dates", str(path)],
                check=True,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            raise BuildError(f"Не удалось strip shared library: {path}") from exc


def _normalise_package_timestamps(stage: Path, source_date_epoch: int) -> None:
    """Apply the release timestamp to every staged path for reproducible dpkg output."""

    for path in sorted(stage.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        os.utime(path, (source_date_epoch, source_date_epoch), follow_symlinks=False)


def _normalise_package_permissions(stage: Path) -> None:
    """Use Debian's conventional modes instead of checkout umask modes."""

    for path in stage.rglob("*"):
        if path.is_symlink():
            continue
        if path.is_dir():
            path.chmod(0o755)
        elif path.is_file():
            mode = path.stat().st_mode
            path.chmod(0o755 if mode & 0o111 else 0o644)


def _build_deb(*, runtime: Path, destination: Path, work: Path, version: str) -> None:
    dpkg = shutil.which("dpkg-deb")
    if not dpkg:
        raise BuildError("dpkg-deb не найден; Debian package собирается на Debian/Ubuntu host")
    if os.environ.get("SAVE_EDITOR_REQUIRE_GLIBC_BASELINE") == "1":
        require_release_glibc()
    source_date_epoch = _source_date_epoch()
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
    _normalise_runtime_libraries(runtime_destination)
    wrapper = stage / "usr" / "bin" / "stalker2-save-editor"
    wrapper.parent.mkdir(parents=True, exist_ok=True)
    wrapper.write_text(
        "#!/bin/sh\nexec /usr/lib/stalker2-save-editor/SaveEditor \"$@\"\n",
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    desktop = stage / "usr" / "share" / "applications" / f"{DESKTOP_ID}.desktop"
    desktop.parent.mkdir(parents=True, exist_ok=True)
    desktop.write_text(_desktop_entry(), encoding="utf-8")
    for size in (256, 128, 64):
        icon_src = repository_root() / "assets" / f"app_icon_{size}.png"
        if not icon_src.is_file():
            raise BuildError(f"Иконка приложения отсутствует: {icon_src}")
        icon_dst = (
            stage / "usr" / "share" / "icons" / "hicolor"
            / f"{size}x{size}" / "apps" / f"{DESKTOP_ID}.png"
        )
        icon_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(icon_src, icon_dst)
    metainfo_src = repository_root() / "packaging" / f"{DESKTOP_ID}.metainfo.xml"
    if not metainfo_src.is_file():
        raise BuildError(f"AppStream metainfo отсутствует: {metainfo_src}")
    metainfo_dst = stage / "usr" / "share" / "metainfo" / metainfo_src.name
    metainfo_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(metainfo_src, metainfo_dst)
    copyright_dst = stage / "usr" / "share" / "doc" / DEBIAN_NAME / "copyright"
    copyright_dst.parent.mkdir(parents=True, exist_ok=True)
    copyright_dst.write_text(_debian_copyright(), encoding="utf-8")
    manpage_dst = stage / "usr" / "share" / "man" / "man1" / "stalker2-save-editor.1.gz"
    manpage_dst.parent.mkdir(parents=True, exist_ok=True)
    with (
        manpage_dst.open("wb") as handle,
        gzip.GzipFile(fileobj=handle, mode="wb", mtime=source_date_epoch) as compressed,
    ):
        compressed.write(_debian_manpage().encode("utf-8"))
    changelog_dst = stage / "usr" / "share" / "doc" / DEBIAN_NAME / "changelog.gz"
    with (
        changelog_dst.open("wb") as handle,
        gzip.GzipFile(fileobj=handle, mode="wb", mtime=source_date_epoch) as compressed,
    ):
        compressed.write(_debian_changelog(version, source_date_epoch).encode("utf-8"))
    overrides_dst = stage / "usr" / "share" / "lintian" / "overrides" / DEBIAN_NAME
    overrides_dst.parent.mkdir(parents=True, exist_ok=True)
    overrides_dst.write_text(_debian_lintian_overrides(), encoding="utf-8")
    control_dir = stage / "DEBIAN"
    control_dir.mkdir(parents=True, exist_ok=True)
    (control_dir / "control").write_text(
        f"""Package: stalker2-save-editor
Version: {_debian_version(version)}
Section: utils
Priority: optional
Architecture: amd64
Maintainer: S.T.A.L.K.E.R. Save Editor contributors <save-editor@users.noreply.github.com>
Homepage: https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor
Installed-Size: {_installed_size_kib(stage)}
Depends: libc6 (>= {libc_requirement()}), {', '.join(DEBIAN_RUNTIME_DEPENDENCIES)}
Description: S.T.A.L.K.E.R. save editor
 A local Qt editor for supported S.T.A.L.K.E.R. saves.
 Safe preview, backup, verification and explicit Steam Cloud workflows.
""",
        encoding="utf-8",
    )
    _normalise_package_permissions(stage)
    _normalise_package_timestamps(stage, source_date_epoch)
    scan_package_tree(stage)
    env = os.environ.copy()
    env["SOURCE_DATE_EPOCH"] = str(source_date_epoch)
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

    app_icon: Path | None = None
    if target == "macos":
        app_icon = _generate_macos_icon(
            root / "assets" / "app_icon_256.png", work / "SaveEditor.icns"
        )
    manifest = build_manifest(root=root, target=target, version=version, output_dir=output_dir)
    app_metadata_dir = (
        stage_macos_bundle_metadata(work, manifest) if target == "macos" else None
    )

    encoder_dir = work / "ooz_encoder"
    try:
        subprocess.run(
            [
                sys.executable,
                str(root / "tools" / "build_ooz_encoder.py"),
                "--root",
                str(root),
                "--output-dir",
                str(encoder_dir),
            ],
            cwd=root,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise BuildError(f"Не удалось собрать обязательный ooz_encoder: {exc}") from exc

    _run_pyinstaller(
        root=root,
        target=target,
        work=work,
        runtime_dist=runtime_dist,
        encoder_dir=encoder_dir,
        app_icon=app_icon,
        app_metadata_dir=app_metadata_dir,
    )
    runtime = runtime_dist / (
        f"{APP_NAME}.app" if target == "macos" else APP_NAME
    )
    executable = (
        runtime / "Contents" / "MacOS" / "SaveEditor"
        if target == "macos"
        else runtime / ("SaveEditor.exe" if target == "windows" else "SaveEditor")
    )
    if not executable.is_file():
        raise BuildError(f"PyInstaller output missing: {executable}")
    updater = (
        runtime / "Contents" / "MacOS" / "SaveEditor-updater"
        if target == "macos"
        else runtime / ("SaveEditor-updater.exe" if target == "windows" else "SaveEditor-updater")
    )
    if not updater.is_file():
        raise BuildError(f"PyInstaller updater output missing: {updater}")
    if target == "macos":
        app_bundle = output_dir / f"{APP_NAME}.app"
        if app_bundle.exists():
            shutil.rmtree(app_bundle)
        shutil.copytree(runtime, app_bundle, symlinks=True)
        scan_package_tree(app_bundle)
    else:
        app_bundle = None
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
    elif target == "windows":
        _make_zip(runtime, archive)
        artifacts.append(archive)
        installer = output_dir / names[1]
        _build_windows_installer(
            runtime=runtime,
            destination=installer,
            work=work,
            version=version,
        )
        artifacts.append(installer)
    else:
        assert app_bundle is not None
        _make_macos_zip(app_bundle, archive)
        artifacts.append(archive)
        disk_image = output_dir / names[1]
        _make_macos_dmg(app_bundle, disk_image, version=version)
        artifacts.append(disk_image)
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
        "architecture": "arm64" if resolved == "macos" else "x86_64",
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
    parser.add_argument(
        "--target", choices=("auto", "linux", "windows", "macos"), default="auto"
    )
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
