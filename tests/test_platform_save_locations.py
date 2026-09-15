from __future__ import annotations

from pathlib import Path

from editor.platforms import (
    InstalledGame,
    installed_games,
    installed_releases,
    manual_save_search_paths,
    save_directories,
    save_search_paths,
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


def test_libraryfolders_vdf_preserves_unescaped_windows_separators(
    tmp_path: Path,
) -> None:
    steam = tmp_path / "steam"
    other = tmp_path / "C" / "SteamLibrary"
    vdf = steam / "steamapps" / "libraryfolders.vdf"
    vdf.parent.mkdir(parents=True)
    other.mkdir(parents=True)
    vdf.write_text(
        '"libraryfolders" { "0" { "path" "C:\\SteamLibrary" } }',
        encoding="utf-8",
    )

    assert steam_libraries(
        system="Windows",
        environ={},
        home=tmp_path / "home",
        filesystem_root=tmp_path,
        steam_library_roots=(steam,),
    ) == (steam, other)


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


def test_installed_releases_exposes_canonical_release_id_and_deduplicates_roots(
    tmp_path: Path,
) -> None:
    library = tmp_path / "library"
    install_dir = library / "steamapps" / "common" / "STALKER Clear Sky"
    install_dir.mkdir(parents=True)
    manifest_dir = library / "steamapps"
    (manifest_dir / "appmanifest_20510.acf").write_text(
        _manifest(20510, "STALKER Clear Sky"),
        encoding="utf-8",
    )

    releases = installed_releases(
        system="Linux",
        environ={},
        home=tmp_path / "home",
        steam_library_roots=(library, library),
    )

    assert len(releases) == 1
    assert releases[0].release_id == "stalker-cs"
    assert releases[0].game_id == "clear_sky"


def test_release_specific_search_does_not_mix_original_and_enhanced_roots(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    documents = home / "Documents"
    original = documents / "stalker-shoc" / "savedgames"
    enhanced = (
        home
        / "Saved Games"
        / "STALKER Shadow of Chornobyl - EE"
        / "STEAM"
        / "savedgames"
    )
    original.mkdir(parents=True)
    enhanced.mkdir(parents=True)

    original_paths = save_search_paths(
        "stalker-soc",
        system="Windows",
        environ={},
        home=home,
    )
    enhanced_paths = save_search_paths(
        "stalker-soc-ee",
        system="Windows",
        environ={},
        home=home,
    )

    assert original in original_paths
    assert enhanced not in original_paths
    assert enhanced in enhanced_paths
    assert original not in enhanced_paths


def test_manual_release_save_root_stays_exclusive(tmp_path: Path) -> None:
    selected = tmp_path / "selected"
    selected.mkdir()

    assert manual_save_search_paths("stalker-cs-ee", save_root=selected) == (selected,)


def test_enhanced_paths_cover_pripyat_spelling_and_gog_root(tmp_path: Path) -> None:
    home = tmp_path / "home"
    paths = save_search_paths(
        "stalker-cop-ee",
        system="Windows",
        environ={},
        home=home,
    )

    saved_games = home / "Saved Games"
    assert (
        saved_games
        / "STALKER Call of Pripyat - EE"
        / "STEAM"
        / "savedgames"
    ) in paths
    assert (
        saved_games
        / "STALKER Call of Pripyat - EE"
        / "gog"
        / "savedgames"
    ) in paths


def test_manual_enhanced_game_root_also_scopes_standard_saved_games(tmp_path: Path) -> None:
    home = tmp_path / "home"
    game_root = tmp_path / "library" / "STALKER Clear Sky - Enhanced Edition"
    game_root.mkdir(parents=True)

    paths = manual_save_search_paths(
        "stalker-cs-ee",
        game_root=game_root,
        system="Windows",
        environ={},
        home=home,
    )

    assert (
        home
        / "Saved Games"
        / "STALKER Clear Sky - EE"
        / "STEAM"
        / "savedgames"
    ) in paths


def test_proton_enhanced_paths_include_steam_and_gog_saved_games(tmp_path: Path) -> None:
    home = tmp_path / "home"
    library = home / ".local" / "share" / "Steam"
    install_dir = library / "steamapps" / "common" / "STALKER Clear Sky - Enhanced Edition"
    install_dir.mkdir(parents=True)
    steamapps = library / "steamapps"
    (steamapps / "appmanifest_2427420.acf").write_text(
        _manifest(2427420, "STALKER Clear Sky - Enhanced Edition"),
        encoding="utf-8",
    )

    paths = save_search_paths(
        "stalker-cs-ee",
        system="Linux",
        environ={},
        home=home,
    )
    prefix_saved_games = (
        steamapps
        / "compatdata"
        / "2427420"
        / "pfx"
        / "drive_c"
        / "users"
        / "steamuser"
        / "Saved Games"
        / "STALKER Clear Sky - EE"
    )
    assert prefix_saved_games / "STEAM" / "savedgames" in paths
    assert prefix_saved_games / "gog" / "savedgames" in paths



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


def test_save_search_paths_explains_missing_candidates_without_creating_them(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    candidates = save_search_paths("stalker2", system="Linux", environ={}, home=home)

    assert home / ".steam" / "steam" not in candidates
    assert home / "AppData" / "Local" / "Stalker2" / "Saved" / "SaveGames" in candidates
    assert candidates
    assert not home.exists()


def test_stalker2_save_search_paths_include_eos_profile(tmp_path: Path) -> None:
    local_app_data = tmp_path / "local-app-data"
    expected = (
        local_app_data
        / "Stalker2"
        / "Saved"
        / "EOS"
        / "SaveGames"
    )

    assert expected in save_search_paths(
        "stalker2",
        system="Windows",
        environ={"LOCALAPPDATA": str(local_app_data)},
        home=tmp_path / "home",
    )


def test_manual_stalker2_game_root_also_checks_documented_local_appdata(
    tmp_path: Path,
) -> None:
    local_app_data = tmp_path / "local-app-data"
    game_root = tmp_path / "S.T.A.L.K.E.R. 2 Heart of Chornobyl"
    expected = local_app_data / "Stalker2" / "Saved" / "EOS" / "SaveGames"

    assert expected in manual_save_search_paths(
        "stalker2",
        game_root=game_root,
        system="Windows",
        environ={"LOCALAPPDATA": str(local_app_data)},
        home=tmp_path / "home",
    )


def test_manual_game_root_uses_fsgame_override_without_auto_fallback(tmp_path: Path) -> None:
    game_root = tmp_path / "STALKER Clear Sky"
    game_root.mkdir()
    (game_root / "fsgame.ltx").write_text(
        "$app_data_root$ = true| false| custom-user-data\\\n"
        "$game_saves$ = true| false| $app_data_root$| saves\\\n",
        encoding="utf-8",
    )
    expected = game_root / "custom-user-data" / "saves"

    assert manual_save_search_paths(
        "clear_sky",
        game_root=game_root,
        system="Windows",
        environ={},
        home=tmp_path / "home",
    ) == (expected, game_root / "_appdata_" / "savedgames")


def test_manual_steam_root_uses_its_installed_game_and_proton_save(tmp_path: Path) -> None:
    home = tmp_path / "home"
    library = home / ".local" / "share" / "Steam"
    install_dir = library / "steamapps" / "common" / "STALKER Clear Sky"
    install_dir.mkdir(parents=True)
    steamapps = library / "steamapps"
    (steamapps / "appmanifest_20510.acf").write_text(
        _manifest(20510, "STALKER Clear Sky"),
        encoding="utf-8",
    )
    expected = (
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

    assert expected in manual_save_search_paths(
        "clear_sky",
        steam_root=library,
        system="Linux",
        environ={},
        home=home,
    )
