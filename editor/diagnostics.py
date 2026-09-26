"""Bounded local application logs and opt-in diagnostics submission."""

from __future__ import annotations

import ctypes
import gzip
import json
import logging
import logging.handlers
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit

from . import codec
from .i18n import tr
from .platforms import InstalledGame, discover_helper, user_data_dir
from .platforms import installed_releases as _installed_releases
from .platforms import save_directories as _platform_save_directories
from .releases import ReleaseDescriptor, official_releases
from .settings import load_settings, search_paths_for_settings
from .steam_vdf import parse_vdf, read_text
from .updater import UpdateClient, detect_installation
from .xray_catalog import read_xray_asset
from .xray_container import lzo1x_compress, lzo1x_decompress

LOGGER_NAME = "stalker2_save_editor"
LOG_FILENAME = "save-editor.log"
# Logs stay tiny: a quarter megabyte plus one rotated copy.
MAX_LOG_BYTES = 256 * 1024
LOG_BACKUP_COUNT = 1
LOG_MAX_AGE_SECONDS = 30 * 24 * 60 * 60
LOG_MAX_TOTAL_BYTES = MAX_LOG_BYTES * (LOG_BACKUP_COUNT + 1)
MAX_BUNDLE_BYTES = 1_500_000
MAX_UPLOAD_BYTES = 2 * 1024 * 1024
DEFAULT_TIMEOUT = 15.0
DEFAULT_ENDPOINT = "https://save-editor-downloads.save-editor.workers.dev/diagnostics"

_URL_SECRET_RE = re.compile(
    r"(?ix)\b(?P<key>access_token|api_key|apikey|auth_token|client_secret|refresh_token|token)"
    r"(?P<separator>\s*=\s*)(?P<value>[^&#\s]+)"
)
_HEADER_SECRET_RE = re.compile(
    r"(?ix)\b(?P<key>authorization|cookie)\b"
    r"(?P<separator>\s*[:=]\s*)(?P<value>[^\r\n]+)"
)
_SECRET_RE = re.compile(
    r"(?ix)\b(?P<key>token|password|passwd|secret)"
    r"(?P<separator>\s*[:=]\s*)"
    r"(?P<value>(?:(?:bearer|basic)\s+)?[^\s,;]+)"
)
_QUOTED_SECRET_RE = re.compile(
    r'(?ix)(?P<prefix>["\'](?:access_token|api_key|apikey|authorization|client_secret|cookie|refresh_token|token|password|passwd|secret)'
    r'["\']\s*:\s*["\'])(?:\\.|[^"\\\r\n])*(?P<suffix>["\'])'
)
_ACCOUNT_ID_RE = re.compile(
    r"(?ix)\b(?P<key>steam(?:_?account)?(?:_?id)?|steamid|owner_?id|account_?id)"
    r"(?P<separator>\s*[:=]\s*)(?P<value>\d{6,20})"
)
_FILE_CONTENT_RE = re.compile(
    r"(?ix)\b(?P<key>save_(?:bytes|data|payload)|raw_(?:bytes|data)|"
    r"file_contents|contents|payload|content)"
    r"(?P<separator>\s*[:=]\s*)(?P<value>.*?)(?=\s+[a-z][\w-]*\s*[:=]|$)"
)
_WINDOWS_HOME_RE = re.compile(r"(?i)(?:[a-z]:)?[\\/]Users[\\/][^\\/\s]+")
_POSIX_HOME_RE = re.compile(r"/home/[^/\s]+|/Users/[^/\s]+")
_STEAM_USERDATA_RE = re.compile(r"(?i)([\\/]userdata[\\/])\d{6,20}")
_LOG_PATH_RE = re.compile(rf"^{re.escape(LOG_FILENAME)}(?:\.\d+)?$")


CRASH_FILENAME = "last-crash.txt"
FATAL_FILENAME = "fatal.log"
MAX_CRASH_BYTES = 32 * 1024
MAX_ENVIRONMENT_REPORT_BYTES = 96 * 1024
PROJECT_ROOT = Path(__file__).resolve().parents[1]
OFFICIAL_NAMES_PATH = PROJECT_ROOT / "web" / "catalog_names.json"
S2_ITEMS_PATH = PROJECT_ROOT / "web" / "s2_items.json"
SOUND_SOURCE = "sounds/interface/console/menu_accept.ogg"
_SOUND_FAMILIES = ("stalker2", "soc", "clear_sky", "cop")
_OFFICIAL_NAME_FAMILIES = ("soc", "clear_sky", "cop")
_SOUND_CACHE_FILES = {
    "soc": (
        "click.wav",
        "tab.wav",
        "hover.wav",
        "error.wav",
        "open.wav",
        "save.wav",
        "menu-music.wav",
    ),
    "clear_sky": (
        "click.wav",
        "tab.wav",
        "hover.wav",
        "error.wav",
        "open.wav",
        "save.wav",
        "menu-music.ogg",
    ),
    "cop": (
        "click.wav",
        "tab.wav",
        "hover.wav",
        "error.wav",
        "open.wav",
        "save.wav",
        "menu-music.ogg",
    ),
}

