from __future__ import annotations

import math
import struct

import pytest

from editor.s2_item_state import (
    S2ItemStateError,
    patch_s2_armor_condition,
    patch_s2_weapon_condition,
    read_s2_armor_condition,
    read_s2_weapon_condition,
)

HANDLE = 0x300009BB
RECORD_OFFSET = 19
NESTED_OFFSET = RECORD_OFFSET + 0x23
VALUE_OFFSET = NESTED_OFFSET + 4


def _record(*, condition: float = 0.75, nested_handle: int = HANDLE, kind: int = 1) -> bytearray:
    raw = bytearray(RECORD_OFFSET + 0x90)
    struct.pack_into("<I", raw, RECORD_OFFSET, HANDLE)
    raw[RECORD_OFFSET + 31] = kind
    struct.pack_into("<I", raw, NESTED_OFFSET, nested_handle)
    struct.pack_into("<f", raw, VALUE_OFFSET, condition)
    return raw


def test_reads_exact_nested_s2_armor_condition_anchor() -> None:
    raw = _record(condition=0.7392341)

    anchor = read_s2_armor_condition(
        bytes(raw),
        handle=HANDLE,
        record_offset=RECORD_OFFSET,
        kind_code=1,
    )

    assert anchor is not None
    assert anchor.handle == HANDLE
    assert anchor.record_offset == RECORD_OFFSET
    assert anchor.nested_offset == NESTED_OFFSET
    assert anchor.value_offset == VALUE_OFFSET
    assert anchor.value == pytest.approx(0.7392341)


def test_patches_only_the_confirmed_four_condition_bytes() -> None:
    raw = _record(condition=0.25)
    before = bytes(raw)

    anchor = patch_s2_armor_condition(
        raw,
        handle=HANDLE,
        record_offset=RECORD_OFFSET,
        kind_code=1,
        value=0.9,
    )

    assert anchor.value == pytest.approx(0.9)
    changed = {
        index
        for index, (left, right) in enumerate(zip(before, raw, strict=True))
        if left != right
    }
    assert changed <= set(range(VALUE_OFFSET, VALUE_OFFSET + 4))
    assert changed
    assert struct.unpack_from("<f", raw, VALUE_OFFSET)[0] == pytest.approx(0.9)


@pytest.mark.parametrize(
    ("raw", "kind", "expected"),
    (
        (_record(kind=0), 0, None),
        (_record(nested_handle=0x30000001), 1, None),
        (_record(condition=math.nan), 1, None),
        (_record(condition=1.25), 1, None),
    ),
)
def test_reader_returns_unknown_for_unsupported_or_malformed_state(
    raw: bytearray,
    kind: int,
    expected: None,
) -> None:
    assert (
        read_s2_armor_condition(
            bytes(raw),
            handle=HANDLE,
            record_offset=RECORD_OFFSET,
            kind_code=kind,
        )
        is expected
    )


@pytest.mark.parametrize("value", (-0.01, 1.01, math.nan, math.inf, -math.inf))
def test_writer_rejects_condition_outside_normalized_range(value: float) -> None:
    with pytest.raises(S2ItemStateError, match="condition"):
        patch_s2_armor_condition(
            _record(),
            handle=HANDLE,
            record_offset=RECORD_OFFSET,
            kind_code=1,
            value=value,
        )


def test_writer_rejects_record_handle_mismatch() -> None:
    with pytest.raises(S2ItemStateError, match="handle"):
        patch_s2_armor_condition(
            _record(),
            handle=0x30000001,
            record_offset=RECORD_OFFSET,
            kind_code=1,
            value=0.5,
        )


def test_writer_rejects_handle_outside_u32() -> None:
    with pytest.raises(S2ItemStateError, match="handle"):
        patch_s2_armor_condition(
            _record(),
            handle=0x1_0000_0000,
            record_offset=RECORD_OFFSET,
            kind_code=1,
            value=0.5,
        )


WEAPON_HANDLE = 0x30002D01
WEAPON_RECORD_OFFSET = 23
WEAPON_CONDITION_OFFSET = WEAPON_RECORD_OFFSET + 0x80
WEAPON_NAMES = (
    "",
    "GunKharod_MagDefault",
    "HP_Laser_1",
    "EN_Silen_3",
    "GunKharod_Upgrade_Stock_1",
    "GunKharod_Upgrade_Barrel_1",
)


def _s2_key(index: int) -> bytes:
    return bytes((4, index & 0xFF, index >> 8))


def _weapon_record(*, condition: float = 0.5, kind: int = 0) -> bytearray:
    raw = bytearray(WEAPON_RECORD_OFFSET + 0x200)
    struct.pack_into("<I", raw, WEAPON_RECORD_OFFSET, WEAPON_HANDLE)
    raw[WEAPON_RECORD_OFFSET + 31] = kind
    modules = (_s2_key(1), _s2_key(2), _s2_key(3))
    module_start = WEAPON_CONDITION_OFFSET - len(modules) * 3
    for index, key in enumerate(modules):
        start = module_start + index * 3
        raw[start : start + 3] = key
    struct.pack_into("<fH", raw, WEAPON_CONDITION_OFFSET, condition, 2)
    upgrades_start = WEAPON_CONDITION_OFFSET + 6
    for index, key in enumerate((_s2_key(4), _s2_key(5))):
        start = upgrades_start + index * 3
        raw[start : start + 3] = key
    return raw


