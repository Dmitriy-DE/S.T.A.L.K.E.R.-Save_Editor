from __future__ import annotations

import struct

import save_format as sf


def _with_embedded_item_names(data: bytes) -> bytes:
    raw = bytearray(sf.decompress_save(data))
    record_offset, _count, _weight, _kind = sf.locate_object_record(
        raw, 0x30000001
    )
    raw[record_offset + 8 : record_offset + 11] = b"\x04\x01\x00"
    names = [""] * 3084
    names[:3] = ["GunAK74_ST", "Bandage", "Medkit"]
    raw += struct.pack("<H", len(names))
    for value in names:
        encoded = value.encode("utf-8")
        raw += struct.pack("<H", len(encoded)) + encoded
    return sf.rebuild_uncompressed(bytes(raw))


def test_s2_item_name_table_resolves_save_local_type_key(synthetic_save: bytes) -> None:
    data = _with_embedded_item_names(synthetic_save)

    info = sf.inspect_save(data)

    item = next(item for item in info.inventory if item.handle == 0x30000001)
    assert item.type_key == "040100"
    assert item.display_name == "Bandage"


def test_s2_item_name_table_keeps_unknown_key_unresolved(synthetic_save: bytes) -> None:
    raw = bytearray(sf.decompress_save(synthetic_save))
    record_offset, _count, _weight, _kind = sf.locate_object_record(
        raw, 0x30000001
    )
    raw[record_offset + 8 : record_offset + 11] = b"\x04\xff\x7f"
    raw += struct.pack("<H", 1) + struct.pack("<H", 10) + b"GunAK74_ST"

    info = sf.inspect_save(sf.rebuild_uncompressed(bytes(raw)))

    item = next(item for item in info.inventory if item.handle == 0x30000001)
    assert item.display_name is None


def test_s2_item_name_table_is_read_only_metadata() -> None:
    table = (
        struct.pack("<H", 2)
        + struct.pack("<H", 10)
        + b"GunAK74_ST"
        + struct.pack("<H", 7)
        + b"Bandage"
    )

    names = sf.locate_s2_item_name_table(table, (b"\x04\x01\x00",))

    assert names == ("GunAK74_ST", "Bandage")