CheckStatus = Literal["ok", "warn", "fail"]


@dataclass(frozen=True)
class Check:
    """One localized Environment Doctor result."""

    group: str
    name: str
    status: CheckStatus
    detail: str
    hint: str


_last_media_error: str | None = None
_output_device: str | None = None


class DiagnosticsError(RuntimeError):
    """A user-safe error from local collection or the diagnostics endpoint."""


def _result(
    group: str,
    name: str,
    status: CheckStatus,
    detail: str,
    hint: str = "",
) -> Check:
    groups = {
        "Игры": tr("Игры"),
        "Данные": tr("Данные"),
        "Звук": tr("Звук"),
        "Обновления": tr("Обновления"),
        "Steam": tr("Steam"),
        "Кодеки": tr("Кодеки"),
        "Дочерние задачи": tr("Дочерние задачи"),
    }
    return Check(groups[group], name, status, detail, hint)


def _named_check(group: str, name: str, status: CheckStatus, detail: str, hint: str = "") -> Check:
    return _result(group, tr(name), status, detail, hint)


def _short_path(value: Path | str) -> str:
    path = Path(value).expanduser()
    try:
        relative = path.relative_to(Path.home())
    except ValueError:
        return str(Path(path.anchor) / "…") if path.is_absolute() else "…"
    return str(Path("~") / relative) if relative.parts else "~"


def _exception_detail(exc: BaseException) -> str:
    return tr("Проверка завершилась ошибкой: {0}", type(exc).__name__)


def format_report(checks: Sequence[Check]) -> str:
    """Render checks as the same localized plain-text report used by the UI and upload."""

    status_names: dict[CheckStatus, str] = {
        "ok": tr("ОК"),
        "warn": tr("ПРЕДУПРЕЖДЕНИЕ"),
        "fail": tr("ОШИБКА"),
    }
    lines: list[str] = []
    previous_group: str | None = None
    for check in checks:
        if check.group != previous_group:
            if lines:
                lines.append("")
            lines.append(tr("Группа: {0}", check.group))
            previous_group = check.group
        lines.append(f"{status_names[check.status]} | {check.name}")
        if check.detail:
            lines.append(tr("Подробности: {0}", check.detail))
        if check.hint:
            lines.append(tr("Совет: {0}", check.hint))
    return "\n".join(lines)


def record_media_error(message: str | None) -> None:
    """Save the most recent QMediaPlayer error without importing Qt here."""

    global _last_media_error
    cleaned = _redact(str(message or "")).strip()
    _last_media_error = cleaned[:500] or None


def record_output_device(description: str | None) -> None:
    """Save the output-device description supplied by the Qt UI layer."""

    global _output_device
    cleaned = _redact(str(description or "")).strip()
    _output_device = cleaned[:200] or None


def _game_check_name(release: ReleaseDescriptor, label: str) -> str:
    return f"{release.title}: {label}"


def _save_directories(release_id: str) -> tuple[Path, ...]:
    settings = load_settings().settings
    paths = search_paths_for_settings(
        release_id,
        settings,
        automatic_fn=_platform_save_directories,
    )
    return tuple(path for path in paths if path.is_dir())


def _find_release_installation(
    release: ReleaseDescriptor,
    installations: Sequence[InstalledGame] | None,
) -> InstalledGame | None:
    entries = _installed_releases() if installations is None else installations
    return next((game for game in entries if game.release_id == release.id), None)


def check_game_installation(
    release: ReleaseDescriptor,
    installations: Sequence[InstalledGame] | None = None,
) -> Check:
    name = _game_check_name(release, tr("Установка"))
    try:
        game = _find_release_installation(release, installations)
    except Exception as exc:
        return _result("Игры", name, "fail", _exception_detail(exc), tr("Проверьте библиотеки Steam."))
    if game is None:
        return _result(
            "Игры", name, "warn", tr("Установка не найдена"), tr("Проверьте библиотеку Steam и выбранный релиз.")
        )
    return _result("Игры", name, "ok", tr("Найдена: {0}", _short_path(game.install_dir)))


def check_game_buildid(
    release: ReleaseDescriptor,
    installations: Sequence[InstalledGame] | None = None,
) -> Check:
    name = _game_check_name(release, tr("Steam buildid"))
    try:
        game = _find_release_installation(release, installations)
        if game is None:
            return _result("Игры", name, "warn", tr("Установка не найдена"), tr("Проверьте библиотеку Steam."))
        manifest = game.library_root / "steamapps" / f"appmanifest_{game.app_id}.acf"
        text = read_text(manifest)
        if text is None:
            return _result("Игры", name, "warn", tr("Манифест Steam не найден"), tr("Проверьте файлы Steam."))
        payload = parse_vdf(text)
        app_state = payload.get("AppState")
        build_id = app_state.get("buildid") if isinstance(app_state, dict) else None
        if not isinstance(build_id, str) or not build_id.strip():
            return _result("Игры", name, "warn", tr("buildid отсутствует"), tr("Проверьте целостность файлов игры в Steam."))
        return _result("Игры", name, "ok", tr("buildid: {0}", build_id.strip()))
    except Exception as exc:
        return _result("Игры", name, "fail", _exception_detail(exc), tr("Проверьте манифест игры в Steam."))


