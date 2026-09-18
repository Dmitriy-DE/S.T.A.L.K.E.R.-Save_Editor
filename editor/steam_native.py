"""Steam Cloud workers over Valve's ``libsteam_api``.

``SteamNativeWorker`` is the small ctypes implementation executed by the
short-lived child mode. The UI uses ``SteamNativeSubprocessWorker`` so a native
call that stops responding can be killed without freezing the editor. This
replaces the third-party ``SteamCloudFileManager`` helper as the primary cloud
backend: no FUSE or helper process is needed when Valve's library is available;
the helper remains a bounded fallback for an initial list failure. It still
depends on Valve's proprietary ``libsteam_api`` — the only door into Steam
Cloud — but that library ships with every Steamworks game and with the helper
payload.

Both public workers mirror :class:`steam_cloud.SteamWorker` (``start``,
``connect``, ``close``, ``list_files``, ``read_file``, ``write_file``,
``sync``, ``wait_persisted``) so they are drop-ins for the Cloud tab's
``worker_factory``. The child mode reports missing libraries, failed init, and
timeouts as data; the parent can then show an error or select the helper.

NOTE: the live download/upload round-trip cannot be verified without an
installed game and a running Steam session; it is exercised only against a
ctypes fake.  Treat live behaviour as user-verified.
"""

from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from steam_cloud import (
    APP_ID,
    MAX_FILE_BYTES,
    SAVE_PREFIX,
    CloudFile,
    SteamCloudError,
    SteamWorker,
    _refuse_automated_live_session,
)

from .platforms import locate_libsteam_api

# Known ISteamRemoteStorage flat accessor versions, newest first.  The exact
# version baked into a given libsteam_api build varies by SDK release, so we
# probe for the first symbol that exists instead of hard-coding one.
_REMOTE_STORAGE_ACCESSORS = tuple(
    f"SteamAPI_SteamRemoteStorage_v{v:03d}" for v in (20, 19, 18, 17, 16, 15, 14)
)


class SteamNativeUnavailableError(SteamCloudError):
    """Raised when the native backend cannot be used (missing lib / init fail)."""


def _load_library(path: Path) -> ctypes.CDLL:
    try:
        return ctypes.CDLL(str(path))
    except OSError as exc:  # pragma: no cover - platform specific
        raise SteamNativeUnavailableError(f"Не удалось загрузить libsteam_api: {exc}") from exc


def _bind(lib: ctypes.CDLL, name: str, restype: Any, argtypes: Any) -> Any:
    fn = getattr(lib, name)
    fn.restype = restype
    fn.argtypes = argtypes
    return fn


