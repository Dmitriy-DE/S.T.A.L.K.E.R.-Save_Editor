"""Operating-system paths and local helper discovery.

The editor stores new state below the platform's user data directory.  The
pre-v0.3 ``~/Stalker2SaveEditor`` directory remains a read-only discovery
fallback so existing backups are never silently moved or deleted.
"""

from __future__ import annotations

import os
import platform
import shutil
from collections.abc import Mapping
from pathlib import Path

APP_DIR_NAME = "Stalker2SaveEditor"
HELPER_ENV = "STALKER2_STEAM_HELPER"


def _system_name(system: str | None) -> str:
    return (platform.system() if system is None else system).strip().lower()


def _home_path(home: Path | None) -> Path:
    return Path.home() if home is None else Path(home).expanduser()


def _environment(environ: Mapping[str, str] | None) -> Mapping[str, str]:
    return os.environ if environ is None else environ


def user_data_dir(
    *,
    system: str | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    """Return the writable application data directory for Linux or Windows."""

    env = _environment(environ)
    home_path = _home_path(home)
    name = _system_name(system)
    if name == "windows":
        root = env.get("APPDATA") or env.get("LOCALAPPDATA")
        base = Path(root).expanduser() if root else home_path / "AppData" / "Roaming"
    else:
        # Linux is the supported POSIX target.  The same XDG fallback is
        # harmless for other POSIX systems and keeps the path deterministic.
        root = env.get("XDG_DATA_HOME")
        base = Path(root).expanduser() if root else home_path / ".local" / "share"
    return base / APP_DIR_NAME


def legacy_data_dir(*, home: Path | None = None) -> Path:
    """Return the old v0.3 directory without creating or migrating anything."""

    return _home_path(home) / APP_DIR_NAME


def backup_dirs(
    *,
    system: str | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> tuple[Path, ...]:
    """Return new backup location first, then the legacy location if distinct."""

    current = user_data_dir(system=system, environ=environ, home=home) / "backups"
    legacy = legacy_data_dir(home=home) / "backups"
    return (current,) if current == legacy else (current, legacy)


def _expand_path(value: str, *, home: Path) -> Path:
    expanded = os.path.expandvars(value.strip().strip('"'))
    path = Path(expanded)
    if not path.is_absolute():
        path = home / path
    return path.expanduser()


def _is_helper_file(path: Path, *, windows: bool) -> bool:
    if not path.is_file():
        return False
    if windows:
        # Windows does not use POSIX execute bits.  PATH entries may be named
        # without a suffix, while scanned release assets must be .exe files.
        return path.suffix.lower() in ("", ".exe")
    try:
        return bool(path.stat().st_mode & 0o111)
    except OSError:
        return False


def _roots_for(
    *,
    system: str,
    environ: Mapping[str, str],
    home: Path,
) -> tuple[Path, ...]:
    if system == "windows":
        values = [
            environ.get("LOCALAPPDATA"),
            environ.get("PROGRAMFILES"),
            environ.get("PROGRAMFILES(X86)"),
        ]
        roots = [Path(value).expanduser() for value in values if value]
        roots.extend((home / "Downloads", home / "Desktop"))
        return tuple(roots)
    values = [environ.get("XDG_DATA_HOME")]
    roots = [Path(value).expanduser() for value in values if value]
    roots.extend((home / "Downloads", home / "Applications", home / ".local" / "bin"))
    return tuple(roots)


def discover_helper(
    *,
    system: str | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path | None:
    """Find an executable SteamCloudFileManager without invoking a shell.

    An explicit ``STALKER2_STEAM_HELPER`` path wins.  Discovery only returns
    existing files; on POSIX a helper must already have an execute bit, while
    Windows release assets are selected by their ``.exe`` suffix.
    """

    name = _system_name(system)
    env = _environment(environ)
    home_path = _home_path(home)
    windows = name == "windows"

    explicit = env.get(HELPER_ENV)
    if explicit:
        candidate = _expand_path(explicit, home=home_path)
        if _is_helper_file(candidate, windows=windows):
            return candidate

    names = (
        ("SteamCloudFileManager.exe", "SteamCloudFileManager")
        if windows
        else ("steam-cloud-file-manager", "SteamCloudFileManager")
    )
    for command in names:
        found = shutil.which(command)
        if found:
            candidate = Path(found).expanduser()
            if _is_helper_file(candidate, windows=windows):
                return candidate

    patterns = (
        ("SteamCloudFileManager*.exe", "*steam*cloud*file*manager*.exe")
        if windows
        else (
            "SteamCloudFileManager*.AppImage",
            "*steam*cloud*file*manager*.AppImage",
            "steam-cloud-file-manager*",
        )
    )
    candidates: list[Path] = []
    seen: set[Path] = set()
    for root in _roots_for(system=name, environ=env, home=home_path):
        if not root.is_dir():
            continue
        for pattern in patterns:
            for candidate in root.glob(pattern):
                resolved = candidate.expanduser()
                if resolved in seen or not _is_helper_file(resolved, windows=windows):
                    continue
                seen.add(resolved)
                candidates.append(resolved)
    candidates.sort(key=lambda path: (path.stat().st_mtime_ns, str(path)), reverse=True)
    return candidates[0] if candidates else None
