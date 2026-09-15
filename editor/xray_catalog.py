"""Read-only catalog extraction from an explicitly selected X-Ray install.

The reader understands the text conventions used by official X-Ray item
configuration: INI-like sections, inheritance, and XML localization.  It
also accepts a deliberately small uncompressed XDB reader for portable
fixtures.  Encrypted or compressed archive variants return no catalog until
their decoder is independently verified; serialized save keys remain visible
in that case.
"""

from __future__ import annotations

import binascii
import logging
import re
import struct
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from .catalog import ItemCatalog, ItemDefinition
from .releases import ReleaseDescriptor
from .xray_container import lzo1x_decompress

LOGGER = logging.getLogger(__name__)

_SECTION_RE = re.compile(r"^\[([^\]]+)\](?::(.*))?$")
_INCLUDE_RE = re.compile(r"^#include\s+[\"']([^\"']+)[\"']", re.IGNORECASE)
_NUMERIC_KEYS = {
    "inv_weight",
    "inv_grid_width",
    "inv_grid_height",
    "inv_max_count",
    "box_size",
}
_KNOWN_MOD_MARKERS = ("ogsm", "srp", "anomaly", "misery", "complete")


@dataclass
class _Section:
    name: str
    bases: tuple[str, ...]
    values: dict[str, str]
    source: str


class _ArchiveUnavailableError(Exception):
    pass


_LZHUF_N = 4096
_LZHUF_F = 60
_LZHUF_THRESHOLD = 2
_LZHUF_MAX_FREQ = 0x4000
_LZHUF_N_CHAR = 256 - _LZHUF_THRESHOLD + _LZHUF_F
_LZHUF_T = _LZHUF_N_CHAR * 2 - 1
_LZHUF_R = _LZHUF_T - 1
_LZHUF_D_CODE = tuple(
    [0] * 32
    + [1] * 16
    + [2] * 16
    + [3] * 16
    + [value for value in range(4, 12) for _ in range(8)]
    + [value for value in range(12, 24) for _ in range(4)]
    + [value for value in range(24, 48) for _ in range(2)]
    + list(range(48, 64))
)
_LZHUF_D_LEN = tuple([3] * 32 + [4] * 48 + [5] * 64 + [6] * 48 + [7] * 48 + [8] * 16)