def check_game_saves_folder(
    release: ReleaseDescriptor,
    directories: Sequence[Path] | None = None,
) -> Check:
    name = _game_check_name(release, tr("Папка сохранений"))
    try:
        folders = _save_directories(release.id) if directories is None else directories
    except Exception as exc:
        return _result("Игры", name, "fail", _exception_detail(exc), tr("Проверьте расположение сохранений."))
    if not folders:
        return _result("Игры", name, "warn", tr("Папка сохранений не найдена"), tr("Запустите игру или укажите путь в настройках."))
    return _result("Игры", name, "ok", tr("Найдена: {0}", _short_path(folders[0])))


def check_game_save_count(
    release: ReleaseDescriptor,
    directories: Sequence[Path] | None = None,
) -> Check:
    name = _game_check_name(release, tr("Число сохранений"))
    try:
        folders = _save_directories(release.id) if directories is None else directories
        count = sum(
            1
            for folder in folders
            for candidate in folder.iterdir()
            if candidate.is_file() and candidate.suffix.casefold() in release.extensions
        )
    except OSError as exc:
        return _result("Игры", name, "fail", _exception_detail(exc), tr("Проверьте доступ к папке сохранений."))
    except Exception as exc:
        return _result("Игры", name, "fail", _exception_detail(exc), tr("Проверьте расположение сохранений."))
    if count == 0:
        return _result("Игры", name, "warn", tr("Сохранения не найдены"), tr("Создайте сохранение в игре."))
    return _result("Игры", name, "ok", tr("Сохранений: {0}", count))


def check_data_directory() -> Check:
    name = tr("Каталог данных")
    try:
        directory = user_data_dir()
        if not directory.is_dir() or not os.access(directory, os.W_OK):
            return _result("Данные", name, "warn", tr("Каталог недоступен: {0}", _short_path(directory)), tr("Проверьте права доступа к каталогу данных."))
        return _result("Данные", name, "ok", tr("Доступен: {0}", _short_path(directory)))
    except Exception as exc:
        return _result("Данные", name, "fail", _exception_detail(exc), tr("Проверьте каталог данных приложения."))


def check_icons() -> Check:
    name = tr("Иконки")
    try:
        desktop = tuple((PROJECT_ROOT / "assets" / "icons").rglob("*.png"))
    except OSError as exc:
        return _result("Данные", name, "fail", _exception_detail(exc), tr("Проверьте файлы приложения."))
    if not desktop:
        return _result("Данные", name, "fail", tr("Иконки отсутствуют"), tr("Восстановите файлы приложения."))
    return _result("Данные", name, "ok", tr("Иконки найдены: {0}", len(desktop)))


def check_official_names() -> Check:
    name = tr("Официальные названия")
    try:
        payload = json.loads(OFFICIAL_NAMES_PATH.read_text(encoding="utf-8"))
        releases = payload.get("releases") if isinstance(payload, dict) else None
        valid = isinstance(releases, dict) and all(
            isinstance(releases.get(family), dict)
            and bool(releases[family].get("items"))
            for family in _OFFICIAL_NAME_FAMILIES
        )
    except (OSError, UnicodeError, json.JSONDecodeError):
        valid = False
    if not valid:
        return _result("Данные", name, "fail", tr("Таблица официальных названий недоступна"), tr("Восстановите файл каталога названий."))
    return _result("Данные", name, "ok", tr("Таблица официальных названий загружена"))


def check_s2_schema() -> Check:
    name = tr("База S2")
    try:
        payload = json.loads(S2_ITEMS_PATH.read_text(encoding="utf-8"))
        version = payload.get("schema_version") if isinstance(payload, dict) else None
        valid = version == 2 and isinstance(payload.get("items"), dict) and bool(payload["items"])
    except (OSError, UnicodeError, json.JSONDecodeError):
        valid = False
        version = None
    if not valid:
        return _result("Данные", name, "fail", tr("Версия схемы базы S2 не поддерживается: {0}", version), tr("Восстановите файл базы S2."))
    return _result("Данные", name, "ok", tr("Версия схемы: {0}", version))


def _sound_cache_root() -> Path:
    return user_data_dir() / "sounds" / "game-v1"


def _family_title(family: str) -> str:
    release = next((item for item in official_releases() if item.family == family), None)
    return release.title if release is not None else family


