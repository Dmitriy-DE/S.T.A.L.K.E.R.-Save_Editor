from __future__ import annotations

import struct

import pytest

import save_format as sf


def _mutate_raw(save: bytes, mutate) -> bytes:
    raw = bytearray(sf.decompress_save(save))
    mutate(raw)
    return sf.rebuild_uncompressed(bytes(raw))


def _layout(save: bytes) -> sf.InventoryLayout:
    return sf.locate_inventory_layout(sf.decompress_save(save))


def test_unknown_kind_is_visible_but_read_only(synthetic_save: bytes) -> None:
    layout = _layout(synthetic_save)
    handle = layout.grid_cells[0].handle
    record_offset, *_ = sf.locate_object_record(sf.decompress_save(synthetic_save), handle)
    changed = _mutate_raw(
        synthetic_save,
        lambda raw: raw.__setitem__(record_offset + sf.STACK_KIND_OFFSET, 99),
    )

    info = sf.inspect_save(changed)
    item = next(item for item in info.inventory if item.handle == handle)
    assert item.kind_code == 99
    assert item.editable_count is False
    assert info.grid_handle_count == 2
    assert any("unknown" in warning.lower() or "неизвест" in warning.lower() for warning in info.warnings)

    with pytest.raises(sf.SaveError, match="safe stack|подтверждённ|kind=99"):
        sf.patch_save(changed, stack_counts={handle: 3})


def test_grid_reference_to_unowned_handle_is_unresolved(synthetic_save: bytes) -> None:
    layout = _layout(synthetic_save)
    unknown_handle = 0x3000AAAA
    changed = _mutate_raw(
        synthetic_save,
        lambda raw: struct.pack_into("<I", raw, layout.grid_offset, unknown_handle),
    )

    info = sf.inspect_save(changed)
    assert unknown_handle in info.unresolved_handles
    assert info.grid_handle_count == 2
    assert any("owned" in warning.lower() for warning in info.warnings)
    assert all(item.handle != unknown_handle for item in info.inventory)


def test_out_of_bounds_grid_cell_is_unresolved_but_file_is_inspectable(
    synthetic_save: bytes,
) -> None:
    layout = _layout(synthetic_save)
    handle = layout.grid_cells[0].handle
    changed = _mutate_raw(
        synthetic_save,
        lambda raw: struct.pack_into("<H", raw, layout.grid_offset + 4, sf.GRID_WIDTH),
    )

    info = sf.inspect_save(changed)
    assert handle in info.unresolved_handles
    assert info.grid_cell_count == 2
    assert info.grid_handle_count == 2
    assert any("grid cell" in warning.lower() or "grid" in warning.lower() for warning in info.warnings)


def test_duplicate_grid_position_marks_both_handles_unresolved(synthetic_save: bytes) -> None:
    layout = _layout(synthetic_save)
    first, second = layout.grid_cells[:2]
    changed = _mutate_raw(
        synthetic_save,
        lambda raw: struct.pack_into(
            "<HH", raw, layout.grid_offset + sf.GRID_RECORD_SIZE + 4, first.x, first.y
        ),
    )

    info = sf.inspect_save(changed)
    assert first.handle in info.unresolved_handles
    assert second.handle in info.unresolved_handles
    assert any("duplicate" in warning.lower() or "дублик" in warning.lower() for warning in info.warnings)


def test_sparse_footprint_is_read_only_and_reported(synthetic_save: bytes) -> None:
    layout = _layout(synthetic_save)
    handle = layout.grid_cells[0].handle
    changed = _mutate_raw(
        synthetic_save,
        lambda raw: struct.pack_into(
            "<IHH", raw, layout.grid_offset + sf.GRID_RECORD_SIZE, handle, 2, 0
        ),
    )

    info = sf.inspect_save(changed)
    item = next(item for item in info.inventory if item.handle == handle)
    assert handle in info.unresolved_handles
    assert item.editable_count is False
    assert any("footprint" in warning.lower() or "коллиз" in warning.lower() for warning in info.warnings)


def test_empty_inventory_is_reported_without_guessing(synthetic_save: bytes) -> None:
    layout = _layout(synthetic_save)
    changed = _mutate_raw(
        synthetic_save,
        lambda raw: struct.pack_into("<H", raw, layout.grid_count_offset, 0),
    )

    info = sf.inspect_save(changed)
    assert info.inventory == ()
    assert info.grid_cell_count == 0
    assert info.grid_handle_count == 0
    assert any("empty" in warning.lower() or "пуст" in warning.lower() for warning in info.warnings)


def test_missing_object_record_becomes_unresolved(synthetic_save: bytes) -> None:
    layout = _layout(synthetic_save)
    handle = layout.grid_cells[0].handle
    record_offset, *_ = sf.locate_object_record(sf.decompress_save(synthetic_save), handle)
    changed = _mutate_raw(
        synthetic_save,
        lambda raw: raw.__setitem__(record_offset + sf.STACK_MARKER_OFFSET, 0),
    )

    info = sf.inspect_save(changed)
    assert handle in info.unresolved_handles
    assert all(item.handle != handle for item in info.inventory)
    assert any("record" in warning.lower() for warning in info.warnings)
