"""The real Steam worker must refuse cloud writes started by a test run.

Project policy has always been "no cloud uploads from automated tests", but
nothing enforced it.  A test that constructs a real SteamWorker would overwrite
a real save slot in the user's Steam Cloud.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import steam_cloud

REMOTE = "Stalker2/Saved/STEAM/SaveGames/Data/slot.sav"


def test_connect_to_the_game_app_id_is_refused_inside_a_test_run(tmp_path: Path) -> None:
    worker = steam_cloud.SteamWorker(tmp_path / "helper")

    with pytest.raises(steam_cloud.SteamCloudError, match="автоматическ"):
        worker.connect(steam_cloud.APP_ID)


def test_write_to_a_live_game_session_is_refused(tmp_path: Path) -> None:
    worker = steam_cloud.SteamWorker(tmp_path / "helper")
    worker.app_id = steam_cloud.APP_ID

    with pytest.raises(steam_cloud.SteamCloudError, match="автоматическ"):
        worker.write_file(REMOTE, b"payload")


def test_a_throwaway_app_id_is_not_blocked(tmp_path: Path) -> None:
    # Worker lifecycle tests drive the fake helper with their own app id; the
    # guard must not get in their way.
    worker = steam_cloud.SteamWorker(tmp_path / "helper")
    worker.app_id = 123

    with pytest.raises(steam_cloud.SteamCloudError) as excinfo:
        worker.write_file(REMOTE, b"payload")
    assert "автоматическ" not in str(excinfo.value)


def test_guard_can_be_lifted_for_a_deliberate_manual_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(steam_cloud.LIVE_WRITE_OVERRIDE_ENV, "1")
    worker = steam_cloud.SteamWorker(tmp_path / "absent-helper")
    worker.app_id = steam_cloud.APP_ID

    # With the override in place the guard steps aside and the call fails on the
    # missing helper instead - it never silently succeeds.
    with pytest.raises(steam_cloud.SteamCloudError) as excinfo:
        worker.write_file(REMOTE, b"payload")
    assert "автоматическ" not in str(excinfo.value)


def test_fake_transports_are_untouched_by_the_guard() -> None:
    from tests.test_cloud_transaction import REMOTE_PATH, FakeCloud

    fake = FakeCloud(b"remote-bytes")
    fake.write_file(REMOTE_PATH, b"payload")
    assert fake.write_calls == [(REMOTE_PATH, b"payload")]
