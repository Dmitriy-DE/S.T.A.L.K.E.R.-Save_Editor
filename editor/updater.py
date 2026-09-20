"""Dependency-free download, staging, and replacement support for updates."""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import uuid
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .update_manifest import (
    DOWNLOAD_BASE_URL,
    DOWNLOAD_HOST,
    ArtifactSpec,
    ManifestError,
    ReleaseManifest,
    compare_versions,
)

DEFAULT_MANIFEST_URL = f"{DOWNLOAD_BASE_URL}/latest.json"
UPDATE_USER_AGENT = "SaveEditor-updater/1"
UpdateState = Literal["current", "available", "unavailable", "invalid"]


@dataclass(frozen=True)
class UpdateCheckResult:
    """A non-throwing result for a background update check."""

    state: UpdateState
    manifest: ReleaseManifest | None = None
    artifact: ArtifactSpec | None = None
    error: str | None = None


@dataclass(frozen=True)
class InstallationInfo:
    """The installation that an external updater is allowed to replace."""

    target: str
    architecture: str
    kind: Literal["portable", "installer", "package", "development"]
    root: Path
    executable: Path


def _default_target() -> str:
    name = platform.system().casefold()
    if name == "windows":
        return "windows"
    if name == "linux":
        return "linux"
    raise ManifestError(f"unsupported update platform: {platform.system()}")


def _validate_url(url: str, *, allowed_hosts: frozenset[str], allowed_schemes: frozenset[str]) -> None:
    parsed = urlparse(url)
    if (
        parsed.scheme not in allowed_schemes
        or parsed.hostname not in allowed_hosts
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ManifestError("update URL is outside the trusted download policy")


class UpdateClient:
    """Fetch and verify a release manifest and one selected artifact."""

    def __init__(
        self,
        *,
        manifest_url: str = DEFAULT_MANIFEST_URL,
        current_version: str,
        target: str | None = None,
        architecture: str = "x86_64",
        kind: str = "portable",
        timeout: float = 15.0,
        allowed_hosts: frozenset[str] = frozenset({DOWNLOAD_HOST}),
        allowed_schemes: frozenset[str] = frozenset({"https"}),
    ) -> None:
        _validate_url(
            manifest_url,
            allowed_hosts=allowed_hosts,
            allowed_schemes=allowed_schemes,
        )
        self.manifest_url = manifest_url
        self.current_version = current_version
        self.target = target or _default_target()
        self.architecture = architecture
        self.kind = kind
        self.timeout = timeout
        self.allowed_hosts = allowed_hosts
        self.allowed_schemes = allowed_schemes

    def _open(self, url: str):
        _validate_url(url, allowed_hosts=self.allowed_hosts, allowed_schemes=self.allowed_schemes)
        request = Request(
            url,
            headers={
                "Accept": "application/json, application/octet-stream",
                "User-Agent": UPDATE_USER_AGENT,
            },
        )
        response = urlopen(request, timeout=self.timeout)
        final_url = response.geturl()
        _validate_url(final_url, allowed_hosts=self.allowed_hosts, allowed_schemes=self.allowed_schemes)
        return response

    def check(self) -> UpdateCheckResult:
        try:
            with self._open(self.manifest_url) as response:
                payload = response.read(2 * 1024 * 1024 + 1)
            if len(payload) > 2 * 1024 * 1024:
                raise ManifestError("update manifest is too large")
            manifest = ReleaseManifest.from_json(
                payload.decode("utf-8"),
                allowed_hosts=self.allowed_hosts,
                allowed_schemes=self.allowed_schemes,
            )
            artifact = manifest.select(self.target, self.architecture, kind=self.kind)
            if compare_versions(self.current_version, manifest.version) >= 0:
                return UpdateCheckResult("current", manifest, artifact)
            return UpdateCheckResult("available", manifest, artifact)
        except ManifestError as exc:
            return UpdateCheckResult("invalid", error=str(exc))
        except (OSError, UnicodeError, URLError, TimeoutError, ValueError) as exc:
            return UpdateCheckResult("unavailable", error=f"{type(exc).__name__}: {exc}")

    def download(self, artifact: ArtifactSpec, destination: Path) -> Path:
        """Download to a sibling temporary file, verify, then atomically publish."""

        destination = Path(destination).expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.", suffix=".part", dir=destination.parent
        )
        os.close(descriptor)
        temporary = Path(temporary_name)
        try:
            with self._open(artifact.url) as response, temporary.open("wb") as output:
                for chunk in iter(lambda: response.read(1024 * 1024), b""):
                    output.write(chunk)
            artifact.verify(temporary)
            os.replace(temporary, destination)
            return destination
        except ManifestError:
            temporary.unlink(missing_ok=True)
            raise
        except (OSError, URLError, TimeoutError, ValueError) as exc:
            temporary.unlink(missing_ok=True)
            raise ManifestError(f"update download failed: {exc}") from exc


