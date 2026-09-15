"""The shared, game-independent part of an original X-Ray save.

The original trilogy stores a little-endian header followed by a raw LZO1X-1
stream.  This module deliberately stops at the container boundary: object
fields and game-specific versions belong to the later format readers.  The
compressor is a small literal-only encoder written from the public format
description.  It is sufficient for safe fixed-size payload edits.  Desktop
systems may use an optional system ``liblzo2`` decoder for large files; the
bounded Python decoder remains the portable and browser implementation.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Any

from save_format import SaveError

try:
    import ctypes
    import ctypes.util
except ImportError:  # pragma: no cover - depends on the Python runtime
    _NATIVE_LZO: Any = None
else:
    _NATIVE_LZO = None
    try:
        _library_name = ctypes.util.find_library("lzo2")
        if _library_name:
            _library = ctypes.CDLL(_library_name)
            _native_lzo = _library.lzo1x_decompress_safe
            _native_lzo.argtypes = [
                ctypes.POINTER(ctypes.c_ubyte),
                ctypes.c_size_t,
                ctypes.POINTER(ctypes.c_ubyte),
                ctypes.POINTER(ctypes.c_size_t),
                ctypes.c_void_p,
            ]
            _native_lzo.restype = ctypes.c_int
            _NATIVE_LZO = _native_lzo
    except (AttributeError, OSError, ValueError):
        # Pyodide and minimal Windows installations do not necessarily expose
        # a shared liblzo2.  The bounded Python decoder below is the portable
        # path and remains the browser implementation.
        _NATIVE_LZO = None

XRAY_MAGIC = 0xFFFFFFFF
XRAY_MAX_UNPACKED_SIZE = 512 * 1024 * 1024
XRAY_SUPPORTED_OUTER_VERSIONS = frozenset({3, 5, 6})
_NATIVE_LZO_MIN_STREAM = 64 * 1024


class XRayError(SaveError):
    """Raised when bytes do not form a supported X-Ray save container."""


def _fail(message: str) -> XRayError:
    return XRayError(f"X-Ray: {message}")


def _literal_length_prefix(length: int) -> bytes:
    if length <= 0:
        return b""
    if length <= 238:
        return bytes((17 + length,))

    value = length - 18
    prefix = bytearray((0,))
    while value > 255:
        prefix.append(0)
        value -= 255
    prefix.append(value)
    return bytes(prefix)


def lzo1x_compress(payload: bytes) -> bytes:
    """Encode ``payload`` as a valid raw LZO1X-1 stream.

    The encoder intentionally emits one literal run and the format's end
    marker.  It does not promise the same compressed bytes as the game's
    dictionary compressor; :class:`XRayContainer` preserves the original
    compressed stream for a no-op round-trip and uses this encoder only after
    an explicit edit.
    """

    data = bytes(payload)
    if not data:
        return b"\x11\x00\x00"
    return _literal_length_prefix(len(data)) + data + b"\x11\x00\x00"


def lzo1x_decompress(stream: bytes, expected_size: int) -> bytes:
    """Decode one raw LZO1X stream with strict input/output bounds."""

    if not isinstance(expected_size, int) or isinstance(expected_size, bool):
        raise _fail("распакованный размер должен быть целым числом")
    if expected_size < 0 or expected_size > XRAY_MAX_UNPACKED_SIZE:
        raise _fail(f"недопустимый распакованный размер: {expected_size}")

    data = bytes(stream)
    if len(data) < 3:
        raise _fail("поток LZO слишком короткий")

    if _NATIVE_LZO is not None and len(data) >= _NATIVE_LZO_MIN_STREAM:
        source = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        target = (ctypes.c_ubyte * expected_size)()
        target_size = ctypes.c_size_t(expected_size)
        result = _NATIVE_LZO(
            source,
            len(data),
            target,
            ctypes.byref(target_size),
            None,
        )
        if result != 0:
            raise _fail(f"поток LZO отклонён native decoder: code={result}")
        if target_size.value != expected_size:
            raise _fail(
                f"native decoder вернул размер {target_size.value} вместо {expected_size}"
            )
        return bytes(target)

    ip = 0
    output = bytearray()
    state = 0
    bitstream_version = 0

    # Newer LZO streams may carry a two-byte bitstream marker.  The original
    # X-Ray streams normally use the legacy raw form, but accepting the marker
    # costs nothing and makes malformed-input handling explicit.
    if len(data) >= 5 and data[0] == 17:
        bitstream_version = data[1]
        ip = 2

    def read_u8() -> int:
        nonlocal ip
        if ip >= len(data):
            raise _fail("поток LZO обрезан")
        value = data[ip]
        ip += 1
        return value

    def read_u16() -> int:
        nonlocal ip
        if ip + 2 > len(data):
            raise _fail("поток LZO обрезан на смещении")
        value = struct.unpack_from("<H", data, ip)[0]
        ip += 2
        return value

    def copy_literals(length: int) -> None:
        nonlocal ip
        if length < 0 or ip + length > len(data):
            raise _fail("литеральный участок LZO обрезан")
        if len(output) + length > expected_size:
            raise _fail("распакованный размер превышает заголовок")
        output.extend(data[ip : ip + length])
        ip += length

    def copy_match(start: int, length: int) -> None:
        if length <= 0 or start < 0 or start >= len(output):
            raise _fail("некорректная обратная ссылка LZO")
        if len(output) + length > expected_size:
            raise _fail("распакованный размер превышает заголовок")
        distance = len(output) - start
        # Matches may overlap the write cursor.  Materialising one copy of the
        # already-emitted distance window and repeating it is equivalent to the
        # byte-at-a-time LZ rule, while keeping large real saves practical in
        # the desktop detector and Pyodide browser build.
        pattern = bytes(output[start : start + distance])
        repetitions = (length + distance - 1) // distance
        output.extend((pattern * repetitions)[:length])

    # A first command above 17 is a literal run encoded as 17 + length.  A
    # short run (<4) is followed by the normal match/literal state transition.
    if ip < len(data) and data[ip] > 17:
        first = read_u8() - 17
        copy_literals(first)
        state = first if first < 4 else 4

    while True:
        command = read_u8()

        if command < 16:
            if state == 0:
                length = command
                if length == 0:
                    zeroes = 0
                    while read_u8() == 0:
                        zeroes += 1
                        if zeroes > (XRAY_MAX_UNPACKED_SIZE // 255) + 1:
                            raise _fail("слишком длинный литеральный участок")
                    length = zeroes * 255 + 15 + data[ip - 1]
                copy_literals(length + 3)
                state = 4
                continue

            next_literals = command & 3
            if state != 4:
                match_start = len(output) - 1 - (command >> 2) - (read_u8() << 2)
                copy_match(match_start, 2)
            else:
                match_start = len(output) - (1 + 0x0800) - (command >> 2) - (read_u8() << 2)
                length = 3

            copy_literals(next_literals)
            state = next_literals
            continue

        if command >= 64:
            next_literals = command & 3
            match_start = len(output) - 1 - ((command >> 2) & 7) - (read_u8() << 3)
            length = (command >> 5) + 1
        elif command >= 32:
            length = (command & 31) + 2
            if length == 2:
                zeroes = 0
                while read_u8() == 0:
                    zeroes += 1
                    if zeroes > (XRAY_MAX_UNPACKED_SIZE // 255) + 1:
                        raise _fail("слишком длинная match-длина")
                length += zeroes * 255 + 31 + data[ip - 1]
            encoded = read_u16()
            match_start = len(output) - 1 - (encoded >> 2)
            next_literals = encoded & 3
        else:
            if ip + 2 > len(data):
                raise _fail("поток LZO обрезан на смещении")
            encoded = struct.unpack_from("<H", data, ip)[0]
            next_literals = encoded & 3

            # This optional extension is part of LZO1X bitstream versions that
            # advertise zero runs.  X-Ray does not use it, but rejecting a
            # truncated extension is safer than interpreting it as a match.
            if bitstream_version and (encoded & 0xFFFC) == 0xFFFC and (command & 0xF8) == 0x18:
                read_u16()
                if ip >= len(data):
                    raise _fail("zero-run extension LZO обрезан")
                length = (command & 7) | (read_u8() << 3)
                length += 4
                if len(output) + length > expected_size:
                    raise _fail("нулевой участок превышает размер payload")
                output.extend(b"\x00" * length)
                copy_literals(next_literals)
                state = next_literals
                continue

            length = (command & 7) + 2
            if length == 2:
                zeroes = 0
                while read_u8() == 0:
                    zeroes += 1
                    if zeroes > (XRAY_MAX_UNPACKED_SIZE // 255) + 1:
                        raise _fail("слишком длинная match-длина")
                length += zeroes * 255 + 7 + data[ip - 1]

            encoded = read_u16()
            next_literals = encoded & 3
            if (command & 8) == 0:
                match_start = len(output) - (encoded >> 2)
                if match_start == len(output):
                    if length != 3:
                        raise _fail("неверный LZO end marker")
                    if ip != len(data):
                        raise _fail("после LZO end marker остались байты")
                    break
            else:
                match_start = len(output) - ((command & 8) << 11) - (encoded >> 2)
            match_start -= 0x4000

        copy_match(match_start, length)
        copy_literals(next_literals)
        state = next_literals

    if len(output) != expected_size:
        raise _fail(
            f"неверный размер после распаковки: {len(output)} вместо {expected_size}"
        )
    return bytes(output)


@dataclass(frozen=True)
class XRayChunk:
    """One top-level ``u32 type, u32 size, bytes`` payload chunk."""

    type: int
    offset: int
    size: int
    data: bytes

    @property
    def end(self) -> int:
        return self.offset + 8 + self.size


def parse_chunks(raw: bytes) -> tuple[XRayChunk, ...]:
    """Parse all top-level chunks and reject truncation or trailing bytes."""

    payload = bytes(raw)
    chunks: list[XRayChunk] = []
    offset = 0
    while offset < len(payload):
        if len(payload) - offset < 8:
            raise _fail(f"chunk header обрезан на смещении 0x{offset:X}")
        chunk_type, size = struct.unpack_from("<II", payload, offset)
        data_start = offset + 8
        data_end = data_start + size
        if data_end > len(payload):
            raise _fail(
                f"chunk type={chunk_type} обрезан: конец 0x{data_end:X}, "
                f"payload заканчивается на 0x{len(payload):X}"
            )
        chunks.append(XRayChunk(chunk_type, offset, size, payload[data_start:data_end]))
        offset = data_end
    if not chunks:
        raise _fail("payload не содержит chunks")
    return tuple(chunks)


@dataclass(frozen=True)
class XRayContainer:
    """Validated original X-Ray container with a lossless no-op builder."""

    original: bytes
    magic: int
    version: int
    unpacked_size: int
    raw: bytes
    chunks: tuple[XRayChunk, ...]

    @classmethod
    def from_bytes(cls, data: bytes) -> XRayContainer:
        original = bytes(data)
        if len(original) < 12:
            raise _fail("заголовок короче 12 байт")

        magic, version, unpacked_size = struct.unpack_from("<III", original, 0)
        if magic != XRAY_MAGIC:
            raise _fail(f"неверная сигнатура 0x{magic:08X}, ожидалось 0xFFFFFFFF")
        if version not in XRAY_SUPPORTED_OUTER_VERSIONS:
            supported = ", ".join(str(value) for value in sorted(XRAY_SUPPORTED_OUTER_VERSIONS))
            raise _fail(f"неподдерживаемая версия контейнера {version}; поддерживаются {supported}")
        if unpacked_size <= 0 or unpacked_size > XRAY_MAX_UNPACKED_SIZE:
            raise _fail(f"недопустимый распакованный размер: {unpacked_size}")

        raw = lzo1x_decompress(original[12:], unpacked_size)
        chunks = parse_chunks(raw)
        return cls(original, magic, version, unpacked_size, raw, chunks)

    @property
    def chunk_types(self) -> tuple[int, ...]:
        return tuple(chunk.type for chunk in self.chunks)

    def build(self, raw: bytes | None = None) -> bytes:
        """Return original bytes for a no-op, or a valid rebuilt container."""

        if raw is None or bytes(raw) == self.raw:
            return self.original
        payload = bytes(raw)
        if not payload or len(payload) > XRAY_MAX_UNPACKED_SIZE:
            raise _fail(
                f"изменённый payload имеет недопустимый размер {len(payload)}"
            )
        parse_chunks(payload)
        return struct.pack("<III", self.magic, self.version, len(payload)) + lzo1x_compress(payload)


__all__ = [
    "XRAY_MAGIC",
    "XRAY_MAX_UNPACKED_SIZE",
    "XRAY_SUPPORTED_OUTER_VERSIONS",
    "XRayChunk",
    "XRayContainer",
    "XRayError",
    "lzo1x_compress",
    "lzo1x_decompress",
    "parse_chunks",
]
