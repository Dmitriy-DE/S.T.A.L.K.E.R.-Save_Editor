"""Read back a save re-saved by the game during the M10 protocol."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path

# Keep the documented module/script entry points independent of the current
# working directory.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from editor.formats import FormatDetectionError  # noqa: E402
from editor.service import EditorService  # noqa: E402
from save_format import SaveError  # noqa: E402
from tools.prepare_ingame_verification import VerificationManifest  # noqa: E402


@dataclass(frozen=True)
class VerificationResult:
    """Hash and parser result for one manually re-saved game file."""

    manifest_path: Path
    resaved_path: Path
    release_id: str
    format_id: str
    resaved_sha256: str | None
    parser_ok: bool
    money_matches: bool
    mutation_matches: bool
    observed_money: int | None
    observed_mutation: dict[str, object]
    container_version: int | None
    format_version: int | None
    warnings: tuple[str, ...]
    error: str | None = None

    def to_payload(self) -> dict[str, object]:
        return {
            "manifest_path": str(self.manifest_path),
            "resaved_path": str(self.resaved_path),
            "release_id": self.release_id,
            "format_id": self.format_id,
            "resaved_sha256": self.resaved_sha256,
            "parser_ok": self.parser_ok,
            "money_matches": self.money_matches,
            "mutation_matches": self.mutation_matches,
            "observed_money": self.observed_money,
            "observed_mutation": self.observed_mutation,
            "container_version": self.container_version,
            "format_version": self.format_version,
            "warnings": list(self.warnings),
            "error": self.error,
        }


def _sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_manifest(path: Path) -> VerificationManifest:
    try:
        payload = json.loads(path.read_text("utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SaveError(f"Не удалось прочитать manifest: {exc}") from exc
    if not isinstance(payload, dict):
        raise SaveError("Manifest должен быть JSON-объектом")
    if payload.get("manifest_version") != 1:
        raise SaveError("Неподдерживаемая версия manifest")
    required = (
        "release_id",
        "format_id",
        "source_path",
        "edited_path",
        "source_sha256",
        "edited_sha256",
        "original_money",
        "edited_money",
    )
    if any(key not in payload for key in required):
        raise SaveError("Manifest не содержит обязательные поля протокола")
    mutation = payload.get("mutation", {})
    if not isinstance(mutation, dict):
        raise SaveError("Manifest mutation должен быть JSON-объектом")
    # Manifests produced before the bounded-equipment extension contain only
    # edited_money.  Keep them verifiable without rewriting private artifacts.
    if not mutation and payload.get("edited_money") is not None:
        mutation = {"money": {"after": int(payload["edited_money"])}}
    warnings = payload.get("warnings", ())
    if not isinstance(warnings, (list, tuple)):
        raise SaveError("Manifest warnings должен быть JSON-массивом")
    return VerificationManifest(
        release_id=str(payload["release_id"]),
        format_id=str(payload["format_id"]),
        source_path=Path(str(payload["source_path"])),
        edited_path=Path(str(payload["edited_path"])),
        manifest_path=path,
        source_sha256=str(payload["source_sha256"]),
        edited_sha256=str(payload["edited_sha256"]),
        original_money=(
            int(payload["original_money"])
            if payload["original_money"] is not None
            else None
        ),
        edited_money=(
            int(payload["edited_money"])
            if payload["edited_money"] is not None
            else None
        ),
        container_version=(
            int(payload["container_version"])
            if payload.get("container_version") is not None
            else None
        ),
        format_version=(
            int(payload["format_version"])
            if payload.get("format_version") is not None
            else None
        ),
        warnings=tuple(str(value) for value in warnings),
        mutation={str(key): value for key, value in mutation.items()},
    )


def _item_by_handle(info, handle: int):
    for item in info.inventory:
        if item.handle == handle:
            return item
    return None


def _verify_mutation(
    info,
    manifest: VerificationManifest,
) -> tuple[bool, bool, dict[str, object], tuple[str, ...]]:
    """Compare the requested bounded values with the game's re-saved file."""

    expected = manifest.mutation
    observed: dict[str, object] = {}
    issues: list[str] = []

    money_matches = True
    mutation_matches = True
    recognized_mutations = 0
    known_keys = {"money", "stacks", "durability", "upgrades", "placements"}
    for key in expected:
        if key not in known_keys:
            issues.append(f"неизвестный тип mutation: {key}")
            mutation_matches = False

    if "money" in expected:
        money_request = expected["money"]
        if not isinstance(money_request, dict) or "after" not in money_request:
            issues.append("money: повреждённая запись в manifest")
            money_matches = False
            mutation_matches = False
        else:
            try:
                target = int(money_request["after"])
            except (TypeError, ValueError):
                issues.append("money: after должен быть целым числом")
                money_matches = False
                mutation_matches = False
            else:
                recognized_mutations += 1
                observed["money"] = {"after": info.money}
                money_matches = info.money == target
                if not money_matches:
                    issues.append(f"money: {info.money!r} вместо {target}")
                mutation_matches = mutation_matches and money_matches

    stacks_observed: list[dict[str, object]] = []
    stacks_request = expected.get("stacks", [])
    if not isinstance(stacks_request, list):
        issues.append("stacks: повреждённая запись в manifest")
        mutation_matches = False
        stacks_request = []
    elif not stacks_request and "stacks" in expected:
        issues.append("stacks: пустая запись в manifest")
        mutation_matches = False
    for row in stacks_request:
        if not isinstance(row, dict) or "handle" not in row or "after" not in row:
            issues.append("stacks: повреждённая строка в manifest")
            mutation_matches = False
            continue
        try:
            handle = int(row["handle"])
            target_count = int(row["after"])
        except (TypeError, ValueError):
            issues.append("stacks: handle/after имеют неверный тип")
            mutation_matches = False
            continue
        if not 1 <= target_count <= 1_000_000:
            issues.append("stacks: after должен быть в диапазоне 1…1 000 000")
            mutation_matches = False
            continue
        recognized_mutations += 1
        item = _item_by_handle(info, handle)
        observed_count = None if item is None else item.count
        stacks_observed.append({"handle": handle, "after": observed_count})
        matched = observed_count == target_count
        if not matched:
            issues.append(
                f"stack 0x{handle:08X}: {observed_count!r} вместо {target_count}"
            )
        mutation_matches = mutation_matches and matched
    if stacks_observed:
        observed["stacks"] = stacks_observed

    durability_observed: list[dict[str, object]] = []
    durability_request = expected.get("durability", [])
    if not isinstance(durability_request, list):
        issues.append("durability: повреждённая запись в manifest")
        mutation_matches = False
        durability_request = []
    elif not durability_request and "durability" in expected:
        issues.append("durability: пустая запись в manifest")
        mutation_matches = False
    for row in durability_request:
        if not isinstance(row, dict) or "handle" not in row or "after" not in row:
            issues.append("durability: повреждённая строка в manifest")
            mutation_matches = False
            continue
        try:
            handle = int(row["handle"])
            target_condition = float(row["after"])
        except (TypeError, ValueError):
            issues.append("durability: handle/after имеют неверный тип")
            mutation_matches = False
            continue
        if not 0 <= target_condition <= 1 or not math.isfinite(target_condition):
            issues.append("durability: after должен быть конечным числом 0…1")
            mutation_matches = False
            continue
        recognized_mutations += 1
        item = _item_by_handle(info, handle)
        observed_value = None if item is None else item.condition
        durability_observed.append({"handle": handle, "after": observed_value})
        matched = observed_value is not None and math.isclose(
            observed_value, target_condition, rel_tol=0.0, abs_tol=1e-6
        )
        if not matched:
            issues.append(
                f"durability 0x{handle:08X}: {observed_value!r} вместо {target_condition}"
            )
        mutation_matches = mutation_matches and matched
    if durability_observed:
        observed["durability"] = durability_observed

    upgrades_observed: list[dict[str, object]] = []
    upgrades_request = expected.get("upgrades", [])
    if not isinstance(upgrades_request, list):
        issues.append("upgrades: повреждённая запись в manifest")
        mutation_matches = False
        upgrades_request = []
    elif not upgrades_request and "upgrades" in expected:
        issues.append("upgrades: пустая запись в manifest")
        mutation_matches = False
    for row in upgrades_request:
        if not isinstance(row, dict) or "handle" not in row or "after" not in row:
            issues.append("upgrades: повреждённая строка в manifest")
            mutation_matches = False
            continue
        values = row["after"]
        if not isinstance(values, list) or any(
            not isinstance(value, str) or not value for value in values
        ):
            issues.append("upgrades: after должен быть массивом непустых строк")
            mutation_matches = False
            continue
        try:
            handle = int(row["handle"])
        except (TypeError, ValueError):
            issues.append("upgrades: handle имеет неверный тип")
            mutation_matches = False
            continue
        target_upgrades = tuple(values)
        recognized_mutations += 1
        item = _item_by_handle(info, handle)
        observed_value = None if item is None else tuple(item.upgrades or ())
        upgrades_observed.append(
            {"handle": handle, "after": None if observed_value is None else list(observed_value)}
        )
        matched = observed_value == target_upgrades
        if not matched:
            issues.append(
                f"upgrades 0x{handle:08X}: {observed_value!r} вместо {target_upgrades!r}"
            )
        mutation_matches = mutation_matches and matched
    if upgrades_observed:
        observed["upgrades"] = upgrades_observed

    placements_observed: list[dict[str, object]] = []
    placements_request = expected.get("placements", [])
    if not isinstance(placements_request, list):
        issues.append("placements: повреждённая запись в manifest")
        mutation_matches = False
        placements_request = []
    elif not placements_request and "placements" in expected:
        issues.append("placements: пустая запись в manifest")
        mutation_matches = False
    for row in placements_request:
        if not isinstance(row, dict) or "handle" not in row or "type" not in row:
            issues.append("placements: повреждённая строка в manifest")
            mutation_matches = False
            continue
        try:
            handle = int(row["handle"])
        except (TypeError, ValueError):
            issues.append("placements: handle имеет неверный тип")
            mutation_matches = False
            continue
        target_type = str(row["type"]).casefold()
        if target_type not in {"slot", "belt", "ruck"}:
            issues.append("placements: type должен быть slot, belt или ruck")
            mutation_matches = False
            continue
        target_slot = row.get("slot")
        try:
            target_slot = None if target_slot is None else int(target_slot)
        except (TypeError, ValueError):
            issues.append("placements: slot имеет неверный тип")
            mutation_matches = False
            continue
        if target_type == "slot" and target_slot not in range(1, 14):
            issues.append("placements: slot должен быть в диапазоне 1…13")
            mutation_matches = False
            continue
        if target_type != "slot" and target_slot is not None:
            issues.append("placements: belt/ruck не должны иметь slot")
            mutation_matches = False
            continue
        recognized_mutations += 1
        item = _item_by_handle(info, handle)
        observed_type = None if item is None else item.placement_type
        observed_slot = None if item is None else item.placement_slot
        placements_observed.append(
            {"handle": handle, "type": observed_type, "slot": observed_slot}
        )
        matched = observed_type == target_type and (
            target_type != "slot" or observed_slot == target_slot
        )
        if not matched:
            issues.append(
                f"placement 0x{handle:08X}: {(observed_type, observed_slot)!r} "
                f"вместо {(target_type, target_slot)!r}"
            )
        mutation_matches = mutation_matches and matched
    if placements_observed:
        observed["placements"] = placements_observed

    if not expected or recognized_mutations == 0:
        issues.append("manifest не содержит bounded-изменения")
        mutation_matches = False
    return money_matches, mutation_matches, observed, tuple(issues)


