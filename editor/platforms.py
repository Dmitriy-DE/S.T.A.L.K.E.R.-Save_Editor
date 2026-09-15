"""Operating-system paths and local helper discovery.

The editor stores new state below the platform's user data directory.  The
pre-v0.3 ``~/Stalker2SaveEditor`` directory remains a read-only discovery
fallback so existing backups are never silently moved or deleted.
"""

from __future__ import annotations

import logging
import os
import platform
import re
import shutil
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias

from .releases import ReleaseDescriptor, official_releases

LOGGER = logging.getLogger(__name__)

APP_DIR_NAME = "Stalker2SaveEditor"
HELPER_ENV = "STALKER2_STEAM_HELPER"


@dataclass(frozen=True)
class InstalledGame:
    """One installed Steam release found from its app manifest.

    ``game_id`` is the canonical family id used by :func:`save_directories`:
    ``stalker2``, ``soc``, ``clear_sky`` or ``cop``.  ``edition`` identifies
    the original X-Ray release, the Enhanced release, or S.T.A.L.K.E.R. 2.
    """

    game_id: str
    app_id: int
    edition: str
    library_root: Path
    install_dir: Path

    @property
    def id(self) -> str:
        """Compatibility spelling for callers that use ``game.id``."""

        return self.game_id

    @property
    def release_id(self) -> str:
        """Return the canonical official release represented by ``app_id``."""

        return _RELEASE_ID_BY_APP_ID.get(self.app_id, self.game_id)


@dataclass(frozen=True)
class _Release:
    game_id: str
    app_id: int
    edition: str
    install_dirs: tuple[str, ...]


_RELEASES: tuple[_Release, ...] = (
    _Release(
        "stalker2",
        1643320,
        "stalker2",
        (
            "S.T.A.L.K.E.R. 2 Heart of Chornobyl",
            "STALKER 2 Heart of Chornobyl",
            "S.T.A.L.K.E.R. 2",
        ),
    ),
    _Release(
        "soc",
        4500,
        "original",
        ("STALKER Shadow of Chernobyl", "STALKER Shadow of Chornobyl"),
    ),
    _Release("clear_sky", 20510, "original", ("STALKER Clear Sky",)),
    _Release(
        "cop",
        41700,
        "original",
        ("Stalker Call of Pripyat", "STALKER Call of Pripyat"),
    ),
    _Release(
        "soc",
        2427410,
        "enhanced",
        ("STALKER Shadow of Chornobyl - Enhanced Edition",),
    ),
    _Release(
        "clear_sky",
        2427420,
        "enhanced",
        ("STALKER Clear Sky - Enhanced Edition",),
    ),
    _Release(
        "cop",
        2427430,
        "enhanced",
        ("STALKER Call of Prypiat - Enhanced Edition",),
    ),
)

_GAME_ALIASES = {
    "stalker2": "stalker2",
    "stalker_2": "stalker2",
    "s2": "stalker2",
    "soc": "soc",
    "shoc": "soc",
    "shadow": "soc",
    "shadow_of_chernobyl": "soc",
    "shadow-of-chernobyl": "soc",
    "clear_sky": "clear_sky",
    "clear-sky": "clear_sky",
    "cs": "clear_sky",
    "cop": "cop",
    "call_of_pripyat": "cop",
    "call-of-pripyat": "cop",
    "call_of_prypiat": "cop",
    "call-of-prypiat": "cop",
}

_RELEASES_BY_ID: dict[str, ReleaseDescriptor] = {
    release.id: release for release in official_releases()
}
_RELEASE_ID_BY_APP_ID: dict[int, str] = {
    app_id: release.id
    for release in official_releases()
    for app_id in release.app_ids
}


def _release_selector(value: str) -> tuple[str, str | None, str | None]:
    """Return ``(family, edition, release_id)`` for a family or release key."""

    selector = value.strip().casefold()
    for release_id, descriptor in _RELEASES_BY_ID.items():
        if selector == release_id.casefold():
            return descriptor.family, descriptor.edition, descriptor.id
    family = _GAME_ALIASES.get(selector)
    if family is None:
        raise ValueError(f"Unsupported STALKER game id: {value!r}")
    return family, None, None


def _selected_release_ids(selector: str) -> tuple[str, ...]:
    family, _edition, release_id = _release_selector(selector)
    if release_id is not None:
        return (release_id,)
    return tuple(
        descriptor.id for descriptor in official_releases() if descriptor.family == family
    )

_EE_SAVE_NAMES: dict[str, tuple[str, ...]] = {
    "soc": ("STALKER Shadow of Chornobyl - EE",),
    "clear_sky": ("STALKER Clear Sky - EE",),
    # Both spellings are present in public Steam/PC path references.  Keep
    # them as independent candidates because Linux Proton paths are case- and
    # spelling-sensitive even though Windows is not.
    "cop": (
        "STALKER Call of Prypiat - EE",
        "STALKER Call of Pripyat - EE",
    ),
}

