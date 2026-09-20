from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from editor.cloud_capabilities import CloudWriteCapability

# Re-exported for ui/cloud_view.py, which imports the helper lookup
# from this module.  Keep it in __all__: an "unused import" cleanup that drops
# it breaks the Cloud tab at import time.
from editor.platforms import discover_helper, resolve_helper_command

__all__ = [
    "APP_ID",
    "LIVE_WRITE_OVERRIDE_ENV",
    "SAVE_PREFIX",
    "CloudFile",
    "CloudFileFilter",
    "SteamCloudError",
    "SteamWorker",
    "default_cloud_file_filter",
    "discover_helper",
]

LIVE_WRITE_OVERRIDE_ENV = "STALKER2_ALLOW_LIVE_CLOUD"


def _refuse_automated_live_session(app_id: int, action: str) -> None:
    """Block a real S.T.A.L.K.E.R. 2 cloud session started by a test run.

    Project policy forbids cloud uploads from automated tests, but the only
    thing enforcing it was a sentence in the README, and a test that reaches a
    real SteamWorker overwrites a real save slot.  The guard keys on the game's
    own app id, so lifecycle tests that drive the fake helper with a throwaway
    id keep working and only the live game's cloud is protected.
    """

    if app_id != APP_ID or "PYTEST_CURRENT_TEST" not in os.environ:
        return
    if os.environ.get(LIVE_WRITE_OVERRIDE_ENV) == "1":
        return
    raise SteamCloudError(
        f"Отказ: {action} для app_id={APP_ID} из автоматического теста. "
        "Используй fake transport; для осознанного ручного прогона установи "
        f"{LIVE_WRITE_OVERRIDE_ENV}=1."
    )


APP_ID = 1643320
SAVE_PREFIX = "Stalker2/Saved/STEAM/SaveGames/Data/"
# A rebuilt local save is currently about 27 MB. The JSON Vec<u8> envelope is
# larger, so allow a bounded margin while still rejecting runaway responses.
MAX_RESPONSE_BYTES = 256 * 1024 * 1024
MAX_FILE_BYTES = 64 * 1024 * 1024

CloudFileFilter = Callable[[str], bool]


def default_cloud_file_filter(name: str) -> bool:
    """Keep backwards-compatible S.T.A.L.K.E.R. 2 filtering by default."""

    normalized = str(name or "").replace("\\", "/")
    return normalized.startswith(SAVE_PREFIX) and normalized.casefold().endswith(".sav")


def _helper_environment(library_dir: Path) -> dict[str, str]:
    """Give extracted POSIX helpers access to their adjacent Steamworks ABI."""

    environment = os.environ.copy()
    if os.name != "nt":
        current = environment.get("LD_LIBRARY_PATH")
        library = str(library_dir)
        environment["LD_LIBRARY_PATH"] = (
            f"{library}{os.pathsep}{current}" if current else library
        )
    return environment


class SteamCloudError(RuntimeError):
    pass


@dataclass
class CloudFile:
    name: str
    size: int
    timestamp: int
    is_persisted: bool
    exists: bool
    # Steam's web cloud page exposes a short-lived download URL even when the
    # client RemoteStorage API returns no file list.  Native/helper callers do
    # not populate it, so the field stays optional and backwards-compatible.
    download_url: str | None = None
    local_path: Path | None = None


