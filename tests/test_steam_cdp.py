from __future__ import annotations

from pathlib import Path

from editor.steam_cdp import cloud_files_from_rows, discover_cached_cloud_files


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
