"""Bounded local application logs and opt-in diagnostics submission."""

from __future__ import annotations

import gzip
import json
import logging
import logging.handlers
import re
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
MAX_BUNDLE_BYTES = 1_500_000
MAX_UPLOAD_BYTES = 2 * 1024 * 1024
DEFAULT_TIMEOUT = 15.0
DEFAULT_ENDPOINT = "https://save-editor-downloads.save-editor.workers.dev/diagnostics"

_SECRET_RE = re.compile(
    r"(?i)\b(token|password|passwd|authorization|cookie|secret)\s*[:=]\s*([^\s,;]+)"
)
_WINDOWS_HOME_RE = re.compile(r"(?i)(?:[a-z]:)?[\\/]Users[\\/][^\\/\s]+")
_POSIX_HOME_RE = re.compile(r"/home/[^/\s]+|/Users/[^/\s]+")


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
) -> Path:
    """Install one idempotent rotating file handler and return its path."""

    if max_bytes <= 0 or backup_count < 0:
        raise ValueError("diagnostic log bounds must be non-negative and non-zero")
    target_dir = Path(directory).expanduser() if directory is not None else log_directory()
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / LOG_FILENAME
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    for handler in tuple(logger.handlers):
        if not getattr(handler, "_save_editor_diagnostics", False):
            continue
        if Path(getattr(handler, "baseFilename", "")).resolve() == target.resolve():
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
    return _SECRET_RE.sub(lambda match: f"{match.group(1)}=<redacted>", text)


def _log_paths(directory: Path) -> list[Path]:
    return sorted(
        (path for path in directory.glob(f"{LOG_FILENAME}*") if path.is_file()),
        key=lambda path: path.stat().st_mtime_ns,
        reverse=True,
    )


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
            text = _redact(path.read_text(encoding="utf-8", errors="replace"))
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
    "collect_log_bundle",
    "configure_logging",
    "log_directory",
    "submit_logs",
]
