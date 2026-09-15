from __future__ import annotations

import struct

import pytest

from editor.xray_container import (
    XRayContainer,
    XRayError,
    lzo1x_compress,
    lzo1x_decompress,
)


def _chunk(kind: int, payload: bytes) -> bytes:
    return struct.pack("<II", kind, len(payload)) + payload


def _raw_payload() -> bytes:
    spawn = _chunk(0, b"all\x00" + bytes(range(16))) + _chunk(1, struct.pack("<I", 7))
    return b"".join(
        (
            _chunk(0, struct.pack("<I", 3)),
            _chunk(5, struct.pack("<Qff", 123456, 10.0, 1.0)),
            _chunk(1, spawn),
            _chunk(9, b"registry bytes"),
        )
    )


def _container(version: int = 3) -> bytes:
    payload = _raw_payload()
    return struct.pack("<III", 0xFFFFFFFF, version, len(payload)) + lzo1x_compress(payload)


@pytest.mark.parametrize(
    "payload",
    (b"", b"a", bytes(range(238)), bytes(range(239)) * 3, b"abc" * 1000),
)
def test_lzo1x_round_trip(payload: bytes) -> None:
    packed = lzo1x_compress(payload)

    assert lzo1x_decompress(packed, len(payload)) == payload


def test_lzo_extended_m4_length_reads_length_bytes_before_offset() -> None:
    """Keep the M4 length-extension order compatible with X-Ray/liblzo."""

    # Seed the 16 KiB M4 window with a small literal run, grow it with M1
    # matches, then use an extended M4 match. Reading the offset first
    # desynchronizes real X-Ray streams that contain commands such as 0x10.
    raw = (
        bytes([255])
        + b"A" * 238
        + b"\x40\x00" * 5383
        + b"\x10\x01\x04\x00"
        + b"\x11\x00\x00"
    )
    expected = b"A" * (238 + 5383 * 3 + 10)

    assert lzo1x_decompress(raw, len(expected)) == expected


def test_xray_container_build_without_edits_is_byte_identical() -> None:
    data = _container()

    parsed = XRayContainer.from_bytes(data)

    assert parsed.magic == 0xFFFFFFFF
    assert parsed.version == 3
    assert parsed.unpacked_size == len(_raw_payload())
    assert parsed.raw == _raw_payload()
    assert parsed.build() == data
    assert parsed.chunk_types == (0, 5, 1, 9)


def test_xray_container_rebuilds_changed_payload_with_same_structure() -> None:
    parsed = XRayContainer.from_bytes(_container())
    changed = parsed.raw.replace(b"registry bytes", b"changed bytes ")

    rebuilt = parsed.build(changed)
    reparsed = XRayContainer.from_bytes(rebuilt)

    assert rebuilt != parsed.original
    assert reparsed.raw == changed
    assert reparsed.chunk_types == parsed.chunk_types


@pytest.mark.parametrize(
    "data, message",
    (
        (b"", "заголовок"),
        (b"\x00" * 4 + b"\xFF" * 8, "сигнатура"),
        (struct.pack("<III", 0xFFFFFFFF, 4, 1) + b"\x11\x00\x00", "версия"),
        (struct.pack("<III", 0xFFFFFFFF, 3, 10) + b"bad", "LZO"),
        (struct.pack("<III", 0xFFFFFFFF, 3, 4) + lzo1x_compress(b"bad"), "размер"),
    ),
)
def test_xray_container_rejects_malformed_input(data: bytes, message: str) -> None:
    with pytest.raises(XRayError, match=message):
        XRayContainer.from_bytes(data)


def test_xray_container_rejects_truncated_chunk() -> None:
    raw = struct.pack("<II", 0, 4) + b"\x03\x00"
    data = struct.pack("<III", 0xFFFFFFFF, 3, len(raw)) + lzo1x_compress(raw)

    with pytest.raises(XRayError, match="chunk|обрезан"):
        XRayContainer.from_bytes(data)


def test_lzo1x_rejects_wrong_output_size() -> None:
    packed = lzo1x_compress(b"payload")

    with pytest.raises(XRayError, match="размер|size"):
        lzo1x_decompress(packed, 6)
