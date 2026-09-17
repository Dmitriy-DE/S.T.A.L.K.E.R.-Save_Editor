"""Bounded Kraken quantum framing and compact rebuild decisions.

The native Oodle decoder remains the authority for decoding a save.  This
module only parses the framing that is needed to decide which encoded blocks
can be copied byte-for-byte.  It never attempts to encode Kraken: a changed
quantum is emitted in the known valid ``CC06`` stored form instead.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

BLOCK_SIZE = 0x40000
MAX_BLOCK_COUNT = 1_000_000
_HEADER_SIZE = 2
_QUANTUM_HEADER_SIZE = 3
_DECODER_KRAKEN = 6
_QUANTUM_SIZE_MASK = 0x3FFFF
_UNCOMPRESSED_FLAG = 0x40
_RESTART_FLAG = 0x80
_HEADER_LOW_NIBBLE = 0x0F
_HEADER_RESERVED_MASK = 0x30
_CHECKSUM_FLAG = 0x80
_UNCOMPRESSED_BLOCK_HEADER = b"\xCC\x06"

RebuildMode = Literal["unchanged", "compact", "full-fallback"]


class KrakenBlocksError(ValueError):
    """The stream cannot be safely interpreted as supported Kraken blocks."""


@dataclass(frozen=True)
class KrakenBlock:
    """One framed Kraken quantum, with offsets relative to the stream."""

    offset: int
    end: int
    encoded: bytes
    raw_size: int
    compressed_size: int
    restart_decoder: bool
    uncompressed: bool
    decoder_type: int
    uses_checksums: bool


@dataclass(frozen=True)
class KrakenStreamLayout:
    """The proven quantum boundaries for one encoded stream."""

    blocks: tuple[KrakenBlock, ...]


@dataclass(frozen=True)
class CompactRebuildResult:
    """A stream plus an explicit decision about preservation or fallback."""

    stream: bytes
    mode: RebuildMode
    preserved_blocks: int
    rebuilt_blocks: int
    reason: str = ""


def _as_bytes(value: bytes | bytearray | memoryview, label: str) -> bytes:
    if not isinstance(value, (bytes, bytearray, memoryview)):
        raise KrakenBlocksError(f"{label} должен быть bytes-подобным")
    return bytes(value)


def _stored_stream(raw: bytes) -> bytes:
    if not raw:
        raise KrakenBlocksError("Нельзя пересобрать пустой raw payload")
    return b"".join(
        _UNCOMPRESSED_BLOCK_HEADER + raw[offset : offset + BLOCK_SIZE]
        for offset in range(0, len(raw), BLOCK_SIZE)
    )


def parse_kraken_stream(
    stream: bytes | bytearray | memoryview,
    unpacked_size: int,
) -> KrakenStreamLayout:
    """Parse supported Kraken quantum boundaries without decoding payloads.

    A two-byte quantum header appears before every block, not only before the
    stream.  The three-byte quantum header stores ``compressed_size - 1`` in
    its low 18 bits.  Only decoder type 6 without checksums is accepted here;
    all other variants are deliberately sent to the caller's full fallback.
    """

    encoded = _as_bytes(stream, "Kraken stream")
    if not isinstance(unpacked_size, int) or isinstance(unpacked_size, bool):
        raise KrakenBlocksError("Распакованный размер должен быть целым числом")
    if unpacked_size <= 0:
        raise KrakenBlocksError("Распакованный размер должен быть положительным")
    if unpacked_size > 512 * 1024 * 1024:
        raise KrakenBlocksError("Распакованный размер слишком большой")

    blocks: list[KrakenBlock] = []
    position = 0
    raw_total = 0
    while raw_total < unpacked_size:
        if len(blocks) >= MAX_BLOCK_COUNT:
            raise KrakenBlocksError("Слишком много Kraken blocks")
        block_offset = position
        if position + _HEADER_SIZE > len(encoded):
            raise KrakenBlocksError("Kraken block header обрезан")

        first, second = encoded[position : position + _HEADER_SIZE]
        position += _HEADER_SIZE
        if (first & _HEADER_LOW_NIBBLE) != 0x0C or first & _HEADER_RESERVED_MASK:
            raise KrakenBlocksError(
                f"Неподдерживаемый Kraken block header 0x{first:02X}{second:02X}"
            )

        restart_decoder = bool(first & _RESTART_FLAG)
        uncompressed = bool(first & _UNCOMPRESSED_FLAG)
        uses_checksums = bool(second & _CHECKSUM_FLAG)
        decoder_type = second & 0x7F
        if decoder_type != _DECODER_KRAKEN:
            raise KrakenBlocksError(
                f"Неподдерживаемый Kraken decoder type={decoder_type}"
            )
        if uses_checksums:
            raise KrakenBlocksError("Kraken blocks with checksums не поддержаны")

        raw_size = min(BLOCK_SIZE, unpacked_size - raw_total)
        if uncompressed:
            compressed_size = raw_size
        else:
            if position + _QUANTUM_HEADER_SIZE > len(encoded):
                raise KrakenBlocksError("Kraken quantum header обрезан")
            quantum_value = int.from_bytes(
                encoded[position : position + _QUANTUM_HEADER_SIZE], "big"
            )
            position += _QUANTUM_HEADER_SIZE
            compressed_size = quantum_value & _QUANTUM_SIZE_MASK
            if compressed_size == _QUANTUM_SIZE_MASK:
                raise KrakenBlocksError("Kraken special quantum size не поддержан")
            compressed_size += 1

        end = position + compressed_size
        if end > len(encoded):
            raise KrakenBlocksError("Kraken block payload обрезан")
        blocks.append(
            KrakenBlock(
                offset=block_offset,
                end=end,
                encoded=encoded[block_offset:end],
                raw_size=raw_size,
                compressed_size=compressed_size,
                restart_decoder=restart_decoder,
                uncompressed=uncompressed,
                decoder_type=decoder_type,
                uses_checksums=uses_checksums,
            )
        )
        position = end
        raw_total += raw_size

    if raw_total != unpacked_size:
        raise KrakenBlocksError(
            f"Kraken blocks декодируют {raw_total} bytes вместо {unpacked_size}"
        )
    if position != len(encoded):
        raise KrakenBlocksError(
            f"Kraken stream содержит trailing bytes: {len(encoded) - position}"
        )
    return KrakenStreamLayout(blocks=tuple(blocks))


def compact_rebuild_stream(
    source_stream: bytes | bytearray | memoryview,
    *,
    original_raw: bytes | bytearray | memoryview,
    new_raw: bytes | bytearray | memoryview,
) -> CompactRebuildResult:
    """Preserve safe original blocks and rebuild changed dependency chains.

    A changed block cannot keep its old compressed bytes.  A following block
    without the restart bit may depend on the previous decoder dictionary, so
    it is rebuilt too.  The chain ends at the next restart block, whose old
    bytes may then be preserved if its raw slice is unchanged.
    """

    source = _as_bytes(source_stream, "Исходный Kraken stream")
    before = _as_bytes(original_raw, "Исходный raw payload")
    after = _as_bytes(new_raw, "Новый raw payload")

    if after == before:
        try:
            layout = parse_kraken_stream(source, len(before))
        except KrakenBlocksError:
            return CompactRebuildResult(
                stream=source,
                mode="unchanged",
                preserved_blocks=0,
                rebuilt_blocks=0,
                reason="No-op: исходный stream сохранён без разбора",
            )
        return CompactRebuildResult(
            stream=source,
            mode="unchanged",
            preserved_blocks=len(layout.blocks),
            rebuilt_blocks=0,
            reason="No-op: raw payload не изменился",
        )

    if len(after) != len(before):
        return CompactRebuildResult(
            stream=_stored_stream(after),
            mode="full-fallback",
            preserved_blocks=0,
            rebuilt_blocks=0,
            reason="Raw payload length changed; compact block mapping is unsafe",
        )

    try:
        layout = parse_kraken_stream(source, len(before))
    except KrakenBlocksError as exc:
        return CompactRebuildResult(
            stream=_stored_stream(after),
            mode="full-fallback",
            preserved_blocks=0,
            rebuilt_blocks=0,
            reason=f"Unsupported Kraken stream: {exc}",
        )

    if sum(block.raw_size for block in layout.blocks) != len(before):
        return CompactRebuildResult(
            stream=_stored_stream(after),
            mode="full-fallback",
            preserved_blocks=0,
            rebuilt_blocks=0,
            reason="Kraken block raw sizes do not cover the original payload",
        )

    output: list[bytes] = []
    preserved_blocks = 0
    rebuilt_blocks = 0
    dirty_dependency = False
    raw_offset = 0
    for block in layout.blocks:
        if block.restart_decoder:
            dirty_dependency = False
        raw_end = raw_offset + block.raw_size
        before_chunk = before[raw_offset:raw_end]
        after_chunk = after[raw_offset:raw_end]
        changed = before_chunk != after_chunk
        if changed or dirty_dependency:
            output.append(_UNCOMPRESSED_BLOCK_HEADER + after_chunk)
            rebuilt_blocks += 1
            dirty_dependency = True
        else:
            output.append(block.encoded)
            preserved_blocks += 1
        raw_offset = raw_end

    return CompactRebuildResult(
        stream=b"".join(output),
        mode="compact",
        preserved_blocks=preserved_blocks,
        rebuilt_blocks=rebuilt_blocks,
        reason="Changed blocks and dependent non-restart blocks rebuilt",
    )
