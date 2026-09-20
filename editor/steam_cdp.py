"""Read-only Steam Cloud discovery through Steam's local CEF debug page.

Steam's client RemoteStorage API can be connected successfully while returning
an empty file list for an account that still has files in Steam's web cloud
view.  The SteamCloudFileManager project handles that case with the same local
Steam session: its CEF page exposes the file rows and short-lived download
URLs.  This module keeps that path optional and local-only.  Writes continue
through the existing authenticated Steamworks transport.
"""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import socket
import struct
import subprocess
import time
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from steam_cloud import (
    APP_ID,
    MAX_FILE_BYTES,
    CloudFile,
    CloudFileFilter,
    SteamCloudError,
    default_cloud_file_filter,
)

from .cloud_capabilities import CloudWriteCapability, CloudWriteNotAttemptedError
from .platforms import _parse_vdf, _read_text, steam_roots


class SteamCdpError(SteamCloudError):
    """Steam's local CEF debugging page is unavailable or returned bad data."""


def _as_int(value: object, default: int = 0) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


def _parse_size(value: object) -> int:
    text = str(value or "").strip().replace(",", ".")
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*([kmgt]?i?b)?", text, re.I)
    if match is None:
        return 0
    number = float(match.group(1))
    unit = (match.group(2) or "b").casefold()
    multipliers = {
        "b": 1,
        "kb": 1_000,
        "mb": 1_000_000,
        "gb": 1_000_000_000,
        "tb": 1_000_000_000_000,
        "kib": 1024,
        "mib": 1024**2,
        "gib": 1024**3,
        "tib": 1024**4,
    }
    return int(number * multipliers.get(unit, 1))


def _parse_page_time(value: object) -> int:
    text = str(value or "").strip()
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%m/%d/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
    ):
        try:
            return int(datetime.strptime(text, fmt).timestamp())
        except ValueError:
            continue
    return int(time.time())


def _full_cloud_name(folder: object, filename: object) -> str:
    directory = str(folder or "").strip().strip("/")
    name = str(filename or "").strip().lstrip("/")
    if "/" in name or "\\" in name:
        return name
    return f"{directory}/{name}" if directory else name


def cloud_files_from_rows(
    rows: Sequence[Mapping[str, object]],
    *,
    cached: Mapping[str, CloudFile] | None = None,
    file_filter: CloudFileFilter | None = None,
) -> list[CloudFile]:
    """Convert Steam web-table rows into the editor's cloud-file model."""

    cached = cached or {}
    file_filter = file_filter or default_cloud_file_filter
    result: list[CloudFile] = []
    seen: set[str] = set()
    for row in rows:
        name = _full_cloud_name(row.get("folder"), row.get("name")).replace("\\", "/")
        if not file_filter(name):
            continue
        if name in seen:
            continue
        seen.add(name)
        cached_file = cached.get(name)
        url = str(row.get("url") or "").strip() or None
        result.append(
            CloudFile(
                name=name,
                size=_parse_size(row.get("size_str")) or (cached_file.size if cached_file else 0),
                timestamp=(
                    cached_file.timestamp
                    if cached_file is not None
                    else _parse_page_time(row.get("time_str"))
                ),
                is_persisted=True,
                exists=cached_file.exists if cached_file is not None else True,
                download_url=url,
                local_path=cached_file.local_path if cached_file is not None else None,
            )
        )
    result.sort(key=lambda item: item.timestamp, reverse=True)
    return result


