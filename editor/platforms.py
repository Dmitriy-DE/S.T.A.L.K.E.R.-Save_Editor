"""Operating-system paths and Steam runtime discovery.

The editor stores new state below the platform's user data directory.  The
pre-v0.3 ``~/Stalker2SaveEditor`` directory remains a read-only discovery
fallback so existing backups are never silently moved or deleted.
"""

from __future__ import annotations

import logging
import os
import platform
import re
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from .releases import official_releases, release_by_app_id, release_by_id
from .steam_vdf import library_paths, parse_vdf, read_text

LOGGER = logging.getLogger(__name__)

APP_DIR_NAME = "Stalker2SaveEditor"


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

        try:
            return release_by_app_id(self.app_id).id
        except KeyError:
            return self.game_id


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

def _release_selector(value: str) -> tuple[str, str | None, str | None]:
    """Return ``(family, edition, release_id)`` for a family or release key."""

    selector = value.strip().casefold()
    for descriptor in official_releases():
        if selector == descriptor.id.casefold():
            return descriptor.family, descriptor.edition, descriptor.id
    family = _GAME_ALIASES.get(selector)
    if family is None:
        raise ValueError(f"Unsupported STALKER game id: {value!r}")
    return family, None, None


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

def _effective_root(
    filesystem_root: Path | None,
    root: Path | None,
) -> Path | None:
    if filesystem_root is not None and root is not None and Path(filesystem_root) != Path(root):
        raise ValueError("filesystem_root and root must refer to the same path")
    value = filesystem_root if filesystem_root is not None else root
    return None if value is None else Path(value).expanduser()


def _system_name(system: str | None) -> str:
    name = (platform.system() if system is None else system).strip().lower()
    return "darwin" if name == "macos" else name


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
    """Return the writable application data directory for the host platform."""

    env = _environment(environ)
    home_path = _home_path(home)
    name = _system_name(system)
    if name == "windows":
        root = env.get("APPDATA") or env.get("LOCALAPPDATA")
        base = Path(root).expanduser() if root else home_path / "AppData" / "Roaming"
    elif name == "darwin":
        base = home_path / "Library" / "Application Support"
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