def _lzhuf_decode(code: bytes) -> bytes:
    """Decode X-Ray's bounded LZ-Huffman header stream."""

    if len(code) < 4:
        raise _ArchiveUnavailableError("LZ-Huffman stream is truncated")
    text_size = struct.unpack_from("<I", code, 0)[0]
    if text_size > 64 * 1024 * 1024:
        raise _ArchiveUnavailableError("LZ-Huffman output is too large")
    freq = [0] * (_LZHUF_T + 1)
    son = [0] * _LZHUF_T
    parent = [0] * (_LZHUF_T + _LZHUF_N_CHAR)
    for index in range(_LZHUF_N_CHAR):
        freq[index] = 1
        son[index] = index + _LZHUF_T
        parent[index + _LZHUF_T] = index
    index = 0
    node = _LZHUF_N_CHAR
    while node <= _LZHUF_R:
        freq[node] = freq[index] + freq[index + 1]
        son[node] = index
        parent[index] = node
        parent[index + 1] = node
        index += 2
        node += 1
    freq[_LZHUF_T] = 0xFFFF
    parent[_LZHUF_R] = 0

    source_pos = 4
    bit_buffer = 0
    bit_count = 0

    def get_bit() -> int:
        nonlocal source_pos, bit_buffer, bit_count
        while bit_count <= 8:
            value = code[source_pos] if source_pos < len(code) else 0
            source_pos += 1
            bit_buffer = (bit_buffer | (value << (8 - bit_count))) & 0xFFFFFFFF
            bit_count += 8
        value = bit_buffer
        bit_buffer = (bit_buffer << 1) & 0xFFFFFFFF
        bit_count -= 1
        return (value >> 15) & 1

    def get_byte() -> int:
        nonlocal source_pos, bit_buffer, bit_count
        while bit_count <= 8:
            value = code[source_pos] if source_pos < len(code) else 0
            source_pos += 1
            bit_buffer = (bit_buffer | (value << (8 - bit_count))) & 0xFFFFFFFF
            bit_count += 8
        value = bit_buffer
        bit_buffer = (bit_buffer << 8) & 0xFFFFFFFF
        bit_count -= 8
        return (value & 0xFF00) >> 8

    def update(symbol: int) -> None:
        nonlocal freq, son, parent
        if freq[_LZHUF_R] == _LZHUF_MAX_FREQ:
            leaf = 0
            for node_index in range(_LZHUF_T):
                if son[node_index] >= _LZHUF_T:
                    freq[leaf] = (freq[node_index] + 1) // 2
                    son[leaf] = son[node_index]
                    leaf += 1
            left = 0
            right = _LZHUF_N_CHAR
            while right < _LZHUF_T:
                next_frequency = freq[left] + freq[left + 1]
                insert = right - 1
                while next_frequency < freq[insert]:
                    insert -= 1
                insert += 1
                for shift in range(right, insert, -1):
                    freq[shift] = freq[shift - 1]
                    son[shift] = son[shift - 1]
                freq[insert] = next_frequency
                son[insert] = left
                left += 2
                right += 1
            for node_index in range(_LZHUF_T):
                child = son[node_index]
                if child >= _LZHUF_T:
                    parent[child] = node_index
                else:
                    parent[child] = node_index
                    parent[child + 1] = node_index

        node = parent[symbol + _LZHUF_T]
        while True:
            next_frequency = freq[node] + 1
            freq[node] = next_frequency
            child = node + 1
            if next_frequency > freq[child]:
                while next_frequency > freq[child + 1]:
                    child += 1
                freq[node], freq[child] = freq[child], next_frequency
                left_child = son[node]
                parent[left_child] = child
                if left_child < _LZHUF_T:
                    parent[left_child + 1] = child
                right_child = son[child]
                son[child] = left_child
                parent[right_child] = node
                if right_child < _LZHUF_T:
                    parent[right_child + 1] = node
                son[node] = right_child
                node = child
            node = parent[node]
            if node == 0:
                break

    def decode_char() -> int:
        node = son[_LZHUF_R]
        while node < _LZHUF_T:
            node = son[node + get_bit()]
        symbol = node - _LZHUF_T
        update(symbol)
        return symbol

    output = bytearray()
    text_buffer = bytearray(b" " * (_LZHUF_N + _LZHUF_F - 1))
    write_pos = _LZHUF_N - _LZHUF_F
    while len(output) < text_size:
        symbol = decode_char()
        if symbol < 256:
            value = symbol
            output.append(value)
            text_buffer[write_pos] = value
            write_pos = (write_pos + 1) & (_LZHUF_N - 1)
            continue
        encoded_position = get_byte()
        distance = _LZHUF_D_CODE[encoded_position] << 6
        bit_length = _LZHUF_D_LEN[encoded_position] - 2
        shifted = encoded_position
        for _ in range(bit_length):
            shifted = (shifted << 1) + get_bit()
        distance |= shifted & 0x3F
        position = (write_pos - distance - 1) & (_LZHUF_N - 1)
        copy_length = symbol - 255 + _LZHUF_THRESHOLD
        for _ in range(copy_length):
            value = text_buffer[position]
            output.append(value)
            text_buffer[write_pos] = value
            position = (position + 1) & (_LZHUF_N - 1)
            write_pos = (write_pos + 1) & (_LZHUF_N - 1)
            if len(output) >= text_size:
                break
    return bytes(output)