def check_sound_cache(family: str) -> Check:
    name = tr("Кэш звука: {0}", _family_title(family))
    expected = _SOUND_CACHE_FILES.get(family)
    if expected is None:
        return _result("Звук", name, "warn", tr("Для игры нет кэша звуковых ресурсов"))
    try:
        directory = _sound_cache_root() / family
        present = sum(1 for filename in expected if (directory / filename).is_file())
    except Exception as exc:
        return _result("Звук", name, "fail", _exception_detail(exc), tr("Проверьте каталог данных приложения."))
    if present != len(expected):
        return _result("Звук", name, "warn", tr("Подготовлено файлов: {0} / {1}", present, len(expected)), tr("Откройте игру, чтобы подготовить кэш звука."))
    return _result("Звук", name, "ok", tr("Кэш подготовлен: {0} файлов", present))


def check_game_audio_source(
    family: str,
    installations: Sequence[InstalledGame] | None = None,
) -> Check:
    name = tr("Источник в игре: {0}", _family_title(family))
    if family == "stalker2":
        return _result(
            "Звук",
            name,
            "warn",
            tr("Для S2 источник звука не подключён"),
            tr("Для игры нет кэша звуковых ресурсов"),
        )
    try:
        entries = _installed_releases() if installations is None else installations
        games = [game for game in entries if game.game_id == family]
        if not games:
            return _result("Звук", name, "warn", tr("Установка игры не найдена"), tr("Установите игру, чтобы проверить её звуковые файлы."))
        games.sort(key=lambda game: game.edition != "original")
        found = read_xray_asset(games[0].install_dir, SOUND_SOURCE)
    except Exception as exc:
        return _result("Звук", name, "fail", _exception_detail(exc), tr("Проверьте файлы игры в Steam."))
    if found is None:
        return _result("Звук", name, "fail", tr("Звуковой файл не найден"), tr("Проверьте целостность файлов игры в Steam."))
    return _result("Звук", name, "ok", tr("Звуковой файл найден"))


def check_last_media_error() -> Check:
    name = tr("Последняя ошибка QMediaPlayer")
    if _last_media_error:
        return _result("Звук", name, "fail", _last_media_error, tr("Проверьте устройство вывода и мультимедийный кодек."))
    return _result("Звук", name, "ok", tr("Ошибок QMediaPlayer нет"))


def check_output_device() -> Check:
    name = tr("Устройство вывода")
    if not _output_device:
        return _result("Звук", name, "warn", tr("Устройство вывода не определено"), tr("Подключите устройство вывода звука."))
    return _result("Звук", name, "ok", tr("Устройство: {0}", _output_device))


def check_update_manifest() -> Check:
    name = tr("Манифест обновления")
    try:
        version = (PROJECT_ROOT / "VERSION").read_text(encoding="utf-8").strip()
        result = UpdateClient(current_version=version, timeout=5.0).check()
    except Exception as exc:
        return _result("Обновления", name, "warn", tr("Манифест недоступен: {0}", type(exc).__name__), tr("Проверьте подключение к интернету."))
    if result.state in {"current", "available"}:
        return _result("Обновления", name, "ok", tr("Манифест доступен"))
    if result.state == "invalid":
        return _result("Обновления", name, "fail", tr("Манифест недоступен"), tr("Проверьте файл манифеста обновления."))
    return _result("Обновления", name, "warn", tr("Манифест недоступен"), tr("Проверьте подключение к интернету."))


def _check_system_tool(command: str) -> Check:
    names = {"pkexec": "pkexec", "apt-get": "apt-get", "xdg-open": "xdg-open"}
    name = tr("Команда {0}", names[command])
    try:
        path = shutil.which(command)
    except Exception as exc:
        return _result("Обновления", name, "fail", _exception_detail(exc), tr("Проверьте системные пути команд."))
    if path is None:
        return _result("Обновления", name, "warn", tr("Не найдена"), tr("Установите системную команду, если она нужна этому способу установки."))
    return _result("Обновления", name, "ok", tr("Найдена: {0}", _short_path(path)))


def check_pkexec() -> Check:
    return _check_system_tool("pkexec")


def check_apt_get() -> Check:
    return _check_system_tool("apt-get")


def check_xdg_open() -> Check:
    return _check_system_tool("xdg-open")


def check_installation_type() -> Check:
    name = tr("Тип установки")
    try:
        info = detect_installation()
    except Exception:
        return _result("Обновления", name, "warn", tr("Не удалось определить тип установки"), tr("Поддерживаются deb, portable и exe."))
    labels = {
        "package": "deb",
        "portable": "portable",
        "installer": "exe",
        "development": "development",
    }
    label = labels.get(info.kind)
    if label is None:
        return _result("Обновления", name, "fail", tr("Неизвестный тип установки"), tr("Поддерживаются deb, portable и exe."))
    return _result("Обновления", name, "ok", tr("Тип: {0}", label))


def _find_steam_api_library() -> Path | None:
    library_names: tuple[str, ...]
    if os.name == "nt":
        library_names = ("steam_api64.dll", "steam_api.dll")
    else:
        library_names = ("libsteam_api.so",)
    helper = discover_helper()
    roots: list[Path] = []
    if helper is not None and helper.suffix.casefold() != ".appimage":
        roots.append(helper.parent)
    roots.extend(game.install_dir for game in _installed_releases())
    for root in roots:
        for directory in (root, root / "bin", root / "Binaries", root / "_CommonRedist"):
            for filename in library_names:
                candidate = directory / filename
                if candidate.is_file():
                    return candidate
    return None


