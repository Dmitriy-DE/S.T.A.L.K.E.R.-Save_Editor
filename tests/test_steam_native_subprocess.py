"""Boundaries for the killable native Steam Cloud transport."""

from __future__ import annotations

import json
import subprocess

import pytest

import editor.steam_native as steam_native
from steam_cloud import APP_ID, CloudFile, SteamCloudError


def test_native_list_timeout_becomes_a_bounded_cloud_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A hung Steam API child must not hang the caller forever."""

    calls: list[dict[str, object]] = []

    def fake_run(*args, **kwargs):
        calls.append({"args": args, "kwargs": kwargs})
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", fake_run)
    worker_type = getattr(steam_native, "SteamNativeSubprocessWorker", None)
    assert worker_type is not None

    worker = worker_type(helper_path=None, timeout=7.5)
    worker.start()
    worker.app_id = APP_ID

    with pytest.raises(SteamCloudError, match="таймаут"):
        worker.list_files()

    assert len(calls) == 1
    assert calls[0]["kwargs"]["timeout"] == 7.5


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

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args[0], returncode=0, stdout=json.dumps(response) + "\n", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    worker_type = getattr(steam_native, "SteamNativeSubprocessWorker", None)
    assert worker_type is not None

    worker = worker_type(helper_path=None)
    worker.start()
    worker.app_id = APP_ID

    files = worker.list_files()

    assert [(item.name, item.size, item.is_persisted) for item in files] == [
        ("Stalker2/Saved/STEAM/SaveGames/Data/slot.sav", 123, True)
    ]


def test_initial_native_list_timeout_selects_helper_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def fake_run(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

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

    monkeypatch.setattr(subprocess, "run", fake_run)
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


def test_native_read_and_write_use_isolated_payload_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[bytes] = []

    def fake_run(command, **kwargs):
        if "read" in command:
            output = command[command.index("--out") + 1]
            with open(output, "wb") as handle:
                handle.write(b"save")
            response = {"type": "Ok", "size": 4}
        else:
            with open(command[command.index("--in") + 1], "rb") as handle:
                seen.append(handle.read())
            response = {"type": "Ok"}
        return subprocess.CompletedProcess(command, 0, json.dumps(response) + "\n", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    worker_type = getattr(steam_native, "SteamNativeSubprocessWorker", None)
    assert worker_type is not None
    worker = worker_type(helper_path=None)
    worker.start()
    worker.app_id = 123

    assert worker.read_file("slot.sav") == b"save"
    worker.write_file("slot.sav", b"edited")

    assert seen == [b"edited"]
