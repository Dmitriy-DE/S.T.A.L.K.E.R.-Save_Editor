#!/usr/bin/env python3
"""Export deterministic, path-free save parser and mutation vectors."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from editor.equipment import equipment_items  # noqa: E402
from editor.formats import SaveFormat, detect_or_raise  # noqa: E402
from editor.models import EditPlan, SourceRef  # noqa: E402
from editor.platforms import user_data_dir  # noqa: E402
from editor.releases import official_releases  # noqa: E402
from save_format import InventoryItem, SaveInfo  # noqa: E402

_SAVE_EXTENSIONS = frozenset(
    extension
    for release in official_releases()
    for extension in release.extensions
    if extension not in {".dds", ".info"}
)


class InputChangedError(ValueError):
    """An input changed while its vectors were being exported."""


def default_output_path() -> Path:
    """Return the per-user RL-5 directory without creating it."""

    return user_data_dir() / "corpus-lab" / "golden-vectors.json"


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return True


def _validated_roots(roots: Iterable[Path]) -> tuple[Path, ...]:
    normalized: set[Path] = set()
    for candidate in roots:
        try:
            root = Path(candidate).expanduser().resolve(strict=True)
        except OSError as exc:
            raise ValueError("each corpus root must exist and be readable") from exc
        if not root.is_dir():
            raise ValueError("each corpus root must be a directory")
        normalized.add(root)
    if not normalized:
        raise ValueError("provide at least one corpus root")
    return tuple(sorted(normalized, key=lambda path: path.as_posix().casefold()))


def _candidate_files(roots: Sequence[Path]) -> tuple[Path, ...]:
    candidates: set[Path] = set()
    for root in roots:
        try:
            for path in root.rglob("*"):
                if (
                    not path.is_symlink()
                    and path.is_file()
                    and path.suffix.casefold() in _SAVE_EXTENSIONS
                ):
                    candidates.add(path.resolve())
        except OSError as exc:
            raise ValueError("unable to enumerate corpus root") from exc
    return tuple(sorted(candidates, key=lambda path: path.as_posix().casefold()))


def _read_snapshot(path: Path) -> tuple[bytes, int, int]:
    try:
        before = path.stat()
        data = path.read_bytes()
        after = path.stat()
    except OSError as exc:
        raise OSError(type(exc).__name__) from exc
    if (
        before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or len(data) != after.st_size
    ):
        raise InputChangedError("input changed during analysis")
    return data, after.st_size, after.st_mtime_ns


def _assert_unchanged(path: Path, data: bytes, size: int, mtime_ns: int) -> None:
    try:
        current_stat = path.stat()
        current = path.read_bytes()
    except OSError as exc:
        raise InputChangedError("input changed during analysis") from exc
    if (
        current_stat.st_size != size
        or current_stat.st_mtime_ns != mtime_ns
        or current != data
    ):
        raise InputChangedError("input changed during analysis")


def _float_or_none(value: float | None) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    return value


def _item_state(item: InventoryItem) -> dict[str, object]:
    return {
        "handle": item.handle,
        "handle_hex": item.handle_hex,
        "type_key": item.type_key,
        "sid_or_section": item.type_key,
        "count": item.count,
        "condition": _float_or_none(item.condition),
        "placement": {
            "x": item.x,
            "y": item.y,
            "width": item.width,
            "height": item.height,
            "cells": [list(cell) for cell in item.cells],
            "storage": item.storage,
            "type": item.placement_type,
            "slot": item.placement_slot,
            "base_slot": item.placement_base_slot,
        },
        "upgrades": None if item.upgrades is None else list(item.upgrades),
    }


def _capabilities(format_: SaveFormat) -> dict[str, object]:
    mutations = {
        name: support.as_dict() | {"writable": support.writable}
        for name, support in sorted(format_.capabilities.mutation_support.items())
    }
    equipment = format_.capabilities.equipment
    return {
        "read_inventory": format_.capabilities.read_inventory,
        "catalog": format_.capabilities.catalog,
        "equipment": None if equipment is None else equipment.as_dict(),
        "mutations": mutations,
    }


def _state(info: SaveInfo, format_: SaveFormat) -> dict[str, object]:
    projected_equipment = equipment_items(
        list(info.inventory), release_id=format_.release_id
    )
    return {
        "money": info.money,
        "items": [_item_state(item) for item in sorted(info.inventory, key=lambda value: value.handle)],
        "equipment": [item.as_dict() for item in sorted(projected_equipment, key=lambda value: value.handle)],
        "character": {
            "name": info.actor_name,
            "health": _float_or_none(info.actor_health),
            "rank": info.actor_rank,
            "reputation": info.actor_reputation,
            "player_faction_index": info.player_faction_index,
            "player_faction_editable": info.player_faction_editable,
            "faction_relations": [
                {"faction_id": faction, "goodwill": goodwill}
                for faction, goodwill in sorted(info.faction_relations)
            ],
        },
        "time": {
            "game_time": info.game_time,
            "time_factor": _float_or_none(info.time_factor),
            "normal_time_factor": _float_or_none(info.normal_time_factor),
            "level_name": info.level_name,
        },
        "integrity": {
            "name": info.integrity_name,
            "crc_present": info.crc_present,
            "crc_ok": info.crc_ok if info.crc_present else None,
        },
        "warnings": list(info.warnings),
        "capabilities": _capabilities(format_),
    }


def _versions(info: SaveInfo) -> dict[str, int | None]:
    return {
        "format": info.format_version,
        "container": info.container_version,
    }


def _mutation_result(
    name: str,
    format_: SaveFormat,
    data: bytes,
    state_before: dict[str, object],
    plan: EditPlan | None,
    *,
    capability: str,
    expected_value: int | None,
    item_handle: int | None = None,
) -> dict[str, object]:
    source_sha = hashlib.sha256(data).hexdigest()
    support = format_.capabilities.support(capability)
    capability_allows = support.writable
    if plan is None:
        return {
            "plan": None,
            "result": "skipped",
            "reason": "edit_target_unavailable",
            "state_after": state_before,
            "safety_checks": {
                "capability_allows": capability_allows,
                "source_sha256_matches": True,
                "source_unchanged": True,
            },
        }

    try:
        prepared = format_.prepare(data, plan)
    except Exception as exc:
        rejected_by_capability = (
            not capability_allows
            and "не подтверждён" in str(exc).casefold()
        )
        return {
            "plan": _plan_payload(plan),
            "result": "blocked" if rejected_by_capability else "failed",
            "error_type": type(exc).__name__,
            "state_after": state_before,
            "safety_checks": {
                "capability_allows": capability_allows,
                "capability_gate_rejected": rejected_by_capability,
                "source_sha256_matches": source_sha == plan.source.sha256,
                "source_unchanged": True,
                "output_sha256_matches": False,
                "reparse_succeeded": False,
                "mutation_visible_after_reparse": False,
                "crc_ok": None,
            },
        }

    after_state: dict[str, object] = state_before
    output_info: SaveInfo | None = None
    format_preserved = False
    try:
        after_format = detect_or_raise(prepared.data, display_name="golden output")
        format_preserved = after_format.id == format_.id
        output_info = after_format.inspect(prepared.data, with_inventory=True)
        after_state = _state(output_info, after_format)
    except Exception:
        output_info = None

    mutation_visible = False
    if output_info is not None and expected_value is not None:
        if name == "money_plus_one":
            mutation_visible = output_info.money == expected_value
        elif item_handle is not None:
            mutation_visible = any(
                item.handle == item_handle and item.count == expected_value
                for item in output_info.inventory
            )

    output_sha_matches = (
        hashlib.sha256(prepared.data).hexdigest() == prepared.output_sha256
    )
    crc_ok = (
        output_info.crc_ok
        if output_info is not None and output_info.crc_present
        else None
    )
    checks: dict[str, bool | None] = {
        "capability_allows": capability_allows,
        "capability_gate_rejected": False,
        "source_sha256_matches": source_sha == plan.source.sha256,
        "source_unchanged": data == bytes(data),
        "output_sha256_matches": output_sha_matches,
        "reparse_succeeded": output_info is not None,
        "format_preserved": format_preserved,
        "mutation_visible_after_reparse": mutation_visible,
        "crc_ok": crc_ok,
    }
    passed = all(
        checks[key] is True
        for key in (
            "capability_allows",
            "source_sha256_matches",
            "source_unchanged",
            "output_sha256_matches",
            "reparse_succeeded",
            "format_preserved",
            "mutation_visible_after_reparse",
        )
    ) and crc_ok is not False
    return {
        "plan": _plan_payload(plan),
        "result": "passed" if passed else "failed",
        "error_type": None,
        "state_after": after_state,
        "safety_checks": checks,
    }


def _plan_payload(plan: EditPlan) -> dict[str, object]:
    return {
        "money": plan.money,
        "stacks": [
            {"handle": handle, "count": count}
            for handle, count in sorted(plan.stacks)
        ],
    }


def _source(data: bytes) -> SourceRef:
    return SourceRef(
        kind="local",
        locator="golden-copy",
        sha256=hashlib.sha256(data).hexdigest(),
    )


def _mutation_vectors(
    format_: SaveFormat,
    data: bytes,
    info: SaveInfo,
    state_before: dict[str, object],
) -> dict[str, dict[str, object]]:
    money = info.money
    money_value = money + 1 if money is not None and money < 2_000_000_000 else None
    money_plan = (
        None
        if money_value is None
        else EditPlan(source=_source(data), money=money_value)
    )
    money_vector = _mutation_result(
        "money_plus_one",
        format_,
        data,
        state_before,
        money_plan,
        capability="edit_money",
        expected_value=money_value,
    )

    candidates = sorted(
        (
            item
            for item in info.inventory
            if item.editable_count and item.count is not None and item.count > 0
        ),
        key=lambda item: item.handle,
    )
    selected = candidates[0] if candidates else None
    stack_value: int | None = None
    stack_handle: int | None = None
    stack_plan: EditPlan | None = None
    if selected is not None and selected.count is not None:
        if selected.count < selected.count_max:
            stack_value = selected.count + 1
        elif selected.count > 1:
            stack_value = selected.count - 1
        if stack_value is not None:
            stack_handle = selected.handle
            stack_plan = EditPlan(
                source=_source(data),
                stacks=((selected.handle, stack_value),),
            )
    stack_vector = _mutation_result(
        "stack_delta",
        format_,
        data,
        state_before,
        stack_plan,
        capability="edit_stacks",
        expected_value=stack_value,
        item_handle=stack_handle,
    )
    return {"money_plus_one": money_vector, "stack_delta": stack_vector}


def _failed_sample(data: bytes | None, exc: BaseException) -> dict[str, object]:
    return {
        "sha256": None if data is None else hashlib.sha256(data).hexdigest(),
        "format": "unknown",
        "release": "unknown",
        "versions": {"format": None, "container": None},
        "parse_status": "error",
        "error_type": type(exc).__name__,
        "state": None,
        "mutations": {},
    }


def _export_one(data: bytes) -> dict[str, object]:
    format_ = detect_or_raise(data, display_name="golden input")
    info = format_.inspect(data, with_inventory=True)
    state = _state(info, format_)
    return {
        "sha256": hashlib.sha256(data).hexdigest(),
        "format": format_.id,
        "release": format_.release_id,
        "versions": _versions(info),
        "parse_status": "ok",
        "error_type": None,
        "state": state,
        "mutations": _mutation_vectors(format_, data, info, state),
    }


def export_roots(roots: Sequence[Path]) -> dict[str, object]:
    """Build a deterministic aggregate from save bytes under local roots."""

    normalized_roots = _validated_roots(roots)
    samples: list[dict[str, object]] = []
    for path in _candidate_files(normalized_roots):
        try:
            data, size, mtime_ns = _read_snapshot(path)
        except OSError as exc:
            samples.append(_failed_sample(None, exc))
            continue
        try:
            try:
                sample = _export_one(data)
            except Exception as exc:
                sample = _failed_sample(data, exc)
        finally:
            _assert_unchanged(path, data, size, mtime_ns)
        samples.append(sample)
    samples.sort(key=lambda sample: (str(sample["release"]), str(sample["sha256"])))
    return {"schema_version": 1, "samples": samples}


def _encode(value: Any, level: int = 0) -> str:
    indent = "  " * level
    child_indent = "  " * (level + 1)
    if isinstance(value, dict):
        if not value:
            return "{}"
        entries = [
            f"{child_indent}{json.dumps(str(key), ensure_ascii=False)}: {_encode(value[key], level + 1)}"
            for key in sorted(value)
        ]
        return "{\n" + ",\n".join(entries) + f"\n{indent}}}"
    if isinstance(value, (list, tuple)):
        if not value:
            return "[]"
        entries = [f"{child_indent}{_encode(item, level + 1)}" for item in value]
        return "[\n" + ",\n".join(entries) + f"\n{indent}]"
    if isinstance(value, float):
        return "null" if not math.isfinite(value) else f"{value:.6f}"
    if value is None or isinstance(value, (str, int, bool)):
        return json.dumps(value, ensure_ascii=False, allow_nan=False)
    raise TypeError(f"unsupported golden JSON value: {type(value).__name__}")


def render_json(payload: dict[str, object]) -> str:
    """Serialize with sorted keys and fixed six-place numeric floats."""

    return _encode(payload) + "\n"


def _validate_output(output: Path, roots: Sequence[Path]) -> Path:
    resolved = output.expanduser().resolve()
    if any(_inside(resolved, root) for root in roots):
        raise ValueError("output file overlaps an input root")
    if _inside(resolved, ROOT):
        raise ValueError("corpus vectors must be written outside the repository")
    return resolved


def write_export(output: Path, payload: dict[str, object]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp")
    temporary.write_text(render_json(payload), encoding="utf-8")
    temporary.replace(output)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roots", nargs="+", required=True, type=Path)
    parser.add_argument("--out", type=Path, default=default_output_path())
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        roots = _validated_roots(args.roots)
        output = _validate_output(args.out, roots)
        payload = export_roots(roots)
        write_export(output, payload)
    except (OSError, ValueError) as exc:
        reason = "input changed during analysis" if isinstance(exc, InputChangedError) else str(exc)
        print(f"Error: {reason}", file=sys.stderr)
        return 2
    samples = cast(list[dict[str, object]], payload["samples"])
    parsed = sum(sample["parse_status"] == "ok" for sample in samples)
    errors = len(samples) - parsed
    print(f"Golden vectors: files={len(samples)} parsed={parsed} errors={errors}; written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
