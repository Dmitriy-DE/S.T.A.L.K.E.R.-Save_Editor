"""S.T.A.L.K.E.R. 2 official names and icons from web/s2_items.json."""

from __future__ import annotations

import json
import re

import pytest

from editor import s2_items
from editor.i18n import set_language
from editor.s2_names import s2_readable_name


@pytest.fixture(autouse=True)
def _reset():
    yield
    s2_items._installed = None
    set_language("ru")


def test_official_names_follow_interface_language():
    set_language("en")
    assert s2_items.s2_official_name("GunAK74_ST") == "AKM-74S"
    assert s2_items.s2_official_name("EArtifactBattery") == "Battery"
    set_language("ru")
    assert s2_items.s2_official_name("GunAK74_ST") == "АКМ-74С"
    assert s2_items.s2_official_name("EArtifactBattery") == "Батарейка"


def test_guard_and_player_variants_resolve_to_the_base_weapon():
    assert s2_items.canonical_sid("GuardGunAK74_ST") == "GunAK74_ST"
    assert s2_items.canonical_sid("gunak74_st") == "GunAK74_ST"
    assert s2_items.s2_variant_of("Gun_SOFMOD_AR") == "AR416"
    assert s2_items.s2_icon_name("GuardGunAK74_ST") == "s2/GunAK74_ST.png"


def test_readable_name_prefers_official_name():
    set_language("en")
    assert s2_readable_name("A545D", kind_code=5) == "5.45x39mm PS"
    set_language("ru")
    assert s2_readable_name("GunLavina_Upgrade_Barrel_1") == s2_items.s2_official_name("GunLavina_Upgrade_Barrel_1")


def test_non_russian_interface_never_shows_russian_only_names():
    payload = {"items": {"OnlyRu": {"names": {"ru": "Только русское"}}}}
    s2_items.install(json.dumps(payload))
    set_language("de")
    assert s2_items.s2_official_name("OnlyRu") is None
    assert not re.search("[А-Яа-я]", s2_readable_name("OnlyRu") or "")


def test_unknown_empty_and_broken_inputs_fall_back():
    assert s2_items.s2_official_name(None) is None
    assert s2_items.canonical_sid("") is None
    assert s2_items.s2_entry("NoSuchSid_XYZ") is None
    assert s2_items.install("not json") == 0
    assert s2_items.s2_icon_name("GunAK74_ST") is None


def test_every_listed_icon_is_shipped():
    items = json.loads(s2_items.ITEMS_PATH.read_text(encoding="utf-8"))["items"]
    root = s2_items.ITEMS_PATH.parents[1] / "assets" / "icons"
    missing = [e["icon"] for e in items.values() if e.get("icon") and not (root / e["icon"]).is_file()]
    web_missing = [e["icon"] for e in items.values() if e.get("icon") and not (s2_items.ITEMS_PATH.parent / "icons" / e["icon"]).is_file()]
    assert missing == [] and web_missing == []


def test_coverage_floor_on_real_save_sids():
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
    import s2_coverage

    sids = json.loads((s2_items.ITEMS_PATH.parents[1] / "data" / "s2_sid_sample.json").read_text(encoding="utf-8"))["sids"]
    stats, _gaps = s2_coverage.coverage(sids)
    # Floors only go up; raise them as gaps are filled (docs/roadmap KB-4).
    for kind in ("weapon", "ammo"):
        assert stats[kind]["en"] == stats[kind]["icon"] == stats[kind]["total"]
    assert stats["item"]["en"] == stats["item"]["total"] and stats["item"]["icon"] >= 73
