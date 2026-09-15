"""Versioned local settings for manual save-location overrides."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias

from .platforms import (
    manual_save_search_paths,
    save_search_paths,
    user_data_dir,
)
from .releases import official_releases, release_by_id

SETTINGS_SCHEMA_VERSION = 1
SETTINGS_FILE_NAME = "settings.json"
SUPPORTED_GAME_IDS = ("stalker2", "cop", "clear_sky", "soc")
SUPPORTED_RELEASE_IDS = tuple(release.id for release in official_releases())
_SUPPORTED_PATH_KEYS = frozenset((*SUPPORTED_GAME_IDS, *SUPPORTED_RELEASE_IDS))

PathValue: TypeAlias = str | Path
PathEntries: TypeAlias = Mapping[str, PathValue] | Sequence[tuple[str, PathValue]]
AutomaticSearchFn: TypeAlias = Callable[[str], Sequence[Path]]
ManualSearchFn: TypeAlias = Callable[..., Sequence[Path]]


def _normalise_path(value: PathValue | None) -> Path | None:
    if value is None:
        return None
    path = Path(value).expanduser()
    if not str(path).strip():
        raise ValueError("path must not be empty")
    return path


def _normalise_entries(value: PathEntries) -> tuple[tuple[str, Path], ...]:
    raw_entries = value.items() if isinstance(value, Mapping) else value
    result: dict[str, Path] = {}
    for game_id, raw_path in raw_entries:
        if game_id not in _SUPPORTED_PATH_KEYS:
            raise ValueError(f"unsupported game id: {game_id!r}")
        path = _normalise_path(raw_path)
        if path is None:
            raise ValueError(f"path for {game_id!r} must not be null")
        result[game_id] = path
    return tuple(sorted(result.items()))


@dataclass(frozen=True)
class PathSettings:
    """Immutable manual path overrides persisted by :func:`save_settings`."""

    steam_root: Path | None = None
    game_roots: tuple[tuple[str, Path], ...] = ()
    save_roots: tuple[tuple[str, Path], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "steam_root", _normalise_path(self.steam_root))
        object.__setattr__(self, "game_roots", _normalise_entries(self.game_roots))
        object.__setattr__(self, "save_roots", _normalise_entries(self.save_roots))

    @staticmethod
    def _lookup(
        entries: tuple[tuple[str, Path], ...], selector: str
    ) -> Path | None:
        values = dict(entries)
        exact = values.get(selector)
        if exact is not None:
            return exact
        try:
            family = release_by_id(selector).family
        except KeyError:
            family = None
        return values.get(family) if family is not None else None

    def game_root(self, game_id: str) -> Path | None:
        return self._lookup(self.game_roots, game_id)

    def save_root(self, game_id: str) -> Path | None:
        return self._lookup(self.save_roots, game_id)

    def with_steam_root(self, value: PathValue | None) -> PathSettings:
        return PathSettings(_normalise_path(value), self.game_roots, self.save_roots)

    def with_game_root(self, game_id: str, value: PathValue | None) -> PathSettings:
        values = dict(self.game_roots)
        if value is None:
            values.pop(game_id, None)
        else:
            path = _normalise_path(value)
            if path is None:
                raise ValueError(f"path for {game_id!r} must not be null")
            values[game_id] = path
        return PathSettings(self.steam_root, tuple(values.items()), self.save_roots)

    def with_save_root(self, game_id: str, value: PathValue | None) -> PathSettings:
        values = dict(self.save_roots)
        if value is None:
            values.pop(game_id, None)
        else:
            path = _normalise_path(value)
            if path is None:
                raise ValueError(f"path for {game_id!r} must not be null")
            values[game_id] = path
        return PathSettings(self.steam_root, self.game_roots, tuple(values.items()))

    def manual_paths(self) -> tuple[Path, ...]:
        values: list[Path] = []
        if self.steam_root is not None:
            values.append(self.steam_root)
        values.extend(path for _game_id, path in self.game_roots)
        values.extend(path for _game_id, path in self.save_roots)
        result: list[Path] = []
        seen: set[Path] = set()
        for path in values:
            if path not in seen:
                seen.add(path)
                result.append(path)
        return tuple(result)


@dataclass(frozen=True)
class SettingsLoad:
    """Best-effort settings read result, including a user-facing diagnostic."""

    path: Path
    settings: PathSettings
    error: str | None = None


def settings_file_path(
    path: Path | None = None,
    *,
    data_dir: Path | None = None,
    system: str | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    """Return the settings file below the existing platform data directory."""

    if path is not None:
        return Path(path).expanduser()
    base = (
        Path(data_dir).expanduser()
        if data_dir is not None
        else user_data_dir(system=system, environ=environ, home=home)
    )
    return base / SETTINGS_FILE_NAME


def _load_error(reason: object) -> str:
    return f"Настройки не загружены: {reason}; используются пустые настройки."


def _json_path(value: object, field: str) -> Path | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} должен быть абсолютным путём или null")
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError(f"{field} должен быть абсолютным путём")
    return path


def _json_entries(value: object, field: str) -> tuple[tuple[str, Path], ...]:
    if value is None:
        return ()
    if not isinstance(value, dict):
        raise ValueError(f"{field} должен быть JSON object")
    entries: list[tuple[str, Path]] = []
    for game_id, raw_path in value.items():
        if not isinstance(game_id, str) or not isinstance(raw_path, str):
            raise ValueError(f"{field} должен содержать строки")
        if not raw_path.strip() or not Path(raw_path).expanduser().is_absolute():
            raise ValueError(f"{field}.{game_id} должен быть абсолютным путём")
        entries.append((game_id, Path(raw_path).expanduser()))
    return tuple(entries)


def _decode_settings(payload: object) -> PathSettings:
    if not isinstance(payload, dict):
        raise ValueError("корень settings должен быть JSON object")
    version = payload.get("schema_version")
    if isinstance(version, bool) or version != SETTINGS_SCHEMA_VERSION:
        raise ValueError(
            f"неподдерживаемая версия schema_version={version!r}; ожидалась "
            f"{SETTINGS_SCHEMA_VERSION}"
        )
    return PathSettings(
        steam_root=_json_path(payload.get("steam_root"), "steam_root"),
        game_roots=_json_entries(payload.get("game_roots"), "game_roots"),
        save_roots=_json_entries(payload.get("save_roots"), "save_roots"),
    )


def load_settings(
    path: Path | None = None,
    *,
    data_dir: Path | None = None,
    system: str | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> SettingsLoad:
    """Load settings without allowing malformed user data to break startup."""

    settings_path = settings_file_path(
        path,
        data_dir=data_dir,
        system=system,
        environ=environ,
        home=home,
    )
    try:
        text = settings_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return SettingsLoad(settings_path, PathSettings())
    except (OSError, UnicodeError) as exc:
        return SettingsLoad(settings_path, PathSettings(), _load_error(exc))

    try:
        payload = json.loads(text)
        settings = _decode_settings(payload)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        return SettingsLoad(settings_path, PathSettings(), _load_error(exc))
    return SettingsLoad(settings_path, settings)


def _encode_settings(settings: PathSettings) -> bytes:
    payload = {
        "schema_version": SETTINGS_SCHEMA_VERSION,
        "steam_root": str(settings.steam_root) if settings.steam_root is not None else None,
        "game_roots": {game_id: str(path) for game_id, path in settings.game_roots},
        "save_roots": {game_id: str(path) for game_id, path in settings.save_roots},
    }
    return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def save_settings(
    settings: PathSettings,
    path: Path | None = None,
    *,
    data_dir: Path | None = None,
    system: str | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    """Persist settings atomically below the user data directory."""

    settings_path = settings_file_path(
        path,
        data_dir=data_dir,
        system=system,
        environ=environ,
        home=home,
    )
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    data = _encode_settings(settings)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{settings_path.name}.", suffix=".tmp", dir=str(settings_path.parent)
    )
    temporary_path = Path(temporary_name)
    try:
        try:
            fchmod = getattr(os, "fchmod", None)
            if fchmod is not None:
                fchmod(descriptor, 0o600)
        except (AttributeError, OSError):
            pass
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, settings_path)
        _fsync_directory(settings_path.parent)
    finally:
        if descriptor != -1:
            os.close(descriptor)
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass
    return settings_path


def _is_directory(path: Path) -> bool:
    try:
        return path.is_dir()
    except OSError:
        return False


def missing_manual_paths(settings: PathSettings) -> tuple[Path, ...]:
    """Return saved manual directories that no longer exist."""

    return tuple(path for path in settings.manual_paths() if not _is_directory(path))


def search_paths_for_settings(
    game_id: str,
    settings: PathSettings,
    *,
    automatic_fn: AutomaticSearchFn = save_search_paths,
    manual_fn: ManualSearchFn = manual_save_search_paths,
) -> tuple[Path, ...]:
    """Use a valid manual scope first and restore auto-search when it vanishes."""

    save_root = settings.save_root(game_id)
    game_root = settings.game_root(game_id)
    if save_root is not None and _is_directory(save_root):
        return tuple(Path(path) for path in manual_fn(game_id, save_root=save_root))
    if game_root is not None and _is_directory(game_root):
        return tuple(Path(path) for path in manual_fn(game_id, game_root=game_root))
    if settings.steam_root is not None and _is_directory(settings.steam_root):
        return tuple(
            Path(path) for path in manual_fn(game_id, steam_root=settings.steam_root)
        )
    return tuple(Path(path) for path in automatic_fn(game_id))


__all__ = [
    "SETTINGS_FILE_NAME",
    "SETTINGS_SCHEMA_VERSION",
    "SUPPORTED_GAME_IDS",
    "SUPPORTED_RELEASE_IDS",
    "PathSettings",
    "SettingsLoad",
    "load_settings",
    "missing_manual_paths",
    "save_settings",
    "search_paths_for_settings",
    "settings_file_path",
]
