"""Prepare a safe, bounded-mutation copy for manual in-game verification.

The command never writes the selected source path or a game installation.  It
copies the selected save into a caller-owned workspace, prepares one supported
bounded edit through the shared format writer, exports a verified copy, and
records only metadata and hashes in a manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from shutil import copy2

# Keep the documented ``python tools/prepare_ingame_verification.py`` entry
# point usable from outside the repository root, like the other tools.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from editor.formats import detect_or_raise  # noqa: E402
from editor.models import EditPlan, SourceRef  # noqa: E402
from editor.releases import official_releases, release_by_id  # noqa: E402
from editor.service import EditorService  # noqa: E402
from save_format import SaveError  # noqa: E402


@dataclass(frozen=True)
class VerificationManifest:
    """Metadata needed to connect a prepared copy to a later game re-save."""

    release_id: str
    format_id: str
    source_path: Path
    edited_path: Path
    manifest_path: Path
    source_sha256: str
    edited_sha256: str
    original_money: int | None
    edited_money: int | None
    container_version: int | None
    format_version: int | None
    warnings: tuple[str, ...]
    mutation: dict[str, object] = field(default_factory=dict)

    def to_payload(self) -> dict[str, object]:
        return {
            "manifest_version": 1,
            "release_id": self.release_id,
            "format_id": self.format_id,
            "source_path": str(self.source_path),
            "edited_path": str(self.edited_path),
            "source_sha256": self.source_sha256,
            "edited_sha256": self.edited_sha256,
            "original_money": self.original_money,
            "edited_money": self.edited_money,
            "container_version": self.container_version,
            "format_version": self.format_version,
            "warnings": list(self.warnings),
            "mutation": self.mutation,
        }


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_manifest(path: Path, manifest: VerificationManifest) -> None:
    encoded = (
        json.dumps(manifest.to_payload(), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    ).encode("utf-8")
    try:
        with path.open("xb") as handle:
            handle.write(encoded)
            handle.flush()
    except FileExistsError as exc:
        raise SaveError(f"Манифест уже существует: {path}") from exc
    except OSError as exc:
        raise SaveError(f"Не удалось записать манифест: {exc}") from exc


def _item_by_handle(info, handle: int):
    for item in info.inventory:
        if item.handle == handle:
            return item
    raise SaveError(f"В inspection нет actor item handle 0x{handle:08X}")


def _verify_requested_mutations(
    info,
    *,
    money: int | None,
    durability: tuple[tuple[int, float], ...],
    upgrades: tuple[tuple[int, tuple[str, ...]], ...],
    placements: tuple[tuple[int, str, int | None], ...],
) -> dict[str, object]:
    """Verify the prepared copy before it is handed to the game."""

    mutation: dict[str, object] = {}
    if money is not None:
        if info.money != money:
            raise SaveError(
                f"Подготовленный output прочитался с деньгами {info.money!r}, "
                f"ожидалось {money}"
            )
        mutation["money"] = {"after": money}

    durability_rows: list[dict[str, object]] = []
    for handle, expected_condition in durability:
        item = _item_by_handle(info, handle)
        observed = item.condition
        if observed is None or not math.isclose(
            observed, expected_condition, rel_tol=0.0, abs_tol=1e-6
        ):
            raise SaveError(
                f"Подготовленный output не сохранил durability 0x{handle:08X}: "
                f"{observed!r} вместо {expected_condition}"
            )
        durability_rows.append({"handle": handle, "after": expected_condition})
    if durability_rows:
        mutation["durability"] = durability_rows

    upgrade_rows: list[dict[str, object]] = []
    for handle, expected_upgrades in upgrades:
        item = _item_by_handle(info, handle)
        observed = tuple(item.upgrades or ())
        if observed != expected_upgrades:
            raise SaveError(
                f"Подготовленный output не сохранил upgrades 0x{handle:08X}: "
                f"{observed!r} вместо {expected_upgrades!r}"
            )
        upgrade_rows.append({"handle": handle, "after": list(expected_upgrades)})
    if upgrade_rows:
        mutation["upgrades"] = upgrade_rows

    placement_rows: list[dict[str, object]] = []
    for handle, expected_type, expected_slot in placements:
        item = _item_by_handle(info, handle)
        observed = (item.placement_type, item.placement_slot)
        expected_placement = (expected_type, expected_slot)
        if observed[0] != expected_placement[0] or (
            expected_type == "slot" and observed[1] != expected_placement[1]
        ):
            raise SaveError(
                f"Подготовленный output не сохранил placement 0x{handle:08X}: "
                f"{observed!r} вместо {expected_placement!r}"
            )
        placement_rows.append(
            {"handle": handle, "type": expected_type, "slot": expected_slot}
        )
    if placement_rows:
        mutation["placements"] = placement_rows
    if not mutation:
        raise SaveError(
            "Укажи хотя бы одно bounded-изменение: money, durability, upgrades или placement"
        )
    return mutation


def prepare_source_copy(
    source: Path,
    release_id: str,
    workspace: Path,
    money: int | None = None,
    *,
    durability: tuple[tuple[int, float], ...] = (),
    upgrades: tuple[tuple[int, tuple[str, ...]], ...] = (),
    placements: tuple[tuple[int, str, int | None], ...] = (),
) -> VerificationManifest:
    """Create a bounded mutation copy without changing the selected source."""

    release_by_id(release_id)
    source = Path(source).expanduser()
    workspace = Path(workspace).expanduser()
    if not source.is_file():
        raise SaveError(f"Исходный сейв не найден: {source}")
    if money is not None and not 0 <= money <= 2_000_000_000:
        raise SaveError("Деньги должны быть в диапазоне 0…2 000 000 000")
    if money is None and not (durability or upgrades or placements):
        raise SaveError(
            "Укажи хотя бы одно bounded-изменение: money, durability, upgrades или placement"
        )
    mutation_categories = sum(
        (
            money is not None,
            bool(durability),
            bool(upgrades),
            bool(placements),
        )
    )
    if mutation_categories > 1:
        raise SaveError(
            "M10 допускает одну категорию bounded-изменения за один controlled run"
        )

    try:
        workspace.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise SaveError(f"Не удалось создать workspace: {exc}") from exc

    suffix = source.suffix or ".sav"
    source_copy = workspace / f"{source.stem}.source{suffix}"
    if money is not None and not (durability or upgrades or placements):
        mutation_label = f"money-{money}"
    elif durability:
        mutation_label = "durability"
    elif upgrades:
        mutation_label = "upgrades"
    else:
        mutation_label = "placement"
    edited_path = workspace / f"{source.stem}.{mutation_label}{suffix}"
    manifest_path = workspace / "manifest.json"
    if any(path.exists() for path in (source_copy, edited_path, manifest_path)):
        raise SaveError(
            "Workspace уже содержит артефакт проверки; выберите новую папку: "
            f"{workspace}"
        )

    try:
        copy2(source, source_copy)
        data = source_copy.read_bytes()
    except OSError as exc:
        raise SaveError(f"Не удалось скопировать исходный сейв: {exc}") from exc

    format_ = detect_or_raise(data, display_name=source.name)
    if format_.release_id != release_id:
        raise SaveError(
            f"Сейв {source.name!r} распознан как {format_.release_id!r}, "
            f"а не как {release_id!r}; игра не соответствует выбранному профилю"
        )

    service = EditorService()
    inspection = service.inspect_result(data, source_name=str(source_copy))
    if inspection.release_id != release_id:
        raise SaveError(
            f"Профиль inspection {inspection.release_id!r} не соответствует {release_id!r}"
        )
    original_money = inspection.info.money
    if money is not None and original_money is None:
        raise SaveError("В выбранном сейве нет однозначно разобранного поля денег")

    source_sha = _sha256(data)
    plan = EditPlan(
        source=SourceRef(kind="local", locator=str(source_copy), sha256=source_sha),
        money=money,
        durability=durability,
        upgrades=upgrades,
        placements=placements,
    )
    prepared = service.prepare(
        data,
        plan,
        source_name=str(source_copy),
        catalog=inspection.catalog,
        game_catalog=inspection.game_catalog,
    )
    receipt = service.export_local(
        source_copy,
        edited_path,
        prepared,
        workspace / "backups",
    )
    edited_data = receipt.output_path.read_bytes()
    edited_inspection = service.inspect_result(
        edited_data,
        source_name=str(receipt.output_path),
    )
    mutation = _verify_requested_mutations(
        edited_inspection.info,
        money=money,
        durability=durability,
        upgrades=upgrades,
        placements=placements,
    )

    manifest = VerificationManifest(
        release_id=release_id,
        format_id=inspection.format_id,
        source_path=source_copy,
        edited_path=receipt.output_path,
        manifest_path=manifest_path,
        source_sha256=source_sha,
        edited_sha256=receipt.output_sha256,
        original_money=original_money,
        edited_money=edited_inspection.info.money,
        container_version=inspection.info.container_version,
        format_version=inspection.info.format_version,
        warnings=inspection.info.warnings,
        mutation=mutation,
    )
    _write_manifest(manifest_path, manifest)
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare one bounded copy for manual STALKER game verification"
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--release", choices=tuple(r.id for r in official_releases()), required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--money", type=int)
    parser.add_argument(
        "--durability",
        nargs=2,
        action="append",
        metavar=("HANDLE", "VALUE"),
        help="one handle/value pair; VALUE is 0…1",
    )
    parser.add_argument(
        "--upgrade",
        nargs=2,
        action="append",
        metavar=("HANDLE", "KEYS"),
        help="one handle and comma-separated desired upgrade keys",
    )
    parser.add_argument(
        "--placement",
        nargs=3,
        action="append",
        metavar=("HANDLE", "TYPE", "SLOT"),
        help="TYPE slot/belt/ruck; use '-' as SLOT for belt/ruck",
    )
    return parser


def _parse_handle(value: str) -> int:
    try:
        return int(value, 0)
    except ValueError:
        return int(value, 16)


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        durability = tuple(
            (_parse_handle(handle), float(value))
            for handle, value in (args.durability or ())
        )
        upgrades = tuple(
            (_parse_handle(handle), tuple(key for key in keys.split(",") if key))
            for handle, keys in (args.upgrade or ())
        )
        placements = tuple(
            (
                _parse_handle(handle),
                placement_type,
                None if slot.casefold() in {"-", "none", "null"} else int(slot),
            )
            for handle, placement_type, slot in (args.placement or ())
        )
        manifest = prepare_source_copy(
            args.source,
            args.release,
            args.workspace,
            args.money,
            durability=durability,
            upgrades=upgrades,
            placements=placements,
        )
        print(json.dumps(manifest.to_payload(), ensure_ascii=False, indent=2, sort_keys=True))
        print(f"Manifest: {manifest.manifest_path}")
        print(
            "После ручной загрузки и повторного сохранения в игре запустите: "
            f"python -m tools.verify_ingame_result --manifest {manifest.manifest_path} "
            "--resaved /path/to/in-game-resaved-save"
        )
        return 0
    except (OSError, SaveError, KeyError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["VerificationManifest", "build_parser", "main", "prepare_source_copy"]