def verify_resaved_save(manifest: Path, resaved: Path) -> VerificationResult:
    """Parse a game re-save and report failure without claiming a pass."""

    manifest = Path(manifest).expanduser()
    resaved = Path(resaved).expanduser()
    loaded = _load_manifest(manifest)
    try:
        resaved_sha = _sha256_path(resaved)
    except OSError as exc:
        return VerificationResult(
            manifest_path=manifest,
            resaved_path=resaved,
            release_id=loaded.release_id,
            format_id=loaded.format_id,
            resaved_sha256=None,
            parser_ok=False,
            money_matches=False,
            mutation_matches=False,
            observed_money=None,
            observed_mutation={},
            container_version=None,
            format_version=None,
            warnings=(),
            error=f"Не удалось прочитать re-saved файл: {exc}",
        )

    try:
        data = resaved.read_bytes()
        inspection = EditorService().inspect_result(data, source_name=str(resaved))
        if inspection.release_id != loaded.release_id:
            raise SaveError(
                f"re-saved файл распознан как {inspection.release_id!r}, "
                f"а ожидался {loaded.release_id!r}"
            )
    except (FormatDetectionError, OSError, SaveError, ValueError) as exc:
        return VerificationResult(
            manifest_path=manifest,
            resaved_path=resaved,
            release_id=loaded.release_id,
            format_id=loaded.format_id,
            resaved_sha256=resaved_sha,
            parser_ok=False,
            money_matches=False,
            mutation_matches=False,
            observed_money=None,
            observed_mutation={},
            container_version=None,
            format_version=None,
            warnings=(),
            error=str(exc),
        )

    observed_money = inspection.info.money
    money_matches, mutation_matches, observed_mutation, issues = _verify_mutation(
        inspection.info,
        loaded,
    )
    return VerificationResult(
        manifest_path=manifest,
        resaved_path=resaved,
        release_id=loaded.release_id,
        format_id=inspection.format_id,
        resaved_sha256=resaved_sha,
        parser_ok=True,
        money_matches=money_matches,
        mutation_matches=mutation_matches,
        observed_money=observed_money,
        observed_mutation=observed_mutation,
        container_version=inspection.info.container_version,
        format_version=inspection.info.format_version,
        warnings=inspection.info.warnings,
        error=None if not issues else "; ".join(issues),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify a save after the game loaded and re-saved it"
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--resaved", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        result = verify_resaved_save(args.manifest, args.resaved)
        print(json.dumps(result.to_payload(), ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if result.parser_ok and result.mutation_matches else 1
    except (OSError, SaveError, ValueError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["VerificationResult", "build_parser", "main", "verify_resaved_save"]
