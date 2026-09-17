from __future__ import annotations

import struct
import zlib

import pytest

import save_format as sf
from editor.kraken_blocks import (
    BLOCK_SIZE,
    CompactRebuildResult,
    KrakenBlocksError,
    compact_rebuild_stream,
    parse_kraken_stream,
)


def _stored_quantum(raw: bytes, *, restart: bool = True, decoder: int = 6) -> bytes:
    first = 0x8C if restart else 0x0C
    # A 256 KiB compressed payload would use Kraken's reserved all-ones
    # quantum value.  These tests exercise framing and dependency decisions,
    # not native decoding, so use a one-byte placeholder for full quanta.
    payload = raw if len(raw) < BLOCK_SIZE else b"x"
    qvalue = len(payload) - 1
    return bytes((first, decoder)) + qvalue.to_bytes(3, "big") + payload


def _container(raw: bytes, blocks: tuple[bytes, ...]) -> bytes:
    stream = b"".join(blocks)
    body = struct.pack("<I", len(raw)) + stream
    return body + struct.pack("<I", zlib.crc32(body) & 0xFFFFFFFF)


def _three_block_source() -> tuple[bytes, bytes, tuple[bytes, ...]]:
    raw = b"A" * BLOCK_SIZE + b"B" * BLOCK_SIZE + b"C" * 17
    blocks = (
        _stored_quantum(raw[:BLOCK_SIZE], restart=True),
        _stored_quantum(raw[BLOCK_SIZE : 2 * BLOCK_SIZE], restart=False),
        _stored_quantum(raw[2 * BLOCK_SIZE :], restart=True),
    )
    return _container(raw, blocks), raw, blocks


def test_parse_kraken_stream_tracks_quantum_boundaries_and_last_size() -> None:
    source, raw, _blocks = _three_block_source()
    layout = parse_kraken_stream(source[4:-4], len(raw))
    assert [block.raw_size for block in layout.blocks] == [BLOCK_SIZE, BLOCK_SIZE, 17]
    assert [block.compressed_size for block in layout.blocks] == [1, 1, 17]
    assert layout.blocks[-1].end == len(source) - 8


def test_compact_rebuild_preserves_clean_restart_block_and_rebuilds_dirty_chain() -> None:
    source, original_raw, original_blocks = _three_block_source()
    changed = b"Z" + original_raw[1:]
    result = compact_rebuild_stream(
        source[4:-4], original_raw=original_raw, new_raw=changed,
    )
    assert isinstance(result, CompactRebuildResult)
    assert result.mode == "compact"
    assert result.rebuilt_blocks == 2
    assert result.preserved_blocks == 1
    assert result.stream.endswith(original_blocks[2])
    assert result.stream.startswith(b"\xCC\x06" + changed[:BLOCK_SIZE])


def test_compact_rebuild_noop_is_byte_identical() -> None:
    source, raw, _blocks = _three_block_source()
    result = compact_rebuild_stream(
        source[4:-4], original_raw=raw, new_raw=raw,
    )
    assert result.mode == "unchanged"
    assert result.stream == source[4:-4]
    assert result.preserved_blocks == 3
    assert result.rebuilt_blocks == 0


def test_compact_rebuild_length_change_uses_explicit_full_fallback() -> None:
    source, original_raw, _blocks = _three_block_source()
    changed = original_raw + b"tail"
    result = compact_rebuild_stream(
        source[4:-4], original_raw=original_raw, new_raw=changed,
    )
    assert result.mode == "full-fallback"
    assert result.preserved_blocks == 0
    assert result.rebuilt_blocks == 0
    assert "length" in result.reason.lower()
    assert result.stream == b"".join(
        b"\xCC\x06" + changed[offset : offset + BLOCK_SIZE]
        for offset in range(0, len(changed), BLOCK_SIZE)
    )


def test_compact_rebuild_unsupported_decoder_uses_full_fallback() -> None:
    raw = b"payload"
    source = _container(raw, (_stored_quantum(raw, decoder=10),))
    result = compact_rebuild_stream(
        source[4:-4], original_raw=raw, new_raw=b"changed",
    )
    assert result.mode == "full-fallback"
    assert "decoder" in result.reason.lower()
    assert result.stream == b"\xCC\x06changed"


def test_save_rebuild_unsupported_stream_returns_valid_full_container() -> None:
    raw = b"payload"
    source = _container(raw, (_stored_quantum(raw, decoder=10),))
    rebuilt, decision = sf.rebuild_compact(
        source, b"changed", original_raw=raw,
    )

    assert decision.mode == "full-fallback"
    assert sf.validate_crc(rebuilt)[2] is True
    assert sf.decompress_save(rebuilt) == b"changed"


def test_parse_kraken_stream_rejects_trailing_bytes() -> None:
    source, raw, _blocks = _three_block_source()
    with pytest.raises(KrakenBlocksError, match="trailing|лишн"):
        parse_kraken_stream(source[4:-4] + b"x", len(raw))


def test_patch_save_reports_compact_rebuild_and_keeps_roundtrip(synthetic_save: bytes) -> None:
    result = sf.patch_save(synthetic_save, new_money=900_000)

    assert result.rebuild_mode == "compact"
    assert result.rebuilt_blocks == 1
    assert result.preserved_blocks == 0
    assert sf.decompress_save(result.data) != sf.decompress_save(synthetic_save)
    assert sf.inspect_save(result.data).crc_ok is True


def test_patch_save_noop_preserves_original_container_bytes(synthetic_save: bytes) -> None:
    raw = sf.decompress_save(synthetic_save)
    result = sf.patch_save(
        synthetic_save,
        raw_patches=[sf.RawPatch(0, "u8", str(raw[0]), "same-byte no-op")],
    )

    assert result.rebuild_mode == "unchanged"
    assert result.data == synthetic_save
    assert sf.inspect_save(result.data).crc_ok is True


def test_patch_save_variable_length_edit_reports_full_fallback(synthetic_save: bytes) -> None:
    result = sf.patch_save(synthetic_save, detach={0x30000002: False})

    assert result.rebuild_mode == "full-fallback"
    assert "length" in result.rebuild_reason.lower()
    assert sf.inspect_save(result.data).crc_ok is True
