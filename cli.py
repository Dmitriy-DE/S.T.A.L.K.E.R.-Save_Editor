#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import sys

from editor.models import EditPlan, SourceRef
from editor.platforms import user_data_dir
from editor.prepare import prepare_edit
from editor.storage import export_local
from save_format import RawPatch, SaveError, decompress_save, diff_record, inspect_save, record_hex


def parse_int(s: str) -> int:
    return int(s, 0)


DEFAULT_BACKUP_DIR = user_data_dir() / "backups"


def add_export_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("-o", "--output")
    parser.add_argument("--backup-dir", help="directory for exclusive backups and journals")


p = argparse.ArgumentParser(description="STALKER 2 offline save editor / research CLI")
sub = p.add_subparsers(dest="cmd", required=True)

q = sub.add_parser("info", help="validate/inspect save")
q.add_argument("save")

q = sub.add_parser("inventory", help="list player inventory objects")
q.add_argument("save"); q.add_argument("--all", action="store_true")

q = sub.add_parser("orphans", help="list owned handles not present in inventory grid")
q.add_argument("save")

q = sub.add_parser("set-money", help="set coupons")
q.add_argument("save"); q.add_argument("money", type=parse_int); add_export_args(q)

q = sub.add_parser("set-stack", help="set confirmed stack count")
q.add_argument("save"); q.add_argument("handle", type=parse_int); q.add_argument("count", type=parse_int); add_export_args(q)

q = sub.add_parser("move", help="EXPERIMENTAL: move existing inventory object")
q.add_argument("save"); q.add_argument("handle", type=parse_int); q.add_argument("x", type=parse_int); q.add_argument("y", type=parse_int); add_export_args(q)

q = sub.add_parser("detach", help="EXPERIMENTAL: remove object cells from inventory grid")
q.add_argument("save"); q.add_argument("handle", type=parse_int); q.add_argument("--deep", action="store_true", help="also remove handle from owned-handle list"); add_export_args(q)

q = sub.add_parser("attach-orphan", help="EXPERIMENTAL: attach existing owned/orphan handle to grid")
q.add_argument("save"); q.add_argument("handle", type=parse_int); q.add_argument("x", type=parse_int); q.add_argument("y", type=parse_int); q.add_argument("width", type=parse_int); q.add_argument("height", type=parse_int); add_export_args(q)

q = sub.add_parser("raw", help="EXPERIMENTAL: overwrite scalar/hex at raw payload offset")
q.add_argument("save"); q.add_argument("offset", type=parse_int); q.add_argument("kind", choices=("u8","u16","u32","i32","f32","hex")); q.add_argument("value"); add_export_args(q)

q = sub.add_parser("dump-record", help="dump guessed object-record window")
q.add_argument("save"); q.add_argument("handle", type=parse_int); q.add_argument("--limit", type=parse_int, default=768)

q = sub.add_parser("diff-record", help="compare same object handle across two saves")
q.add_argument("save_a"); q.add_argument("save_b"); q.add_argument("handle", type=parse_int); q.add_argument("--limit", type=parse_int, default=2048)

q = sub.add_parser("edit", help="batch safe + experimental edits")
q.add_argument("save"); q.add_argument("--money", type=parse_int)
q.add_argument("--stack", action="append", default=[], metavar="HANDLE=COUNT")
q.add_argument("--move", action="append", default=[], metavar="HANDLE=X,Y")
q.add_argument("--detach", action="append", default=[], metavar="HANDLE[:deep]")
q.add_argument("--attach", action="append", default=[], metavar="HANDLE=X,Y,W,H")
q.add_argument("--raw", action="append", default=[], metavar="OFFSET:TYPE:VALUE")
add_export_args(q)

a = p.parse_args()

if a.cmd == "diff-record":
    ra = decompress_save(Path(a.save_a).read_bytes()); rb = decompress_save(Path(a.save_b).read_bytes())
    diffs = diff_record(ra, rb, a.handle, a.limit)
    if not diffs:
        print("No differences in compared record window")
    for rel, ba, bb in diffs:
        print(f"+0x{rel:04X}: {ba.hex(' ')}  ->  {bb.hex(' ')}")
    raise SystemExit(0)

src = Path(a.save)
data = src.read_bytes()

if a.cmd == "info":
    x = inspect_save(data)
    parsed_grid_handles = len({item.handle for item in x.inventory})
    print(f"CRC: OK\nPacked: {x.packed_size}\nRaw: {x.unpacked_size}\nSHA256: {x.sha256}\nMoney: {x.money}\nOwned handles: {len(x.owned_handles)}\nGrid handles parsed/total: {parsed_grid_handles}/{x.grid_handle_count}\nGrid cells: {x.grid_cell_count}\nInventory objects: {len(x.inventory)}\nOrphans: {len(x.orphans)}\nUnresolved handles: {len(x.unresolved_handles)}")
    for warning in x.warnings:
        print(f"Warning: {warning}")
