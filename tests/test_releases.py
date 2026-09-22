from __future__ import annotations

from pathlib import Path

import pytest

from editor.releases import official_releases, release_by_app_id, release_by_id


def test_official_releases_list_four_families_and_three_ee_variants() -> None:
    releases = official_releases()

    assert [release.id for release in releases] == [
        "stalker2",
        "stalker-soc",
        "stalker-cs",
        "stalker-cop",
        "stalker-soc-ee",
        "stalker-cs-ee",
        "stalker-cop-ee",
    ]
    assert release_by_id("stalker-cop").edition == "original"
    assert release_by_id("stalker-cs-ee").edition == "enhanced"
    assert release_by_id("stalker2").app_ids == (1643320,)


def test_release_by_id_rejects_unknown_or_mod_release() -> None:
    with pytest.raises(KeyError):
        release_by_id("anomaly")

    with pytest.raises(KeyError):
        release_by_id("unknown")


def test_ee_descriptors_keep_save_extensions_as_candidate_hints() -> None:
    assert release_by_id("stalker-soc-ee").extensions == frozenset({".sav", ".dds", ".info"})
    assert release_by_id("stalker-cs-ee").extensions == frozenset(
        {".sav", ".scop", ".scs", ".dds", ".info"}
    )
    assert release_by_id("stalker-cop-ee").extensions == frozenset(
        {".sav", ".scop", ".scs", ".dds", ".info"}
    )


def test_registry_owns_unique_app_ids_and_cross_surface_traits() -> None:
    releases = official_releases()

    assert len({release.id for release in releases}) == len(releases)
    app_ids = [app_id for release in releases for app_id in release.app_ids]
    assert len(set(app_ids)) == len(app_ids)
    assert all(release.app_id > 0 for release in releases)
    assert all(release.install_dirs for release in releases)
    assert all(release.cloud_prefixes for release in releases)
    assert all(release.cloud_extensions is not None for release in releases)

    stalker2 = release_by_id("stalker2")
    assert stalker2.app_id == 1643320
    assert stalker2.install_dirs == (
        "S.T.A.L.K.E.R. 2 Heart of Chornobyl",
        "STALKER 2 Heart of Chornobyl",
        "S.T.A.L.K.E.R. 2",
    )
    assert stalker2.cloud_prefixes == (
        "Stalker2/Saved/STEAM/SaveGames/Data/",
    )
    assert stalker2.cloud_extensions == frozenset({".sav"})
    assert release_by_app_id(1643320) is stalker2
    assert stalker2.equipment is not None
    assert "binocular" in stalker2.equipment.device_subtypes
    assert stalker2.equipment.support("durability").maturity == "experimental"


def test_platform_and_catalog_modules_do_not_redeclare_official_app_ids() -> None:
    root = Path(__file__).parents[1]
    platforms = (root / "editor" / "platforms.py").read_text(encoding="utf-8")
    steam_profiles = (root / "editor" / "steam_profiles.py").read_text(encoding="utf-8")
    s2_catalog = (root / "editor" / "s2_catalog.py").read_text(encoding="utf-8")

    for source in (platforms, steam_profiles, s2_catalog):
        assert "1643320" not in source
        assert "2427410" not in source
        assert "2427420" not in source
        assert "2427430" not in source
