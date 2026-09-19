from __future__ import annotations

import math
import struct

import pytest

from editor.s2_item_state import (
    S2ItemStateError,
    patch_s2_armor_condition,
    read_s2_armor_condition,
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
    changed = {index for index, (left, right) in enumerate(zip(before, raw)) if left != right}
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