def _xray_scramble_decrypt(data: bytes, *, world_wide: bool) -> bytes:
    """Undo the public X-Ray 2947 regional header scrambler."""

    seed = 0x16EB2EB if world_wide else 0x131A9D3
    seed0 = 0x5BBC4B if world_wide else 0x1329436
    size_multiplier = 4 if world_wide else 8
    sbox = list(range(256))
    for _ in range(size_multiplier * 256):
        seed0 = (1 + seed0 * 0x8088405) & 0xFFFFFFFF
        first = (seed0 >> 24) & 0xFF
        while True:
            seed0 = (1 + seed0 * 0x8088405) & 0xFFFFFFFF
            second = (seed0 >> 24) & 0xFF
            if first != second:
                break
        sbox[first], sbox[second] = sbox[second], sbox[first]
    inverse = [0] * 256
    for index, value in enumerate(sbox):
        inverse[value] = index
    output = bytearray(len(data))
    for index, value in enumerate(data):
        seed = (1 + seed * 0x8088405) & 0xFFFFFFFF
        output[index] = inverse[value ^ ((seed >> 24) & 0xFF)]
    return bytes(output)


def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1251"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _strip_comment(line: str) -> str:
    quote: str | None = None
    for index, character in enumerate(line):
        if character in "\"'":
            if quote == character:
                quote = None
            elif quote is None:
                quote = character
        elif quote is None and character in ";":
            return line[:index]
    return line


def _parse_ltx(text: str, source: str) -> dict[str, _Section]:
    sections: dict[str, _Section] = {}
    current: _Section | None = None
    for raw_line in text.splitlines():
        line = _strip_comment(raw_line).strip()
        if not line:
            continue
        include = _INCLUDE_RE.match(line)
        if include:
            # Includes are expanded by the provider where a filesystem base
            # is available.  Keeping the directive out of values prevents it
            # from becoming a false item field in an archive entry.
            continue
        match = _SECTION_RE.match(line)
        if match:
            name = match.group(1).strip()
            bases = tuple(
                base.strip() for base in (match.group(2) or "").split(",") if base.strip()
            )
            current = _Section(name, bases, {}, source)
            sections[name] = current
            continue
        if current is None or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().casefold()
        value = value.strip().strip("\"'").strip()
        current.values[key] = value
    return sections


def _parse_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value.replace(",", "."))
    except ValueError:
        return None


def _parse_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value, 0)
    except ValueError:
        try:
            return int(float(value.replace(",", ".")))
        except ValueError:
            return None


def _parse_slots(value: str | None) -> tuple[str, ...]:
    if value is None:
        return ()
    return tuple(
        token.strip() for token in re.split(r"[,; ]+", value) if token.strip()
    )


def _localization(root: Path, files: Mapping[str, bytes] | None = None) -> dict[str, str]:
    values: dict[str, str] = {}
    raw_files: Iterable[tuple[str, bytes]]
    if files is None:
        all_candidates = tuple(
            path
            for base in (root / "config" / "text", root / "text", root / "localization")
            if base.is_dir()
            for path in base.rglob("*.xml")
            if path.is_file()
        )
        preferred = tuple(
            path
            for path in all_candidates
            if "/text/eng/" in f"/{path.as_posix().casefold()}/"
            or "/text/en/" in f"/{path.as_posix().casefold()}/"
            or "/localization/eng/" in f"/{path.as_posix().casefold()}/"
        )
        candidates = preferred or all_candidates
        raw_files = ((path.as_posix(), path.read_bytes()) for path in candidates)
    else:
        all_files = tuple(
            (name, data)
            for name, data in files.items()
            if name.casefold().endswith(".xml")
            and (
                "/text/" in f"/{name.casefold()}"
                or "/localization/" in f"/{name.casefold()}"
            )
        )
        preferred_files = tuple(
            (name, data)
            for name, data in all_files
            if "/text/eng/" in f"/{name.casefold()}/"
            or "/text/en/" in f"/{name.casefold()}/"
            or "/localization/eng/" in f"/{name.casefold()}/"
        )
        raw_files = (
            preferred_files or all_files
        )
    for name, data in raw_files:
        try:
            tree = ET.fromstring(data)
        except (ET.ParseError, ValueError):
            LOGGER.debug("Skipping malformed X-Ray localization file %s", name)
            continue
        for element in tree.iter():
            if element.tag.rsplit("}", 1)[-1] != "string":
                continue
            key = element.attrib.get("id")
            text = next(
                (
                    child.text.strip()
                    for child in element
                    if child.tag.rsplit("}", 1)[-1] == "text" and child.text
                ),
                None,
            )
            if key and text:
                values[key] = text
    return values


