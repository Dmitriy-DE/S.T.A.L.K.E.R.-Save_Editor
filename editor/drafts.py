"""Crash-safe persistence for unapplied edit plans."""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from save_format import RawPatch

from .models import EditPlan, SourceRef
from .platforms import user_data_dir

_SCHEMA_VERSION = 1
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_DRAFT_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True)
class DraftJournal:
    """A sequence of immutable draft states and the currently selected step."""

    plans: tuple[EditPlan, ...]
    index: int

    def __post_init__(self) -> None:
        if not self.plans:
            raise ValueError("A draft journal must contain at least one plan")
        if isinstance(self.index, bool) or not isinstance(self.index, int):
            raise ValueError("A draft journal index must be an integer")
        if not 0 <= self.index < len(self.plans):
            raise ValueError("A draft journal index is out of range")
        if len({plan.source.sha256 for plan in self.plans}) != 1:
            raise ValueError("Draft journal plans must share one save SHA256")

    @property
    def current(self) -> EditPlan:
        return self.plans[self.index]


class DraftStore:
    """Store draft snapshots outside the repository, keyed only by save SHA."""

    def __init__(self, directory: Path | None = None) -> None:
        self.directory = Path(directory) if directory is not None else user_data_dir() / "drafts"

    def path_for(self, sha256: str) -> Path:
        normalized = self._validate_sha256(sha256)
        return self.directory / f"{normalized}.json"

    def save(self, sha256: str, plans: tuple[EditPlan, ...], index: int) -> None:
        normalized = self._validate_sha256(sha256)
        journal = DraftJournal(tuple(plans), index)
        if any(plan.source.sha256 != normalized for plan in journal.plans):
            raise ValueError("Draft plan SHA256 does not match its journal key")
        path = self.path_for(normalized)
        if not _has_changes(journal.current):
            path.unlink(missing_ok=True)
            return

        encoded = _encode_journal(normalized, journal)
        if len(encoded) > _MAX_DRAFT_BYTES:
            journal = DraftJournal((EditPlan(source=journal.current.source), journal.current), 1)
            encoded = _encode_journal(normalized, journal)
            if len(encoded) > _MAX_DRAFT_BYTES:
                raise OSError("Current edit draft exceeds the storage limit")
        self.directory.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{normalized}.",
            suffix=".tmp",
            dir=self.directory,
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, path)
            _sync_directory(self.directory)
        finally:
            temporary_path.unlink(missing_ok=True)

    def load(self, sha256: str, source: SourceRef) -> DraftJournal | None:
        normalized = self._validate_sha256(sha256)
        if source.sha256 != normalized:
            return None
        path = self.path_for(normalized)
        try:
            if not path.is_file() or path.stat().st_size > _MAX_DRAFT_BYTES:
                return None
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return None
            schema = raw.get("schema")
            if isinstance(schema, bool) or not isinstance(schema, int) or schema != _SCHEMA_VERSION:
                return None
            if raw.get("source_sha256") != normalized:
                return None
            raw_plans = raw.get("plans")
            index = raw.get("index")
            if not isinstance(raw_plans, list) or not raw_plans:
                return None
            if isinstance(index, bool) or not isinstance(index, int):
                return None
            plans = tuple(_deserialize_plan(source, item) for item in raw_plans)
            journal = DraftJournal(plans, index)
            if not _has_changes(journal.current):
                return None
            return journal
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
            return None

    def remove(self, sha256: str) -> None:
        self.path_for(sha256).unlink(missing_ok=True)

    @staticmethod
    def _validate_sha256(value: str) -> str:
        if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
            raise ValueError("Draft key must be a lowercase SHA256")
        return value


def _serialize_plan(plan: EditPlan) -> dict[str, object]:
    return {
        "adds": [list(entry) for entry in plan.adds],
        "attach": [list(entry) for entry in plan.attach],
        "detach": [list(entry) for entry in plan.detach],
        "durability": [list(entry) for entry in plan.durability],
        "faction_relations": [list(entry) for entry in plan.faction_relations],
        "money": plan.money,
        "moves": [list(entry) for entry in plan.moves],
        "placements": [list(entry) for entry in plan.placements],
        "player_faction": plan.player_faction,
        "stash_takes": list(plan.stash_takes),
        "stash_puts": [list(entry) for entry in plan.stash_puts],
        "raw": [
            {
                "kind": patch.kind,
                "note": patch.note,
                "offset": patch.offset,
                "value": patch.value,
            }
            for patch in plan.raw
        ],
        "stacks": [list(entry) for entry in plan.stacks],
        "upgrades": [[handle, list(values)] for handle, values in plan.upgrades],
    }


