from __future__ import annotations

import struct

import pytest

import save_format as sf

STACK_HANDLE = 0x30000001
VISIBLE_SINGLE_HANDLE = 0x30000002
ORPHAN_HANDLE = 0x30000003
UNKNOWN_ORPHAN_HANDLE = 0x30000004


def _item(save: bytes, handle: int) -> sf.InventoryItem:
    info = sf.inspect_save(save)
    return next(item for item in info.inventory if item.handle == handle)


def test_synthetic_fixture_describes_layout_without_private_save_bytes(synthetic_save: bytes) -> None:
    info = sf.inspect_save(synthetic_save)

    assert info.money == 100
    assert info.money_anchor_count == 1
    assert info.owned_handles == (
        STACK_HANDLE,
        VISIBLE_SINGLE_HANDLE,
        ORPHAN_HANDLE,
        UNKNOWN_ORPHAN_HANDLE,
    )
    assert info.grid_cell_count == 2
    assert len(info.inventory) == 2
    assert {item.handle for item in info.inventory} == {
        STACK_HANDLE,
        VISIBLE_SINGLE_HANDLE,
    }
    assert {item.handle for item in info.orphans} == {
        ORPHAN_HANDLE,
        UNKNOWN_ORPHAN_HANDLE,
    }

    stack = _item(synthetic_save, STACK_HANDLE)
    assert (stack.x, stack.y, stack.width, stack.height) == (0, 0, 1, 1)
    assert stack.count == 2
    assert stack.total_weight == pytest.approx(0.2)
    assert stack.editable_count is True


def test_money_patch_round_trip_changes_only_four_wallet_bytes(synthetic_save: bytes) -> None:
    before = sf.decompress_save(synthetic_save)
    money_offset, old_money = sf.locate_money(before)
    assert old_money == 100

    result = sf.patch_save(synthetic_save, new_money=900_000)
    after = sf.decompress_save(result.data)

    assert sf.locate_money(after)[1] == 900_000
    assert result.old_money == 100
    assert result.new_money == 900_000
    changed = {i for i, (left, right) in enumerate(zip(before, after, strict=True)) if left != right}
    assert changed <= set(range(money_offset, money_offset + 4))
    assert len(changed) > 0
    assert sf.inspect_save(result.data).crc_ok is True


def test_stack_patch_updates_count_and_cached_total_weight_only(synthetic_save: bytes) -> None:
    before = sf.decompress_save(synthetic_save)
    stack = _item(synthetic_save, STACK_HANDLE)

    result = sf.patch_save(synthetic_save, stack_counts={STACK_HANDLE: 3})
    after = sf.decompress_save(result.data)
    edited = _item(result.data, STACK_HANDLE)

    assert edited.count == 3
    assert edited.total_weight == pytest.approx(0.3, abs=1e-6)
    assert result.changed_stacks == ((STACK_HANDLE, 2, 3),)
    allowed = set(range(stack.record_offset + sf.STACK_COUNT_OFFSET, stack.record_offset + sf.STACK_COUNT_OFFSET + 4))
    allowed |= set(range(stack.record_offset + sf.STACK_WEIGHT_OFFSET, stack.record_offset + sf.STACK_WEIGHT_OFFSET + 4))
    changed = {i for i, (left, right) in enumerate(zip(before, after, strict=True)) if left != right}
    assert changed <= allowed
    assert changed


def test_bad_crc_is_rejected_before_any_patch(synthetic_save: bytes) -> None:
    broken = bytearray(synthetic_save)
    broken[-1] ^= 0x01

    with pytest.raises(sf.SaveError, match="CRC32"):
        sf.patch_save(bytes(broken), new_money=900_000)


def test_missing_money_anchor_is_rejected(synthetic_save: bytes) -> None:
    raw = sf.decompress_save(synthetic_save)
    replacement = b"\xA5" * len(sf.MONEY_ANCHOR)
    raw_without_anchor = raw.replace(sf.MONEY_ANCHOR, replacement, 1)
    broken = sf.rebuild_uncompressed(raw_without_anchor)

    with pytest.raises(sf.SaveError, match="найдена 0"):
        sf.patch_save(broken, new_money=900_000)


def test_duplicate_money_anchor_is_rejected(synthetic_save: bytes) -> None:
    raw = sf.decompress_save(synthetic_save) + sf.MONEY_ANCHOR
    broken = sf.rebuild_uncompressed(raw)

    with pytest.raises(sf.SaveError, match="найдена 2"):
        sf.patch_save(broken, new_money=900_000)


def test_invalid_money_range_is_rejected(synthetic_save: bytes) -> None:
    for value in (-1, 2_000_000_001):
        with pytest.raises(sf.SaveError, match="0 до 2 000 000 000"):
            sf.patch_save(synthetic_save, new_money=value)


def test_empty_patch_is_rejected(synthetic_save: bytes) -> None:
    with pytest.raises(sf.SaveError, match="Нет изменений"):
        sf.patch_save(synthetic_save)


def test_fixture_has_expected_little_endian_record_fields(synthetic_save: bytes) -> None:
    raw = sf.decompress_save(synthetic_save)
    stack = _item(synthetic_save, STACK_HANDLE)

    assert struct.unpack_from("<I", raw, stack.record_offset)[0] == STACK_HANDLE
    assert struct.unpack_from("<H", raw, stack.record_offset + sf.OBJ_POS_X_OFFSET)[0] == 0
    assert struct.unpack_from("<H", raw, stack.record_offset + sf.OBJ_POS_Y_OFFSET)[0] == 0
    assert raw[stack.record_offset + sf.STACK_MARKER_OFFSET] == 0x38
    assert struct.unpack_from("<I", raw, stack.record_offset + sf.STACK_COUNT_OFFSET)[0] == 2
    assert struct.unpack_from("<f", raw, stack.record_offset + sf.STACK_WEIGHT_OFFSET)[0] == pytest.approx(0.2)