def check_steam_api_library() -> Check:
    name = tr("libsteam_api")
    try:
        library = _find_steam_api_library()
        if library is None:
            return _result("Steam", name, "warn", tr("Библиотека не найдена"), tr("Установите игру из Steam или её native helper."))
        loader = getattr(ctypes, "WinDLL", ctypes.CDLL) if os.name == "nt" else ctypes.CDLL
        loader(str(library))
    except Exception as exc:
        return _result("Steam", name, "fail", _exception_detail(exc), tr("Проверьте файлы библиотеки Steam."))
    return _result("Steam", name, "ok", tr("Библиотека загружена"))


def _steam_process_running() -> bool:
    if os.name == "nt":
        command = ["tasklist", "/FI", "IMAGENAME eq steam.exe"]
        expected = "steam.exe"
    else:
        command = ["pgrep", "-x", "steam"]
        expected = ""
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=2.0)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return expected in result.stdout.casefold() if expected else result.returncode == 0


def check_steam_running() -> Check:
    name = tr("Клиент Steam")
    try:
        running = _steam_process_running()
    except Exception as exc:
        return _result("Steam", name, "fail", _exception_detail(exc), tr("Запустите Steam и повторите проверку."))
    if not running:
        return _result("Steam", name, "warn", tr("Steam не запущен"), tr("Запустите Steam, если требуется работа с Cloud."))
    return _result("Steam", name, "ok", tr("Steam запущен"))


def check_kraken_decode() -> Check:
    name = tr("Kraken decode")
    raw = b"Save Editor Kraken decoder probe\x00" * 32
    stream = b"\xCC\x06" + raw
    try:
        decoder = codec.load_decoder()
        decoded = codec.decompress(stream, len(raw), decoder=decoder)
        if decoded != raw:
            raise codec.CodecError("decoder probe returned different bytes")
    except Exception as exc:
        return _result("Кодеки", name, "fail", _exception_detail(exc), tr("Восстановите native decoder для этой платформы."))
    return _result("Кодеки", name, "ok", tr("Тестовое распаковывание выполнено"))


def check_kraken_encode() -> Check:
    name = tr("Kraken encode")
    raw = b"Save Editor environment check\x00" * 64
    try:
        encoder = codec.load_encoder()
    except Exception as exc:
        return _result("Кодеки", name, "warn", _exception_detail(exc), tr("Переустановите сборку с Kraken encoder."))
    try:
        encoded = codec.compress(raw, encoder=encoder, level=1)
        if not encoded:
            raise codec.CodecError("encoder returned an empty stream")
    except Exception as exc:
        return _result("Кодеки", name, "fail", _exception_detail(exc), tr("Проверьте Kraken encoder в сборке."))
    return _result("Кодеки", name, "ok", tr("Тестовое сжатие выполнено"))


def check_xray_lzo() -> Check:
    name = tr("X-Ray LZO")
    payload = b"Save Editor LZO environment check\x00" * 32
    try:
        encoded = lzo1x_compress(payload)
        decoded = lzo1x_decompress(encoded, len(payload))
        if decoded != payload:
            raise ValueError("LZO round-trip mismatch")
    except Exception as exc:
        return _result("Кодеки", name, "fail", _exception_detail(exc), tr("Проверьте модуль X-Ray LZO."))
    return _result("Кодеки", name, "ok", tr("Тестовое распаковывание выполнено"))


def _run_peek() -> bool:
    if getattr(sys, "frozen", False):
        executable = Path(sys.executable)
        native = executable.with_name("SaveEditor-native" + executable.suffix)
        command = [str(native if native.is_file() else executable), "--peek"]
        cwd = None
    else:
        command = [sys.executable, "-m", "ui", "--peek"]
        cwd = str(PROJECT_ROOT)
    try:
        with tempfile.TemporaryDirectory(prefix="save-editor-doctor-") as directory:
            empty_save = Path(directory) / "synthetic-empty.sav"
            empty_save.write_bytes(b"")
            result = subprocess.run(
                [*command, str(empty_save)],
                capture_output=True,
                text=True,
                check=False,
                timeout=15.0,
                cwd=cwd,
            )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if result.returncode != 0:
        return False
    for line in reversed(result.stdout.splitlines()):
        try:
            json.loads(line)
        except json.JSONDecodeError:
            continue
        return True
    return False


def check_child_peek() -> Check:
    name = tr("Дочерняя задача --peek")
    try:
        if not _run_peek():
            return _result("Дочерние задачи", name, "fail", tr("Корректный JSON-ответ не получен"), tr("Проверьте запуск приложения и повторите проверку."))
    except Exception as exc:
        return _result("Дочерние задачи", name, "fail", _exception_detail(exc), tr("Проверьте запуск приложения."))
    return _result("Дочерние задачи", name, "ok", tr("Получен JSON-ответ"))


