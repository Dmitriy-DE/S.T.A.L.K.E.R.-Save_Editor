from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

import steam_cloud as sc

FAKE_HELPER = Path(__file__).with_name("fake_worker.py")


@pytest.fixture
def helper_path(tmp_path: Path) -> str:
    """Return a path the OS will actually execute.

    The real helper is a binary, so SteamWorker launches the path directly.
    Windows cannot execute a .py that way (WinError 193), so the fake helper is
    wrapped in a .cmd shim there rather than weakening the product code.
    """

    if os.name == "nt":
        shim = tmp_path / "fake_worker.cmd"
        shim.write_text(
            f'@echo off\r\n"{sys.executable}" "{FAKE_HELPER}" %*\r\n',
            encoding="utf-8",
        )
        return str(shim)

    FAKE_HELPER.chmod(FAKE_HELPER.stat().st_mode | 0o111)
    return str(FAKE_HELPER)


def test_posix_helper_gets_its_adjacent_library_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if os.name == "nt":
        pytest.skip("LD_LIBRARY_PATH is POSIX-only")
    monkeypatch.setenv("LD_LIBRARY_PATH", "/existing/lib")

    environment = sc._helper_environment(tmp_path / "steam-cloud-file-manager")

    assert environment["LD_LIBRARY_PATH"] == f"{tmp_path}:/existing/lib"


def test_normal_worker_round_trip_and_close_has_no_child(
    helper_path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_WORKER_MODE", "normal")
    worker = sc.SteamWorker(helper_path)

    worker.start()
    worker.connect(123)
    assert worker.list_files() == []
    assert worker.read_file("save.sav") == bytes([1, 2, 3])
    worker.write_file("save.sav", b"payload")
    worker.sync()
    worker.close()

    assert worker.proc is None


def test_crashed_process_request_returns_within_external_time_bound(
    helper_path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_WORKER_MODE", "crash")
    worker = sc.SteamWorker(helper_path)
    started = time.monotonic()
    with pytest.raises(sc.SteamCloudError):
        worker.request({"type": "GetFiles"}, timeout=0.5)
    elapsed = time.monotonic() - started

    assert elapsed < 2.0
    assert worker.proc is None


def test_timeout_invalidates_session_and_delayed_reply_cannot_leak(
    helper_path: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_WORKER_MODE", "delayed_once")
    monkeypatch.setenv("FAKE_WORKER_MARKER", str(tmp_path / "first-request.marker"))
    worker = sc.SteamWorker(helper_path)

    with pytest.raises(sc.SteamCloudError, match="Таймаут"):
        worker.request({"type": "GetFiles"}, timeout=0.05)
    assert worker.proc is None

    worker.connect(123)
    response = worker.request({"type": "GetFiles"}, timeout=1.0)
    assert response["type"] == "Files"
    worker.close()


def test_malformed_response_invalidates_session(
    helper_path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_WORKER_MODE", "malformed")
    worker = sc.SteamWorker(helper_path)

    with pytest.raises(sc.SteamCloudError, match="не JSON"):
        worker.start()
    assert worker.proc is None


def test_stderr_flood_is_drained_and_chunked_json_is_supported(
    helper_path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_WORKER_MODE", "stderr_flood")
    worker = sc.SteamWorker(helper_path)
    worker.start()
    worker.close()

    monkeypatch.setenv("FAKE_WORKER_MODE", "chunked")
    worker = sc.SteamWorker(helper_path)
    worker.start()
    worker.close()


def test_response_size_limit_invalidates_session(
    helper_path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_WORKER_MODE", "oversize")
    monkeypatch.setattr(sc, "MAX_RESPONSE_BYTES", 128)
    worker = sc.SteamWorker(helper_path)

    with pytest.raises(sc.SteamCloudError, match="слишком большой"):
        worker.start()
    assert worker.proc is None


def test_close_reaps_a_helper_that_ignores_exit(
    helper_path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_WORKER_MODE", "normal")
    worker = sc.SteamWorker(helper_path)
    worker.start()
    proc = worker.proc
    assert proc is not None
    worker.close()
    assert proc.poll() is not None
