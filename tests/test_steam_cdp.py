from __future__ import annotations

import urllib.request
from pathlib import Path

from editor.steam_cdp import (
    SteamCdpWorker,
    cloud_files_from_rows,
    discover_cached_cloud_files,
)
from editor.steam_profiles import steam_cloud_profile_for_release


def test_discover_cached_cloud_files_reads_steam_remotecache(tmp_path: Path) -> None:
    steam = tmp_path / ".local" / "share" / "Steam"
    cache_dir = steam / "userdata" / "765" / "1643320"
    cache_dir.mkdir(parents=True)
    (cache_dir / "remotecache.vdf").write_text(
        '''"1643320"
{
    "Stalker2/Saved/STEAM/SaveGames/Data/slot.sav"
    {
        "size" "1234"
        "time" "1700000000"
        "syncstate" "1"
    }
}
''',
        encoding="utf-8",
    )

    files = discover_cached_cloud_files(
        1643320,
        system="Linux",
        environ={},
        home=tmp_path,
    )

    assert len(files) == 1
    assert files[0].name.endswith("/slot.sav")
    assert files[0].size == 1234
    assert files[0].timestamp == 1700000000
    assert files[0].is_persisted is False


def test_cloud_files_from_cdp_rows_builds_full_data_paths_and_download_urls() -> None:
    files = cloud_files_from_rows(
        [
            {
                "folder": "Stalker2/Saved/STEAM/SaveGames/Data",
                "name": "slot.sav",
                "size_str": "6.4 MB",
                "time_str": "2026-09-19 12:00:00",
                "url": "https://steamusercontent-a.akamaihd.net/file",
            }
        ]
    )

    assert len(files) == 1
    assert files[0].name == "Stalker2/Saved/STEAM/SaveGames/Data/slot.sav"
    assert files[0].size == 6_400_000
    assert files[0].download_url == "https://steamusercontent-a.akamaihd.net/file"
    assert files[0].is_persisted is True


def test_cloud_files_from_cdp_rows_accepts_original_savedgames_paths() -> None:
    profile = steam_cloud_profile_for_release("stalker-cop")
    files = cloud_files_from_rows(
        [
            {
                "folder": "_appdata_/savedgames",
                "name": "slot.scop",
                "size_str": "1 KB",
                "time_str": "2026-09-19 12:00:00",
            },
            {
                "folder": "_appdata_/screenshots",
                "name": "slot.png",
                "size_str": "1 KB",
                "time_str": "2026-09-19 12:00:00",
            },
        ],
        file_filter=profile.accepts,
    )

    assert [item.name for item in files] == ["_appdata_/savedgames/slot.scop"]


def test_cdp_read_refreshes_an_expired_download_url(monkeypatch) -> None:
    name = "Stalker2/Saved/STEAM/SaveGames/Data/slot.sav"
    worker = SteamCdpWorker()
    worker._urls = {name: "https://steamusercontent-a.akamaihd.net/expired"}
    refreshes: list[str] = []

    def refresh() -> list[object]:
        refreshes.append(name)
        worker._urls[name] = "https://steamusercontent-a.akamaihd.net/fresh"
        return []

    monkeypatch.setattr(worker, "list_files", refresh)
    calls = 0

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, _limit: int) -> bytes:
            return b"save"

    def open_url(url: str, *, timeout: float):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise urllib.error.HTTPError(url, 403, "expired", {}, None)
        assert url.endswith("/fresh")
        assert timeout == worker.timeout
        return Response()

    monkeypatch.setattr(urllib.request, "urlopen", open_url)

    assert worker.read_file(name) == b"save"
    assert refreshes == [name]
    assert calls == 2
