from __future__ import annotations

from pathlib import Path

from editor.platforms import (
    InstalledGame,
    installed_games,
    save_directories,
    steam_libraries,
    steam_roots,
)


def _manifest(app_id: int, install_dir: str) -> str:
    return f'''
"AppState"
{{
    "appid" "{app_id}"
    "installdir" "{install_dir}"
}}
'''


def test_linux_steam_roots_include_standard_and_flatpak_locations(tmp_path: Path) -> None:
    home = tmp_path / "home"

    assert steam_roots(system="Linux", environ={}, home=home) == (
        home / ".steam" / "steam",
        home / ".local" / "share" / "Steam",
        home / ".var" / "app" / "com.valvesoftware.Steam" / "data" / "Steam",
    )


def test_windows_steam_roots_prefer_injected_registry_then_program_files(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "registry-steam"
    program_files_x86 = tmp_path / "Program Files (x86)"

    assert steam_roots(
        system="Windows",
        environ={"PROGRAMFILES(X86)": str(program_files_x86)},
        home=tmp_path / "home",
        registry_reader=lambda: registry,
    ) == (registry, program_files_x86 / "Steam")


def test_libraryfolders_vdf_finds_library_on_another_disk(tmp_path: Path) -> None:
    steam = tmp_path / "home" / ".local" / "share" / "Steam"
    other = tmp_path / "mnt" / "games" / "SteamLibrary"
    vdf = steam / "steamapps" / "libraryfolders.vdf"
    vdf.parent.mkdir(parents=True)
    other.mkdir(parents=True)
    vdf.write_text(
        '"libraryfolders"\n{\n'
        f'    "0" "{steam}"\n'
        f'    "1"\n    {{\n        "path" "{other}"\n    }}\n'
        '}\n',
        encoding="utf-8",
    )

    assert steam_libraries(system="Linux", environ={}, home=tmp_path / "home") == (
        steam,
        other,
    )


def test_broken_libraryfolders_is_skipped_without_hiding_other_library(
    tmp_path: Path,
) -> None:
    broken = tmp_path / "home" / ".steam" / "steam"
    working = tmp_path / "home" / ".local" / "share" / "Steam"
    (broken / "steamapps").mkdir(parents=True)
    (broken / "steamapps" / "libraryfolders.vdf").write_text(
        '"libraryfolders" { "0" { "path" "unterminated" ',
        encoding="utf-8",
    )
    (working / "steamapps").mkdir(parents=True)
    (working / "steamapps" / "libraryfolders.vdf").write_text(
        f'"libraryfolders" {{ "0" "{working}" }}',
        encoding="utf-8",
    )

    libraries = steam_libraries(system="Linux", environ={}, home=tmp_path / "home")

    assert working in libraries


def test_installed_games_require_manifest_and_install_directory(tmp_path: Path) -> None:
    library = tmp_path / "library"
    install_dir = library / "steamapps" / "common" / "STALKER Clear Sky"
    install_dir.mkdir(parents=True)
    manifest_dir = library / "steamapps"
    manifest_dir.mkdir(exist_ok=True)
    (manifest_dir / "appmanifest_20510.acf").write_text(
        _manifest(20510, "STALKER Clear Sky"),
        encoding="utf-8",
    )

    games = installed_games(
        system="Linux",
        environ={"XDG_DATA_HOME": str(tmp_path / "unused")},
        home=tmp_path / "home",
        steam_library_roots=(library,),
    )

    assert games == (
        InstalledGame(
            game_id="clear_sky",
            app_id=20510,
            edition="original",
            library_root=library,
            install_dir=install_dir,
        ),
    )


def test_save_directories_find_localized_documents_directory(tmp_path: Path) -> None:
    documents = tmp_path / "home" / "Документы"
    save_dir = documents / "Stalker-STCS" / "savedgames"
    save_dir.mkdir(parents=True)

    assert save_directories(
        "clear_sky",
        system="Windows",
        environ={},
        home=tmp_path / "home",
    ) == (save_dir,)


def test_save_directories_find_save_inside_proton_prefix(tmp_path: Path) -> None:
    home = tmp_path / "home"
    library = home / ".local" / "share" / "Steam"
    install_dir = library / "steamapps" / "common" / "STALKER Clear Sky"
    install_dir.mkdir(parents=True)
    steamapps = library / "steamapps"
    (steamapps / "appmanifest_20510.acf").write_text(
        _manifest(20510, "STALKER Clear Sky"),
        encoding="utf-8",
    )
    save_dir = (
        steamapps
        / "compatdata"
        / "20510"
        / "pfx"
        / "drive_c"
        / "users"
        / "steamuser"
        / "Documents"
        / "Stalker-STCS"
        / "savedgames"
    )
    save_dir.mkdir(parents=True)

    assert save_dir in save_directories(
        "clear_sky",
        system="Linux",
        environ={},
        home=home,
    )


def test_fsgame_ltx_override_is_used_for_installed_xray_game(tmp_path: Path) -> None:
    library = tmp_path / "library"
    install_dir = library / "steamapps" / "common" / "STALKER Clear Sky"
    install_dir.mkdir(parents=True)
    (library / "steamapps" / "appmanifest_20510.acf").write_text(
        _manifest(20510, "STALKER Clear Sky"),
        encoding="utf-8",
    )
    (install_dir / "fsgame.ltx").write_text(
        "$app_data_root$ = true| false| custom-user-data\\\n"
        "$game_saves$ = true| false| $app_data_root$| saves\\\n",
        encoding="utf-8",
    )
    save_dir = install_dir / "custom-user-data" / "saves"
    save_dir.mkdir(parents=True)

    assert save_directories(
        "clear_sky",
        system="Windows",
        environ={},
        home=tmp_path / "home",
        steam_library_roots=(library,),
    ) == (save_dir,)


def test_save_directories_find_stalker2_microsoft_store_user_container(
    tmp_path: Path,
) -> None:
    local_app_data = tmp_path / "local-app-data"
    save_dir = (
        local_app_data
        / "Packages"
        / "GSCGameWorld.S.T.A.L.K.E.R.2HeartofChornobyl_6fr1t1rwfarwt"
        / "SystemAppData"
        / "xgs"
        / "user-123"
        / "SaveGames"
    )
    save_dir.mkdir(parents=True)

    assert save_dir in save_directories(
        "stalker2",
        system="Windows",
        environ={"LOCALAPPDATA": str(local_app_data)},
        home=tmp_path / "home",
    )


def test_no_installed_store_or_steam_games_is_an_empty_read_only_result(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    before = tuple(home.rglob("*")) if home.exists() else ()

    assert installed_games(system="Linux", environ={}, home=home) == ()
    assert save_directories("stalker2", system="Linux", environ={}, home=home) == ()
    after = tuple(home.rglob("*")) if home.exists() else ()

    assert before == after