def locate_libsteam_api(
    *,
    system: str | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path | None:
    """Find Valve's ``libsteam_api`` for the native Steam Cloud worker.

    On Linux, prefer the Steam client's ``steamrt64`` runtime, followed by
    Steam library game installs. Returns ``None`` when no supported copy is
    available; Steam web can still provide read-only cloud access.
    """

    name = _system_name(system)
    lib_names = (
        ("steam_api64.dll", "steam_api.dll")
        if name == "windows"
        else ("libsteam_api.dylib",)
        if name == "darwin"
        else ("libsteam_api.so",)
    )

    def _first_lib(directory: Path) -> Path | None:
        for lib in lib_names:
            candidate = directory / lib
            if candidate.is_file():
                return candidate
        return None

    if name == "darwin":
        home_path = _home_path(home)
        steam_root = home_path / "Library" / "Application Support" / "Steam"
        candidate_dirs = [
            Path(sys.executable).expanduser().resolve().parent,
            Path(sys.executable).expanduser().resolve().parent.parent / "Frameworks",
            steam_root,
            steam_root / "Steam.AppBundle" / "Steam" / "Contents" / "MacOS",
            steam_root / "Steam.AppBundle" / "Steam" / "Contents" / "Frameworks",
            home_path / "Applications" / "Steam.app" / "Contents" / "MacOS",
            home_path / "Applications" / "Steam.app" / "Contents" / "Frameworks",
            Path("/Applications/Steam.app/Contents/MacOS"),
            Path("/Applications/Steam.app/Contents/Frameworks"),
        ]
        for directory in _dedupe_paths(candidate_dirs):
            found = _first_lib(directory)
            if found is not None:
                return found

    # The Linux Steam client ships its own runtime copy, even when no installed
    # Steamworks game has a native Linux build.
    if name != "windows":
        for root in steam_roots(system=name, environ=environ, home=home):
            found = _first_lib(root / "steamrt64") if sys.maxsize > 2**32 else _first_lib(root / "steamrt32")
            if found is not None:
                return found

    for game in installed_games(system=name, environ=environ, home=home):
        found = _first_lib(game.install_dir)
        if found is not None:
            return found
        subdirectories = ["bin", "Binaries", "_CommonRedist"]
        if name == "darwin":
            subdirectories.extend(
                (
                    "Contents/Frameworks",
                    "Contents/Plugins/steam_api.bundle/Contents/MacOS",
                )
            )
        for sub in subdirectories:
            found = _first_lib(game.install_dir / sub)
            if found is not None:
                return found

    return None


def _dedupe_paths(paths: Sequence[Path]) -> tuple[Path, ...]:
    result: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        value = Path(path)
        # Collapse the same directory reached through different symlinked
        # prefixes (e.g. ~/.steam/steam vs ~/.local/share/Steam), so a save
        # folder is never searched — and its files never listed — twice.
        key = os.path.realpath(value)
        if key in seen:
            continue
        seen.add(key)
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
    locations; macOS uses its Application Support directory. Existence is
    intentionally checked by :func:`steam_libraries`.
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

    if name == "darwin":
        return (home_path / "Library" / "Application Support" / "Steam",)

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
            value.expanduser()
            if isinstance(value, Path)
            else _path_value(
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
        text = read_text(library_file)
        if text is None:
            LOGGER.warning("Skipping unreadable Steam library file %s", library_file)
            continue
        try:
            parsed = parse_vdf(text)
        except ValueError as error:
            LOGGER.warning("Skipping malformed Steam library file %s: %s", library_file, error)
            continue
        for value in library_paths(parsed.get("libraryfolders")):
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


def _manifest_install_dir(
    manifest: Path,
    *,
    app_id: int,
    library: Path,
    home: Path,
    environ: Mapping[str, str],
    filesystem_root: Path | None,
) -> Path | None:
    text = read_text(manifest)
    if text is None:
        LOGGER.warning("Skipping unreadable Steam manifest %s", manifest)
        return None
    try:
        parsed = parse_vdf(text)
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
    for release in official_releases():
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
                    game_id=release.family,
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
        text = read_text(config)
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


def _stalker2_proton_save_directories(library_root: Path) -> tuple[Path, ...]:
    """Return S2 Proton save roots even when Steam has no app manifest.

    Cloud downloads and older Proton prefixes can exist without a current
    ``appmanifest_<app-id>.acf``. Wine/Proton has used both the modern
    ``AppData/Local`` spelling and the legacy ``Local Settings/Application
    Data`` spelling, so discovery must cover both.
    """

    prefix = (
        Path(library_root)
        / "steamapps"
        / "compatdata"
        / str(release_by_id("stalker2").app_id)
        / "pfx"
        / "drive_c"
    )
    user = prefix / "users" / "steamuser"
    roots: list[Path] = []
    for local_root in (
        user / "AppData" / "Local",
        user / "Local Settings" / "Application Data",
    ):
        saved = local_root / "Stalker2" / "Saved"
        roots.extend(
            (
                saved / "SaveGames",
                saved / "SaveGames" / "Data",
                saved / "STEAM" / "SaveGames",
                saved / "STEAM" / "SaveGames" / "Data",
                saved / "EOS" / "SaveGames",
                saved / "EOS" / "SaveGames" / "Data",
                saved / "GOG" / "SaveGames",
                saved / "GOG" / "SaveGames" / "Data",
            )
        )
    return tuple(roots)


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
        candidates.extend(_stalker2_proton_save_directories(game.library_root))
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
        saved / "SaveGames" / "Data",
        saved / "STEAM" / "SaveGames",
        saved / "STEAM" / "SaveGames" / "Data",
        saved / "EOS" / "SaveGames",
        saved / "EOS" / "SaveGames" / "Data",
        saved / "GOG" / "SaveGames",
        saved / "GOG" / "SaveGames" / "Data",
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


def _stalker2_macos_bottle_save_directories(
    *, home: Path, environ: Mapping[str, str]
) -> tuple[Path, ...]:
    """Return S2 save candidates under known CrossOver and Whisky bottles.

    This enumerates bottle/user directory names only. It never reads save
    contents, starts either compatibility layer, or creates a missing path.
    """

    roots = [
        home / "Library" / "Application Support" / "CrossOver" / "Bottles",
        home / "Library" / "Application Support" / "CrossOver Games" / "Bottles",
        Path("/Library/Application Support/CrossOver/Bottles"),
        home
        / "Library"
        / "Containers"
        / "com.isaacmarovitz.Whisky"
        / "Bottles",
    ]
    for key in ("CX_BOTTLE_PATH", "CX_MANAGED_BOTTLE_PATH"):
        value = _env_get(environ, key)
        if value:
            roots.extend(
                _path_value(raw, home=home, environ=environ)
                for raw in value.split(os.pathsep)
                if raw.strip()
            )

    candidates: list[Path] = []
    for root in _dedupe_paths(roots):
        try:
            bottles = tuple(root.iterdir())
        except OSError:
            continue
        for bottle in bottles:
            users_root = bottle / "drive_c" / "users"
            try:
                users = tuple(users_root.iterdir())
            except OSError:
                continue
            for user in users:
                for local_root in (
                    user / "AppData" / "Local",
                    user / "Local Settings" / "Application Data",
                ):
                    saved = local_root / "Stalker2" / "Saved"
                    candidates.extend(
                        (
                            saved / "SaveGames",
                            saved / "SaveGames" / "Data",
                            saved / "STEAM" / "SaveGames",
                            saved / "STEAM" / "SaveGames" / "Data",
                            saved / "EOS" / "SaveGames",
                            saved / "EOS" / "SaveGames" / "Data",
                            saved / "GOG" / "SaveGames",
                            saved / "GOG" / "SaveGames" / "Data",
                        )
                    )
    return tuple(candidates)


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
        if name == "darwin":
            candidates.extend(
                _stalker2_macos_bottle_save_directories(home=home_path, environ=env)
            )
        # A cloud download may create a Proton prefix without installing the
        # game or leaving a current appmanifest behind. Search every known
        # Steam library directly in that case as well.
        for library in steam_libraries(
            system=name,
            environ=env,
            home=home_path,
            filesystem_root=filesystem_root,
            registry_reader=registry_reader,
            steam_library_roots=steam_library_roots,
        ):
            candidates.extend(_stalker2_proton_save_directories(library))
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

    # Orphaned installs: Steam can drop a game's manifest while keeping its
    # ``_appdata_/savedgames`` folder (the classic X-Ray save location), e.g.
    # when the original game is uninstalled but its saves are kept.  Probe
    # every Steam library for the release's known install-dir names directly,
    # so those saves are still found without a manifest.
    if key != "stalker2":
        libraries = steam_libraries(
            system=name,
            environ=env,
            home=home_path,
            filesystem_root=filesystem_root,
            registry_reader=registry_reader,
            steam_library_roots=steam_library_roots,
        )
        for release in official_releases():
            if release.family != key or release.edition != "original":
                continue
            if (
                selected_release_id is not None
                and release.id != selected_release_id
            ):
                continue
            for library in libraries:
                common = library / "steamapps" / "common"
                for folder in release.install_dirs:
                    candidates.append(common / folder / "_appdata_" / "savedgames")

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

    candidates: list[Path] = []
    if save_root is not None:
        return (as_path(save_root),)

    if game_root is not None:
        install_dir = as_path(game_root)
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
    if key == "stalker2":
        candidates.extend(_stalker2_proton_save_directories(selected_steam_root))
    games = installed_releases(
        system=name,
        environ=env,
        home=home_path,
        filesystem_root=filesystem_root,
        steam_library_roots=(selected_steam_root,),
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

    # Keep the explicit Steam-root setting useful for retained/orphaned X-Ray
    # installs too. A missing manifest must not hide the documented
    # ``steamapps/common/<game>/_appdata_/savedgames`` folders.
    if key != "stalker2":
        for release in official_releases():
            if release.family != key or release.edition != "original":
                continue
            if (
                selected_release_id is not None
                and release.id != selected_release_id
            ):
                continue
            common = selected_steam_root / "steamapps" / "common"
            candidates.extend(
                common / folder / "_appdata_" / "savedgames"
                for folder in release.install_dirs
            )
    return _dedupe_paths(candidates)