def _category(name: str, values: Mapping[str, str]) -> str | None:
    class_name = values.get("class", "").upper()
    lowered = name.casefold()
    if class_name == "AMMO" or lowered.startswith("ammo_"):
        return "ammo"
    if values.get("weapon_class") or values.get("ammo_class") or lowered.startswith(
        ("wpn_", "weapon_")
    ):
        return "weapon"
    if class_name.startswith("G_") or lowered.startswith(("grenade", "rgd", "f1_")):
        return "grenade"
    if lowered.startswith(("outfit_", "scientific_", "helm_", "armor_")):
        return "outfit"
    if lowered.startswith(("af_", "artifact_")):
        return "artifact"
    if lowered.startswith(
        ("medkit", "bandage", "antirad", "drug_", "food_", "bread", "kolbasa", "vodka", "energy")
    ):
        return "consumable"
    if "inv_name" in values or "inv_name_short" in values:
        return "item"
    return None


def _resolve_sections(sections: Mapping[str, _Section]) -> Iterable[tuple[str, _Section, dict[str, str]]]:
    cache: dict[str, dict[str, str]] = {}

    def resolve(name: str, stack: tuple[str, ...] = ()) -> dict[str, str]:
        if name in cache:
            return cache[name]
        if name in stack:
            return {}
        section = sections[name]
        values: dict[str, str] = {}
        for base in section.bases:
            if base in sections:
                values.update(resolve(base, (*stack, name)))
        values.update(section.values)
        cache[name] = values
        return values

    for name, section in sections.items():
        yield name, section, resolve(name)


def _items_from_sections(
    sections: Mapping[str, _Section],
    localization: Mapping[str, str],
    *,
    source_prefix: str = "",
) -> tuple[ItemDefinition, ...]:
    items: list[ItemDefinition] = []
    for name, section, values in _resolve_sections(sections):
        category = _category(name, values)
        if category is None or name.startswith("$"):
            continue
        name_key = values.get("inv_name_short") or values.get("inv_name")
        display_name = localization.get(name_key) if name_key else None
        max_stack = _parse_int(values.get("box_size"))
        if max_stack is None:
            max_stack = _parse_int(values.get("inv_max_count"))
        source = f"{source_prefix}{section.source}#{name}"
        items.append(
            ItemDefinition(
                key=name,
                display_name=display_name,
                category=category,
                unit_weight=_parse_float(values.get("inv_weight")),
                width=_parse_int(values.get("inv_grid_width")),
                height=_parse_int(values.get("inv_grid_height")),
                max_stack=max_stack,
                slots=_parse_slots(values.get("inv_grid_slot")),
                prototype=None,
                source=source,
            )
        )
    return tuple(items)


