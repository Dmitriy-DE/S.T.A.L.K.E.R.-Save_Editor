from __future__ import annotations

from editor.equipment_matrix import equipment_profile_for_release, equipment_profiles
from editor.releases import official_releases


def test_equipment_matrix_covers_every_registered_release_once() -> None:
    profiles = equipment_profiles()
    releases = official_releases()

    assert [profile.release_id for profile in profiles] == [release.id for release in releases]
    assert all(profile.categories for profile in profiles)
    assert all(profile.icon_source for profile in profiles)


def test_matrix_keeps_per_game_equipment_rules_explicit() -> None:
    soc = equipment_profile_for_release("stalker-soc")
    cop = equipment_profile_for_release("stalker-cop")
    s2 = equipment_profile_for_release("stalker2")
    ee = equipment_profile_for_release("stalker-cop-ee")

    assert soc.support("upgrades").maturity == "unsupported"
    assert "helmet" not in soc.categories
    assert set(soc.categories) >= {"module", "device"}
    assert "helmet" in cop.categories
    assert s2.support("upgrades").maturity == "research"
    assert s2.support("durability").maturity == "experimental"
    assert set(s2.device_subtypes) >= {"nvg", "binocular", "detector"}
    assert all(
        ee.support(feature).maturity == "unsupported"
        for feature in ("durability", "upgrades", "placement", "add", "remove")
    )