def run_checks() -> list[Check]:
    """Run the Qt-free, read-only checks defined by RL-3."""

    try:
        installations = _installed_releases()
    except Exception:
        installations = ()
    checks: list[Check] = []
    for release in official_releases():
        try:
            directories = _save_directories(release.id)
        except Exception:
            directories = ()
        checks.extend(
            (
                check_game_installation(release, installations),
                check_game_buildid(release, installations),
                check_game_saves_folder(release, directories),
                check_game_save_count(release, directories),
            )
        )
    checks.extend((check_data_directory(), check_icons(), check_official_names(), check_s2_schema()))
    for family in _SOUND_FAMILIES:
        checks.append(check_sound_cache(family))
        checks.append(check_game_audio_source(family, installations))
    checks.extend((check_last_media_error(), check_output_device()))
    checks.extend(
        (
            check_update_manifest(),
            check_pkexec(),
            check_apt_get(),
            check_xdg_open(),
            check_installation_type(),
        )
    )
    checks.extend((check_steam_api_library(), check_steam_running()))
    checks.extend((check_kraken_decode(), check_kraken_encode(), check_xray_lzo()))
    checks.append(check_child_peek())
    return checks


def log_directory() -> Path:
    """Return the application-owned directory used for rotating diagnostics."""

    return user_data_dir() / "logs"


def configure_logging(
    directory: Path | None = None,
    *,
    max_bytes: int = MAX_LOG_BYTES,
    backup_count: int = LOG_BACKUP_COUNT,
    max_age_seconds: int = LOG_MAX_AGE_SECONDS,
    max_total_bytes: int | None = None,
) -> Path:
    """Install one idempotent rotating file handler and return its path."""

    if max_bytes <= 0 or backup_count < 0:
        raise ValueError("diagnostic log bounds must be non-negative and non-zero")
    target_dir = Path(directory).expanduser() if directory is not None else log_directory()
    target_dir.mkdir(parents=True, exist_ok=True)
    cleanup_logs(
        target_dir,
        max_age_seconds=max_age_seconds,
        max_total_bytes=(
            max_total_bytes
            if max_total_bytes is not None
            else max_bytes * (backup_count + 1)
        ),
    )
    target = target_dir / LOG_FILENAME
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    for handler in tuple(logger.handlers):
        if not getattr(handler, "_save_editor_diagnostics", False):
            continue
        if Path(getattr(handler, "baseFilename", "")).resolve() == target.resolve():
            if isinstance(handler, logging.handlers.RotatingFileHandler):
                handler.maxBytes = max_bytes
                handler.backupCount = backup_count
            return target
        logger.removeHandler(handler)
        handler.close()
    handler = logging.handlers.RotatingFileHandler(
        target,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    handler._save_editor_diagnostics = True  # type: ignore[attr-defined]
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )
    logger.addHandler(handler)
    return target


def _redact(text: str) -> str:
    home = str(Path.home()).rstrip("/\\")
    if home:
        text = text.replace(home, "<home>")
    text = _WINDOWS_HOME_RE.sub("<home>", text)
    text = _POSIX_HOME_RE.sub("<home>", text)
    text = _STEAM_USERDATA_RE.sub(r"\1<redacted>", text)
    text = _URL_SECRET_RE.sub(lambda match: f"{match.group('key')}=<redacted>", text)
    text = _HEADER_SECRET_RE.sub(lambda match: f"{match.group('key')}=<redacted>", text)
    text = _QUOTED_SECRET_RE.sub(
        lambda match: f"{match.group('prefix')}<redacted>{match.group('suffix')}",
        text,
    )
    text = _SECRET_RE.sub(lambda match: f"{match.group('key')}=<redacted>", text)
    text = _ACCOUNT_ID_RE.sub(lambda match: f"{match.group('key')}=<redacted>", text)
    return _FILE_CONTENT_RE.sub(lambda match: f"{match.group('key')}=<redacted>", text)


def _log_paths(directory: Path) -> list[Path]:
    try:
        if not directory.is_dir():
            return []
        paths = [
            path
            for path in directory.iterdir()
            if path.is_file() and _LOG_PATH_RE.fullmatch(path.name)
        ]
    except OSError:
        return []
    def mtime_ns(path: Path) -> int:
        try:
            return path.stat().st_mtime_ns
        except OSError:
            # Rotation can replace a file between iterdir() and stat(). Keep
            # the vanished path in the bounded read list; callers already
            # handle the subsequent read/unlink race without failing logging.
            return -1

    return sorted(paths, key=mtime_ns, reverse=True)


