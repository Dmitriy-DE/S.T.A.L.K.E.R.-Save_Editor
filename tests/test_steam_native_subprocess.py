"""Boundaries for the killable native Steam Cloud transport."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from pathlib import Path

import pytest

import editor.steam_native as steam_native
from editor.cloud_capabilities import CloudWriteNotAttemptedError
from editor.steam_profiles import steam_cloud_profile_for_release
from steam_cloud import APP_ID, CloudFile, SteamCloudError


class _FakeProcess:
    def __init__(self, args, *, stdout: str = "", stderr: str = "") -> None:
        self.args = args
        self.stdout = stdout
        self.stderr = stderr
        self.returncode: int | None = None
        self.killed = False
        self.communicate_timeouts: list[float | None] = []

    def communicate(self, timeout=None):
        self.communicate_timeouts.append(timeout)
        self.returncode = 0
        return self.stdout, self.stderr

    def poll(self):
        return self.returncode

    def kill(self):
        self.killed = True
        self.returncode = -9


def test_native_list_timeout_becomes_a_bounded_cloud_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A hung Steam API child must not hang the caller forever."""

    calls: list[_FakeProcess] = []

    def fake_popen(command, **_kwargs):
        process = _FakeProcess(command)
        calls.append(process)

        def timeout_communicate(timeout=None):
            process.communicate_timeouts.append(timeout)
            if timeout is not None:
                raise subprocess.TimeoutExpired(command, timeout)
            process.returncode = -9
            return "", ""

        process.communicate = timeout_communicate
        return process

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    worker_type = getattr(steam_native, "SteamNativeSubprocessWorker", None)
    assert worker_type is not None

    worker = worker_type(helper_path=None, timeout=7.5)
    worker.start()
    worker.app_id = APP_ID

    with pytest.raises(SteamCloudError, match="таймаут"):
        worker.list_files()

    assert len(calls) == 1
    assert calls[0].communicate_timeouts == [7.5, None]
    assert calls[0].killed is True


def test_native_list_decodes_child_file_records(monkeypatch: pytest.MonkeyPatch) -> None:
    response = {
        "type": "Files",
        "files": [
            {
                "name": "Stalker2/Saved/STEAM/SaveGames/Data/slot.sav",
                "size": 123,
                "timestamp": 1_700_000_000,
                "is_persisted": True,
                "exists": True,
            }
        ],
    }

    def fake_popen(command, **_kwargs):
        return _FakeProcess(command, stdout=json.dumps(response) + "\n")

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    worker_type = getattr(steam_native, "SteamNativeSubprocessWorker", None)
    assert worker_type is not None

    worker = worker_type(helper_path=None)
    worker.start()
    worker.app_id = APP_ID

    files = worker.list_files()

    assert [(item.name, item.size, item.is_persisted) for item in files] == [
        ("Stalker2/Saved/STEAM/SaveGames/Data/slot.sav", 123, True)
    ]


def test_native_list_uses_selected_release_filter_and_reports_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = {
        "type": "Files",
        "files": [
            {
                "name": "Stalker2/Saved/STEAM/SaveGames/Data/slot.sav",
                "size": 123,
                "timestamp": 1_700_000_000,
                "is_persisted": True,
                "exists": True,
            },
            {
                "name": "_appdata_/savedgames/slot.scop",
                "size": 456,
                "timestamp": 1_700_000_001,
                "is_persisted": True,
                "exists": True,
            },
        ],
    }

    def fake_popen(command, **_kwargs):
        assert "--app-id" in command
        assert command[command.index("--app-id") + 1] == "41700"
        return _FakeProcess(command, stdout=json.dumps(response) + "\n")

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    profile = steam_cloud_profile_for_release("stalker-cop")
    worker = steam_native.SteamNativeSubprocessWorker(file_filter=profile.accepts)
    worker.start()
    worker.app_id = profile.app_id

    files = worker.list_files()

    assert [item.name for item in files] == ["_appdata_/savedgames/slot.scop"]
    assert "RemoteStorage" in worker.status_hint
    assert "41700" in worker.status_hint


def test_initial_native_list_timeout_selects_helper_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def fake_popen(command, **_kwargs):
        nonlocal calls
        calls += 1
        process = _FakeProcess(command)

        def timeout_communicate(timeout=None):
            if timeout is not None:
                raise subprocess.TimeoutExpired(command, timeout)
            process.returncode = -9
            return "", ""

        process.communicate = timeout_communicate
        return process

    class FakeHelper:
        def __init__(self, path, *, log=None):
            self.path = path
            self.started = False
            self.connected = None
            self.list_calls = 0

        def start(self):
            self.started = True

        def connect(self, app_id):
            self.connected = app_id

        def list_files(self):
            self.list_calls += 1
            return [CloudFile("slot.sav", 4, 1, True, True)]

        def close(self):
            return None

    helper_instances = []

    def make_helper(path, *, log=None):
        helper = FakeHelper(path, log=log)
        helper_instances.append(helper)
        return helper

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    worker_type = getattr(steam_native, "SteamNativeSubprocessWorker", None)
    assert worker_type is not None

    worker = worker_type(
        helper_path="/tmp/helper", helper_factory=make_helper, timeout=1.0
    )
    worker.start()
    worker.app_id = APP_ID

    assert [item.name for item in worker.list_files()] == ["slot.sav"]
    assert [item.name for item in worker.list_files()] == ["slot.sav"]
    assert calls == 1
    assert len(helper_instances) == 1
    assert helper_instances[0].started is True
    assert helper_instances[0].connected == APP_ID
    assert helper_instances[0].list_calls == 2


