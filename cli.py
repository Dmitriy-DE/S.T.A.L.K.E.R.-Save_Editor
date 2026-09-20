#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

from editor.formats import FormatDetectionError, detect_or_raise
from editor.models import EditPlan, SourceRef
from editor.platforms import user_data_dir
from editor.service import EditorService
from editor.xray_save import parse_xray
from save_format import RawPatch, SaveError, decompress_save, diff_record, record_hex

EDITOR_SERVICE = EditorService()


def _print_error(exc: Exception) -> None:
    if isinstance(exc, FormatDetectionError):
        print(str(exc), file=sys.stderr)
    else:
        print(f"Error: {exc}", file=sys.stderr)


def parse_int(s: str) -> int:
    return int(s, 0)


DEFAULT_BACKUP_DIR = user_data_dir() / "backups"


def add_export_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("-o", "--output")
    parser.add_argument("--backup-dir", help="directory for exclusive backups and journals")


def build_parser() -> argparse.ArgumentParser:
    """Return the CLI parser.

    Constructing the parser inside a function keeps `import cli` free of
    side effects, so the commands can be regression-tested without running
    the process.
    """

    p = argparse.ArgumentParser(description="S.T.A.L.K.E.R. offline save editor / research CLI")
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
    q.add_argument("--add", action="append", default=[], metavar="ITEM=COUNT")
    q.add_argument(
        "--durability",
        action="append",
        default=[],
        metavar="HANDLE=VALUE",
        help="bounded condition value in the range 0…1",
    )
    q.add_argument(
        "--upgrade",
        action="append",
        default=[],
        metavar="HANDLE=KEY[,KEY]",
        help="replace one confirmed X-Ray upgrade vector; empty keys clears it",
    )
    q.add_argument(
        "--placement",
        action="append",
        default=[],
        metavar="HANDLE=TYPE[:SLOT]",
        help="slot:1…13, belt, or ruck for one confirmed X-Ray item",
    )
    add_export_args(q)
    return p


def main(argv: list[str] | None = None) -> int:
    """Run one CLI command and return the process exit code.

    Read-only commands used to let a missing or unreadable file escape as a
    traceback while the editing commands reported `Error: ...`.  One guard now
    covers every command.
    """

    try:
        return _run(argv)
    except (OSError, SaveError, ValueError, IndexError) as exc:
        _print_error(exc)
        return 2


