"""S2 stash → backpack transfer, as the game records it (ED-2 stage 1)."""

from __future__ import annotations

import struct

import pytest
from conftest import _object_record

import save_format as sf

STASHED = 0x30000010


def _save_with_stash(*, flagged: bool = True) -> bytes:
    owned = (0x30000001, 0x30000002, 0x30000003, 0x30000004)
    raw = bytearray(b"SYNTHETIC-FIXTURE\x00")
    raw += sf.MONEY_ANCHOR
    raw += struct.pack("<IIH", 100, 1, len(owned)) + struct.pack("<4I", *owned)
    raw += struct.pack("<H", 1) + struct.pack("<IHH", owned[0], 0, 0)
    # Stash header, one live slot, one tombstone, a 1x2 item at (3, 0).
    raw += b"\x00\xff\xff\xff\xff\x06\x01\x00\x00\x00\x06\x00\x00\x00\x00\x00\x00\x03\x00\x00\x00"
    raw += struct.pack("<H", 2) + struct.pack("<II", sf.STASH_TOMBSTONE, STASHED)
    raw += struct.pack("<H", 2) + struct.pack("<IHH", STASHED, 3, 0) + struct.pack("<IHH", STASHED, 3, 1)
    raw += _object_record(0x30000001, x=0, y=0, count=2, total_weight=0.2, kind=4, type_key=b"\x01\x02\x03")
    for handle in owned[1:]:
        raw += _object_record(handle, x=0xFFFF, y=0xFFFF, count=1, total_weight=0.0, kind=0, type_key=b"\x07\x08\x09")
    stashed = bytearray(_object_record(STASHED, x=3, y=0, count=30, total_weight=0.3, kind=5, type_key=b"\x04\x05\x06"))
    if flagged:
        stashed[sf.OBJ_STASH_FLAG_OFFSET] = 1
        stashed[sf.OBJ_FLAGS_OFFSET] = 0x99
    raw += stashed
    return bytes(raw)


def test_stash_is_parsed_after_the_player_arrays() -> None:
    stash = sf.locate_stash_layout(_save_with_stash())
    assert stash.owned_handles == (sf.STASH_TOMBSTONE, STASHED)
    assert stash.live_handles == (STASHED,)
    assert [(c.x, c.y) for c in stash.grid_cells] == [(3, 0), (3, 1)]


def test_transfer_moves_the_item_like_the_game() -> None:
    raw = sf._stash_to_player_in_raw(_save_with_stash(), STASHED)
    stash = sf.locate_stash_layout(raw)
    player = sf.locate_inventory_layout(raw)
    assert stash.owned_handles == (sf.STASH_TOMBSTONE, sf.STASH_TOMBSTONE)
    assert stash.grid_cells == ()
    assert player.owned_handles == (0x30000001, 0x30000002, 0x30000003, 0x30000004, STASHED)
    # Same 1x2 shape, first free spot next to the existing item.
    assert [(c.x, c.y) for c in player.grid_cells if c.handle == STASHED] == [(1, 0), (1, 1)]
    offset, count, _weight, _kind = sf.locate_object_record(raw, STASHED)
    assert count == 30
    assert raw[offset + sf.OBJ_STASH_FLAG_OFFSET] == 0
    assert raw[offset + sf.OBJ_FLAGS_OFFSET] == 0x91
    assert struct.unpack_from("<HH", raw, offset + sf.OBJ_POS_X_OFFSET)[0] == 1


def test_transfer_refuses_items_outside_the_stash_or_unflagged() -> None:
    with pytest.raises(sf.SaveError, match="не лежит в тайнике"):
        sf._stash_to_player_in_raw(_save_with_stash(), 0x30000002)
    with pytest.raises(sf.SaveError, match="не помечена"):
        sf._stash_to_player_in_raw(_save_with_stash(flagged=False), STASHED)


def test_a_save_without_a_stash_is_refused(synthetic_save: bytes) -> None:
    with pytest.raises(sf.SaveError, match="тайника"):
        sf.locate_stash_layout(sf.decompress_save(synthetic_save))
