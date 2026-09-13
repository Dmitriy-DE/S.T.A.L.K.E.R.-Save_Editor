from __future__ import annotations

import glob
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

APP_ID = 1643320
SAVE_PREFIX = "Stalker2/Saved/STEAM/SaveGames/Data/"


class SteamCloudError(RuntimeError):
    pass


@dataclass
class CloudFile:
    name: str
    size: int
    timestamp: int
    is_persisted: bool
    exists: bool


def discover_helper() -> str | None:
    for name in ("steam-cloud-file-manager", "SteamCloudFileManager"):
        p = shutil.which(name)
        if p:
            return p
    patterns = [
        "~/Downloads/SteamCloudFileManager*.AppImage",
        "~/Downloads/*steam*cloud*file*manager*.AppImage",
        "~/Applications/SteamCloudFileManager*.AppImage",
        "~/.local/bin/steam-cloud-file-manager",
    ]
    for pat in patterns:
        hits = sorted(glob.glob(os.path.expanduser(pat)), reverse=True)
        if hits:
            return hits[0]
    return None


class SteamWorker:
    """JSON-RPC bridge to SteamCloudFileManager's --steam-worker mode.

    This worker is the same Steamworks RemoteStorage backend used by
    SteamCloudFileManager itself.  We deliberately do not automate its GUI.
    """

    def __init__(self, helper_path: str, log: Callable[[str], None] | None = None):
        self.helper_path = str(Path(helper_path).expanduser())
        self.log = log or (lambda _s: None)
        self.proc: subprocess.Popen[str] | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        if self.proc and self.proc.poll() is None:
            return
        p = Path(self.helper_path)
        if not p.exists():
            raise SteamCloudError(f"SteamCloudFileManager не найден: {p}")
        try:
            mode = p.stat().st_mode
            p.chmod(mode | 0o111)
        except Exception:
            pass
        try:
            self.proc = subprocess.Popen(
                [str(p), "--steam-worker"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                bufsize=1,
            )
        except Exception as exc:
            raise SteamCloudError(f"Не удалось запустить helper: {exc}") from exc

        # worker supports Ping before Steam connection
        resp = self.request({"type": "Ping"}, timeout=10)
        if resp.get("type") != "Pong":
            raise SteamCloudError(f"Helper не ответил Pong: {resp}")

    def _ensure(self):
        if not self.proc or self.proc.poll() is not None:
            self.start()
        assert self.proc and self.proc.stdin and self.proc.stdout
        return self.proc

    def _readline_with_timeout(self, timeout: float) -> str:
        proc = self._ensure()
        assert proc.stdout
        holder: list[str] = []
        err: list[BaseException] = []

        def run():
            try:
                holder.append(proc.stdout.readline())
            except BaseException as exc:
                err.append(exc)

        t = threading.Thread(target=run, daemon=True)
        t.start()
        t.join(timeout)
        if t.is_alive():
            raise SteamCloudError("Таймаут ответа Steam worker")
        if err:
            raise SteamCloudError(str(err[0]))
        if not holder or not holder[0]:
            stderr = ""
            try:
                if proc.stderr:
                    stderr = proc.stderr.read(2000)
            except Exception:
                pass
            raise SteamCloudError(f"Steam worker завершился/закрыл stdout. {stderr}")
        return holder[0]

    def request(self, obj: dict[str, Any], timeout: float = 45) -> dict[str, Any]:
        with self._lock:
            proc = self._ensure()
            assert proc.stdin
            try:
                proc.stdin.write(json.dumps(obj, separators=(",", ":")) + "\n")
                proc.stdin.flush()
            except Exception as exc:
                raise SteamCloudError(f"Ошибка записи в Steam worker: {exc}") from exc
            line = self._readline_with_timeout(timeout)
            try:
                resp = json.loads(line)
            except Exception as exc:
                raise SteamCloudError(
                    f"Steam worker вернул не JSON: {line[:500]!r}"
                ) from exc
            if resp.get("type") == "Error":
                raise SteamCloudError(resp.get("message", "Unknown worker error"))
            return resp

    def connect(self, app_id: int = APP_ID) -> None:
        resp = self.request({"type": "Connect", "app_id": app_id}, timeout=30)
        if resp.get("type") != "Connected":
            raise SteamCloudError(f"Неожиданный Connect response: {resp}")

    def list_files(self) -> list[CloudFile]:
        resp = self.request({"type": "GetFiles"}, timeout=45)
        if resp.get("type") != "Files":
            raise SteamCloudError(f"Неожиданный GetFiles response: {resp}")
        out: list[CloudFile] = []
        for f in resp.get("files", []):
            name = str(f.get("name", ""))
            if not name.startswith(SAVE_PREFIX) or not name.lower().endswith(".sav"):
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
        try:
            return bytes(data)
        except Exception as exc:
            raise SteamCloudError("ReadFile: некорректный массив байт") from exc

    def write_file(self, filename: str, data: bytes) -> None:
        # Worker IPC expects JSON Vec<u8>.  Never do list(data) for a 27 MB
        # rebuilt save: a Python list of 27 million ints can eat close to a GB.
        # Stream one JSON line directly into the child's stdin in small chunks.
        # The Rust side still receives the same protocol, but our memory stays sane.
        with self._lock:
            proc = self._ensure()
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
                raise SteamCloudError(f"Ошибка streaming WriteFile в Steam worker: {exc}") from exc

            line = self._readline_with_timeout(300)
            try:
                resp = json.loads(line)
            except Exception as exc:
                raise SteamCloudError(f"Steam worker вернул не JSON после WriteFile: {line[:500]!r}") from exc
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
        if not self.proc:
            return
        try:
            self.request({"type": "Exit"}, timeout=2)
        except Exception:
            pass
        try:
            self.proc.terminate()
        except Exception:
            pass
        self.proc = None