def _run(argv: list[str] | None) -> int:
    a = build_parser().parse_args(argv)

    if a.cmd == "diff-record":
        data_a = Path(a.save_a).read_bytes()
        data_b = Path(a.save_b).read_bytes()
        fmt_a = detect_or_raise(data_a, display_name=Path(a.save_a).name)
        fmt_b = detect_or_raise(data_b, display_name=Path(a.save_b).name)
        if fmt_a.id.startswith("stalker-") or fmt_b.id.startswith("stalker-"):
            if fmt_a.id != fmt_b.id or not hasattr(fmt_a, "spec"):
                raise SaveError(
                    "diff-record: оба файла должны быть одной оригинальной X-Ray игрой"
                )
            parsed_a = parse_xray(data_a, fmt_a.spec)
            parsed_b = parse_xray(data_b, fmt_a.spec)
            object_a = parsed_a.object_by_id(a.handle)
            object_b = parsed_b.object_by_id(a.handle)
            ra = parsed_a.container.raw[object_a.record_offset : object_a.record_end]
            rb = parsed_b.container.raw[object_b.record_offset : object_b.record_end]
            diffs = []
            for rel in range(min(len(ra), len(rb))):
                if ra[rel] != rb[rel]:
                    diffs.append((rel, ra[rel : rel + 1], rb[rel : rel + 1]))
            for rel in range(min(len(ra), len(rb)), max(len(ra), len(rb))):
                diffs.append((rel, ra[rel : rel + 1], rb[rel : rel + 1]))
        else:
            ra = decompress_save(data_a)
            rb = decompress_save(data_b)
            diffs = diff_record(ra, rb, a.handle, a.limit)
        if not diffs:
            print("No differences in compared record window")
        for rel, ba, bb in diffs:
            print(f"+0x{rel:04X}: {ba.hex(' ')}  ->  {bb.hex(' ')}")
        return 0

    src = Path(a.save)
    data = src.read_bytes()

    if a.cmd == "info":
        x = EDITOR_SERVICE.inspect(data, source_name=src.name)
        result = EDITOR_SERVICE.inspect_result(data, source_name=src.name)
        integrity = "CRC: OK" if x.crc_present else f"Integrity: {x.integrity_name} OK"
        parsed_grid_handles = len({item.handle for item in x.inventory})
        print(f"{integrity}\nFormat: {result.format_id}\nPacked: {x.packed_size}\nRaw: {x.unpacked_size}\nSHA256: {x.sha256}\nMoney: {x.money}\nOwned handles: {len(x.owned_handles)}\nGrid handles parsed/total: {parsed_grid_handles}/{x.grid_handle_count}\nGrid cells: {x.grid_cell_count}\nInventory objects: {len(x.inventory)}\nOrphans: {len(x.orphans)}\nUnresolved handles: {len(x.unresolved_handles)}")
        if x.format_version is not None:
            print(f"Container version: {x.container_version}\nActor spawn version: {x.format_version}")
        if x.level_name is not None:
            print(f"Level: {x.level_name}")
        for warning in x.warnings:
            print(f"Warning: {warning}")
    elif a.cmd == "inventory":
        x = EDITOR_SERVICE.inspect(data, source_name=src.name)
        print("POS        SIZE       TYPE                 KEY                       COUNT   WEIGHT      HANDLE       STATUS")
        for it in x.inventory:
            status = "editable" if it.editable_count else ("unresolved" if it.handle in x.unresolved_handles else "read-only")
            count_text = "unknown" if it.count is None else str(it.count)
            weight = "unknown" if it.total_weight is None else f"{it.total_weight:.3f}"
            print(f"{it.position:<10} {it.size_text:<10} {it.category:<20} {it.type_key:<25} {count_text:>7} {weight:>10}  {it.handle_hex}  {status}")
    elif a.cmd == "orphans":
        x = EDITOR_SERVICE.inspect(data, source_name=src.name)
        print("TYPE                 KEY     COUNT  RECORDPOS     HANDLE")
        for o in x.orphans:
            print(f"{o.category:<20} {o.type_key:<7} {o.count:>5}  {o.x:>5},{o.y:<5}  {o.handle_hex}")
    elif a.cmd == "dump-record":
        format_ = detect_or_raise(data, display_name=src.name)
        if format_.id.startswith("stalker-") and hasattr(format_, "spec"):
            parsed = parse_xray(data, format_.spec)
            obj = parsed.object_by_id(a.handle)
            base = obj.record_offset
            blob = parsed.container.raw[obj.record_offset : min(obj.record_end, obj.record_offset + a.limit)]
        else:
            raw = decompress_save(data)
            base, blob = record_hex(raw, a.handle, a.limit)
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
            adds: list[tuple[str, int, str]] = []
            durability: dict[int, float] = {}
            upgrades: dict[int, tuple[str, ...]] = {}
            placements: dict[int, tuple[str, int | None]] = {}
            if a.cmd == "set-money": money = a.money
            elif a.cmd == "set-stack": stacks[a.handle] = a.count
            elif a.cmd == "move": moves[a.handle] = (a.x, a.y)
            elif a.cmd == "detach": detach[a.handle] = a.deep
            elif a.cmd == "attach-orphan": attach[a.handle] = (a.x, a.y, a.width, a.height)
            elif a.cmd == "raw": raw_patches = [RawPatch(a.offset, a.kind, a.value, "CLI")]
            elif a.cmd == "edit":
                money = a.money
                for spec in a.stack:
                    h, value = spec.split("=", 1); stacks[int(h, 0)] = int(value, 0)
                for spec in a.move:
                    h, xy = spec.split("=", 1); cell_x, cell_y = xy.split(",", 1); moves[int(h, 0)] = (int(cell_x, 0), int(cell_y, 0))
                for spec in a.detach:
                    parts = spec.split(":", 1); detach[int(parts[0], 0)] = len(parts) > 1 and parts[1].lower() in ("deep", "1", "true", "yes")
                for spec in a.attach:
                    h, values = spec.split("=", 1); at_x, at_y, at_w, at_h = (int(value, 0) for value in values.split(",")); attach[int(h, 0)] = (at_x, at_y, at_w, at_h)
                for spec in a.raw:
                    offset, kind, value = spec.split(":", 2); raw_patches.append(RawPatch(int(offset, 0), kind, value, "batch CLI"))
                for spec in a.add:
                    item_key, quantity = spec.split("=", 1)
                    adds.append((item_key, int(quantity, 0), "inventory"))
                for spec in a.durability:
                    handle, value = spec.split("=", 1)
                    durability[parse_int(handle)] = float(value)
                for spec in a.upgrade:
                    handle, values = spec.split("=", 1)
                    upgrades[parse_int(handle)] = tuple(
                        value for value in values.split(",") if value
                    )
                for spec in a.placement:
                    handle, value = spec.split("=", 1)
                    placement_type, separator, raw_slot = value.partition(":")
                    slot_id = int(raw_slot, 0) if separator and raw_slot else None
                    placements[parse_int(handle)] = (placement_type, slot_id)

            if money is None and not (
                stacks
                or moves
                or detach
                or attach
                or raw_patches
                or adds
                or durability
                or upgrades
                or placements
            ):
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
                adds=tuple(adds),
                durability=tuple(durability.items()),
                upgrades=tuple(upgrades.items()),
                placements=tuple(
                    (handle, placement_type, slot_id)
                    for handle, (placement_type, slot_id) in placements.items()
                ),
            )
            catalog = None
            game_catalog = None
            if adds or upgrades:
                inspection = EDITOR_SERVICE.inspect_result(
                    data,
                    with_inventory=True,
                    source_name=str(src),
                    catalog_source=src,
                )
                catalog = inspection.catalog
                game_catalog = inspection.game_catalog
            prepared = EDITOR_SERVICE.prepare(
                data,
                plan,
                source_name=str(src),
                catalog=catalog,
                game_catalog=game_catalog,
            )
            suffix = ".scop" if src.suffix.lower() == ".scop" else ".sav"
            destination = Path(a.output) if a.output else src.with_name(src.stem + "_edited" + suffix)
            backup_dir = Path(a.backup_dir) if a.backup_dir else DEFAULT_BACKUP_DIR
            receipt = EDITOR_SERVICE.export_local(src, destination, prepared, backup_dir)
            before = EDITOR_SERVICE.inspect(
                data, with_inventory=True, source_name=src.name
            )
            edited_data = receipt.output_path.read_bytes()
            after = EDITOR_SERVICE.inspect(
                edited_data,
                with_inventory=True,
                source_name=receipt.output_path.name,
            )
            print(f"Output: {receipt.output_path}\nSize: {len(edited_data)}\nBackup: {receipt.backup_path}\nSHA256: {receipt.output_sha256}")
            if money is not None: print(f"Money: {before.money} -> {after.money}")
            before_by_handle = {item.handle: item for item in before.inventory}
            after_by_handle = {item.handle: item for item in after.inventory}
            for handle, new_count in stacks.items():
                previous = before_by_handle.get(handle)
                current = after_by_handle.get(handle)
                print(
                    f"Stack 0x{handle:08X}: {previous.count if previous else '?'} -> "
                    f"{current.count if current else new_count}"
                )
            for handle, (cell_x, cell_y) in moves.items():
                previous = before_by_handle.get(handle)
                print(
                    f"Move 0x{handle:08X}: {previous.x if previous else '?'},"
                    f"{previous.y if previous else '?'} -> {cell_x},{cell_y}"
                )
            for handle, deep in detach.items(): print(f"Detach 0x{handle:08X}: deep={deep}")
            for handle, (at_x, at_y, at_w, at_h) in attach.items(): print(f"Attach 0x{handle:08X}: {at_x},{at_y} {at_w}x{at_h}")
            for patch in raw_patches: print(f"Raw 0x{patch.offset:X}: {patch.kind}={patch.value}")
            for item_key, quantity, _destination in adds: print(f"Add {item_key} x{quantity}")
            for handle, condition in durability.items():
                previous = before_by_handle.get(handle)
                current = after_by_handle.get(handle)
                print(
                    f"Durability 0x{handle:08X}: "
                    f"{previous.condition if previous else '?'} -> "
                    f"{current.condition if current else condition}"
                )
            for handle, values in upgrades.items():
                previous = before_by_handle.get(handle)
                current = after_by_handle.get(handle)
                print(
                    f"Upgrades 0x{handle:08X}: "
                    f"{previous.upgrades if previous else '?'} -> "
                    f"{current.upgrades if current else values}"
                )
            for handle, (placement_type, slot_id) in placements.items():
                previous = before_by_handle.get(handle)
                current = after_by_handle.get(handle)
                before_place = (
                    (previous.placement_type, previous.placement_slot)
                    if previous
                    else "?"
                )
                after_place = (
                    (current.placement_type, current.placement_slot)
                    if current
                    else (placement_type, slot_id)
                )
                print(f"Placement 0x{handle:08X}: {before_place} -> {after_place}")
        except (OSError, SaveError, ValueError, IndexError) as exc:
            _print_error(exc)
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