def cleanup_logs(
    directory: Path | None = None,
    *,
    max_age_seconds: int = LOG_MAX_AGE_SECONDS,
    max_total_bytes: int = LOG_MAX_TOTAL_BYTES,
    now: float | None = None,
) -> list[Path]:
    """Delete only rotated diagnostics logs outside the age/total budget."""

    if max_age_seconds < 0 or max_total_bytes <= 0:
        raise ValueError("diagnostic cleanup bounds must be non-negative and positive")
    source_dir = Path(directory).expanduser() if directory is not None else log_directory()
    if not source_dir.is_dir():
        return []
    current_time = time.time() if now is None else now
    paths = _log_paths(source_dir)
    removed: list[Path] = []
    cutoff = current_time - max_age_seconds
    for path in paths[1:]:
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
                removed.append(path)
        except OSError:
            continue
    sized_paths: list[tuple[Path, int]] = []
    for path in paths:
        if path in removed:
            continue
        try:
            sized_paths.append((path, path.stat().st_size))
        except OSError:
            continue
    total_bytes = sum(size for _path, size in sized_paths)
    for path, size in reversed(sized_paths[1:]):
        if total_bytes <= max_total_bytes:
            break
        try:
            total_bytes -= size
            path.unlink()
            removed.append(path)
        except OSError:
            continue
    return removed


def _read_log_tail(path: Path, max_bytes: int) -> str:
    """Read at most the newest ``max_bytes`` from one log file."""

    if max_bytes <= 0:
        return ""
    with path.open("rb") as handle:
        handle.seek(0, 2)
        size = handle.tell()
        handle.seek(max(0, size - max_bytes))
        data = handle.read(max_bytes)
    # FileHandler uses the platform newline convention.  Normalize it before
    # bundling so diagnostics have one stable wire format on Linux and Windows
    # and callers do not need platform-specific assertions/parsers.
    return data.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")


def collect_log_bundle(
    directory: Path | None = None,
    *,
    max_bytes: int = MAX_BUNDLE_BYTES,
    environment_report: str | None = None,
) -> bytes:
    """Collect logs and an optional Environment Doctor report into gzip."""

    if max_bytes <= 0:
        raise ValueError("diagnostic bundle bound must be positive")
    source_dir = Path(directory).expanduser() if directory is not None else log_directory()
    remaining = max_bytes
    blocks: list[str] = []
    if environment_report:
        report = _redact(environment_report)[:MAX_ENVIRONMENT_REPORT_BYTES]
        encoded_report = f"--- environment ---\n{report}\n".encode("utf-8", errors="replace")
        if len(encoded_report) > remaining:
            encoded_report = encoded_report[:remaining]
        blocks.append(encoded_report.decode("utf-8", errors="replace"))
        remaining -= len(encoded_report)
    for path in _log_paths(source_dir):
        if remaining <= 0:
            break
        try:
            text = _redact(_read_log_tail(path, remaining))
        except OSError:
            continue
        block = f"--- {path.name} ---\n{text}\n"
        encoded = block.encode("utf-8", errors="replace")
        if len(encoded) > remaining:
            encoded = encoded[-remaining:]
        blocks.append(encoded.decode("utf-8", errors="replace"))
        remaining -= len(encoded)
    crash = pending_crash_report(source_dir)
    if crash and remaining > 0:
        block = f"--- crash ---\n{crash[-MAX_CRASH_BYTES:]}\n"
        encoded = block.encode("utf-8", errors="replace")[:remaining]
        blocks.append(encoded.decode("utf-8", errors="replace"))
    raw = "".join(reversed(blocks)).encode("utf-8", errors="replace")
    payload = gzip.compress(raw, mtime=0)
    if len(payload) > MAX_UPLOAD_BYTES:
        raise DiagnosticsError("Логи слишком большие для отправки")
    return payload


def export_log_bundle(
    destination: Path,
    directory: Path | None = None,
    *,
    max_bytes: int = MAX_BUNDLE_BYTES,
) -> Path:
    """Write the same redacted bounded bundle used for upload to a local path."""

    destination = Path(destination).expanduser()
    if destination.exists() and destination.is_dir():
        raise DiagnosticsError("Путь экспорта логов является каталогом")
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = collect_log_bundle(directory, max_bytes=max_bytes)
    if len(payload) > MAX_UPLOAD_BYTES:
        raise DiagnosticsError("Логи слишком большие для отправки")
    try:
        destination.write_bytes(payload)
    except OSError as exc:
        raise DiagnosticsError(f"Не удалось сохранить экспорт логов: {exc}") from exc
    return destination