def detect_installation(
    *,
    executable: Path | None = None,
    platform_name: str | None = None,
) -> InstallationInfo:
    """Detect a frozen portable/package installation without touching files."""

    target = (platform_name or platform.system()).casefold()
    if target not in {"windows", "linux"}:
        raise ManifestError(f"unsupported update platform: {platform_name or platform.system()}")
    path = Path(executable or sys.executable).expanduser().resolve()
    root = path.parent
    manifest_path = root / "BUILD_MANIFEST.json"
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ManifestError(f"packaged build manifest is invalid: {exc}") from exc
        if manifest.get("target") != target:
            raise ManifestError("packaged build target does not match the current platform")
        architecture = str(manifest.get("architecture") or "x86_64")
        kind: Literal["portable", "installer"] = (
            "installer"
            if target == "windows" and (root / "INSTALLER_MARKER").is_file()
            else "portable"
        )
        return InstallationInfo(target, architecture, kind, root, path)
    if target == "linux" and root == Path("/usr/lib/stalker2-save-editor"):
        return InstallationInfo(target, "x86_64", "package", root, path)
    return InstallationInfo(target, "x86_64", "development", root, path)


def _safe_destination(root: Path, member_name: str) -> Path:
    name = PurePosixPath(member_name)
    if name.is_absolute() or ".." in name.parts:
        raise ManifestError(f"archive contains unsafe path: {member_name}")
    destination = (root / Path(*name.parts)).resolve()
    if destination != root and root not in destination.parents:
        raise ManifestError(f"archive contains unsafe path: {member_name}")
    return destination


def _extract_zip(archive: Path, destination: Path) -> None:
    with zipfile.ZipFile(archive) as source:
        for member in source.infolist():
            target = _safe_destination(destination, member.filename)
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with source.open(member) as input_file, target.open("wb") as output:
                shutil.copyfileobj(input_file, output)


