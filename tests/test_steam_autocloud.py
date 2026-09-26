"""S2 cloud writes go through the local Auto-Cloud folder and a game session."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import editor.steam_native as steam_native
from editor.releases import release_by_id
from editor.steam_autocloud import auto_cloud_local_path, auto_cloud_local_root
from steam_cloud import CloudFile

S2 = release_by_id("stalker2").app_id
NAME = "Stalker2/Saved/STEAM/SaveGames/Data/slot.sav"
# A throwaway id keeps the live-game guard out of the way.
TEST_APP = 999_001


def test_local_root_is_found_in_the_proton_prefix(tmp_path: Path) -> None:
    root = tmp_path / "steamapps/compatdata" / str(S2) / "pfx/drive_c/users/steamuser/Local Settings/Application Data"
    (root / "Stalker2").mkdir(parents=True)
    assert auto_cloud_local_root(S2, system="linux", libraries=[tmp_path]) == root


def test_local_root_is_absent_for_games_without_auto_cloud_saves(tmp_path: Path) -> None:
    assert auto_cloud_local_root(S2, system="linux", libraries=[tmp_path]) is None
    assert auto_cloud_local_root(release_by_id("stalker-cop").app_id, system="linux", libraries=[tmp_path]) is None


def test_local_root_on_windows_uses_localappdata(tmp_path: Path) -> None:
    (tmp_path / "Stalker2").mkdir()
    assert auto_cloud_local_root(S2, system="win32", environ={"LOCALAPPDATA": str(tmp_path)}) == tmp_path


@pytest.mark.parametrize("name", ["", "../x.sav", "Stalker2//x.sav", "Stalker2/./x.sav"])
def test_local_path_refuses_names_outside_the_root(tmp_path: Path, name: str) -> None:
    with pytest.raises(ValueError):
        auto_cloud_local_path(tmp_path, name)


class _Cloud:
    """Steam web view: serves what the local file held when the session ended."""

    def __init__(self, local: Path, uploaded: bool = True) -> None:
        self.local = local
        self.remote = b"old save"
        self.uploaded = uploaded

    def factory(self, *_args, **_kwargs):
        return self

    def start(self):
        return None

    def connect(self, _app_id):
        return None

    def set_file_filter(self, _filter):
        return None

    def list_files(self):
        return [CloudFile(NAME, 6_000_000, 1, True, True, source="web")]

    def read_file(self, _name):
        return self.remote

    def close(self):
        return None


def _worker(tmp_path: Path, cloud: _Cloud, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "local"
    (root / "Stalker2/Saved/STEAM/SaveGames/Data").mkdir(parents=True)
    events: list[str] = []

    def no_native(*_args, **_kwargs):
        raise AssertionError("FileWrite/native list must not run for Auto-Cloud saves")

    monkeypatch.setattr(subprocess, "Popen", no_native)
    worker = steam_native.SteamNativeSubprocessWorker(
        cdp_factory=cloud.factory,
        cache_finder=lambda *_a, **_k: (),
        auto_cloud_finder=lambda _app: root,
        session_settle=0,
    )
    active = {"on": False}

    def begin():
        events.append("begin")
        active["on"] = True

    def end(**_kwargs):
        events.append("end")
        active["on"] = False
        if cloud.uploaded:
            cloud.remote = (root / NAME).read_bytes()
        return True

    monkeypatch.setattr(worker, "begin_game_session", begin)
    monkeypatch.setattr(worker, "end_game_session", end)
    monkeypatch.setattr(type(worker), "game_session_active", property(lambda _self: active["on"]))
    worker.start()
    worker.connect(TEST_APP)
    return worker, root, events


def test_write_goes_to_the_local_folder_inside_a_game_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cloud = _Cloud(tmp_path)
    worker, root, events = _worker(tmp_path, cloud, monkeypatch)

    assert [item.name for item in worker.list_files()] == [NAME]
    assert worker.write_capability.writable is True
    worker.write_file(NAME, b"edited save")

    assert (root / NAME).read_bytes() == b"edited save"
    assert events == ["begin", "end"]
    assert worker.wait_persisted(NAME, len(b"edited save"), timeout=1) is True
    assert worker.readback_file(NAME) == b"edited save"


def test_unsynced_upload_is_not_reported_as_persisted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cloud = _Cloud(tmp_path, uploaded=False)
    worker, _root, _events = _worker(tmp_path, cloud, monkeypatch)
    worker.list_files()
    worker.write_file(NAME, b"edited save")
    assert worker.wait_persisted(NAME, len(b"edited save"), timeout=0.1) is False


def test_write_is_refused_without_steam_web_verification(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cloud = _Cloud(tmp_path)
    worker, _root, _events = _worker(tmp_path, cloud, monkeypatch)
    # No list yet, so Steam web is not connected.
    assert worker.write_capability.writable is False