def install_crash_handler(directory: Path | None = None) -> None:
    """Record unhandled Python errors and hard crashes for the next start.

    The traceback goes to the regular log and, redacted and capped, to
    ``last-crash.txt`` so the next launch can offer to send it.  Native
    crashes (segfaults inside Qt) are captured by :mod:`faulthandler`.
    """

    import faulthandler
    import sys
    import threading
    import traceback

    target = directory or log_directory()
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError:
        return
    logger = logging.getLogger(LOGGER_NAME)

    def record(kind: str, exc_type, exc, tb) -> None:
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        logger.critical("unhandled %s\n%s", kind, text)
        report = _redact(f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {kind}\n{text}")
        try:
            (target / CRASH_FILENAME).write_text(report[-MAX_CRASH_BYTES:], encoding="utf-8")
        except OSError:
            pass

    previous_hook = sys.excepthook

    def excepthook(exc_type, exc, tb) -> None:
        record("exception", exc_type, exc, tb)
        previous_hook(exc_type, exc, tb)

    def thread_hook(args) -> None:
        if args.exc_type is not SystemExit:
            record(f"exception in thread {getattr(args.thread, 'name', '?')}", args.exc_type, args.exc_value, args.exc_traceback)

    sys.excepthook = excepthook
    threading.excepthook = thread_hook
    fatal = target / FATAL_FILENAME
    try:
        if fatal.is_file() and fatal.stat().st_size > MAX_CRASH_BYTES:
            fatal.unlink()
        handle = open(fatal, "a", encoding="utf-8")  # noqa: SIM115 - must outlive this call
        faulthandler.enable(handle)
        install_crash_handler._fatal_handle = handle  # type: ignore[attr-defined]
    except (OSError, RuntimeError, ValueError):
        pass


def pending_crash_report(directory: Path | None = None) -> str | None:
    """Return the redacted report of the previous crash, if one is waiting."""

    target = directory or log_directory()
    parts: list[str] = []
    try:
        crash = target / CRASH_FILENAME
        if crash.is_file():
            parts.append(crash.read_text(encoding="utf-8", errors="replace"))
        fatal = target / FATAL_FILENAME
        if fatal.is_file() and fatal.stat().st_size:
            parts.append(_redact(fatal.read_text(encoding="utf-8", errors="replace"))[-MAX_CRASH_BYTES:])
    except OSError:
        return None
    report = "\n".join(part for part in parts if part.strip())
    return report or None


def clear_crash_report(directory: Path | None = None) -> None:
    target = directory or log_directory()
    for name in (CRASH_FILENAME, FATAL_FILENAME):
        path = target / name
        try:
            if name == FATAL_FILENAME:
                # faulthandler keeps the file open; empty it instead.
                if path.is_file():
                    path.write_text("", encoding="utf-8")
            else:
                path.unlink(missing_ok=True)
        except OSError:
            pass


def _response_payload(response: Any) -> dict[str, object]:
    try:
        status = int(getattr(response, "status", 200))
        body = response.read(MAX_UPLOAD_BYTES)
    except (OSError, ValueError) as exc:
        raise DiagnosticsError(f"Не удалось прочитать ответ сервера логов: {exc}") from exc
    if status < 200 or status >= 300:
        raise DiagnosticsError(f"Сервер логов вернул HTTP {status}")
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DiagnosticsError("Сервер логов вернул некорректный ответ") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("report_id"), str):
        raise DiagnosticsError("Сервер логов не вернул report_id")
    return payload


def submit_logs(
    *,
    endpoint: str = DEFAULT_ENDPOINT,
    directory: Path | None = None,
    log_dir: Path | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    environment_report: str | None = None,
) -> str:
    """Submit a bounded diagnostic bundle and return its opaque report id."""

    if directory is not None and log_dir is not None:
        raise ValueError("use directory or log_dir, not both")
    source_dir = directory if directory is not None else log_dir
    parsed = urlsplit(endpoint)
    if parsed.scheme != "https" or not parsed.hostname:
        raise DiagnosticsError("Сервер логов должен использовать HTTPS")
    payload = collect_log_bundle(source_dir, environment_report=environment_report)
    if len(payload) > MAX_UPLOAD_BYTES:
        raise DiagnosticsError("Логи слишком большие для отправки")
    request = urllib.request.Request(
        endpoint,
        data=payload,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/gzip",
            "User-Agent": "SaveEditor-diagnostics/1",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            result = _response_payload(response)
    except (HTTPError, URLError, OSError, TimeoutError) as exc:
        raise DiagnosticsError(f"Не удалось отправить логи: {exc}") from exc
    return str(result["report_id"])


__all__ = [
    "DEFAULT_ENDPOINT",
    "DEFAULT_TIMEOUT",
    "Check",
    "CheckStatus",
    "DiagnosticsError",
    "check_apt_get",
    "check_child_peek",
    "check_data_directory",
    "check_game_audio_source",
    "check_game_buildid",
    "check_game_installation",
    "check_game_save_count",
    "check_game_saves_folder",
    "check_icons",
    "check_installation_type",
    "check_kraken_decode",
    "check_kraken_encode",
    "check_last_media_error",
    "check_official_names",
    "check_output_device",
    "check_pkexec",
    "check_s2_schema",
    "check_sound_cache",
    "check_steam_api_library",
    "check_steam_running",
    "check_update_manifest",
    "check_xdg_open",
    "check_xray_lzo",
    "cleanup_logs",
    "clear_crash_report",
    "collect_log_bundle",
    "configure_logging",
    "export_log_bundle",
    "format_report",
    "install_crash_handler",
    "log_directory",
    "pending_crash_report",
    "record_media_error",
    "record_output_device",
    "run_checks",
    "submit_logs",
]