def _cache_file_paths(
    app_id: int,
    *,
    system: str | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> tuple[Path, ...]:
    paths: list[Path] = []
    for root in steam_roots(system=system, environ=environ, home=home):
        userdata = root / "userdata"
        try:
            users = tuple(userdata.iterdir())
        except OSError:
            continue
        for user in users:
            if not user.is_dir() or not user.name.isdigit():
                continue
            candidate = user / str(app_id) / "remotecache.vdf"
            if candidate.is_file():
                paths.append(candidate)
    return tuple(paths)


def discover_cached_cloud_files(
    app_id: int = APP_ID,
    *,
    system: str | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
    file_filter: CloudFileFilter | None = None,
) -> tuple[CloudFile, ...]:
    """Read Steam's local metadata cache without starting another process."""

    file_filter = file_filter or default_cloud_file_filter
    result: dict[str, CloudFile] = {}
    for cache_path in _cache_file_paths(
        app_id,
        system=system,
        environ=environ,
        home=home,
    ):
        text = _read_text(cache_path)
        if text is None:
            continue
        try:
            parsed = _parse_vdf(text)
        except ValueError:
            continue
        app_value = parsed.get(str(app_id))
        if not isinstance(app_value, dict):
            continue
        remote_root = cache_path.parent / "remote"
        for raw_name, raw_entry in app_value.items():
            name = str(raw_name).replace("\\", "/")
            if not file_filter(name):
                continue
            entry = raw_entry if isinstance(raw_entry, dict) else {}
            relative = Path(*name.split("/"))
            local_path = remote_root / relative
            try:
                local_exists = local_path.is_file()
            except OSError:
                local_exists = False
            candidate = CloudFile(
                name=name,
                size=max(0, _as_int(entry.get("size"))),
                timestamp=max(
                    0,
                    _as_int(
                        entry.get("remotetime")
                        or entry.get("time")
                        or entry.get("localtime")
                    ),
                ),
                is_persisted=_as_int(entry.get("syncstate")) == 2,
                exists=local_exists,
                local_path=local_path if local_exists else None,
            )
            previous = result.get(name)
            if previous is None or candidate.timestamp >= previous.timestamp:
                result[name] = candidate
    return tuple(sorted(result.values(), key=lambda item: item.timestamp, reverse=True))


def _read_exact(stream: socket.socket, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = stream.recv(remaining)
        if not chunk:
            raise SteamCdpError("Steam CEF debug socket closed")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


class _WebSocket:
    """Minimal local CDP WebSocket client using only the Python stdlib."""

    def __init__(self, url: str, *, timeout: float = 15.0) -> None:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme not in {"ws", "wss"} or parsed.hostname not in {
            "127.0.0.1",
            "localhost",
            "::1",
        }:
            raise SteamCdpError("Steam CEF returned a non-local websocket target")
        port = parsed.port or (443 if parsed.scheme == "wss" else 80)
        raw = socket.create_connection((parsed.hostname, port), timeout=timeout)
        self.socket = raw
        self.socket.settimeout(timeout)
        if parsed.scheme == "wss":
            import ssl

            self.socket = ssl.create_default_context().wrap_socket(
                raw,
                server_hostname=parsed.hostname,
            )
        self._message_id = 0
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        path = parsed.path or "/"
        if parsed.query:
            path += f"?{parsed.query}"
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {parsed.hostname}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        ).encode("ascii")
        self.socket.sendall(request)
        header = bytearray()
        while b"\r\n\r\n" not in header:
            header.extend(self.socket.recv(4096))
            if len(header) > 64 * 1024:
                raise SteamCdpError("Steam CEF websocket handshake is too large")
        first_line = bytes(header).split(b"\r\n", 1)[0]
        if b" 101 " not in first_line:
            raise SteamCdpError(f"Steam CEF websocket handshake failed: {first_line.decode(errors='replace')}")

    def _send_frame(self, opcode: int, payload: bytes) -> None:
        length = len(payload)
        if length < 126:
            header = bytes((0x80 | opcode, 0x80 | length))
        elif length < 65_536:
            header = bytes((0x80 | opcode, 0x80 | 126)) + struct.pack(">H", length)
        else:
            header = bytes((0x80 | opcode, 0x80 | 127)) + struct.pack(">Q", length)
        mask = os.urandom(4)
        masked = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
        self.socket.sendall(header + mask + masked)

    def _receive_frame(self) -> tuple[int, bytes]:
        first, second = _read_exact(self.socket, 2)
        opcode = first & 0x0F
        length = second & 0x7F
        if length == 126:
            length = struct.unpack(">H", _read_exact(self.socket, 2))[0]
        elif length == 127:
            length = struct.unpack(">Q", _read_exact(self.socket, 8))[0]
        if length > MAX_FILE_BYTES * 4:
            raise SteamCdpError("Steam CEF websocket response is too large")
        payload = _read_exact(self.socket, length)
        if second & 0x80:
            mask = payload[:4]
            payload = bytes(
                value ^ mask[index % 4]
                for index, value in enumerate(payload[4:])
            )
        return opcode, payload

    def command(self, method: str, params: Mapping[str, object] | None = None) -> Any:
        self._message_id += 1
        request_id = self._message_id
        self._send_frame(
            0x1,
            json.dumps(
                {"id": request_id, "method": method, "params": dict(params or {})},
                separators=(",", ":"),
            ).encode("utf-8"),
        )
        fragments: list[bytes] = []
        while True:
            opcode, payload = self._receive_frame()
            if opcode == 0x9:
                self._send_frame(0xA, payload)
                continue
            if opcode == 0x8:
                raise SteamCdpError("Steam CEF websocket closed")
            if opcode == 0x0 or opcode == 0x1:
                fragments.append(payload)
            if opcode not in (0x0, 0x1):
                continue
            try:
                response = json.loads(b"".join(fragments).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if response.get("id") != request_id:
                fragments.clear()
                continue
            if response.get("error") is not None:
                raise SteamCdpError(f"CDP {method} failed: {response['error']}")
            return response.get("result")

    def close(self) -> None:
        try:
            self._send_frame(0x8, b"")
        except OSError:
            pass
        try:
            self.socket.close()
        except OSError:
            pass


def _debug_targets(endpoint: str, timeout: float) -> list[dict[str, object]]:
    try:
        with urllib.request.urlopen(endpoint, timeout=timeout) as response:
            payload = json.loads(response.read(2 * 1024 * 1024).decode("utf-8"))
    except Exception as exc:
        raise SteamCdpError(
            "Steam Cloud web channel is unavailable. Close Steam and relaunch it "
            "with -cef-enable-debugging, then retry."
        ) from exc
    if not isinstance(payload, list):
        raise SteamCdpError("Steam CEF returned an invalid target list")
    return [item for item in payload if isinstance(item, dict)]


def _steam_executable() -> str | None:
    found = shutil.which("steam")
    if found:
        return found
    for root in steam_roots():
        for candidate in (
            root / "steam",
            root / "ubuntu12_32" / "steam",
            root / "steam.exe",
        ):
            if candidate.is_file():
                return str(candidate)
    return None


def _steam_process_running() -> bool:
    if os.name == "nt":
        try:
            output = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq steam.exe"],
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError:
            return False
        return "steam.exe" in output.stdout.casefold()
    try:
        output = subprocess.run(
            ["pgrep", "-x", "steam"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return False
    return output.returncode == 0


def restart_steam_with_debugging(*, timeout: float = 45.0) -> None:
    """Restart Steam with CEF debugging when the user explicitly requests it."""

    try:
        _debug_targets("http://127.0.0.1:8080/json", 0.5)
        return
    except SteamCdpError:
        pass
    executable = _steam_executable()
    if executable is None:
        raise SteamCdpError("Не найден исполняемый файл Steam")
    try:
        subprocess.run(
            [executable, "-shutdown"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SteamCdpError(f"Не удалось закрыть Steam перед перезапуском: {exc}") from exc
    shutdown_deadline = time.monotonic() + 20
    while _steam_process_running() and time.monotonic() < shutdown_deadline:
        time.sleep(0.25)
    try:
        subprocess.Popen(
            [executable, "-cef-enable-debugging"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=os.name != "nt",
        )
    except OSError as exc:
        raise SteamCdpError(f"Не удалось запустить Steam с CEF debugging: {exc}") from exc
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            _debug_targets("http://127.0.0.1:8080/json", 0.5)
            return
        except SteamCdpError:
            time.sleep(0.5)
    raise SteamCdpError(
        "Steam запущен, но CEF debug-порт 8080 не появился; "
        "проверь, что Steam полностью завершился перед повтором"
    )


class SteamCdpClient:
    """Navigate Steam's logged-in cloud page and evaluate small JS snippets."""

    def __init__(self, websocket: _WebSocket, *, timeout: float = 15.0) -> None:
        self.websocket = websocket
        self.timeout = timeout

    @classmethod
    def connect(cls, *, timeout: float = 15.0) -> SteamCdpClient:
        targets = _debug_targets("http://127.0.0.1:8080/json", timeout)
        selected: dict[str, object] | None = None
        fallback: dict[str, object] | None = None
        for target in targets:
            if target.get("type") != "page" or not target.get("webSocketDebuggerUrl"):
                continue
            url = str(target.get("url") or "")
            if "remotestorageapp" in url:
                selected = target
                break
            if selected is None and "store.steampowered.com" in url:
                selected = target
            if fallback is None and not url.startswith("about:"):
                fallback = target
        if selected is None:
            selected = fallback
        if selected is None:
            selected = next(
                (
                    target
                    for target in targets
                    if target.get("type") == "page"
                    and target.get("webSocketDebuggerUrl")
                ),
                None,
            )
        if selected is None:
            raise SteamCdpError(
                "Steam CEF debug page is running, but no page target is available"
            )
        return cls(_WebSocket(str(selected["webSocketDebuggerUrl"]), timeout=timeout), timeout=timeout)

    def evaluate(self, expression: str) -> Any:
        result = self.websocket.command(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": True,
            },
        )
        if not isinstance(result, dict):
            return None
        if result.get("exceptionDetails") is not None:
            raise SteamCdpError(f"Steam Cloud page JS failed: {result['exceptionDetails']}")
        return result.get("result", {}).get("value")

    def navigate(self, url: str) -> None:
        self.websocket.command("Page.navigate", {"url": url})
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            try:
                if self.evaluate("document.readyState") == "complete":
                    return
            except SteamCdpError:
                pass
            time.sleep(0.25)

    def wait_for_table(self) -> None:
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            try:
                if self.evaluate("document.querySelector('.accountTable') !== null") is True:
                    return
            except SteamCdpError:
                pass
            time.sleep(0.25)

    def close(self) -> None:
        self.websocket.close()


class SteamCdpWorker:
    """Cloud read transport backed by Steam's logged-in web page."""

    def __init__(
        self,
        *,
        client_factory: type[SteamCdpClient] = SteamCdpClient,
        timeout: float = 15.0,
        file_filter: CloudFileFilter | None = None,
    ) -> None:
        self.client_factory = client_factory
        self.timeout = timeout
        self.app_id: int | None = None
        self.client: SteamCdpClient | None = None
        self._urls: dict[str, str] = {}
        self._closed = False
        self._file_filter: CloudFileFilter = file_filter or default_cloud_file_filter

    def set_file_filter(self, file_filter: CloudFileFilter | None) -> None:
        """Change the release allow-list without rebuilding the CEF session."""

        self._file_filter = file_filter or default_cloud_file_filter

    def start(self) -> None:
        if self._closed:
            raise SteamCdpError("Steam CEF cloud worker уже закрыт")

    def connect(self, app_id: int = APP_ID) -> None:
        if self._closed:
            raise SteamCdpError("Steam CEF cloud worker уже закрыт")
        if int(app_id) <= 0:
            raise SteamCdpError(f"Некорректный Steam app_id: {app_id}")
        self.app_id = app_id
        self.client = self.client_factory.connect(timeout=self.timeout)

    def list_files(self) -> list[CloudFile]:
        if self.client is None:
            raise SteamCdpError("Steam web cloud не подключён")
        assert self.app_id is not None
        cached = {
            item.name: item
            for item in discover_cached_cloud_files(
                self.app_id,
                file_filter=self._file_filter,
            )
        }
        all_rows: list[Mapping[str, object]] = []
        for offset in range(0, 1000, 50):
            url = (
                "https://store.steampowered.com/account/remotestorageapp/"
                f"?appid={self.app_id}"
                + (f"&index={offset}" if offset else "")
            )
            self.client.navigate(url)
            self.client.wait_for_table()
            value = self.client.evaluate(
                """
                (() => Array.from(document.querySelectorAll('.accountTable tr')).map(tr => {
                    const cells = tr.querySelectorAll('td');
                    if (cells.length < 4) return null;
                    const link = tr.querySelector(
                      'a[href*="ugc"], a[href*="filedownload"], a[href*="steamusercontent"]'
                    );
                    return {
                      folder: cells[0].textContent.trim(),
                      name: cells[1].textContent.trim(),
                      size_str: cells[2].textContent.trim(),
                      time_str: cells[3].textContent.trim(),
                      url: link ? link.href : ''
                    };
                }).filter(row => row && row.name))()
                """
            )
            rows = value if isinstance(value, list) else []
            valid_rows = [row for row in rows if isinstance(row, dict)]
            all_rows.extend(valid_rows)
            if len(valid_rows) < 50:
                break
        files = cloud_files_from_rows(
            all_rows,
            cached=cached,
            file_filter=self._file_filter,
        )
        self._urls = {
            file.name: file.download_url
            for file in files
            if file.download_url
        }
        return files

    def read_file(self, filename: str) -> bytes:
        last_error: Exception | None = None
        for attempt in range(2):
            url = self._urls.get(filename)
            if not url:
                raise SteamCdpError(
                    f"Steam web cloud не дал download URL для {filename}; обнови список"
                )
            parsed = urllib.parse.urlsplit(url)
            host = (parsed.hostname or "").casefold()
            if parsed.scheme != "https" or not (
                host == "store.steampowered.com"
                or host.endswith(".steamusercontent.com")
                or host.endswith(".akamaihd.net")
            ):
                raise SteamCdpError("Steam Cloud download URL не прошёл проверку домена")
            try:
                with urllib.request.urlopen(url, timeout=self.timeout) as response:
                    data = response.read(MAX_FILE_BYTES + 1)
            except Exception as exc:
                last_error = exc
                if attempt == 0:
                    try:
                        # Steam's web links expire. Re-listing obtains a new
                        # signed URL before the transaction attempts a fresh
                        # source read or read-back.
                        self.list_files()
                    except Exception as refresh_exc:
                        last_error = refresh_exc
                        break
                    continue
                break
            if len(data) > MAX_FILE_BYTES:
                raise SteamCdpError(f"Steam Cloud файл слишком большой (>{MAX_FILE_BYTES} bytes)")
            return data
        raise SteamCdpError(f"Не удалось скачать Steam Cloud файл: {last_error}") from last_error

    @property
    def write_capability(self) -> CloudWriteCapability:
        return CloudWriteCapability(
            False,
            "Steam web cloud read-only; запись требует Steam RemoteStorage",
        )

    def write_file(self, _filename: str, _data: bytes) -> None:
        raise CloudWriteNotAttemptedError(self.write_capability.reason)

    def sync(self) -> None:
        return None

    def wait_persisted(self, filename: str, expected_size: int, timeout: int = 120) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for item in self.list_files():
                if item.name == filename and item.size == expected_size and item.is_persisted:
                    return True
            time.sleep(min(2.0, max(0.0, deadline - time.monotonic())))
        return False

    def close(self) -> None:
        self._closed = True
        if self.client is not None:
            self.client.close()
            self.client = None


__all__ = [
    "SteamCdpClient",
    "SteamCdpError",
    "SteamCdpWorker",
    "cloud_files_from_rows",
    "discover_cached_cloud_files",
    "restart_steam_with_debugging",
]
