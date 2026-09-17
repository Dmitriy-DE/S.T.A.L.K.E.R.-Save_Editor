from __future__ import annotations

import struct

import pytest

from tools.analyze_attachments import (
    ADDON_MASKS,
    ADDON_STATUS_NAMES,
    WeaponAddonObservation,
    WeaponProfile,
    read_weapon_addon_state,
    weapon_profiles_from_ltx,
    weapon_profiles_from_sources,
)


def _z(value: str) -> bytes:
    return value.encode("utf-8") + b"\x00"


def _weapon_state(version: int, flags: int) -> bytes:
    """Build only the source-defined X-Ray weapon STATE prefix."""

    state = bytearray()
    if 24 < version < 83:
        state += struct.pack("<fHfIIH", 1.0, 15, 2.0, 0, 56, 0)
        state += _z("spawn")
        state += _z("weapon.ogf")
    else:
        state += struct.pack("<HfIII", 15, 2.0, 0, 56, 0)
        state += _z("[weapon]")
        state += struct.pack("<II", 0, 0)
        state += _z("weapon.ogf")
        state += b"\x00"  # dynamic visual flags
    if version > 52:
        state += struct.pack("<f", 0.75)  # inventory condition
    if version > 123:
        state += struct.pack("<I", 0)  # m_upgrades
    state += struct.pack("<HHB", 17, 4, 3)  # current, elapsed, weapon state
    if version > 40:
        state += bytes((flags,))
    if version > 46:
        state += b"\x01"  # ammo type
    if version > 122:
        state += b"\x00"  # grenade count/type
    return bytes(state)


def test_addon_masks_and_status_values_are_source_defined() -> None:
    assert ADDON_MASKS == {
        "scope": 0x01,
        "grenade_launcher": 0x02,
        "silencer": 0x04,
    }
    assert ADDON_STATUS_NAMES == {
        0: "disabled",
        1: "permanent",
        2: "attachable",
    }


def test_weapon_state_reads_flags_after_upgrades_and_preserves_unknown_bits() -> None:
    raw = _weapon_state(128, 0x80 | ADDON_MASKS["scope"] | ADDON_MASKS["silencer"])

    state = read_weapon_addon_state(raw, version=128, label="fixture weapon")

    assert state.addon_flags == 0x85
    assert state.addon_flags_offset == 60
    assert state.attached_slots == ("scope", "silencer")
    assert state.unknown_flags == 0x80


@pytest.mark.parametrize("version", (40, 39))
def test_weapon_state_before_addon_flag_boundary_is_read_only(version: int) -> None:
    state = read_weapon_addon_state(_weapon_state(version, 0), version=version, label="old")

    assert state.addon_flags is None
    assert state.addon_flags_offset is None
    assert state.attached_slots == ()
    assert state.reason == "addon flag is absent before weapon STATE version 41"


def test_weapon_profiles_resolve_status_component_and_scope_options() -> None:
    profiles = weapon_profiles_from_ltx(
        """
[wpn_test]:weapon_base
scope_status = 2
silencer_status = 1
grenade_launcher_status = 0
scopes_sect = scope_test, scope_test_night
silencer_name = wpn_addon_silencer

[weapon_base]
class = WP_RIFLE
""",
        source="configs/weapons/w_test.ltx",
    )

    profile = profiles["wpn_test"]
    assert profile.class_name == "WP_RIFLE"
    assert profile.statuses == (
        ("scope", "attachable"),
        ("grenade_launcher", "disabled"),
        ("silencer", "permanent"),
    )
    assert profile.components == (("silencer", "wpn_addon_silencer"),)
    assert profile.scope_options == ("scope_test", "scope_test_night")


def test_weapon_profiles_from_sources_ignore_non_release_weapon_paths() -> None:
    sources = {
        "configs/weapons/w_test.ltx": b"[wpn_test]\nclass=WP_RIFLE\nscope_status=2\n",
        "configs/mp/weapons_mp/weapons_mp.ltx": b"[mp_wpn_test]\nscope_status=2\n",
    }

    profiles = weapon_profiles_from_sources(sources)

    assert tuple(profiles) == ("wpn_test",)


def test_weapon_profiles_reject_unknown_status_without_enabling_compatibility() -> None:
    profiles = weapon_profiles_from_ltx(
        """
[wpn_test]
class = WP_RIFLE
scope_status = 9
""",
        source="fixture.ltx",
    )

    profile = profiles["wpn_test"]
    assert profile.statuses == (("scope", "unknown(9)"),)
    assert profile.components == ()


def test_effective_slots_keep_permanent_addons_separate_from_state_flags() -> None:
    state = read_weapon_addon_state(_weapon_state(128, ADDON_MASKS["silencer"]), version=128, label="fixture")
    profile = WeaponProfile(
        key="wpn_test",
        class_name="WP_RIFLE",
        statuses=(("scope", "permanent"), ("silencer", "attachable")),
        status_codes=(("scope", 1), ("silencer", 2)),
        components=(("scope", "wpn_addon_scope"), ("silencer", "wpn_addon_silencer")),
        scope_options=(),
        source="fixture",
    )
    observation = WeaponAddonObservation(
        object_id=1,
        name="wpn_test",
        version=128,
        state_offset=0,
        state=state,
        profile=profile,
        upgrades=(),
    )

    assert state.attached_slots == ("silencer",)
    assert observation.effective_attached_slots == ("scope", "silencer")
