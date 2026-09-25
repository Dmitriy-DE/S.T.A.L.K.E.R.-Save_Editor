"""Read-only metadata for S.T.A.L.K.E.R. 2 save slots.

The game names slots by GUID; the human context (region, play time, save
time) lives in ``SaveGames/CampaignsSave.sav`` and a JPEG preview in
``SaveGames/Thumbnails/<GUID>.sav``.  Both use the same compressed container
as ordinary saves.  This module only reads them; nothing here is ever written.

Campaign record layout observed on builds 0x11, 0xb6 and 0xbb::

    u32 id, 16-byte GUID (four LE u32), u32 kind, u32 build,
    i64 FDateTime ticks, f32 play seconds, str region, str quest, 6 bytes

``str`` is a deduplicated u16 index; a new index is followed by a u16 length
and ASCII text.  Parsing stops at the first record that does not fit, so an
unknown layout degrades to "no metadata" instead of wrong labels.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from save_format import decompress_save

_TICKS_EPOCH = datetime(1, 1, 1, tzinfo=UTC)
_RECORD_FIXED = 40
_MAX_CAMPAIGN_BYTES = 8 * 1024 * 1024
_MAX_THUMBNAIL_BYTES = 4 * 1024 * 1024


@dataclass(frozen=True)
class S2SlotMeta:
    guid: str
    region_key: str
    quest_key: str
    play_hours: float
    saved_at: datetime


def _guid(raw: bytes) -> str:
    return "".join(f"{value:08X}" for value in struct.unpack("<4I", raw))


def parse_campaigns(raw: bytes) -> dict[str, S2SlotMeta]:
    """Parse decompressed ``CampaignsSave`` bytes into metadata keyed by GUID."""

    end = raw.find(b"Achievements")
    if end < 0:
        end = len(raw)
    # Header: build and flags, then a NUL-terminated slot name ("Slot_02")
    # starting at byte 13; the first record begins right after it.
    name_end = raw.find(b"\x00", 13, 128)
    if name_end < 0:
        return {}
    position = name_end + 1
    strings: list[str] = []
    result: dict[str, S2SlotMeta] = {}

    def read_string(offset: int) -> tuple[str, int]:
        (index,) = struct.unpack_from("<H", raw, offset)
        offset += 2
        if index == len(strings):
            (length,) = struct.unpack_from("<H", raw, offset)
            offset += 2
            text = raw[offset : offset + length]
            if len(text) != length or not text.isascii():
                raise ValueError("bad string")
            strings.append(text.decode("ascii"))
            offset += length
        elif index > len(strings):
            raise ValueError("forward string reference")
        return strings[index], offset

    while position + _RECORD_FIXED < end:
        try:
            guid = _guid(raw[position + 4 : position + 20])
            _kind, _build, ticks, seconds = struct.unpack_from("<IIqf", raw, position + 20)
            region, offset = read_string(position + _RECORD_FIXED)
            quest, offset = read_string(offset)
        except (struct.error, ValueError):
            break
        if not 0 < ticks < 3_155_378_975_999_999_999 or not 0 <= seconds < 1e8:
            break
        result[guid] = S2SlotMeta(
            guid=guid,
            region_key=region,
            quest_key=quest,
            play_hours=seconds / 3600,
            saved_at=_TICKS_EPOCH + timedelta(microseconds=ticks // 10),
        )
        position = offset + 6
    return result


def _slot_guid(save_path: Path) -> str:
    """The GUID part of a slot name; copies such as ``<GUID>-edited`` share it."""

    return save_path.stem[:32].upper()


_CACHE: dict[Path, tuple[int, int, dict[str, S2SlotMeta]]] = {}


def slot_meta(save_path: Path) -> S2SlotMeta | None:
    """Return campaign metadata for an S2 ``SaveGames/Data/<GUID>.sav`` slot."""

    index = save_path.parent.parent / "CampaignsSave.sav"
    try:
        stat = index.stat()
    except OSError:
        return None
    cached = _CACHE.get(index)
    if cached is None or cached[:2] != (stat.st_size, stat.st_mtime_ns):
        records: dict[str, S2SlotMeta] = {}
        if stat.st_size <= _MAX_CAMPAIGN_BYTES:
            try:
                records = parse_campaigns(decompress_save(index.read_bytes()))
            except Exception:
                records = {}
        cached = (stat.st_size, stat.st_mtime_ns, records)
        _CACHE[index] = cached
    return cached[2].get(_slot_guid(save_path))


def thumbnail_jpeg(save_path: Path) -> bytes | None:
    """Return the in-game JPEG preview stored next to an S2 slot, if any."""

    path = save_path.parent.parent / "Thumbnails" / f"{_slot_guid(save_path)}.sav"
    try:
        if path.stat().st_size > _MAX_THUMBNAIL_BYTES:
            return None
        raw = decompress_save(path.read_bytes())
    except Exception:
        return None
    start = raw.find(b"\xff\xd8\xff")
    return raw[start:] if 0 <= start < 64 else None


def region_slug(region_key: str) -> str:
    """``sid_locations_region_iron_forest_name`` → ``iron_forest``."""

    value = region_key
    if value.startswith("sid_locations_region_"):
        value = value[len("sid_locations_region_") :]
    if value.endswith("_name"):
        value = value[: -len("_name")]
    return value


__all__ = ["S2SlotMeta", "parse_campaigns", "region_slug", "slot_meta", "thumbnail_jpeg"]