def test_reads_s2_weapon_condition_and_separates_modules_from_upgrades() -> None:
    anchor = read_s2_weapon_condition(
        bytes(_weapon_record(condition=0.86)),
        handle=WEAPON_HANDLE,
        record_offset=WEAPON_RECORD_OFFSET,
        record_end=WEAPON_RECORD_OFFSET + 0x200,
        kind_code=0,
        name_table=WEAPON_NAMES,
    )

    assert anchor is not None
    assert anchor.value == pytest.approx(0.86)
    assert anchor.value_offset == WEAPON_CONDITION_OFFSET
    assert anchor.modules == (
        "GunKharod_MagDefault",
        "HP_Laser_1",
        "EN_Silen_3",
    )
    assert anchor.upgrades == (
        "GunKharod_Upgrade_Stock_1",
        "GunKharod_Upgrade_Barrel_1",
    )


@pytest.mark.parametrize(
    ("module_names", "upgrade_names"),
    (
        (
            ("GunLavina_MagDefault", "TopRailLavina", "RU_Grip_1"),
            ("GunLavina_Upgrade_Stock_1", "GunLavina_Upgrade_Barrel_1"),
        ),
        (
            ("GunD12_MagDefault", "TopRailD12", "HP_Laser_2"),
            ("GunD12_Upgrade_Stock_1", "GunD12_Upgrade_Barrel_1"),
        ),
        (
            ("GunPM_MagIncreased", "RU_Silen_1", "HP_Laser_1"),
            ("GunPM_Upgrade_Grip_1", "GunPM_Upgrade_Sight_1"),
        ),
    ),
)
def test_weapon_condition_codec_is_not_hardcoded_to_one_weapon_family(
    module_names: tuple[str, str, str],
    upgrade_names: tuple[str, str],
) -> None:
    names = ("", *module_names, *upgrade_names)
    anchor = read_s2_weapon_condition(
        bytes(_weapon_record(condition=0.61)),
        handle=WEAPON_HANDLE,
        record_offset=WEAPON_RECORD_OFFSET,
        record_end=WEAPON_RECORD_OFFSET + 0x200,
        kind_code=0,
        name_table=names,
    )

    assert anchor is not None
    assert anchor.modules == module_names
    assert anchor.upgrades == upgrade_names


def test_patches_only_s2_weapon_condition_bytes() -> None:
    raw = _weapon_record(condition=0.25)
    before = bytes(raw)

    anchor = patch_s2_weapon_condition(
        raw,
        handle=WEAPON_HANDLE,
        record_offset=WEAPON_RECORD_OFFSET,
        record_end=WEAPON_RECORD_OFFSET + 0x200,
        kind_code=0,
        name_table=WEAPON_NAMES,
        value=0.95,
    )

    changed = {
        index
        for index, (left, right) in enumerate(zip(before, raw, strict=True))
        if left != right
    }
    assert changed == set(
        range(WEAPON_CONDITION_OFFSET, WEAPON_CONDITION_OFFSET + 4)
    )
    assert anchor.value == pytest.approx(0.95)


def test_weapon_reader_prefers_primary_state_over_late_embedded_snapshot() -> None:
    names = (*WEAPON_NAMES,
        "GunLavina_MagDefault",
        "TopRailLavina",
        "GunLavina_Upgrade_Stock_1",
        "GunLavina_Upgrade_Barrel_1",
    )
    raw = bytearray(_weapon_record(condition=0.86))
    late_condition = WEAPON_RECORD_OFFSET + 0x600
    raw.extend(b"\x00" * (WEAPON_RECORD_OFFSET + 0x800 - len(raw)))
    late_modules = (_s2_key(6), _s2_key(7))
    for index, key in enumerate(late_modules):
        start = late_condition - len(late_modules) * 3 + index * 3
        raw[start : start + 3] = key
    struct.pack_into("<fH", raw, late_condition, 0.39, 2)
    for index, key in enumerate((_s2_key(8), _s2_key(9))):
        start = late_condition + 6 + index * 3
        raw[start : start + 3] = key

    anchor = read_s2_weapon_condition(
        bytes(raw),
        handle=WEAPON_HANDLE,
        record_offset=WEAPON_RECORD_OFFSET,
        record_end=WEAPON_RECORD_OFFSET + 0x800,
        kind_code=0,
        name_table=names,
    )

    assert anchor is not None
    assert anchor.value == pytest.approx(0.86)
    assert anchor.modules == (
        "GunKharod_MagDefault",
        "HP_Laser_1",
        "EN_Silen_3",
    )


@pytest.mark.parametrize(
    "kind",
    (1, 4),
)
def test_s2_weapon_condition_does_not_classify_armor_or_devices(kind: int) -> None:
    assert (
        read_s2_weapon_condition(
            bytes(_weapon_record(kind=kind)),
            handle=WEAPON_HANDLE,
            record_offset=WEAPON_RECORD_OFFSET,
            record_end=WEAPON_RECORD_OFFSET + 0x200,
            kind_code=kind,
            name_table=WEAPON_NAMES,
        )
        is None
    )