class SteamWorker:
    """JSON-RPC bridge to SteamCloudFileManager's --steam-worker mode.

    This worker is the same Steamworks RemoteStorage backend used by
    SteamCloudFileManager itself.  We deliberately do not automate its GUI.
    """

    def __init__(
        self,
        helper_path: str | Path,
        log: Callable[[str], None] | None = None,
        file_filter: CloudFileFilter | None = None,
    ):
        self.helper_path = str(Path(helper_path).expanduser())
        self.log = log or (lambda _s: None)
        self.proc: subprocess.Popen[str] | None = None
        self._lock = threading.Lock()
        self._responses: queue.Queue[object] | None = None
        self._reader_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self._stderr_tail: deque[str] = deque(maxlen=32)
        # The app id of the last successful Connect, used by the live-session
        # guard so a WriteFile is judged by the cloud it targets.
        self.app_id: int | None = None
        self._file_filter: CloudFileFilter = file_filter or default_cloud_file_filter

    def set_file_filter(self, file_filter: CloudFileFilter | None) -> None:
        """Select the release-aware save allow-list without reconnecting."""

        self._file_filter = file_filter or default_cloud_file_filter

    @property
    def write_capability(self) -> CloudWriteCapability:
        return CloudWriteCapability(True, "SteamCloudFileManager writer готов")

    def _reader_loop(
        self, proc: subprocess.Popen[str], responses: queue.Queue[object]
    ) -> None:
        assert proc.stdout
        try:
            while True:
                line = proc.stdout.readline()
                if not line:
                    responses.put(SteamCloudError("Steam worker завершился/закрыл stdout"))
                    return
                if len(line.encode("utf-8", errors="replace")) > MAX_RESPONSE_BYTES:
                    responses.put(
                        SteamCloudError(
                            f"Ответ Steam worker слишком большой (>{MAX_RESPONSE_BYTES} bytes)"
                        )
                    )
                    return
                responses.put(line)
        except BaseException as exc:
            responses.put(SteamCloudError(f"Reader Steam worker завершился: {exc}"))

    def _stderr_loop(self, proc: subprocess.Popen[str]) -> None:
        if not proc.stderr:
            return
        try:
            while True:
                chunk = proc.stderr.read(4096)
                if not chunk:
                    return
                self._stderr_tail.append(chunk[-4096:])
        except Exception:
            return

    def _spawn_unlocked(self) -> subprocess.Popen[str]:
        p = Path(self.helper_path)
        if not p.exists():
            raise SteamCloudError(f"SteamCloudFileManager не найден: {p}")
        # An AppImage is transparently extracted (no FUSE) and its inner ELF is
        # run instead; a plain binary runs in place.
        try:
            executable, library_dir = resolve_helper_command(p)
        except (OSError, RuntimeError) as exc:
            raise SteamCloudError(f"Не удалось подготовить helper: {exc}") from exc
        if os.name != "nt" and executable.suffix.lower() != ".exe":
            try:
                mode = executable.stat().st_mode
                executable.chmod(mode | 0o111)
            except OSError:
                pass
        try:
            proc = subprocess.Popen(
                [str(executable), "--steam-worker"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                text=True,
                encoding="utf-8",
                bufsize=1,
                env=_helper_environment(library_dir),
            )
        except Exception as exc:
            raise SteamCloudError(f"Не удалось запустить helper: {exc}") from exc

        responses: queue.Queue[object] = queue.Queue()
        self.proc = proc
        self._responses = responses
        self._reader_thread = threading.Thread(
            target=self._reader_loop, args=(proc, responses), name="steam-worker-reader", daemon=True
        )
        self._stderr_thread = threading.Thread(
            target=self._stderr_loop, args=(proc,), name="steam-worker-stderr", daemon=True
        )
        self._reader_thread.start()
        self._stderr_thread.start()
        return proc

    def _stderr_context(self) -> str:
        return "".join(self._stderr_tail)[-4000:]

    def _invalidate_unlocked(self) -> None:
        proc = self.proc
        self.proc = None
        self._responses = None
        reader, stderr = self._reader_thread, self._stderr_thread
        self._reader_thread = None
        self._stderr_thread = None
        if proc is not None:
            for stream in (proc.stdin, proc.stdout, proc.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except Exception:
                        pass
            try:
                if proc.poll() is None:
                    proc.terminate()
                    proc.wait(timeout=1)
            except Exception:
                try:
                    proc.kill()
                    proc.wait(timeout=1)
                except Exception:
                    pass
        current = threading.current_thread()
        for thread in (reader, stderr):
            if thread is not None and thread is not current:
                thread.join(timeout=1)

    def _decode_response(self, line: str) -> dict[str, Any]:
        try:
            resp = json.loads(line)
        except Exception as exc:
            self._invalidate_unlocked()
            raise SteamCloudError(f"Steam worker вернул не JSON: {line[:500]!r}") from exc
        if not isinstance(resp, dict):
            self._invalidate_unlocked()
            raise SteamCloudError("Steam worker вернул JSON не-объект")
        if resp.get("type") == "Error":
            raise SteamCloudError(resp.get("message", "Unknown worker error"))
        return resp

    def _wait_response_unlocked(self, timeout: float) -> dict[str, Any]:
        responses = self._responses
        if responses is None:
            raise SteamCloudError("Steam worker session отсутствует")
        try:
            item = responses.get(timeout=timeout)
        except queue.Empty as exc:
            self._invalidate_unlocked()
            raise SteamCloudError("Таймаут ответа Steam worker") from exc
        if isinstance(item, BaseException):
            message = str(item)
            self._invalidate_unlocked()
            stderr = self._stderr_context()
            if stderr:
                message += f" stderr={stderr[-1000:]}"
            raise SteamCloudError(message)
        if not isinstance(item, str):
            self._invalidate_unlocked()
            raise SteamCloudError("Steam worker вернул неизвестный тип ответа")
        return self._decode_response(item)

    def _ensure_unlocked(self) -> subprocess.Popen[str]:
        if self.proc is not None and self.proc.poll() is None:
            return self.proc
        if self.proc is not None:
            self._invalidate_unlocked()
        self._spawn_unlocked()
        try:
            response = self._request_unlocked({"type": "Ping"}, timeout=10)
            if response.get("type") != "Pong":
                raise SteamCloudError(f"Helper не ответил Pong: {response}")
        except Exception:
            self._invalidate_unlocked()
            raise
        assert self.proc is not None
        return self.proc

    def start(self) -> None:
        with self._lock:
            self._ensure_unlocked()

    def _request_unlocked(self, obj: dict[str, Any], timeout: float) -> dict[str, Any]:
        proc = self._ensure_unlocked() if self.proc is None else self.proc
        assert proc.stdin
        try:
            proc.stdin.write(json.dumps(obj, separators=(",", ":")) + "\n")
            proc.stdin.flush()
        except Exception as exc:
            self._invalidate_unlocked()
            raise SteamCloudError(f"Ошибка записи в Steam worker: {exc}") from exc
        return self._wait_response_unlocked(timeout)

    def request(self, obj: dict[str, Any], timeout: float = 45) -> dict[str, Any]:
        with self._lock:
            self._ensure_unlocked()
            return self._request_unlocked(obj, timeout)

    def connect(self, app_id: int = APP_ID) -> None:
        _refuse_automated_live_session(app_id, "Connect")
        resp = self.request({"type": "Connect", "app_id": app_id}, timeout=30)
        if resp.get("type") != "Connected":
            raise SteamCloudError(f"Неожиданный Connect response: {resp}")
        self.app_id = app_id

    def list_files(self) -> list[CloudFile]:
        resp = self.request({"type": "GetFiles"}, timeout=45)
        if resp.get("type") != "Files":
            raise SteamCloudError(f"Неожиданный GetFiles response: {resp}")
        out: list[CloudFile] = []
        for f in resp.get("files", []):
            name = str(f.get("name", ""))
            if not self._file_filter(name):
                continue
            out.append(
                CloudFile(
                    name=name,
                    size=int(f.get("size", 0)),
                    timestamp=int(f.get("timestamp", 0)),
                    is_persisted=bool(f.get("is_persisted", False)),
                    exists=bool(f.get("exists", True)),
                )
            )
        out.sort(key=lambda x: x.timestamp, reverse=True)
        return out

    def read_file(self, filename: str) -> bytes:
        resp = self.request({"type": "ReadFile", "filename": filename}, timeout=90)
        if resp.get("type") != "FileData":
            raise SteamCloudError(f"Неожиданный ReadFile response: {resp.get('type')}")
        data = resp.get("data")
        if not isinstance(data, list):
            raise SteamCloudError("ReadFile: поле data отсутствует")
        if len(data) > MAX_FILE_BYTES:
            with self._lock:
                self._invalidate_unlocked()
            raise SteamCloudError(
                f"ReadFile: файл слишком большой (>{MAX_FILE_BYTES} bytes)"
            )
        try:
            return bytes(data)
        except Exception as exc:
            raise SteamCloudError("ReadFile: некорректный массив байт") from exc

    def write_file(self, filename: str, data: bytes) -> None:
        _refuse_automated_live_session(self.app_id or 0, "WriteFile")
        # Worker IPC expects JSON Vec<u8>.  Never do list(data) for a 27 MB
        # rebuilt save: a Python list of 27 million ints can eat close to a GB.
        # Stream one JSON line directly into the child's stdin in small chunks.
        # The Rust side still receives the same protocol, but our memory stays sane.
        with self._lock:
            self._ensure_unlocked()
            proc = self.proc
            assert proc is not None
            assert proc.stdin
            try:
                prefix = '{"type":"WriteFile","filename":' + json.dumps(filename) + ',"data":['
                proc.stdin.write(prefix)
                first = True
                chunk_size = 64 * 1024
                for off in range(0, len(data), chunk_size):
                    chunk = data[off : off + chunk_size]
                    text = ",".join(str(b) for b in chunk)
                    if not first:
                        proc.stdin.write(",")
                    proc.stdin.write(text)
                    first = False
                proc.stdin.write("]}\n")
                proc.stdin.flush()
            except Exception as exc:
                self._invalidate_unlocked()
                raise SteamCloudError(f"Ошибка streaming WriteFile в Steam worker: {exc}") from exc

            resp = self._wait_response_unlocked(300)
            if resp.get("type") == "Error":
                raise SteamCloudError(resp.get("message", "Unknown worker error"))
            if resp.get("type") != "Ok":
                raise SteamCloudError(f"Неожиданный WriteFile response: {resp}")

    def sync(self) -> None:
        resp = self.request({"type": "SyncCloudFiles"}, timeout=30)
        if resp.get("type") != "Ok":
            raise SteamCloudError(f"Неожиданный Sync response: {resp}")

    def wait_persisted(self, filename: str, expected_size: int, timeout: int = 120) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                self.sync()
            except Exception:
                pass
            for f in self.list_files():
                if f.name == filename and f.size == expected_size and f.is_persisted:
                    return True
            time.sleep(2)
        return False

    def close(self) -> None:
        with self._lock:
            if not self.proc:
                return
            try:
                self._request_unlocked({"type": "Exit"}, timeout=2)
            except Exception:
                pass
            self._invalidate_unlocked()
