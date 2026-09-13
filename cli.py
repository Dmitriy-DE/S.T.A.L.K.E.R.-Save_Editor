#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from save_format import RawPatch, decompress_save, diff_record, inspect_save, patch_save, record_hex


def parse_int(s: str) -> int:
    return int(s, 0)


def write_result(src: Path, output: str | None, data: bytes) -> Path:
    dst = Path(output) if output else src.with_name(src.stem + "_edited.sav")
    dst.write_bytes(data)
    return dst


p = argparse.ArgumentParser(description="STALKER 2 offline save editor / research CLI")
sub = p.add_subparsers(dest="cmd", required=True)

q = sub.add_parser("info", help="validate/inspect save")
q.add_argument("save")

q = sub.add_parser("inventory", help="list player inventory objects")
q.add_argument("save"); q.add_argument("--all", action="store_true")

q = sub.add_parser("orphans", help="list owned handles not present in inventory grid")
q.add_argument("save")

q = sub.add_parser("set-money", help="set coupons")
q.add_argument("save"); q.add_argument("money", type=parse_int); q.add_argument("-o", "--output")

q = sub.add_parser("set-stack", help="set confirmed stack count")
q.add_argument("save"); q.add_argument("handle", type=parse_int); q.add_argument("count", type=parse_int); q.add_argument("-o", "--output")

q = sub.add_parser("move", help="EXPERIMENTAL: move existing inventory object")
q.add_argument("save"); q.add_argument("handle", type=parse_int); q.add_argument("x", type=parse_int); q.add_argument("y", type=parse_int); q.add_argument("-o", "--output")

q = sub.add_parser("detach", help="EXPERIMENTAL: remove object cells from inventory grid")
q.add_argument("save"); q.add_argument("handle", type=parse_int); q.add_argument("--deep", action="store_true", help="also remove handle from owned-handle list"); q.add_argument("-o", "--output")

q = sub.add_parser("attach-orphan", help="EXPERIMENTAL: attach existing owned/orphan handle to grid")
q.add_argument("save"); q.add_argument("handle", type=parse_int); q.add_argument("x", type=parse_int); q.add_argument("y", type=parse_int); q.add_argument("width", type=parse_int); q.add_argument("height", type=parse_int); q.add_argument("-o", "--output")

q = sub.add_parser("raw", help="EXPERIMENTAL: overwrite scalar/hex at raw payload offset")
q.add_argument("save"); q.add_argument("offset", type=parse_int); q.add_argument("kind", choices=("u8","u16","u32","i32","f32","hex")); q.add_argument("value"); q.add_argument("-o", "--output")

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
q.add_argument("-o", "--output")

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
    print(f"CRC: OK\nPacked: {x.packed_size}\nRaw: {x.unpacked_size}\nSHA256: {x.sha256}\nMoney: {x.money}\nOwned handles: {len(x.owned_handles)}\nGrid cells: {x.grid_cell_count}\nInventory objects: {len(x.inventory)}\nOrphans: {len(x.orphans)}")
elif a.cmd == "inventory":
    x = inspect_save(data)
    print("POS   SIZE  TYPE                 KEY     COUNT   WEIGHT    HANDLE       EDIT")
    for it in x.inventory:
        if not a.all and not it.editable_count:
            continue
        print(f"{it.position:<5} {it.size_text:<5} {it.category:<20} {it.type_key:<7} {it.count:>6} {it.total_weight:>9.3f}  {it.handle_hex}  {'yes' if it.editable_count else 'no'}")
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
    kwargs = {}
    if a.cmd == "set-money": kwargs["new_money"] = a.money
    elif a.cmd == "set-stack": kwargs["stack_counts"] = {a.handle: a.count}
    elif a.cmd == "move": kwargs["moves"] = {a.handle: (a.x, a.y)}
    elif a.cmd == "detach": kwargs["detach"] = {a.handle: a.deep}
    elif a.cmd == "attach-orphan": kwargs["attach_orphans"] = {a.handle: (a.x, a.y, a.width, a.height)}
    elif a.cmd == "raw": kwargs["raw_patches"] = [RawPatch(a.offset, a.kind, a.value, "CLI")]
    elif a.cmd == "edit":
        if a.money is not None: kwargs["new_money"] = a.money
        stacks = {}
        for s in a.stack:
            h, v = s.split("=", 1); stacks[int(h,0)] = int(v,0)
        if stacks: kwargs["stack_counts"] = stacks
        moves = {}
        for s in a.move:
            h, xy = s.split("=",1); x,y=xy.split(",",1); moves[int(h,0)] = (int(x,0),int(y,0))
        if moves: kwargs["moves"] = moves
        det = {}
        for s in a.detach:
            parts=s.split(":",1); det[int(parts[0],0)] = len(parts)>1 and parts[1].lower() in ("deep","1","true","yes")
        if det: kwargs["detach"] = det
        att = {}
        for s in a.attach:
            h, vals=s.split("=",1); x,y,w,hgt=(int(v,0) for v in vals.split(",")); att[int(h,0)] = (x,y,w,hgt)
        if att: kwargs["attach_orphans"] = att
        rawp=[]
        for s in a.raw:
            off, kind, value = s.split(":",2); rawp.append(RawPatch(int(off,0),kind,value,"batch CLI"))
        if rawp: kwargs["raw_patches"] = rawp
    r = patch_save(data, **kwargs)
    dst = write_result(src, getattr(a,"output",None), r.data)
    print(f"Output: {dst}\nSize: {len(r.data)}")
    if r.old_money is not None: print(f"Money: {r.old_money} -> {r.new_money}")
    for h,old,new in r.changed_stacks: print(f"Stack 0x{h:08X}: {old} -> {new}")
    for h,ox,oy,nx,ny in r.moved_items: print(f"Move 0x{h:08X}: {ox},{oy} -> {nx},{ny}")
    for h,deep in r.detached_items: print(f"Detach 0x{h:08X}: deep={deep}")
    for h,x,y,w,hh in r.attached_items: print(f"Attach 0x{h:08X}: {x},{y} {w}x{hh}")
    for rp in r.raw_patches: print(f"Raw 0x{rp.offset:X}: {rp.kind}={rp.value}")
