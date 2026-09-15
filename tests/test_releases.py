from __future__ import annotations

import pytest

from editor.releases import official_releases, release_by_id


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
