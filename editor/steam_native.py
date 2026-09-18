"""In-process Steam Cloud worker via ctypes over Valve's ``libsteam_api``.

This replaces the third-party ``SteamCloudFileManager`` helper as the primary
cloud backend: no subprocess, no JSON-RPC, no AppImage/FUSE.  It still depends
on Valve's proprietary ``libsteam_api`` — the only door into Steam Cloud — but
that library ships with every Steamworks game and with the helper payload, so
nothing external to the machine is required.

The public surface mirrors :class:`steam_cloud.SteamWorker` (``start``,
``connect``, ``close``, ``list_files``, ``read_file``, ``write_file``,
``sync``, ``wait_persisted``) so it is a drop-in for the Cloud tab's
``worker_factory``.  When ``libsteam_api`` is missing or ``SteamAPI_Init``
fails (no running Steam client, app not owned), construction/``start`` raises
and :mod:`editor.steam_backend` silently falls back to the helper worker.

NOTE: the live download/upload round-trip cannot be verified without an
installed game and a running Steam session; it is exercised only against a
ctypes fake.  Treat live behaviour as user-verified.
"""

from __future__ import annotations

import ctypes
import os
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


__all__ = ["SteamNativeUnavailableError", "SteamNativeWorker"]