def _read_uncompressed_xdb(path: Path) -> dict[str, bytes]:
    data = path.read_bytes()
    chunks: dict[int, list[bytes]] = {}
    position = 0
    while position < len(data):
        if position + 8 > len(data):
            raise _ArchiveUnavailableError("truncated XDB chunk")
        chunk_type, size = struct.unpack_from("<II", data, position)
        position += 8
        end = position + size
        if end > len(data):
            raise _ArchiveUnavailableError("XDB chunk exceeds archive")
        if chunk_type & 0x80000000:
            raise _ArchiveUnavailableError("compressed XDB chunks are not verified")
        chunks.setdefault(chunk_type, []).append(data[position:end])
        position = end
    headers = chunks.get(1, [])
    bodies = chunks.get(0, [])
    if len(headers) != 1 or len(bodies) != 1:
        raise _ArchiveUnavailableError("XDB requires one header and one data chunk")
    header = headers[0]
    files: dict[str, bytes] = {}
    position = 0
    while position < len(header):
        if position + 14 > len(header):
            raise _ArchiveUnavailableError("truncated XDB file record")
        name_size, real_size, compressed_size, crc = struct.unpack_from(
            "<HIII", header, position
        )
        position += 14
        name_length = name_size - 16
        if name_length < 0 or position + name_length > len(header):
            raise _ArchiveUnavailableError("invalid XDB file name size")
        name = _decode(header[position : position + name_length]).replace("\\", "/")
        position += name_length
        if position + 4 > len(header):
            raise _ArchiveUnavailableError("truncated XDB file offset")
        offset = struct.unpack_from("<I", header, position)[0]
        position += 4
        if offset == 0:
            continue
        if offset + compressed_size > len(data):
            raise _ArchiveUnavailableError("XDB file data exceeds archive")
        raw = data[offset : offset + compressed_size]
        if compressed_size != real_size:
            raw = lzo1x_decompress(raw, real_size)
        if len(raw) != real_size:
            raise _ArchiveUnavailableError("XDB file size mismatch")
        if crc and (binascii.crc32(raw) & 0xFFFFFFFF) != crc:
            raise _ArchiveUnavailableError("XDB file CRC mismatch")
        files[name] = bytes(raw)
    return files


def _read_xray_archive(path: Path) -> dict[str, bytes]:
    """Read only config/localization entries from one X-Ray DB archive."""

    file_size = path.stat().st_size
    header_data: bytes | None = None
    header_compressed = False
    data_start: int | None = None
    data_end = 0
    with path.open("rb") as handle:
        position = 0
        while position < file_size:
            handle.seek(position)
            raw_header = handle.read(8)
            if len(raw_header) != 8:
                raise _ArchiveUnavailableError("truncated X-Ray archive chunk")
            chunk_type, chunk_size = struct.unpack("<II", raw_header)
            body_offset = position + 8
            body_end = body_offset + chunk_size
            if body_end > file_size:
                raise _ArchiveUnavailableError("X-Ray archive chunk exceeds file")
            base_type = chunk_type & 0x7FFFFFFF
            if base_type == 0:
                if data_start is None:
                    data_start = body_offset
                data_end = max(data_end, body_end)
            elif base_type == 1:
                if header_data is not None:
                    raise _ArchiveUnavailableError("multiple X-Ray archive headers")
                handle.seek(body_offset)
                header_data = handle.read(chunk_size)
                header_compressed = bool(chunk_type & 0x80000000)
            position = body_end
    if header_data is None or data_start is None or data_end == 0:
        raise _ArchiveUnavailableError("X-Ray archive has no data/header chunks")

    decoded_headers: list[bytes] = []
    if not header_compressed:
        decoded_headers.append(header_data)
    else:
        for world_wide in (True, False):
            try:
                decoded_headers.append(
                    _lzhuf_decode(
                        _xray_scramble_decrypt(header_data, world_wide=world_wide)
                    )
                )
            except _ArchiveUnavailableError:
                continue
    for header in decoded_headers:
        entries: list[tuple[str, int, int, int, int]] = []
        position = 0
        valid = True
        while position < len(header):
            if position + 14 > len(header):
                valid = False
                break
            name_size, real_size, compressed_size, crc = struct.unpack_from(
                "<HIII", header, position
            )
            position += 14
            name_length = name_size - 16
            if name_length < 0 or position + name_length > len(header):
                valid = False
                break
            name = _decode(header[position : position + name_length]).replace("\\", "/")
            position += name_length
            if position + 4 > len(header):
                valid = False
                break
            offset = struct.unpack_from("<I", header, position)[0]
            position += 4
            if offset and (
                offset < data_start or offset + compressed_size > data_end
            ):
                valid = False
                break
            entries.append((name, real_size, compressed_size, crc, offset))
        if not valid or not entries:
            continue

        files: dict[str, bytes] = {}
        with path.open("rb") as handle:
            for name, real_size, compressed_size, crc, offset in entries:
                lowered = name.casefold()
                if not offset or not (
                    lowered.endswith(".ltx") or lowered.endswith(".xml")
                ):
                    continue
                if "config/" not in lowered and "localization/" not in lowered:
                    continue
                if offset + compressed_size > file_size:
                    valid = False
                    break
                handle.seek(offset)
                raw = handle.read(compressed_size)
                if len(raw) != compressed_size:
                    valid = False
                    break
                if compressed_size != real_size:
                    try:
                        raw = lzo1x_decompress(raw, real_size)
                    except Exception:
                        valid = False
                        break
                if len(raw) != real_size:
                    valid = False
                    break
                if crc and (binascii.crc32(raw) & 0xFFFFFFFF) != crc:
                    valid = False
                    break
                files[name] = bytes(raw)
        if valid and files:
            return files
    raise _ArchiveUnavailableError("no verified X-Ray archive header variant")