elif a.cmd == "inventory":
    x = inspect_save(data)
    print("POS   SIZE  TYPE                 KEY     COUNT   WEIGHT    HANDLE       STATUS")
    for it in x.inventory:
        status = "editable" if it.editable_count else ("unresolved" if it.handle in x.unresolved_handles else "read-only")
        print(f"{it.position:<5} {it.size_text:<5} {it.category:<20} {it.type_key:<7} {it.count:>6} {it.total_weight:>9.3f}  {it.handle_hex}  {status}")
elif a.cmd == "orphans":
    x = inspect_save(data)
    print("TYPE                 KEY     COUNT  RECORDPOS     HANDLE")
    for o in x.orphans:
        print(f"{o.category:<20} {o.type_key:<7} {o.count:>5}  {o.x:>5},{o.y:<5}  {o.handle_hex}")
elif a.cmd == "dump-record":
    raw = decompress_save(data); base, blob = record_hex(raw, a.handle, a.limit)
    print(f"base=0x{base:X}, bytes={len(blob)}")
    for i in range(0, len(blob), 16):
        print(f"+0x{i:04X}  {blob[i:i+16].hex(' ')}")
else:
    try:
        money = None
        stacks: dict[int, int] = {}
        moves: dict[int, tuple[int, int]] = {}
        detach: dict[int, bool] = {}
        attach: dict[int, tuple[int, int, int, int]] = {}
        raw_patches: list[RawPatch] = []
        if a.cmd == "set-money": money = a.money
        elif a.cmd == "set-stack": stacks[a.handle] = a.count
        elif a.cmd == "move": moves[a.handle] = (a.x, a.y)
        elif a.cmd == "detach": detach[a.handle] = a.deep
        elif a.cmd == "attach-orphan": attach[a.handle] = (a.x, a.y, a.width, a.height)
        elif a.cmd == "raw": raw_patches = [RawPatch(a.offset, a.kind, a.value, "CLI")]
        elif a.cmd == "edit":
            money = a.money
            for s in a.stack:
                h, value = s.split("=", 1); stacks[int(h, 0)] = int(value, 0)
            for s in a.move:
                h, xy = s.split("=", 1); x, y = xy.split(",", 1); moves[int(h, 0)] = (int(x, 0), int(y, 0))
            for s in a.detach:
                parts = s.split(":", 1); detach[int(parts[0], 0)] = len(parts) > 1 and parts[1].lower() in ("deep", "1", "true", "yes")
            for s in a.attach:
                h, values = s.split("=", 1); x, y, width, height = (int(value, 0) for value in values.split(",")); attach[int(h, 0)] = (x, y, width, height)
            for s in a.raw:
                offset, kind, value = s.split(":", 2); raw_patches.append(RawPatch(int(offset, 0), kind, value, "batch CLI"))

        if money is None and not (stacks or moves or detach or attach or raw_patches):
            raise SaveError("Нет изменений")
        source_sha = hashlib.sha256(data).hexdigest()
        plan = EditPlan(
            source=SourceRef(kind="local", locator=str(src.resolve()), sha256=source_sha),
            money=money,
            stacks=tuple(stacks.items()),
            moves=tuple((handle, x, y) for handle, (x, y) in moves.items()),
            detach=tuple(detach.items()),
            attach=tuple((handle, x, y, width, height) for handle, (x, y, width, height) in attach.items()),
            raw=tuple(raw_patches),
        )
        prepared = prepare_edit(data, plan)
        destination = Path(a.output) if a.output else src.with_name(src.stem + "_edited.sav")
        backup_dir = Path(a.backup_dir) if a.backup_dir else DEFAULT_BACKUP_DIR
        receipt = export_local(src, destination, prepared, backup_dir)
        before = inspect_save(data, with_inventory=True)
        edited_data = receipt.output_path.read_bytes()
        after = inspect_save(edited_data, with_inventory=True)
        print(f"Output: {receipt.output_path}\nSize: {len(edited_data)}\nBackup: {receipt.backup_path}\nSHA256: {receipt.output_sha256}")
        if money is not None: print(f"Money: {before.money} -> {after.money}")
        before_by_handle = {item.handle: item for item in before.inventory}
        after_by_handle = {item.handle: item for item in after.inventory}
        for handle, count in stacks.items(): print(f"Stack 0x{handle:08X}: {before_by_handle.get(handle).count if handle in before_by_handle else '?'} -> {after_by_handle.get(handle).count if handle in after_by_handle else count}")
        for handle, (x, y) in moves.items():
            old = before_by_handle.get(handle)
            print(f"Move 0x{handle:08X}: {old.x if old else '?'},{old.y if old else '?'} -> {x},{y}")
        for handle, deep in detach.items(): print(f"Detach 0x{handle:08X}: deep={deep}")
        for handle, (x, y, width, height) in attach.items(): print(f"Attach 0x{handle:08X}: {x},{y} {width}x{height}")
        for patch in raw_patches: print(f"Raw 0x{patch.offset:X}: {patch.kind}={patch.value}")
    except (OSError, SaveError, ValueError, IndexError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(2)
