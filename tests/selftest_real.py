#!/usr/bin/env python3
"""Self-test against real STALKER 2 saves supplied by the user.

The repo intentionally does NOT bundle those private save files. Point S2_TEST_SAVE
at a save, or place the known D639... file next to this project and pass it as argv[1].
This validates format parsing/container rebuild; only the game can validate semantic
behaviour of experimental structural edits.
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import save_format as sf


def main(path: Path) -> None:
    data = path.read_bytes()
    info = sf.inspect_save(data)
    print("source", path)
    print("money", info.money, "inventory", len(info.inventory), "cells", info.grid_cell_count, "orphans", len(info.orphans))
    assert info.crc_ok and info.money is not None and info.inventory

    stack = next((x for x in info.inventory if x.editable_count), None)
    assert stack
    new_count = stack.count + 1
    r = sf.patch_save(data, stack_counts={stack.handle: new_count})
    i = sf.inspect_save(r.data)
    assert next(x for x in i.inventory if x.handle == stack.handle).count == new_count
    print("stack patch OK", stack.handle_hex, stack.count, "->", new_count)

    movable = next(x for x in info.inventory if x.width == 1 and x.height == 1)
    r = sf.patch_save(data, moves={movable.handle: (0, 20)})
    i = sf.inspect_save(r.data)
    got = next(x for x in i.inventory if x.handle == movable.handle)
    assert (got.x, got.y) == (0, 20)
    print("move structural round-trip OK", movable.handle_hex)

    r = sf.patch_save(data, detach={movable.handle: False})
    raw = sf.decompress_save(r.data)
    assert movable.handle not in {c.handle for c in sf.locate_inventory_layout(raw).grid_cells}
    print("detach structural round-trip OK", movable.handle_hex)

    orphan = next((o for o in info.orphans if o.x in (255, 65535) or o.y in (255, 65535)), None)
    if orphan:
        r = sf.patch_save(data, attach_orphans={orphan.handle: (0, 20, 1, 1)})
        i = sf.inspect_save(r.data)
        assert any(x.handle == orphan.handle for x in i.inventory)
        print("attach-orphan structural round-trip OK", orphan.handle_hex)

    # Raw patch with SAME current byte to verify plumbing without changing semantics.
    raw0 = sf.decompress_save(data)
    off = len(raw0) - 32
    same = raw0[off]
    r = sf.patch_save(data, raw_patches=[sf.RawPatch(off, "u8", str(same), "selftest same-byte")])
    assert sf.decompress_save(r.data) == raw0
    print("raw patch plumbing OK")
    print("ALL STRUCTURAL/CONTAINER SELFTESTS PASSED")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python3 tests/selftest_real.py /path/to/save.sav")
    main(Path(sys.argv[1]))