def _candidate_archives(root: Path) -> tuple[Path, ...]:
    return tuple(
        sorted(
            (
                path
                for path in root.iterdir()
                if path.is_file()
                and (
                    path.name.startswith("gamedata.db")
                    or path.name.startswith("gamedata.xdb")
                )
            ),
            key=lambda path: path.name.casefold(),
        )
    )


def _has_obvious_mod_overlay(data_root: Path) -> bool:
    """Reject well-known community overlays under the official-only scope."""

    try:
        for path in data_root.rglob("*"):
            if any(marker in path.name.casefold() for marker in _KNOWN_MOD_MARKERS):
                return True
    except OSError:
        return True
    return False


class XRayCatalogProvider:
    """Load a catalog from one explicit original X-Ray installation root."""

    def __init__(self) -> None:
        self._catalog: ItemCatalog | None = None

    def load(
        self,
        release: ReleaseDescriptor,
        game_root: Path | None = None,
    ) -> ItemCatalog | None:
        self._catalog = None
        if release.family not in {"soc", "clear_sky", "cop"} or release.edition != "original":
            return None
        if game_root is None:
            return None
        root = Path(game_root).expanduser()
        if not root.is_dir():
            return None

        data_root = root / "gamedata"
        section_sources: dict[str, _Section] = {}
        localization: dict[str, str] = {}
        if data_root.is_dir():
            if _has_obvious_mod_overlay(data_root):
                LOGGER.info("Ignoring an obvious community mod overlay in %s", data_root)
                return None
            for path in sorted(data_root.rglob("*.ltx"), key=lambda value: value.as_posix().casefold()):
                try:
                    parsed = _parse_ltx(_decode(path.read_bytes()), path.relative_to(data_root).as_posix())
                except OSError:
                    continue
                section_sources.update(parsed)
            localization = _localization(data_root)
            source_root = data_root
        else:
            files: dict[str, bytes] = {}
            for archive in _candidate_archives(root):
                try:
                    files.update(_read_xray_archive(archive))
                except (_ArchiveUnavailableError, OSError, ValueError) as exc:
                    LOGGER.info("Skipping X-Ray archive %s: %s", archive.name, exc)
            if not files:
                return None
            for name, raw in files.items():
                if name.casefold().endswith(".ltx"):
                    section_sources.update(_parse_ltx(_decode(raw), name))
            localization = _localization(root, files)
            source_root = root

        items = _items_from_sections(section_sources, localization)
        if not items:
            return None
        self._catalog = ItemCatalog(release.id, source_root, items)
        return self._catalog

    def resolve(self, key: str) -> ItemDefinition | None:
        return self._catalog.resolve(key) if self._catalog is not None else None


__all__ = ["XRayCatalogProvider"]
