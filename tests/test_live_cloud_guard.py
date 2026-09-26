"""Live Steam Cloud operations stay blocked inside automated tests."""

from __future__ import annotations

import pytest

import editor.steam_native as steam_native
from steam_cloud import APP_ID, LIVE_WRITE_OVERRIDE_ENV, SteamCloudError

REMOTE = "Stalker2/Saved/STEAM/SaveGames/Data/slot.sav"


def _raise_fake_native(*_args, **_kwargs):
    raise SteamCloudError("synthetic native operation")


def test_connect_to_the_game_app_id_is_refused_inside_a_test_run() -> None:
    worker = steam_native.SteamNativeSubprocessWorker()

    with pytest.raises(SteamCloudError, match="автоматическ"):
        worker.connect(APP_ID)


def test_write_to_a_live_game_session_is_refused_before_native_io(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker = steam_native.SteamNativeSubprocessWorker()
    worker.app_id = APP_ID
    monkeypatch.setattr(worker, "_run_native", _raise_fake_native)

    with pytest.raises(SteamCloudError, match="автоматическ"):
        worker.write_file(REMOTE, b"synthetic")


def test_a_throwaway_app_id_reaches_only_the_fake_native_operation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker = steam_native.SteamNativeSubprocessWorker()
    worker.app_id = 123
    monkeypatch.setattr(worker, "_run_native", _raise_fake_native)

    with pytest.raises(SteamCloudError, match="synthetic native operation") as excinfo:
        worker.write_file(REMOTE, b"synthetic")
    assert "автоматическ" not in str(excinfo.value)


def test_guard_can_be_lifted_for_a_deliberate_manual_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(LIVE_WRITE_OVERRIDE_ENV, "1")
    worker = steam_native.SteamNativeSubprocessWorker()
    worker.app_id = APP_ID
    monkeypatch.setattr(worker, "_run_native", _raise_fake_native)

    with pytest.raises(SteamCloudError, match="synthetic native operation") as excinfo:
        worker.write_file(REMOTE, b"synthetic")
    assert "автоматическ" not in str(excinfo.value)


def test_fake_transports_are_untouched_by_the_guard() -> None:
    from tests.test_cloud_transaction import REMOTE_PATH, FakeCloud

    fake = FakeCloud(b"remote-bytes")
    fake.write_file(REMOTE_PATH, b"payload")
    assert fake.write_calls == [(REMOTE_PATH, b"payload")]
