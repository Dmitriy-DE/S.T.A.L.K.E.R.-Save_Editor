"""Dependency-free download, staging, and replacement support for updates."""

from __future__ import annotations

import json
import os
import platform
import re
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
from http.client import HTTPMessage
from pathlib import Path, PurePosixPath
from typing import IO, Literal
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

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
PACKAGE_INSTALL_ROOT = Path("/usr/lib/stalker2-save-editor")
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
    if name == "darwin":
        return "macos"
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


class _PolicyRedirectHandler(HTTPRedirectHandler):
    """Reject redirects before urllib connects to an untrusted destination."""

    def __init__(
        self,
        *,
        allowed_hosts: frozenset[str],
        allowed_schemes: frozenset[str],
    ) -> None:
        super().__init__()
        self.allowed_hosts = allowed_hosts
        self.allowed_schemes = allowed_schemes

    def redirect_request(
        self,
        req: Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: HTTPMessage,
        newurl: str,
    ) -> Request | None:
        _validate_url(
            newurl,
            allowed_hosts=self.allowed_hosts,
            allowed_schemes=self.allowed_schemes,
        )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class UpdateClient:
    """Fetch and verify a release manifest and one selected artifact."""

    def __init__(
        self,
        *,
        manifest_url: str = DEFAULT_MANIFEST_URL,
        current_version: str,
        target: str | None = None,
        architecture: str | None = None,
        kind: str | None = None,
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
        detected_target = (target or _default_target()).casefold()
        self.target = "macos" if detected_target.casefold() == "darwin" else detected_target
        machine = platform.machine().casefold()
        default_architecture = (
            "arm64" if self.target == "macos" and machine in {"arm64", "aarch64"} else "x86_64"
        )
        self.architecture = architecture or default_architecture
        self.kind = kind or ("disk-image" if self.target == "macos" else "portable")
        self.timeout = timeout
        self.allowed_hosts = allowed_hosts
        self.allowed_schemes = allowed_schemes
        self._opener = build_opener(
            _PolicyRedirectHandler(
                allowed_hosts=allowed_hosts,
                allowed_schemes=allowed_schemes,
            )
        )

    def _open(self, url: str):
        _validate_url(url, allowed_hosts=self.allowed_hosts, allowed_schemes=self.allowed_schemes)
        request = Request(
            url,
            headers={
                "Accept": "application/json, application/octet-stream",
                "User-Agent": UPDATE_USER_AGENT,
            },
        )
        response = self._opener.open(request, timeout=self.timeout)
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
        if destination.is_file():
            # A verified copy from an earlier attempt is reused instead of
            # downloading the same release again.
            try:
                artifact.verify(destination)
                return destination
            except ManifestError:
                destination.unlink(missing_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.", suffix=".part", dir=destination.parent
        )
        os.close(descriptor)
        temporary = Path(temporary_name)
        try:
            with self._open(artifact.url) as response, temporary.open("wb") as output:
                written = 0
                for chunk in iter(lambda: response.read(1024 * 1024), b""):
                    written += len(chunk)
                    # Stop a wrong or endless body early instead of filling
                    # the disk before the size/SHA check can reject it.
                    if written > artifact.size:
                        raise ManifestError(
                            f"update download is larger than the manifest size {artifact.size}"
                        )
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

    platform_value = (platform_name or platform.system()).casefold()
    target = "macos" if platform_value == "darwin" else platform_value
    if target not in {"windows", "linux", "macos"}:
        raise ManifestError(f"unsupported update platform: {platform_name or platform.system()}")
    path = Path(executable or sys.executable).expanduser().resolve()
    app_bundle = (
        next((parent for parent in path.parents if parent.suffix.casefold() == ".app"), None)
        if target == "macos"
        else None
    )
    root = app_bundle or path.parent
    manifest_path = (
        root / "Contents" / "Resources" / "BUILD_MANIFEST.json"
        if app_bundle is not None
        else root / "BUILD_MANIFEST.json"
    )
    if target == "linux" and root == PACKAGE_INSTALL_ROOT:
        return InstallationInfo(target, "x86_64", "package", root, path)
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ManifestError(f"packaged build manifest is invalid: {exc}") from exc
        if manifest.get("target") != target:
            raise ManifestError("packaged build target does not match the current platform")
        default_architecture = "arm64" if target == "macos" else "x86_64"
        architecture = str(manifest.get("architecture") or default_architecture)
        kind: Literal["portable", "installer"] = (
            "installer"
            if target == "windows" and (root / "INSTALLER_MARKER").is_file()
            else "portable"
        )
        return InstallationInfo(target, architecture, kind, root, path)
    default_architecture = "arm64" if target == "macos" else "x86_64"
    return InstallationInfo(target, default_architecture, "development", root, path)


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
    except Exception:
        if current.exists():
            shutil.rmtree(current)
        if backup.exists():
            os.replace(backup, current)
        raise
    try:
        shutil.rmtree(backup)
    except OSError:
        # The new installation is already committed and launched. Keep the
        # recoverable backup instead of rolling back a successful update.
        pass
    return current


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


# $0 pkexec, $1 apt-get, $2 package, $3 editor to start afterwards.
PKEXEC_HANDOFF_SCRIPT = '"$0" "$1" install -y "$2" && { rm -f "$2"; [ -z "$3" ] || "$3" >/dev/null 2>&1 & }'


def build_installer_command(
    archive: Path,
    installation: InstallationInfo,
    *,
    kind: str | None = None,
    platform_name: str | None = None,
) -> list[str]:
    """Build an explicit OS installer handoff for a verified artifact."""

    archive = Path(archive).resolve()
    if not archive.is_file():
        raise ManifestError(f"update installer is missing: {archive}")
    selected_kind = kind or installation.kind
    target = (platform_name or installation.target).casefold()
    if target == "darwin":
        target = "macos"
    if selected_kind == "disk-image":
        if target != "macos" or archive.suffix.casefold() != ".dmg":
            raise ManifestError("macOS disk-image handoff requires a verified .dmg")
        return ["open", str(archive)]
    if selected_kind == "installer":
        if target != "windows" or archive.suffix.casefold() != ".exe":
            raise ManifestError("Windows installer handoff requires a verified .exe")
        return [str(archive)]
    if selected_kind != "package" or target != "linux" or archive.suffix.casefold() != ".deb":
        raise ManifestError("unsupported installer handoff")
    pkexec = shutil.which("pkexec")
    apt_get = shutil.which("apt-get")
    if pkexec and apt_get:
        # pkexec refuses to run once its parent is gone ("Refusing to render
        # service to dead parents"), and the editor quits right after the
        # handoff.  A small shell stays alive as that parent, then starts the
        # updated editor again.
        shell = shutil.which("sh") or "/bin/sh"
        relaunch = shutil.which("stalker2-save-editor") or ""
        return [shell, "-c", PKEXEC_HANDOFF_SCRIPT, pkexec, apt_get, str(archive), relaunch]
    xdg_open = shutil.which("xdg-open")
    if xdg_open:
        return [xdg_open, str(archive)]
    raise ManifestError("Linux package manager handoff is unavailable (pkexec/xdg-open missing)")


# pkexec reports a dismissed or failed password prompt with these codes.
PKEXEC_CANCELLED_CODES = frozenset({126, 127})
_STALE_DOWNLOAD = re.compile(r"^SaveEditor-update-\d+-.+")


def remove_stale_downloads(directory: Path | None = None) -> int:
    """Delete downloads named by the old per-process scheme (before 0.7.4)."""

    folder = Path(directory or tempfile.gettempdir())
    removed = 0
    try:
        entries = list(folder.iterdir())
    except OSError:
        return 0
    for entry in entries:
        if _STALE_DOWNLOAD.match(entry.name) and entry.is_file():
            try:
                entry.unlink()
                removed += 1
            except OSError:
                pass
    return removed


def launch_installer(
    archive: Path,
    installation: InstallationInfo,
    *,
    kind: str | None = None,
    platform_name: str | None = None,
) -> subprocess.Popen[bytes]:
    """Start a verified installer/package-manager handoff with user approval."""

    command = build_installer_command(
        archive,
        installation,
        kind=kind,
        platform_name=platform_name,
    )
    return subprocess.Popen(command, start_new_session=True)


def _windows_process_running(pid: int) -> bool:
    """Check a process handle without sending a signal on Windows."""

    import ctypes

    synchronize = 0x00100000
    wait_object_0 = 0x00000000
    wait_timeout = 0x00000102
    error_access_denied = 5
    error_invalid_parameter = 87
    # ``ctypes`` exposes these names only on Windows.  ``getattr`` keeps the
    # runtime guard honest while also type-checking on both mypy platforms.
    win_dll = ctypes.__dict__["WinDLL"]
    get_last_error = ctypes.__dict__["get_last_error"]
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