class SteamNativeWorker:
    """Steam Cloud RemoteStorage client running inside this process."""

    def __init__(
        self,
        library_path: str | Path | None = None,
        log: Callable[[str], None] | None = None,
    ) -> None:
        self.log = log or (lambda _s: None)
        self.app_id: int | None = None
        self._initialised = False
        self._remote: Any = None
        resolved = Path(library_path).expanduser() if library_path else locate_libsteam_api()
        if resolved is None or not Path(resolved).is_file():
            raise SteamNativeUnavailableError("libsteam_api не найдена")
        self._library_path = Path(resolved)
        self._lib = _load_library(self._library_path)
        self._bind_symbols()

    def _bind_symbols(self) -> None:
        lib = self._lib
        c = ctypes
        # Init/shutdown/callbacks.  Prefer the flat init that reports an error
        # string; fall back to the plain bool init on older builds.
        if hasattr(lib, "SteamAPI_InitFlat"):
            self._init_flat = _bind(lib, "SteamAPI_InitFlat", c.c_int, [c.c_char_p])
            self._init = None
        else:
            self._init_flat = None
            self._init = _bind(lib, "SteamAPI_Init", c.c_bool, [])
        self._shutdown = _bind(lib, "SteamAPI_Shutdown", None, [])
        self._run_callbacks = _bind(lib, "SteamAPI_RunCallbacks", None, [])
        # RemoteStorage accessor: first symbol that resolves.
        self._accessor: Any = None
        for name in _REMOTE_STORAGE_ACCESSORS:
            if hasattr(lib, name):
                self._accessor = _bind(lib, name, c.c_void_p, [])
                break
        if self._accessor is None:
            raise SteamNativeUnavailableError(
                "libsteam_api не экспортирует ISteamRemoteStorage accessor"
            )
        p = c.c_void_p
        self._rs_get_file_count = _bind(
            lib, "SteamAPI_ISteamRemoteStorage_GetFileCount", c.c_int32, [p]
        )
        self._rs_get_name_size = _bind(
            lib,
            "SteamAPI_ISteamRemoteStorage_GetFileNameAndSize",
            c.c_char_p,
            [p, c.c_int, c.POINTER(c.c_int32)],
        )
        self._rs_get_timestamp = _bind(
            lib, "SteamAPI_ISteamRemoteStorage_GetFileTimestamp", c.c_int64, [p, c.c_char_p]
        )
        self._rs_file_exists = _bind(
            lib, "SteamAPI_ISteamRemoteStorage_FileExists", c.c_bool, [p, c.c_char_p]
        )
        self._rs_file_persisted = _bind(
            lib, "SteamAPI_ISteamRemoteStorage_FilePersisted", c.c_bool, [p, c.c_char_p]
        )
        self._rs_get_size = _bind(
            lib, "SteamAPI_ISteamRemoteStorage_GetFileSize", c.c_int32, [p, c.c_char_p]
        )
        self._rs_file_read = _bind(
            lib,
            "SteamAPI_ISteamRemoteStorage_FileRead",
            c.c_int32,
            [p, c.c_char_p, c.c_void_p, c.c_int32],
        )
        self._rs_file_write = _bind(
            lib,
            "SteamAPI_ISteamRemoteStorage_FileWrite",
            c.c_bool,
            [p, c.c_char_p, c.c_void_p, c.c_int32],
        )

    # ---- lifecycle -----------------------------------------------------
    def start(self) -> None:
        if self._initialised:
            return
        os.environ.setdefault("SteamAppId", str(APP_ID))
        os.environ.setdefault("SteamGameId", str(APP_ID))
        if self._init_flat is not None:
            buf = ctypes.create_string_buffer(1024)
            rc = self._init_flat(buf)
            # k_ESteamAPIInitResult_OK == 0
            if rc != 0:
                raise SteamNativeUnavailableError(
                    f"SteamAPI_InitFlat rc={rc}: {buf.value.decode('utf-8', 'replace')}"
                )
        else:
            assert self._init is not None
            if not self._init():
                raise SteamNativeUnavailableError(
                    "SteamAPI_Init вернул false (клиент Steam не запущен?)"
                )
        self._initialised = True

    def connect(self, app_id: int = APP_ID) -> None:
        _refuse_automated_live_session(app_id, "Connect")
        if not self._initialised:
            self.start()
        if app_id != APP_ID:
            # The native worker binds the app at init via SteamAppId; a
            # different app id would need a re-init with a matching env.
            raise SteamCloudError(
                f"Нативный worker инициализирован для app_id={APP_ID}, запрошен {app_id}"
            )
        remote = self._accessor()
        if not remote:
            raise SteamCloudError("ISteamRemoteStorage недоступен")
        self._remote = remote
        self.app_id = app_id

    def close(self) -> None:
        if self._initialised:
            try:
                self._shutdown()
            except Exception:
                pass
        self._initialised = False
        self._remote = None

    # ---- helpers -------------------------------------------------------
    def _require_remote(self) -> Any:
        if self._remote is None:
            raise SteamCloudError("Steam Cloud не подключён (native)")
        return self._remote

    def _pump(self) -> None:
        try:
            self._run_callbacks()
        except Exception:
            pass

    # ---- RemoteStorage operations -------------------------------------
    def list_files(self) -> list[CloudFile]:
        remote = self._require_remote()
        self._pump()
        count = int(self._rs_get_file_count(remote))
        out: list[CloudFile] = []
        for i in range(count):
            size = ctypes.c_int32(0)
            name_ptr = self._rs_get_name_size(remote, i, ctypes.byref(size))
            if not name_ptr:
                continue
            name = name_ptr.decode("utf-8", "replace")
            if not name.startswith(SAVE_PREFIX) or not name.lower().endswith(".sav"):
                continue
            name_b = name.encode("utf-8")
            out.append(
                CloudFile(
                    name=name,
                    size=int(size.value),
                    timestamp=int(self._rs_get_timestamp(remote, name_b)),
                    is_persisted=bool(self._rs_file_persisted(remote, name_b)),
                    exists=bool(self._rs_file_exists(remote, name_b)),
                )
            )
        out.sort(key=lambda x: x.timestamp, reverse=True)
        return out

    def read_file(self, filename: str) -> bytes:
        remote = self._require_remote()
        self._pump()
        name_b = filename.encode("utf-8")
        if not self._rs_file_exists(remote, name_b):
            raise SteamCloudError(f"ReadFile: файл отсутствует в облаке: {filename}")
        size = int(self._rs_get_size(remote, name_b))
        if size < 0:
            raise SteamCloudError("ReadFile: некорректный размер")
        if size > MAX_FILE_BYTES:
            raise SteamCloudError(f"ReadFile: файл слишком большой (>{MAX_FILE_BYTES} bytes)")
        buf = ctypes.create_string_buffer(size)
        read = int(self._rs_file_read(remote, name_b, buf, size))
        if read != size:
            raise SteamCloudError(f"ReadFile: прочитано {read} из {size} байт")
        return buf.raw[:size]

    def write_file(self, filename: str, data: bytes) -> None:
        _refuse_automated_live_session(self.app_id or 0, "WriteFile")
        remote = self._require_remote()
        if len(data) > MAX_FILE_BYTES:
            raise SteamCloudError(f"WriteFile: файл слишком большой (>{MAX_FILE_BYTES} bytes)")
        name_b = filename.encode("utf-8")
        buf = (ctypes.c_char * len(data)).from_buffer_copy(data)
        ok = bool(self._rs_file_write(remote, name_b, buf, len(data)))
        if not ok:
            raise SteamCloudError(f"WriteFile: Steam отклонил запись {filename}")
        self._pump()

    def sync(self) -> None:
        # RemoteStorage writes are queued to the cloud by the Steam client;
        # pumping callbacks lets that progress.  There is no explicit flat
        # "sync now" call, so this is a no-op beyond the callback pump.
        self._pump()

    def wait_persisted(self, filename: str, expected_size: int, timeout: int = 120) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.sync()
            for f in self.list_files():
                if f.name == filename and f.size == expected_size and f.is_persisted:
                    return True
            time.sleep(2)
        return False


