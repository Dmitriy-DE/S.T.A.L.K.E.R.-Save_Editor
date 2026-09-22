from __future__ import annotations

import struct

import save_format as sf

EQUIPPED_HANDLE = 0x300009BB
ORPHAN_HANDLE = 0x30000003
WEAPON_HANDLE = 0x30000AAA


def _equipped_record(handle: int = EQUIPPED_HANDLE, condition: float = 0.75) -> bytes:
    record = bytearray(0x90)
    struct.pack_into("<I", record, 0, handle)
    record[8:11] = b"\x01\x20\x01"
    struct.pack_into("<HH", record, sf.OBJ_POS_X_OFFSET, 0xFFFF, 0xFFFF)
    record[sf.STACK_MARKER_OFFSET] = 0x38
    struct.pack_into("<I", record, sf.STACK_COUNT_OFFSET, 1)
    struct.pack_into("<f", record, sf.STACK_WEIGHT_OFFSET, 8.5)
    record[sf.STACK_KIND_OFFSET] = 1
    nested = 0x23
    struct.pack_into("<I", record, nested, handle)
    struct.pack_into("<f", record, nested + 4, condition)
    return bytes(record)


def _save_with_equipped_armor(
    synthetic_save: bytes,
    *,
    display_name: str = "Exoskeleton_Monolith_Armor",
) -> bytes:
    raw = sf.decompress_save(synthetic_save)
    layout = sf.locate_inventory_layout(raw)
    raw = sf._rebuild_inventory_arrays(
        raw,
        owned_handles=(*layout.owned_handles, EQUIPPED_HANDLE),
        grid_cells=layout.grid_cells,
    )
    names = [""] * 289
    names[0] = "GunAK74_ST"
    names[0x120] = display_name
    name_table = struct.pack("<H", len(names))
    name_table += b"".join(
        struct.pack("<H", len(value.encode("utf-8"))) + value.encode("utf-8")
        for value in names
    )
    return sf.rebuild_uncompressed(raw + _equipped_record() + name_table)


def _s2_key(index: int) -> bytes:
    return bytes((4, index & 0xFF, index >> 8))


def _grid_weapon_record(condition: float = 0.75) -> bytes:
    record = bytearray(0x220)
    struct.pack_into("<I", record, 0, WEAPON_HANDLE)
    record[8:11] = _s2_key(0x120)
    struct.pack_into("<HH", record, sf.OBJ_POS_X_OFFSET, 2, 1)
    record[sf.STACK_MARKER_OFFSET] = 0x38
    struct.pack_into("<I", record, sf.STACK_COUNT_OFFSET, 1)
    struct.pack_into("<f", record, sf.STACK_WEIGHT_OFFSET, 4.0)
    record[sf.STACK_KIND_OFFSET] = 0
    condition_offset = 0x80
    modules = (_s2_key(0x121), _s2_key(0x122))
    for index, key in enumerate(modules):
        start = condition_offset - len(modules) * 3 + index * 3
        record[start : start + 3] = key
    struct.pack_into("<fH", record, condition_offset, condition, 2)
    for index, key in enumerate((_s2_key(0x123), _s2_key(0x124))):
        start = condition_offset + 6 + index * 3
        record[start : start + 3] = key
    return bytes(record)


def _save_with_grid_weapon(synthetic_save: bytes, *, condition: float = 0.75) -> bytes:
    raw = sf.decompress_save(synthetic_save)
    layout = sf.locate_inventory_layout(raw)
    raw = sf._rebuild_inventory_arrays(
        raw,
        owned_handles=(*layout.owned_handles, WEAPON_HANDLE),
        grid_cells=(*layout.grid_cells, sf.GridCell(WEAPON_HANDLE, 2, 1)),
    )
    names = [""] * 0x125
    names[0] = "GunAK74_ST"
    names[0x120] = "GunKharod_ST"
    names[0x121] = "GunKharod_MagDefault"
    names[0x122] = "HP_Laser_1"
    names[0x123] = "GunKharod_Upgrade_Stock_1"
    names[0x124] = "GunKharod_Upgrade_Barrel_1"
    name_table = struct.pack("<H", len(names))
    name_table += b"".join(
        struct.pack("<H", len(value.encode("utf-8"))) + value.encode("utf-8")
        for value in names
    )
    return sf.rebuild_uncompressed(raw + _grid_weapon_record(condition) + name_table)


def test_s2_equipped_armor_is_listed_with_editable_condition(
    synthetic_save: bytes,
) -> None:
    save = _save_with_equipped_armor(synthetic_save)

    info = sf.inspect_save(save, with_inventory=True)
    item = next(item for item in info.inventory if item.handle == EQUIPPED_HANDLE)

    assert item.position_label == "экипировано"
    assert item.x is None and item.y is None
    assert item.cells == ()
    assert item.condition == 0.75
    assert item.condition_editable is True
    assert item.display_name == "Exoskeleton_Monolith_Armor"
    assert item.observation_source == "equipped"


def test_s2_grid_weapon_exposes_condition_modules_and_upgrades(
    synthetic_save: bytes,
) -> None:
    save = _save_with_grid_weapon(synthetic_save, condition=0.75)

    item = next(
        item for item in sf.inspect_save(save).inventory if item.handle == WEAPON_HANDLE
    )

    assert item.storage == "inventory"
    assert item.observation_source == "grid"
    assert item.display_name == "Kharod"
    assert item.condition == 0.75
    assert item.condition_editable is True
    assert item.modules == ("GunKharod_MagDefault", "HP_Laser_1")
    assert item.upgrades == (
        "GunKharod_Upgrade_Stock_1",
        "GunKharod_Upgrade_Barrel_1",
    )


def test_s2_presentation_labels_cover_observed_devices_without_changing_unknowns() -> None:
    from editor.s2_presentation import s2_presentation_name

    assert s2_presentation_name("NVG_NPC_Gen3") == "ПНВ (3-е поколение)"
    assert s2_presentation_name("Binoculars_03") == "Бинокль"
    assert s2_presentation_name("unmapped_save_name") == "unmapped_save_name"


def test_s2_shape_guard_does_not_reclassify_existing_synthetic_orphan(
    synthetic_save: bytes,
) -> None:
    info = sf.inspect_save(synthetic_save, with_inventory=True)

    assert ORPHAN_HANDLE in {item.handle for item in info.orphans}
    assert ORPHAN_HANDLE not in {item.handle for item in info.inventory}