_DOCUMENT_NAMES = {
    "documents",
    "my documents",
    "mes documents",
    "documentos",
    "dokumente",
    "documenti",
    "dokumenty",
    "dokumenti",
    "документы",
    "документи",
    "文档",
}

_SAVED_GAMES_NAMES = {
    "saved games",
    "my saved games",
    "parties enregistrées",
    "gespeicherte spiele",
    "partite salvate",
    "сохраненные игры",
    "сохранённые игры",
    "збережені ігри",
}

_XRAY_SAVE_DIRS: dict[str, tuple[str, ...]] = {
    "soc": ("stalker-shoc", "Stalker-SHOC"),
    "clear_sky": ("Stalker-STCS",),
    "cop": (
        "S.T.A.L.K.E.R. - Call of Pripyat",
        "Stalker-COP",
    ),
}

_STALKER2_PACKAGE = "GSCGameWorld.S.T.A.L.K.E.R.2HeartofChornobyl_6fr1t1rwfarwt"

_VdfValue: TypeAlias = str | dict[str, "_VdfValue"]


def _effective_root(
    filesystem_root: Path | None,
    root: Path | None,
) -> Path | None:
    if filesystem_root is not None and root is not None and Path(filesystem_root) != Path(root):
        raise ValueError("filesystem_root and root must refer to the same path")
    value = filesystem_root if filesystem_root is not None else root
    return None if value is None else Path(value).expanduser()


def _system_name(system: str | None) -> str:
    return (platform.system() if system is None else system).strip().lower()


def _home_path(home: Path | None) -> Path:
    return Path.home() if home is None else Path(home).expanduser()


def _environment(environ: Mapping[str, str] | None) -> Mapping[str, str]:
    return os.environ if environ is None else environ


def _env_get(environ: Mapping[str, str], key: str) -> str | None:
    """Read an environment key with Windows' case-insensitive semantics."""

    wanted = key.casefold()
    for candidate, value in environ.items():
        if candidate.casefold() == wanted:
            return value
    return None


_ENV_VAR_RE = re.compile(r"%([^%]+)%|\$\{([^}]+)\}|\$([A-Za-z_][A-Za-z0-9_]*)")