def _extract_tar(archive: Path, destination: Path) -> None:
    with tarfile.open(archive, "r:*") as source:
        for member in source.getmembers():
            target = _safe_destination(destination, member.name)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                raise ManifestError(f"archive contains unsupported entry: {member.name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            input_file = source.extractfile(member)
            if input_file is None:
                raise ManifestError(f"archive entry cannot be read: {member.name}")
            with input_file, target.open("wb") as output:
                shutil.copyfileobj(input_file, output)
            target.chmod(member.mode & 0o777 or 0o644)


def stage_archive(archive: Path, installation: InstallationInfo, staging_root: Path) -> Path:
    """Safely extract an already verified archive and return its app directory."""

    archive = Path(archive).resolve()
    staging_root = Path(staging_root).resolve()
    if not archive.is_file():
        raise ManifestError(f"update archive is missing: {archive}")
    if staging_root.exists():
        shutil.rmtree(staging_root)
    extracted = staging_root / "extracted"
    extracted.mkdir(parents=True)
    try:
        if archive.name.casefold().endswith(".zip"):
            _extract_zip(archive, extracted)
        elif archive.name.casefold().endswith((".tar.gz", ".tgz", ".tar")):
            _extract_tar(archive, extracted)
        else:
            raise ManifestError("unsupported update archive type")
        application = extracted / "SaveEditor"
        executable_name = "SaveEditor.exe" if installation.target == "windows" else "SaveEditor"
        if not (application / executable_name).is_file():
            raise ManifestError("update archive has no expected SaveEditor executable")
        manifest = application / "BUILD_MANIFEST.json"
        if not manifest.is_file():
            raise ManifestError("update archive has no BUILD_MANIFEST.json")
        return application
    except Exception:
        shutil.rmtree(staging_root, ignore_errors=True)
        raise


def replace_installation(
    staged_root: Path,
    installation: InstallationInfo,
    *,
    launcher: Callable[[Path], object] | None = None,
) -> Path:
    """Replace a portable application and restore it if launch fails."""

    current = installation.root.resolve()
    staged_root = Path(staged_root).resolve()
    if not staged_root.is_dir() or staged_root == current:
        raise ManifestError("invalid staged installation")
    if not current.is_dir():
        raise ManifestError(f"current installation is missing: {current}")
    backup = current.with_name(f".{current.name}.backup-{uuid.uuid4().hex}")
    os.replace(current, backup)
    try:
        os.replace(staged_root, current)
        new_executable = current / ("SaveEditor.exe" if installation.target == "windows" else "SaveEditor")
        if launcher is not None:
            launcher(new_executable)
        shutil.rmtree(backup)
        return current
    except Exception:
        if current.exists():
            shutil.rmtree(current)
        if backup.exists():
            os.replace(backup, current)
        raise


def build_update_command(
    updater_executable: Path,
    archive: Path,
    installation: InstallationInfo,
    *,
    parent_pid: int | None = None,
) -> list[str]:
    """Build the explicit command used by the GUI to leave replacement work."""

    return [
        str(updater_executable),
        "--parent-pid",
        str(os.getpid() if parent_pid is None else parent_pid),
        "--archive",
        str(Path(archive).resolve()),
        "--installation",
        str(installation.root),
        "--target",
        installation.target,
        "--kind",
        installation.kind,
        "--launch",
        str(installation.executable),
    ]


def launch_update(command: list[str]) -> subprocess.Popen[bytes]:
    """Start the detached updater and return its process handle."""

    return subprocess.Popen(command, start_new_session=True)


def _windows_process_running(pid: int) -> bool:
    """Check a process handle without sending a signal on Windows."""

    import ctypes

    synchronize = 0x00100000
    wait_object_0 = 0x00000000
    wait_timeout = 0x00000102
    error_access_denied = 5
    error_invalid_parameter = 87
    win_dll = ctypes.WinDLL  # type: ignore[attr-defined]
    get_last_error = ctypes.get_last_error  # type: ignore[attr-defined]
    kernel32 = win_dll("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel32.WaitForSingleObject.restype = ctypes.c_uint32
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_int
    handle = kernel32.OpenProcess(synchronize, 0, pid)
    if not handle:
        error = get_last_error()
        if error == error_invalid_parameter:
            return False
        if error == error_access_denied:
            return True
        raise OSError(error, f"OpenProcess failed for pid {pid}")
    try:
        result = kernel32.WaitForSingleObject(handle, 0)
        if result == wait_object_0:
            return False
        if result == wait_timeout:
            return True
        error = get_last_error()
        raise OSError(error, f"WaitForSingleObject failed for pid {pid}")
    finally:
        kernel32.CloseHandle(handle)


def _process_running(pid: int) -> bool:
    if os.name == "nt":
        return _windows_process_running(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def wait_for_process_exit(pid: int, timeout: float = 30.0) -> None:
    if pid <= 0:
        raise ValueError("parent pid must be positive")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _process_running(pid):
            return
        time.sleep(0.1)
    raise TimeoutError(f"parent process did not exit within {timeout:.1f}s")


__all__ = [
    "DEFAULT_MANIFEST_URL",
    "UPDATE_USER_AGENT",
    "InstallationInfo",
    "UpdateCheckResult",
    "UpdateClient",
    "build_update_command",
    "detect_installation",
    "launch_update",
    "replace_installation",
    "stage_archive",
    "wait_for_process_exit",
]