def test_empty_native_list_uses_cdp_cloud_files_for_download(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = {"type": "Files", "files": []}

    def fake_popen(command, **_kwargs):
        return _FakeProcess(command, stdout=json.dumps(response) + "\n")

    class FakeCdp:
        def __init__(self, *_args, **_kwargs):
            self.closed = False

        def start(self):
            return None

        def connect(self, _app_id):
            return None

        def list_files(self):
            return [CloudFile("Stalker2/Saved/STEAM/SaveGames/Data/slot.sav", 4, 1, True, True)]

        def read_file(self, _filename):
            return b"save"

        def close(self):
            self.closed = True

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    worker = steam_native.SteamNativeSubprocessWorker(
        cdp_factory=FakeCdp,
        cache_finder=lambda _app_id: (),
    )
    worker.start()
    worker.app_id = APP_ID

    files = worker.list_files()

    assert [item.name for item in files] == [
        "Stalker2/Saved/STEAM/SaveGames/Data/slot.sav"
    ]
    assert worker.read_file(files[0].name) == b"save"
    assert worker.write_capability.writable is False

    native_calls: list[str] = []

    def forbid_native_write(operation: str, **_kwargs):
        native_calls.append(operation)
        raise AssertionError("read-only fallback must not invoke native write")

    monkeypatch.setattr(worker, "_run_native", forbid_native_write)
    with pytest.raises(CloudWriteNotAttemptedError, match="web"):
        worker.write_file(files[0].name, b"edited")
    assert native_calls == []


def test_native_read_and_write_use_isolated_payload_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[bytes] = []

    def fake_popen(command, **_kwargs):
        if "read" in command:
            output = command[command.index("--out") + 1]
            with open(output, "wb") as handle:
                handle.write(b"save")
            response = {"type": "Ok", "size": 4}
        else:
            with open(command[command.index("--in") + 1], "rb") as handle:
                seen.append(handle.read())
            response = {"type": "Ok"}
        return _FakeProcess(command, stdout=json.dumps(response) + "\n")

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    worker_type = getattr(steam_native, "SteamNativeSubprocessWorker", None)
    assert worker_type is not None
    worker = worker_type(helper_path=None)
    worker.start()
    worker.app_id = 123

    assert worker.read_file("slot.sav") == b"save"
    worker.write_file("slot.sav", b"edited")

    assert seen == [b"edited"]


def test_close_kills_an_active_native_child(monkeypatch: pytest.MonkeyPatch) -> None:
    started = threading.Event()
    released = threading.Event()
    processes: list[_FakeProcess] = []

    class BlockingProcess(_FakeProcess):
        def communicate(self, timeout=None):
            self.communicate_timeouts.append(timeout)
            started.set()
            released.wait(2)
            return self.stdout, self.stderr

        def kill(self):
            super().kill()
            released.set()

    def fake_popen(command, **_kwargs):
        process = BlockingProcess(command)
        processes.append(process)
        return process

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    worker = steam_native.SteamNativeSubprocessWorker(timeout=10)
    worker.start()
    worker.app_id = APP_ID
    errors: list[Exception] = []

    def run_list() -> None:
        try:
            worker.list_files()
        except Exception as exc:
            errors.append(exc)

    thread = threading.Thread(target=run_list)
    thread.start()

    assert started.wait(1)
    worker.close()
    thread.join(1)

    assert not thread.is_alive()
    assert processes[0].killed is True
    assert errors and isinstance(errors[0], SteamCloudError)


def test_frozen_worker_uses_console_native_entrypoint(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    gui = tmp_path / ("SaveEditor.exe" if sys.platform == "win32" else "SaveEditor")
    native = gui.with_name("SaveEditor-native" + gui.suffix)
    native.touch()
    monkeypatch.setattr(sys, "executable", str(gui))
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    worker = steam_native.SteamNativeSubprocessWorker()
    worker.app_id = APP_ID

    assert worker._command("list")[0] == str(native)


def test_wait_persisted_caps_each_native_list_to_remaining_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker = steam_native.SteamNativeSubprocessWorker(timeout=15)
    worker.app_id = APP_ID
    timeouts: list[float | None] = []
    requested_timeout = 0.02

    def fake_native_list(*, timeout=None):
        timeouts.append(timeout)
        return []

    monkeypatch.setattr(worker, "_native_list", fake_native_list)

    assert worker.wait_persisted("slot.sav", 4, timeout=requested_timeout) is False
    assert timeouts
    # ``monotonic() + timeout - monotonic()`` can round a few microseconds
    # above the requested value on Windows.  That does not allow the child
    # operation to outlive the deadline; the production path applies the
    # final min() again in ``_run_native``.
    assert all(
        timeout is not None and timeout <= requested_timeout + 0.001
        for timeout in timeouts
    )
