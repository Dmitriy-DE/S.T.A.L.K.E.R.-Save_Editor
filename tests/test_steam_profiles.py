from __future__ import annotations

import pytest

from editor.steam_profiles import (
    steam_cloud_profile_for_app_id,
    steam_cloud_profile_for_release,
    steam_cloud_profiles,
)


def test_profiles_cover_all_official_apps_without_sidecars() -> None:
    assert [profile.release_id for profile in steam_cloud_profiles()] == [
        "stalker2",
        "stalker-soc",
        "stalker-cs",
        "stalker-cop",
        "stalker-soc-ee",
        "stalker-cs-ee",
        "stalker-cop-ee",
    ]
    assert steam_cloud_profile_for_app_id(2427410).release_id == "stalker-soc-ee"

    s2 = steam_cloud_profile_for_release("stalker2")
    assert s2.accepts("Stalker2/Saved/STEAM/SaveGames/Data/slot.sav")
    assert not s2.accepts("Stalker2/Saved/STEAM/SaveGames/Data/slot.dds")

    ee = steam_cloud_profile_for_release("stalker-cs-ee")
    assert ee.accepts("STALKER Clear Sky - EE/STEAM/savedgames/slot.scop")
    assert ee.accepts("stalker clear sky - ee\\steam\\savedgames\\slot.SCS")
    assert ee.accepts("STALKER Clear Sky - EE/STEAM/savedgames/slot.dds")
    assert not ee.accepts("STALKER Clear Sky - EE/STEAM/screenshots/slot.png")


def test_original_profiles_use_the_actual_auto_cloud_savedgames_root() -> None:
    soc = steam_cloud_profile_for_release("stalker-soc")
    cop = steam_cloud_profile_for_release("stalker-cop")

    assert soc.accepts("_appdata_/savedgames/quicksave.sav")
    assert soc.accepts("_appdata_/savedgames/quicksave.scop")
    assert cop.accepts("_appdata_/savedgames/quicksave.scop")
    assert soc.accepts("_appdata_/savedgames/extensionless-slot")
    assert not cop.accepts("_appdata_/screenshots/shot.png")


def test_unknown_app_id_fails_closed() -> None:
    with pytest.raises(KeyError):
        steam_cloud_profile_for_app_id(123)
