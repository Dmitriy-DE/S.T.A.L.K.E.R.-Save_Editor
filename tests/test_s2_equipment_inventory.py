from __future__ import annotations

import struct

import save_format as sf

EQUIPPED_HANDLE = 0x300009BB
ORPHAN_HANDLE = 0x30000003


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


def test_s2_shape_guard_does_not_reclassify_existing_synthetic_orphan(
    synthetic_save: bytes,
) -> None:
    info = sf.inspect_save(synthetic_save, with_inventory=True)

    assert ORPHAN_HANDLE in {item.handle for item in info.orphans}
    assert ORPHAN_HANDLE not in {item.handle for item in info.inventory}
