"""Bounded local application logs and opt-in diagnostics submission."""

from __future__ import annotations

import gzip
import json
import logging
import logging.handlers
import re
import time
import urllib.request
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit

from .platforms import user_data_dir

LOGGER_NAME = "stalker2_save_editor"
LOG_FILENAME = "save-editor.log"
MAX_LOG_BYTES = 1 * 1024 * 1024
LOG_BACKUP_COUNT = 3
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


class DiagnosticsError(RuntimeError):
    """A user-safe error from local collection or the diagnostics endpoint."""


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


def collect_log_bundle(directory: Path | None = None, *, max_bytes: int = MAX_BUNDLE_BYTES) -> bytes:
    """Collect recent text logs into a bounded, redacted gzip payload."""

    if max_bytes <= 0:
        raise ValueError("diagnostic bundle bound must be positive")
    source_dir = Path(directory).expanduser() if directory is not None else log_directory()
    remaining = max_bytes
    blocks: list[str] = []
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
) -> str:
    """Submit a bounded diagnostic bundle and return its opaque report id."""

    if directory is not None and log_dir is not None:
        raise ValueError("use directory or log_dir, not both")
    source_dir = directory if directory is not None else log_dir
    parsed = urlsplit(endpoint)
    if parsed.scheme != "https" or not parsed.hostname:
        raise DiagnosticsError("Сервер логов должен использовать HTTPS")
    payload = collect_log_bundle(source_dir)
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
    "DiagnosticsError",
    "cleanup_logs",
    "collect_log_bundle",
    "configure_logging",
    "export_log_bundle",
    "log_directory",
    "submit_logs",
]