def _expand_environment(value: str, environ: Mapping[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        key = next(group for group in match.groups() if group is not None)
        replacement = _env_get(environ, key)
        return match.group(0) if replacement is None else replacement

    return _ENV_VAR_RE.sub(replace, value)


def _virtualize_absolute(path: Path, filesystem_root: Path | None) -> Path:
    if filesystem_root is None or not path.is_absolute():
        return path
    try:
        path.relative_to(filesystem_root)
    except ValueError:
        return filesystem_root / Path(*path.parts[1:])
    return path


def _injected_home(home: Path | None, filesystem_root: Path | None) -> Path:
    return _virtualize_absolute(_home_path(home), filesystem_root)


def _path_value(
    value: str | Path,
    *,
    home: Path,
    environ: Mapping[str, str],
    base: Path | None = None,
    filesystem_root: Path | None = None,
) -> Path:
    text = _expand_environment(str(value).strip().strip('"'), environ).strip()
    if text == "~":
        return home
    if text.startswith("~/") or text.startswith("~\\"):
        text = str(home / text[2:])

    # fsgame.ltx and Windows VDF files use backslashes even when tests run on
    # POSIX.  A drive-qualified path gets a deterministic representation under
    # the injected filesystem root; without an injected root, native Windows
    # still receives its normal Path semantics.
    drive_match = re.match(r"^([A-Za-z]):[\\/](.*)$", text)
    if drive_match:
        if filesystem_root is not None:
            path = filesystem_root / drive_match.group(1).upper() / Path(
                drive_match.group(2).replace("\\", "/")
            )
        else:
            path = Path(text)
    else:
        normalized = text.replace("\\", "/")
        path = Path(normalized)
        if not path.is_absolute():
            path = (home if base is None else base) / path
    return _virtualize_absolute(path.expanduser(), filesystem_root)


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
    return _path_value(value, home=home, environ=os.environ)


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


def _dedupe_paths(paths: Sequence[Path]) -> tuple[Path, ...]:
    result: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        value = Path(path)
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return tuple(result)


def _existing_directories(paths: Sequence[Path]) -> tuple[Path, ...]:
    result: list[Path] = []
    for path in _dedupe_paths(paths):
        try:
            is_directory = path.is_dir()
        except OSError:
            is_directory = False
        if is_directory:
            result.append(path)
    return tuple(result)


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        try:
            return path.read_text(encoding="cp1251")
        except (OSError, UnicodeDecodeError):
            return None
    except OSError:
        return None


def _registry_steam_path() -> str | None:
    try:
        import winreg
    except ImportError:
        return None

    try:
        # ``winreg`` is intentionally imported lazily so non-Windows builds do
        # not need a platform stub.  ``getattr`` keeps that boundary type-safe
        # on both the Windows and non-Windows typeshed variants.
        open_key_name = "OpenKey"
        current_user_name = "HKEY_CURRENT_USER"
        query_value_name = "QueryValueEx"
        open_key = getattr(winreg, open_key_name)
        current_user = getattr(winreg, current_user_name)
        query_value = getattr(winreg, query_value_name)
        with open_key(current_user, r"Software\Valve\Steam") as key:
            value, _ = query_value(key, "SteamPath")
    except OSError:
        return None
    return value if isinstance(value, str) and value.strip() else None


def steam_roots(
    *,
    system: str | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
    filesystem_root: Path | None = None,
    root: Path | None = None,
    registry_reader: Callable[[], str | Path | None] | None = None,
) -> tuple[Path, ...]:
    """Return candidate Steam roots without touching or creating the client.

    On Windows the current-user Steam registry value is authoritative when it
    can be read.  The injected ``registry_reader`` keeps that branch testable
    on non-Windows hosts.  Linux includes the regular, legacy, and Flatpak
    locations; existence is intentionally checked by :func:`steam_libraries`.
    """

    env = _environment(environ)
    filesystem_root = _effective_root(filesystem_root, root)
    home_path = _injected_home(home, filesystem_root)
    name = _system_name(system)

    if name == "windows":
        registry_value = (
            registry_reader() if registry_reader is not None else _registry_steam_path()
        )
        candidates: list[Path] = []
        if registry_value:
            candidates.append(
                _path_value(
                    registry_value,
                    home=home_path,
                    environ=env,
                    filesystem_root=filesystem_root,
                )
            )
        program_files_x86 = _env_get(env, "PROGRAMFILES(X86)")
        if program_files_x86:
            candidates.append(
                _path_value(
                    program_files_x86,
                    home=home_path,
                    environ=env,
                    filesystem_root=filesystem_root,
                )
                / "Steam"
            )
        return _dedupe_paths(candidates)

    return _dedupe_paths(
        (
            home_path / ".steam" / "steam",
            home_path / ".local" / "share" / "Steam",
            home_path
            / ".var"
            / "app"
            / "com.valvesoftware.Steam"
            / "data"
            / "Steam",
        )
    )


def _tokenize_vdf(text: str) -> list[str]:
    tokens: list[str] = []
    index = 0
    length = len(text)
    while index < length:
        character = text[index]
        if character.isspace():
            index += 1
            continue
        if text.startswith("//", index):
            newline = text.find("\n", index + 2)
            index = length if newline < 0 else newline + 1
            continue
        if character in "{}":
            tokens.append(character)
            index += 1
            continue
        if character == '"':
            index += 1
            value: list[str] = []
            while index < length:
                character = text[index]
                if character == '"':
                    index += 1
                    break
                if character == "\\" and index + 1 < length:
                    value.append(text[index + 1])
                    index += 2
                    continue
                value.append(character)
                index += 1
            else:
                raise ValueError("unterminated quoted VDF string")
            tokens.append("".join(value))
            continue

        start = index
        while index < length and not text[index].isspace() and text[index] not in "{}":
            index += 1
        if start == index:
            raise ValueError("empty VDF token")
        tokens.append(text[start:index])
    return tokens


def _parse_vdf(text: str) -> dict[str, _VdfValue]:
    tokens = _tokenize_vdf(text)
    position = 0

    def parse_object(*, closing: bool) -> dict[str, _VdfValue]:
        nonlocal position
        result: dict[str, _VdfValue] = {}
        while position < len(tokens):
            if tokens[position] == "}":
                if not closing:
                    raise ValueError("unexpected closing VDF brace")
                position += 1
                return result
            key = tokens[position]
            if key == "{":
                raise ValueError("VDF object is missing a key")
            position += 1
            if position >= len(tokens):
                raise ValueError("VDF key is missing a value")
            value = tokens[position]
            position += 1
            if value == "{":
                result[key] = parse_object(closing=True)
            elif value == "}":
                raise ValueError("VDF key is missing a value")
            else:
                result[key] = value
        if closing:
            raise ValueError("unterminated VDF object")
        return result

    result = parse_object(closing=False)
    if position != len(tokens):
        raise ValueError("trailing VDF tokens")
    return result


def _vdf_library_paths(value: _VdfValue | None) -> tuple[str, ...]:
    if not isinstance(value, dict):
        return ()
    paths: list[str] = []
    for entry in value.values():
        if isinstance(entry, str):
            paths.append(entry)
        elif isinstance(entry, dict):
            path = entry.get("path")
            if isinstance(path, str) and path.strip():
                paths.append(path)
    return tuple(paths)


def steam_libraries(
    *,
    system: str | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
    filesystem_root: Path | None = None,
    root: Path | None = None,
    registry_reader: Callable[[], str | Path | None] | None = None,
    steam_library_roots: Sequence[str | Path] | None = None,
) -> tuple[Path, ...]:
    """Enumerate Steam libraries from ``libraryfolders.vdf``.

    The parser deliberately handles the small Valve KeyValues subset used by
    this file instead of adding a dependency.  A malformed file is isolated to
    its root and logged; a different Steam root can still be inspected.
    """

    env = _environment(environ)
    filesystem_root = _effective_root(filesystem_root, root)
    home_path = _injected_home(home, filesystem_root)
    roots = (
        tuple(
            _path_value(
                value,
                home=home_path,
                environ=env,
                filesystem_root=filesystem_root,
            )
            for value in steam_library_roots
        )
        if steam_library_roots is not None
        else steam_roots(
            system=system,
            environ=env,
            home=home_path,
            filesystem_root=filesystem_root,
            registry_reader=registry_reader,
        )
    )

    libraries: list[Path] = []
    scanned_roots: set[Path] = set()
    for steam_root in _dedupe_paths(roots):
        try:
            if not steam_root.is_dir():
                continue
        except OSError:
            continue
        if steam_root in scanned_roots:
            continue
        scanned_roots.add(steam_root)
        libraries.append(steam_root)

        library_file = steam_root / "steamapps" / "libraryfolders.vdf"
        if not library_file.is_file():
            continue
        text = _read_text(library_file)
        if text is None:
            LOGGER.warning("Skipping unreadable Steam library file %s", library_file)
            continue
        try:
            parsed = _parse_vdf(text)
        except ValueError as error:
            LOGGER.warning("Skipping malformed Steam library file %s: %s", library_file, error)
            continue
        for value in _vdf_library_paths(parsed.get("libraryfolders")):
            library = _path_value(
                value,
                home=home_path,
                environ=env,
                filesystem_root=filesystem_root,
            )
            if library in scanned_roots:
                continue
            try:
                exists = library.is_dir()
            except OSError:
                exists = False
            if exists:
                scanned_roots.add(library)
                libraries.append(library)
    return tuple(libraries)


def gog_roots(
    *,
    system: str | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
    filesystem_root: Path | None = None,
    root: Path | None = None,
) -> tuple[Path, ...]:
    """Return candidate GOG install roots used for optional fsgame discovery."""

    env = _environment(environ)
    filesystem_root = _effective_root(filesystem_root, root)
    home_path = _injected_home(home, filesystem_root)
    values: list[str | Path] = []
    for key in ("GOG_GAMES_PATH", "GOG_GAMES_ROOT"):
        value = _env_get(env, key)
        if value:
            values.append(value)
    if _system_name(system) == "windows":
        for key in ("PROGRAMFILES(X86)", "PROGRAMFILES"):
            value = _env_get(env, key)
            if value:
                values.append(
                    _path_value(
                        value,
                        home=home_path,
                        environ=env,
                        filesystem_root=filesystem_root,
                    )
                    / "GOG Galaxy"
                    / "Games"
                )
    values.append(home_path / "GOG Games")
    return _dedupe_paths(
        tuple(
            _path_value(
                value,
                home=home_path,
                environ=env,
                filesystem_root=filesystem_root,
            )
            for value in values
        )
    )


def xbox_roots(
    *,
    system: str | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
    filesystem_root: Path | None = None,
    root: Path | None = None,
) -> tuple[Path, ...]:
    """Return candidate Microsoft Store package roots."""

    if _system_name(system) != "windows":
        return ()
    env = _environment(environ)
    filesystem_root = _effective_root(filesystem_root, root)
    home_path = _injected_home(home, filesystem_root)
    local = _env_get(env, "LOCALAPPDATA")
    program_files = _env_get(env, "PROGRAMFILES")
    candidates: list[Path] = []
    if local:
        candidates.append(
            _path_value(
                local,
                home=home_path,
                environ=env,
                filesystem_root=filesystem_root,
            )
            / "Packages"
        )
    else:
        candidates.append(home_path / "AppData" / "Local" / "Packages")
    if program_files:
        candidates.append(
            _path_value(
                program_files,
                home=home_path,
                environ=env,
                filesystem_root=filesystem_root,
            )
            / "WindowsApps"
        )
    return _dedupe_paths(candidates)


def _manifest_install_dir(
    manifest: Path,
    *,
    app_id: int,
    library: Path,
    home: Path,
    environ: Mapping[str, str],
    filesystem_root: Path | None,
) -> Path | None:
    text = _read_text(manifest)
    if text is None:
        LOGGER.warning("Skipping unreadable Steam manifest %s", manifest)
        return None
    try:
        parsed = _parse_vdf(text)
    except ValueError as error:
        LOGGER.warning("Skipping malformed Steam manifest %s: %s", manifest, error)
        return None
    app_state = parsed.get("AppState")
    if not isinstance(app_state, dict):
        return None
    manifest_app_id = app_state.get("appid")
    install_dir = app_state.get("installdir")
    if not isinstance(manifest_app_id, str) or not manifest_app_id.isdigit():
        return None
    if int(manifest_app_id) != app_id or not isinstance(install_dir, str) or not install_dir.strip():
        return None
    return _path_value(
        install_dir,
        home=home,
        environ=environ,
        base=library / "steamapps" / "common",
        filesystem_root=filesystem_root,
    )


def _find_install_directory(
    common: Path,
    names: Sequence[str],
) -> Path | None:
    for name in names:
        candidate = common / name
        try:
            if candidate.is_dir():
                return candidate
        except OSError:
            continue
    try:
        children = tuple(common.iterdir())
    except OSError:
        return None
    wanted = {name.casefold() for name in names}
    for child in children:
        if child.is_dir() and child.name.casefold() in wanted:
            return child
    return None


def installed_games(
    *,
    system: str | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
    filesystem_root: Path | None = None,
    root: Path | None = None,
    registry_reader: Callable[[], str | Path | None] | None = None,
    steam_library_roots: Sequence[str | Path] | None = None,
) -> tuple[InstalledGame, ...]:
    """Find supported Steam releases with both a valid manifest and game dir."""

    env = _environment(environ)
    filesystem_root = _effective_root(filesystem_root, root)
    home_path = _injected_home(home, filesystem_root)
    libraries = steam_libraries(
        system=system,
        environ=env,
        home=home_path,
        filesystem_root=filesystem_root,
        registry_reader=registry_reader,
        steam_library_roots=steam_library_roots,
    )
    games: list[InstalledGame] = []
    for release in _RELEASES:
        for library in libraries:
            manifest = library / "steamapps" / f"appmanifest_{release.app_id}.acf"
            if not manifest.is_file():
                continue
            install_dir = _manifest_install_dir(
                manifest,
                app_id=release.app_id,
                library=library,
                home=home_path,
                environ=env,
                filesystem_root=filesystem_root,
            )
            if install_dir is None:
                continue
            if not install_dir.is_dir():
                install_dir = _find_install_directory(
                    library / "steamapps" / "common", release.install_dirs
                )
            if install_dir is None:
                continue
            games.append(
                InstalledGame(
                    game_id=release.game_id,
                    app_id=release.app_id,
                    edition=release.edition,
                    library_root=library,
                    install_dir=install_dir,
                )
            )
    return tuple(games)


def installed_releases(
    *,
    system: str | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
    filesystem_root: Path | None = None,
    root: Path | None = None,
    registry_reader: Callable[[], str | Path | None] | None = None,
    steam_library_roots: Sequence[str | Path] | None = None,
) -> tuple[InstalledGame, ...]:
    """Return installed official releases once per release and install tree.

    Steam can expose the same library through more than one configured root.
    The legacy :func:`installed_games` result remains unchanged for callers
    that need every manifest observation; this public release-aware view is
    the deduplicated selector used by path discovery.
    """

    games = installed_games(
        system=system,
        environ=environ,
        home=home,
        filesystem_root=filesystem_root,
        root=root,
        registry_reader=registry_reader,
        steam_library_roots=steam_library_roots,
    )
    result: list[InstalledGame] = []
    seen: set[tuple[str, Path]] = set()
    for game in games:
        try:
            install_tree = game.install_dir.resolve()
        except OSError:
            install_tree = game.install_dir
        key = (game.release_id, install_tree)
        if key in seen:
            continue
        seen.add(key)
        result.append(game)
    return tuple(result)


def _document_roots(
    *,
    home: Path,
    environ: Mapping[str, str],
    filesystem_root: Path | None,
) -> tuple[Path, ...]:
    user = _path_value(
        _env_get(environ, "USERPROFILE") or home,
        home=home,
        environ=environ,
        filesystem_root=filesystem_root,
    )
    public_value = _env_get(environ, "PUBLIC")
    public = (
        _path_value(
            public_value,
            home=home,
            environ=environ,
            filesystem_root=filesystem_root,
        )
        if public_value
        else None
    )
    candidates: list[Path] = []
    parents = _dedupe_paths(tuple(path for path in (home, user, public) if path is not None))
    for parent in parents:
        candidates.extend(
            parent / name
            for name in (
                "Documents",
                "My Documents",
                "Документы",
                "Документи",
                "Documentos",
                "Dokumente",
                "Documenti",
            )
        )
        try:
            children = tuple(parent.iterdir())
        except OSError:
            children = ()
        candidates.extend(
            child
            for child in children
            if child.is_dir() and child.name.casefold() in _DOCUMENT_NAMES
        )
    if public is not None:
        candidates.extend((public / "Documents", public / "Public Documents"))
    return _dedupe_paths(candidates)


def _saved_games_roots(
    *,
    home: Path,
    environ: Mapping[str, str],
    filesystem_root: Path | None,
) -> tuple[Path, ...]:
    user = _path_value(
        _env_get(environ, "USERPROFILE") or home,
        home=home,
        environ=environ,
        filesystem_root=filesystem_root,
    )
    candidates: list[Path] = []
    for parent in _dedupe_paths((home, user)):
        candidates.extend(
            parent / name
            for name in (
                "Saved Games",
                "My Saved Games",
                "Сохраненные игры",
                "Сохранённые игры",
                "Збережені ігри",
            )
        )
        try:
            children = tuple(parent.iterdir())
        except OSError:
            children = ()
        candidates.extend(
            child
            for child in children
            if child.is_dir() and child.name.casefold() in _SAVED_GAMES_NAMES
        )
    return _dedupe_paths(candidates)


def _fsgame_definitions(text: str) -> dict[str, tuple[str, ...]]:
    result: dict[str, tuple[str, ...]] = {}
    for line in text.splitlines():
        line = line.split(";", 1)[0].strip()
        if not line:
            continue
        match = re.match(r"^(\$[^$]+\$)\s*=\s*(.*)$", line)
        if match is None:
            continue
        values = tuple(part.strip().strip('"') for part in match.group(2).split("|"))
        if len(values) >= 3:
            result[match.group(1)] = values
    return result


def _resolve_fsgame_alias(
    alias: str,
    definitions: Mapping[str, tuple[str, ...]],
    *,
    install_dir: Path,
    home: Path,
    environ: Mapping[str, str],
    filesystem_root: Path | None,
    stack: tuple[str, ...] = (),
) -> Path | None:
    if alias == "$fs_root$":
        return install_dir
    if alias in stack:
        return None
    values = definitions.get(alias)
    if values is None or len(values) < 3:
        return None
    parent_value = values[2]
    if parent_value.startswith("$") and parent_value.endswith("$"):
        base = _resolve_fsgame_alias(
            parent_value,
            definitions,
            install_dir=install_dir,
            home=home,
            environ=environ,
            filesystem_root=filesystem_root,
            stack=(*stack, alias),
        )
    else:
        base = _path_value(
            parent_value,
            home=home,
            environ=environ,
            base=install_dir,
            filesystem_root=filesystem_root,
        )
    if base is None:
        return None
    if len(values) >= 4 and values[3]:
        base = _path_value(
            values[3],
            home=home,
            environ=environ,
            base=base,
            filesystem_root=filesystem_root,
        )
    return base


def _fsgame_save_directory(
    install_dir: Path,
    *,
    game_id: str,
    home: Path,
    environ: Mapping[str, str],
    filesystem_root: Path | None,
) -> Path | None:
    names = ["fsgame.ltx"]
    if game_id == "soc":
        names.insert(0, "fsgame_soc.ltx")
    for name in names:
        config = install_dir / name
        if not config.is_file():
            continue
        text = _read_text(config)
        if text is None:
            continue
        definitions = _fsgame_definitions(text)
        return _resolve_fsgame_alias(
            "$game_saves$",
            definitions,
            install_dir=install_dir,
            home=home,
            environ=environ,
            filesystem_root=filesystem_root,
        )
    return None


def _proton_prefix(game: InstalledGame) -> Path:
    return (
        game.library_root
        / "steamapps"
        / "compatdata"
        / str(game.app_id)
        / "pfx"
        / "drive_c"
    )


def _add_xray_candidates(
    candidates: list[Path],
    game_id: str,
    roots: Sequence[Path],
) -> None:
    for document_root in roots:
        for folder in _XRAY_SAVE_DIRS[game_id]:
            candidates.append(document_root / folder / "savedgames")


def _add_ee_candidates(
    candidates: list[Path],
    game_id: str,
    roots: Sequence[Path],
) -> None:
    names = _EE_SAVE_NAMES[game_id]
    for saved_games in roots:
        for name in names:
            candidates.append(saved_games / name / "STEAM" / "savedgames")
            # The Shadow page documents the GOG spelling explicitly.  The
            # same existing-directory probe is useful for the other two EE
            # releases, whose PCGW pages currently list the GOG edition but
            # omit its path.
            candidates.append(saved_games / name / "gog" / "savedgames")


def _add_proton_candidates(candidates: list[Path], game: InstalledGame) -> None:
    prefix = _proton_prefix(game)
    users = (prefix / "users" / "steamuser", prefix / "users" / "Public")
    if game.game_id == "stalker2":
        for user in users[:1]:
            local = user / "AppData" / "Local" / "Stalker2" / "Saved"
            candidates.extend(
                (
                    local / "SaveGames",
                    local / "STEAM" / "SaveGames",
                    local / "EOS" / "SaveGames",
                    local / "GOG" / "SaveGames",
                )
            )
        return
    for user in users:
        documents = user / "Documents"
        for folder in _XRAY_SAVE_DIRS[game.game_id]:
            candidates.append(documents / folder / "savedgames")
        saved_games = user / "Saved Games"
        if game.edition == "enhanced":
            for name in _EE_SAVE_NAMES[game.game_id]:
                candidates.extend(
                    (
                        saved_games / name / "STEAM" / "savedgames",
                        saved_games / name / "gog" / "savedgames",
                    )
                )
    candidates.extend(
        prefix / "ProgramData" / "Documents" / folder / "savedgames"
        for folder in _XRAY_SAVE_DIRS[game.game_id]
    )


def _stalker2_local_save_directories(
    *,
    environ: Mapping[str, str],
    home: Path,
    filesystem_root: Path | None,
) -> tuple[Path, ...]:
    """Return the documented local S2 profile save roots in stable order."""

    local = _env_get(environ, "LOCALAPPDATA")
    local_root = (
        _path_value(
            local,
            home=home,
            environ=environ,
            filesystem_root=filesystem_root,
        )
        if local
        else home / "AppData" / "Local"
    )
    saved = local_root / "Stalker2" / "Saved"
    return (
        saved / "SaveGames",
        saved / "STEAM" / "SaveGames",
        saved / "EOS" / "SaveGames",
        saved / "GOG" / "SaveGames",
    )


def _stalker2_package_save_directories(
    *,
    environ: Mapping[str, str],
    home: Path,
    filesystem_root: Path | None,
) -> tuple[Path, ...]:
    local = _env_get(environ, "LOCALAPPDATA")
    local_root = (
        _path_value(
            local,
            home=home,
            environ=environ,
            filesystem_root=filesystem_root,
        )
        if local
        else home / "AppData" / "Local"
    )
    package = local_root / "Packages" / _STALKER2_PACKAGE / "SystemAppData" / "xgs"
    try:
        profiles = tuple(package.iterdir())
    except OSError:
        return ()
    return tuple(
        profile / "SaveGames"
        for profile in profiles
        if profile.is_dir() and (profile / "SaveGames").is_dir()
    )


def _save_directory_candidates(
    game_id: str,
    *,
    system: str | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
    filesystem_root: Path | None = None,
    root: Path | None = None,
    registry_reader: Callable[[], str | Path | None] | None = None,
    steam_library_roots: Sequence[str | Path] | None = None,
) -> tuple[Path, ...]:
    """Return all configured candidate locations, including missing paths.

    This is a read-only search.  It does not create directories, move files,
    invoke a launcher, or read save contents.  X-Ray locations are augmented
    with an installed release's own ``fsgame*.ltx`` result when present.
    """

    key, edition, selected_release_id = _release_selector(game_id)
    env = _environment(environ)
    filesystem_root = _effective_root(filesystem_root, root)
    home_path = _injected_home(home, filesystem_root)
    name = _system_name(system)
    candidates: list[Path] = []

    if key == "stalker2":
        candidates.extend(
            _stalker2_local_save_directories(
                environ=env,
                home=home_path,
                filesystem_root=filesystem_root,
            )
        )
        candidates.extend(
            _stalker2_package_save_directories(
                environ=env,
                home=home_path,
                filesystem_root=filesystem_root,
            )
        )
    else:
        _add_xray_candidates(
            candidates,
            key,
            _document_roots(
                home=home_path,
                environ=env,
                filesystem_root=filesystem_root,
            ),
        )
        if edition == "enhanced":
            candidates = []
            _add_ee_candidates(
                candidates,
                key,
                _saved_games_roots(
                    home=home_path,
                    environ=env,
                    filesystem_root=filesystem_root,
                ),
            )
        elif edition != "original":
            _add_ee_candidates(
                candidates,
                key,
                _saved_games_roots(
                    home=home_path,
                    environ=env,
                    filesystem_root=filesystem_root,
                ),
            )

    games = installed_releases(
        system=name,
        environ=env,
        home=home_path,
        filesystem_root=filesystem_root,
        registry_reader=registry_reader,
        steam_library_roots=steam_library_roots,
    )
    for game in games:
        if game.game_id != key or (
            selected_release_id is not None and game.release_id != selected_release_id
        ):
            continue
        override = _fsgame_save_directory(
            game.install_dir,
            game_id=key,
            home=home_path,
            environ=env,
            filesystem_root=filesystem_root,
        )
        if override is not None:
            candidates.append(override)
        if name == "windows":
            if game.edition == "original":
                candidates.append(game.install_dir / "_appdata_" / "savedgames")
        else:
            _add_proton_candidates(candidates, game)
            if game.edition == "original":
                candidates.append(game.install_dir / "_appdata_" / "savedgames")

    return _dedupe_paths(candidates)


def save_search_paths(
    game_id: str,
    *,
    system: str | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
    filesystem_root: Path | None = None,
    root: Path | None = None,
    registry_reader: Callable[[], str | Path | None] | None = None,
    steam_library_roots: Sequence[str | Path] | None = None,
) -> tuple[Path, ...]:
    """Return the candidate paths that a save search inspected."""

    return _save_directory_candidates(
        game_id,
        system=system,
        environ=environ,
        home=home,
        filesystem_root=filesystem_root,
        root=root,
        registry_reader=registry_reader,
        steam_library_roots=steam_library_roots,
    )


def save_directories(
    game_id: str,
    *,
    system: str | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
    filesystem_root: Path | None = None,
    root: Path | None = None,
    registry_reader: Callable[[], str | Path | None] | None = None,
    steam_library_roots: Sequence[str | Path] | None = None,
) -> tuple[Path, ...]:
    """Return existing local save directories for one supported game family."""

    return _existing_directories(
        _save_directory_candidates(
            game_id,
            system=system,
            environ=environ,
            home=home,
            filesystem_root=filesystem_root,
            root=root,
            registry_reader=registry_reader,
            steam_library_roots=steam_library_roots,
        )
    )


def manual_save_search_paths(
    game_id: str,
    *,
    steam_root: str | Path | None = None,
    game_root: str | Path | None = None,
    save_root: str | Path | None = None,
    system: str | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
    filesystem_root: Path | None = None,
    root: Path | None = None,
) -> tuple[Path, ...]:
    """Resolve save candidates from one explicitly selected manual root.

    The three manual scopes are intentionally exclusive: a save directory
    wins over a game directory, which wins over a Steam root.  This function
    never falls back to automatic locations; the settings layer decides when
    a missing manual root should make automatic discovery available again.
    """

    key, edition, selected_release_id = _release_selector(game_id)
    env = _environment(environ)
    filesystem_root = _effective_root(filesystem_root, root)
    home_path = _injected_home(home, filesystem_root)
    name = _system_name(system)

    def as_path(value: str | Path) -> Path:
        return _path_value(
            value,
            home=home_path,
            environ=env,
            filesystem_root=filesystem_root,
        )

    if save_root is not None:
        return (as_path(save_root),)

    if game_root is not None:
        install_dir = as_path(game_root)
        candidates: list[Path] = []
        if key == "stalker2":
            candidates.extend(
                (
                    install_dir / "Saved" / "SaveGames",
                    install_dir / "Saved" / "STEAM" / "SaveGames",
                    install_dir / "Saved" / "EOS" / "SaveGames",
                    install_dir / "Saved" / "GOG" / "SaveGames",
                )
            )
            # S2 keeps saves under the user profile rather than beside the
            # executable.  A selected game directory still identifies the
            # release, so include the documented profile roots as well.
            candidates.extend(
                _stalker2_local_save_directories(
                    environ=env,
                    home=home_path,
                    filesystem_root=filesystem_root,
                )
            )
        elif edition != "enhanced":
            override = _fsgame_save_directory(
                install_dir,
                game_id=key,
                home=home_path,
                environ=env,
                filesystem_root=filesystem_root,
            )
            if override is not None:
                candidates.append(override)
            candidates.append(install_dir / "_appdata_" / "savedgames")
        else:
            override = _fsgame_save_directory(
                install_dir,
                game_id=key,
                home=home_path,
                environ=env,
                filesystem_root=filesystem_root,
            )
            if override is not None:
                candidates.append(override)
            _add_ee_candidates(
                candidates,
                key,
                _saved_games_roots(
                    home=home_path,
                    environ=env,
                    filesystem_root=filesystem_root,
                ),
            )
            # Some EE installations have an overridden fsgame path inside
            # the selected game directory; keep the conventional X-Ray
            # fallback visible without claiming it is the default.
            candidates.append(install_dir / "_appdata_" / "savedgames")
        return _dedupe_paths(candidates)

    if steam_root is None:
        return ()

    selected_steam_root = as_path(steam_root)
    games = installed_releases(
        system=name,
        environ=env,
        home=home_path,
        filesystem_root=filesystem_root,
        steam_library_roots=(selected_steam_root,),
    )
    candidates = []
    for game in games:
        if game.game_id != key or (
            selected_release_id is not None and game.release_id != selected_release_id
        ):
            continue
        override = _fsgame_save_directory(
            game.install_dir,
            game_id=key,
            home=home_path,
            environ=env,
            filesystem_root=filesystem_root,
        )
        if override is not None:
            candidates.append(override)
        if name == "windows":
            if game.game_id == "stalker2":
                candidates.extend(
                    _stalker2_local_save_directories(
                        environ=env,
                        home=home_path,
                        filesystem_root=filesystem_root,
                    )
                )
            elif game.edition == "original":
                candidates.append(game.install_dir / "_appdata_" / "savedgames")
            else:
                _add_ee_candidates(
                    candidates,
                    key,
                    _saved_games_roots(
                        home=home_path,
                        environ=env,
                        filesystem_root=filesystem_root,
                    ),
                )
        else:
            _add_proton_candidates(candidates, game)
    return _dedupe_paths(candidates)