def _encode_journal(sha256: str, journal: DraftJournal) -> bytes:
    payload = {
        "index": journal.index,
        "plans": [_serialize_plan(plan) for plan in journal.plans],
        "schema": _SCHEMA_VERSION,
        "source_sha256": sha256,
    }
    return json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _deserialize_plan(source: SourceRef, raw: object) -> EditPlan:
    if not isinstance(raw, dict):
        raise ValueError("Draft plan must be an object")
    expected = {
        "adds",
        "attach",
        "detach",
        "durability",
        "faction_relations",
        "money",
        "moves",
        "placements",
        "player_faction",
        "raw",
        "stacks",
        "upgrades",
    }
    # Drafts written before stash moves existed simply have none.
    raw = {"stash_takes": [], "stash_puts": [], **raw}
    expected.update({"stash_takes", "stash_puts"})
    if set(raw) != expected:
        raise ValueError("Draft plan has an unknown or missing field")
    money = raw["money"]
    if money is not None:
        money = _integer(money)
    player_faction = raw["player_faction"]
    if player_faction is not None and not isinstance(player_faction, str):
        raise ValueError("Draft player faction must be text or null")
    raw_patches = _list(raw["raw"])
    patches: list[RawPatch] = []
    for item in raw_patches:
        if not isinstance(item, dict) or set(item) != {"kind", "note", "offset", "value"}:
            raise ValueError("Draft raw patch has an invalid shape")
        if not all(isinstance(item[key], str) for key in ("kind", "note", "value")):
            raise ValueError("Draft raw patch text fields must be strings")
        patches.append(RawPatch(_integer(item["offset"]), item["kind"], item["value"], item["note"]))

    return EditPlan(
        source=source,
        money=money,
        stacks=tuple((_integer_pair(item)) for item in _list(raw["stacks"])),
        moves=tuple((_integer_triple(item)) for item in _list(raw["moves"])),
        detach=tuple((_integer(item[0]), _boolean(item[1])) for item in _pairs(raw["detach"])),
        attach=tuple((_integer_five(item)) for item in _list(raw["attach"])),
        raw=tuple(patches),
        adds=tuple(
            (_text(item[0]), _integer(item[1]), _text(item[2]))
            for item in _triples(raw["adds"])
        ),
        durability=tuple(
            (_integer(item[0]), _number(item[1])) for item in _pairs(raw["durability"])
        ),
        faction_relations=tuple(
            (_text(item[0]), _integer(item[1])) for item in _pairs(raw["faction_relations"])
        ),
        player_faction=player_faction,
        upgrades=tuple(
            (_integer(item[0]), tuple(_text(value) for value in _list(item[1])))
            for item in _pairs(raw["upgrades"])
        ),
        placements=tuple(
            (_integer(item[0]), _text(item[1]), None if item[2] is None else _integer(item[2]))
            for item in _triples(raw["placements"])
        ),
        stash_takes=tuple(_integer(item) for item in _list(raw["stash_takes"])),
        stash_puts=tuple(_integer_pair(item) for item in _list(raw["stash_puts"])),
    )


def _list(value: object) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError("Draft plan collection must be an array")
    return value


def _tuple_of(value: object, size: int) -> tuple[Any, ...]:
    if not isinstance(value, list) or len(value) != size:
        raise ValueError("Draft plan row has an invalid shape")
    return tuple(value)


def _pairs(value: object) -> list[tuple[Any, ...]]:
    return [_tuple_of(item, 2) for item in _list(value)]


def _triples(value: object) -> list[tuple[Any, ...]]:
    return [_tuple_of(item, 3) for item in _list(value)]


def _integer_pair(value: object) -> tuple[int, int]:
    first, second = _tuple_of(value, 2)
    return _integer(first), _integer(second)


def _integer_triple(value: object) -> tuple[int, int, int]:
    first, second, third = _tuple_of(value, 3)
    return _integer(first), _integer(second), _integer(third)


def _integer_five(value: object) -> tuple[int, int, int, int, int]:
    first, second, third, fourth, fifth = _tuple_of(value, 5)
    return _integer(first), _integer(second), _integer(third), _integer(fourth), _integer(fifth)


def _integer(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("Draft integer value is invalid")
    return value


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Draft number value is invalid")
    return float(value)


def _boolean(value: object) -> bool:
    if not isinstance(value, bool):
        raise ValueError("Draft boolean value is invalid")
    return value


def _text(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("Draft text value is invalid")
    return value


def _has_changes(plan: EditPlan) -> bool:
    return bool(
        plan.money is not None
        or plan.stacks
        or plan.moves
        or plan.detach
        or plan.attach
        or plan.raw
        or plan.adds
        or plan.durability
        or plan.faction_relations
        or plan.player_faction is not None
        or plan.upgrades
        or plan.placements
        or plan.stash_takes
        or plan.stash_puts
    )


def _sync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


__all__ = ["DraftJournal", "DraftStore"]