class SteamNativeSubprocessWorker:
    """Killable parent-side transport for the native Steam API.

    ``ctypes`` cannot interrupt a native call that stops responding.  The Qt
    worker therefore must never call :class:`SteamNativeWorker` directly.  Each
    native operation runs in a short-lived child process and is bounded by a
    hard timeout.  A failed initial ``list`` can select the existing helper
    fallback; failures after that selection are returned to the transaction and
    are never retried through another backend.
    """

    def __init__(
        self,
        *,
        helper_path: str | Path | None = None,
        helper_factory: Callable[..., Any] = SteamWorker,
        log: Callable[[str], None] | None = None,
        timeout: float = 15.0,
    ) -> None:
        if timeout <= 0:
            raise ValueError("native cloud timeout must be positive")
        self.helper_path = Path(helper_path).expanduser() if helper_path is not None else None
        self.helper_factory = helper_factory
        self.log = log or (lambda _s: None)
        self.timeout = timeout
        self.app_id: int | None = None
        self._helper: SteamWorker | None = None
        self._closed = False
        self._process_lock = threading.Lock()
        self._active_process: subprocess.Popen[str] | None = None

    def start(self) -> None:
        if self._closed:
            raise SteamCloudError("Steam Cloud worker уже закрыт")

    def connect(self, app_id: int = APP_ID) -> None:
        _refuse_automated_live_session(app_id, "Connect")
        if app_id != APP_ID:
            raise SteamCloudError(
                f"Нативный worker поддерживает только app_id={APP_ID}, запрошен {app_id}"
            )
        if self._closed:
            raise SteamCloudError("Steam Cloud worker уже закрыт")
        self.app_id = app_id

    def _command(self, op: str) -> list[str]:
        if getattr(sys, "frozen", False):
            native_executable = Path(sys.executable).with_name(
                "SaveEditor-native" + Path(sys.executable).suffix
            )
            if not native_executable.is_file():
                raise SteamCloudError(
                    f"Упакованный Steam native child не найден: {native_executable}"
                )
            return [
                str(native_executable),
                "--steam-native-op",
                op,
                "--app-id",
                str(self.app_id or APP_ID),
            ]
        return [
            sys.executable,
            "-m",
            "ui",
            "--steam-native-op",
            op,
            "--app-id",
            str(self.app_id or APP_ID),
        ]

    def _child_environment(self) -> dict[str, str]:
        environment = os.environ.copy()
        if not getattr(sys, "frozen", False):
            project_root = Path(__file__).resolve().parents[1]
            current = environment.get("PYTHONPATH")
            environment["PYTHONPATH"] = os.pathsep.join(
                value for value in (str(project_root), current) if value
            )
        return environment

    @staticmethod
    def _decode_child_response(stdout: str, stderr: str) -> dict[str, Any]:
        for line in reversed(stdout.splitlines()):
            text = line.strip()
            if not text:
                continue
            try:
                response = json.loads(text)
            except json.JSONDecodeError:
                continue
            if not isinstance(response, dict):
                raise SteamCloudError("Steam native child вернул JSON не-объект")
            kind = response.get("type")
            if kind in ("Error", "Unavailable"):
                message = str(response.get("message") or "неизвестная ошибка")
                raise SteamCloudError(f"Steam native child: {message}")
            return response
        detail = stderr.strip()[-1000:]
        suffix = f" stderr={detail}" if detail else ""
        raise SteamCloudError(f"Steam native child не вернул JSON{suffix}")

    def _set_active_process(self, process: subprocess.Popen[str]) -> bool:
        with self._process_lock:
            if self._closed:
                return False
            self._active_process = process
            return True

    def _clear_active_process(self, process: subprocess.Popen[str]) -> None:
        with self._process_lock:
            if self._active_process is process:
                self._active_process = None

    @staticmethod
    def _kill_process(process: subprocess.Popen[str]) -> None:
        try:
            if process.poll() is None:
                process.kill()
        except OSError:
            pass

    def _run_native(
        self,
        op: str,
        *,
        name: str | None = None,
        payload: bytes | None = None,
        read_output: bool = False,
        timeout: float | None = None,
    ) -> tuple[dict[str, Any], bytes | None]:
        if self._closed:
            raise SteamCloudError("Steam Cloud worker уже закрыт")
        command = self._command(op)
        operation_timeout = (
            self.timeout
            if timeout is None
            else min(self.timeout, max(0.001, timeout))
        )
        output_path: Path | None = None
        with tempfile.TemporaryDirectory(prefix="stalker2-native-cloud-") as directory:
            root = Path(directory)
            if name is not None:
                command.extend(("--name", name))
            if payload is not None:
                input_path = root / "input.bin"
                input_path.write_bytes(payload)
                command.extend(("--in", str(input_path)))
            if read_output:
                output_path = root / "output.bin"
                command.extend(("--out", str(output_path)))
            try:
                process = subprocess.Popen(
                    command,
                    cwd=str(root),
                    env=self._child_environment(),
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
            except OSError as exc:
                raise SteamCloudError(f"Не удалось запустить Steam native child: {exc}") from exc
            if not self._set_active_process(process):
                self._kill_process(process)
                raise SteamCloudError("Steam native child остановлен: worker закрыт")
            try:
                try:
                    stdout, stderr = process.communicate(timeout=operation_timeout)
                except subprocess.TimeoutExpired as exc:
                    self._kill_process(process)
                    try:
                        process.communicate()
                    except OSError:
                        pass
                    raise SteamCloudError(
                        f"Steam Cloud native operation {op} превысила таймаут "
                        f"{operation_timeout:g} с"
                    ) from exc
            finally:
                self._clear_active_process(process)
            if process.returncode != 0:
                detail = stderr.strip()[-1000:]
                suffix = f" stderr={detail}" if detail else ""
                raise SteamCloudError(
                    f"Steam native child завершился с кодом {process.returncode}{suffix}"
                )
            response = self._decode_child_response(stdout, stderr)
            data = None
            if read_output:
                assert output_path is not None
                try:
                    data = output_path.read_bytes()
                except OSError as exc:
                    raise SteamCloudError(f"Steam native child не создал read output: {exc}") from exc
            return response, data

    def _native_list(self, *, timeout: float | None = None) -> list[CloudFile]:
        response, _ = self._run_native("list", timeout=timeout)
        if response.get("type") != "Files" or not isinstance(response.get("files"), list):
            raise SteamCloudError(f"Steam native child вернул неожиданный list response: {response}")
        files: list[CloudFile] = []
        for item in response["files"]:
            if not isinstance(item, dict):
                raise SteamCloudError("Steam native child вернул некорректную запись файла")
            try:
                files.append(
                    CloudFile(
                        name=str(item["name"]),
                        size=int(item["size"]),
                        timestamp=int(item["timestamp"]),
                        is_persisted=bool(item["is_persisted"]),
                        exists=bool(item["exists"]),
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise SteamCloudError(
                    f"Steam native child вернул некорректные поля файла: {item}"
                ) from exc
        return files

    def list_files(self) -> list[CloudFile]:
        if self._closed:
            raise SteamCloudError("Steam Cloud worker уже закрыт")
        if self._helper is not None:
            return self._helper.list_files()
        try:
            return self._native_list()
        except SteamCloudError as native_error:
            if self.helper_path is None:
                raise
            helper = self.helper_factory(self.helper_path, log=self.log)
            try:
                helper.start()
                helper.connect(self.app_id or APP_ID)
                files = helper.list_files()
            except Exception as helper_error:
                try:
                    helper.close()
                except Exception:
                    pass
                raise SteamCloudError(
                    f"Нативный Steam Cloud недоступен ({native_error}); helper тоже не ответил: "
                    f"{helper_error}"
                ) from helper_error
            self._helper = helper
            self.log(f"Steam Cloud: native child недоступен ({native_error}); использую helper")
            return files

    def read_file(self, filename: str) -> bytes:
        if self._helper is not None:
            return self._helper.read_file(filename)
        response, data = self._run_native("read", name=filename, read_output=True)
        if response.get("type") != "Ok" or data is None:
            raise SteamCloudError(f"Steam native child вернул неожиданный read response: {response}")
        expected_size = response.get("size")
        if expected_size is not None and int(expected_size) != len(data):
            raise SteamCloudError(
                f"Steam native child read size mismatch: {len(data)} != {expected_size}"
            )
        return data

    def write_file(self, filename: str, data: bytes) -> None:
        _refuse_automated_live_session(self.app_id or 0, "WriteFile")
        if self._helper is not None:
            self._helper.write_file(filename, data)
            return
        response, _ = self._run_native("write", name=filename, payload=bytes(data))
        if response.get("type") != "Ok":
            raise SteamCloudError(f"Steam native child вернул неожиданный write response: {response}")

    def sync(self) -> None:
        if self._helper is not None:
            self._helper.sync()
        # The child pumps callbacks after FileWrite and shuts down immediately.

    def wait_persisted(self, filename: str, expected_size: int, timeout: int = 120) -> bool:
        if self._helper is not None:
            return self._helper.wait_persisted(filename, expected_size, timeout=timeout)
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            if any(
                item.name == filename
                and item.size == expected_size
                and item.is_persisted
                for item in self._native_list(timeout=remaining)
            ):
                return True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            time.sleep(min(2.0, remaining))

    def close(self) -> None:
        self._closed = True
        with self._process_lock:
            process = self._active_process
        if process is not None:
            self._kill_process(process)
        if self._helper is not None:
            try:
                self._helper.close()
            finally:
                self._helper = None


def run_cli_op(args: list[str]) -> int:
    """One-shot native cloud op for the isolated subprocess worker.

    Runs init+connect and a single operation, prints a JSON line, exits. Kept
    tiny and window-free so the parent can spawn it with a hard timeout — a
    hung ``SteamAPI_Init``/``GetFileCount`` (e.g. when the game is not
    installed) then never freezes the app: the parent kills this process.

    Protocol (stdout, one JSON object):
      list                      -> {"type":"Files","files":[...]}
      read --name N --out PATH  -> {"type":"Ok","size":n}
      write --name N --in PATH  -> {"type":"Ok"}
    Errors: {"type":"Error"|"Unavailable","message":str}
    """

    import argparse
    import base64  # noqa: F401 - kept for future binary framing if needed

    parser = argparse.ArgumentParser(prog="SaveEditor --steam-native-op", add_help=False)
    parser.add_argument("op", choices=("list", "read", "write"))
    parser.add_argument("--name")
    parser.add_argument("--out")
    parser.add_argument("--in", dest="in_path")
    parser.add_argument("--app-id", type=int, default=APP_ID)
    parsed = parser.parse_args(args)

    def emit(obj: dict[str, Any]) -> None:
        sys.stdout.write(json.dumps(obj) + "\n")
        sys.stdout.flush()

    # Set the app identity in the short-lived child instead of writing a
    # steam_appid.txt beside whatever directory the caller happens to use.
    os.environ.update(
        {"SteamAppId": str(parsed.app_id), "SteamGameId": str(parsed.app_id)}
    )

    try:
        worker = SteamNativeWorker()
    except SteamNativeUnavailableError as exc:
        emit({"type": "Unavailable", "message": str(exc)})
        return 0
    try:
        worker.start()
        worker.connect(parsed.app_id)
        if parsed.op == "list":
            files = worker.list_files()
            emit(
                {
                    "type": "Files",
                    "files": [
                        {
                            "name": f.name,
                            "size": f.size,
                            "timestamp": f.timestamp,
                            "is_persisted": f.is_persisted,
                            "exists": f.exists,
                        }
                        for f in files
                    ],
                }
            )
        elif parsed.op == "read":
            if not parsed.name or not parsed.out:
                emit({"type": "Error", "message": "read требует --name и --out"})
                return 0
            data = worker.read_file(parsed.name)
            Path(parsed.out).write_bytes(data)
            emit({"type": "Ok", "size": len(data)})
        elif parsed.op == "write":
            if not parsed.name or not parsed.in_path:
                emit({"type": "Error", "message": "write требует --name и --in"})
                return 0
            payload = Path(parsed.in_path).read_bytes()
            worker.write_file(parsed.name, payload)
            emit({"type": "Ok"})
    except SteamCloudError as exc:
        emit({"type": "Error", "message": str(exc)})
    except Exception as exc:
        emit({"type": "Error", "message": f"{type(exc).__name__}: {exc}"})
    finally:
        try:
            worker.close()
        except Exception:
            pass
    return 0


__all__ = [
    "SteamNativeSubprocessWorker",
    "SteamNativeUnavailableError",
    "SteamNativeWorker",
    "run_cli_op",
]
