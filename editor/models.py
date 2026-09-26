from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from save_format import RawPatch

_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


@dataclass(frozen=True)
class SourceRef:
    """The analyzed source identity used to guard an edit against stale bytes."""

    kind: Literal["local", "cloud"]
    locator: str
    sha256: str

    def __post_init__(self) -> None:
        if self.kind not in ("local", "cloud"):
            raise ValueError(f"Unsupported source kind: {self.kind!r}")
        if not isinstance(self.locator, str) or not self.locator.strip():
            raise ValueError("Source locator must be a non-empty string")
        if not isinstance(self.sha256, str) or not _SHA256_RE.fullmatch(self.sha256):
            raise ValueError("Source SHA256 must be a 64-character hexadecimal string")
        if self.sha256 != self.sha256.lower():
            object.__setattr__(self, "sha256", self.sha256.lower())


@dataclass(frozen=True)
class EditPlan:
    """A complete, immutable snapshot of staged edits.

    Tk widgets and their mutable staging dictionaries must never be read from a
    worker thread.  The UI creates this value on the main thread and workers
    receive only this frozen snapshot.
    """

    source: SourceRef
    money: int | None = None
    stacks: tuple[tuple[int, int], ...] = ()
    moves: tuple[tuple[int, int, int], ...] = ()
    detach: tuple[tuple[int, bool], ...] = ()
    attach: tuple[tuple[int, int, int, int, int], ...] = ()
    raw: tuple[RawPatch, ...] = ()
    adds: tuple[tuple[str, int, str], ...] = ()
    durability: tuple[tuple[int, float], ...] = ()
    faction_relations: tuple[tuple[str, int], ...] = ()
    player_faction: str | None = None
    upgrades: tuple[tuple[int, tuple[str, ...]], ...] = ()
    placements: tuple[tuple[int, str, int | None], ...] = ()
    # Items taken from a level stash (inventory box) into the backpack.
    stash_takes: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if self.money is not None and not isinstance(self.money, int):
            raise TypeError("money must be an int or None")

        stacks = tuple((int(handle), int(count)) for handle, count in self.stacks)
        moves = tuple(
            (int(handle), int(x), int(y)) for handle, x, y in self.moves
        )
        detach = tuple(
            (int(handle), bool(deep)) for handle, deep in self.detach
        )
        attach = tuple(
            (int(handle), int(x), int(y), int(width), int(height))
            for handle, x, y, width, height in self.attach
        )
        raw = tuple(self.raw)
        adds = tuple(
            (str(item_key), int(quantity), str(destination))
            for item_key, quantity, destination in self.adds
        )
        durability = tuple(
            (int(handle), float(condition)) for handle, condition in self.durability
        )
        faction_relations = tuple(
            (str(key).strip(), int(goodwill))
            for key, goodwill in self.faction_relations
        )
        player_faction = (
            None if self.player_faction is None else str(self.player_faction).strip()
        )
        normalized_upgrades: list[tuple[int, tuple[str, ...]]] = []
        for handle, values in self.upgrades:
            if isinstance(values, (str, bytes, bytearray)):
                raise TypeError("upgrade values must be a sequence of exact keys")
            keys = tuple(str(value) for value in values)
            if len(set(keys)) != len(keys):
                raise ValueError("Duplicate upgrade key in one upgrade vector")
            for key in keys:
                if not key:
                    raise ValueError("upgrade key must be non-empty")
                if "\x00" in key:
                    raise ValueError("upgrade key must not contain NUL")
            normalized_upgrades.append((int(handle), keys))
        upgrades = tuple(normalized_upgrades)
        normalized_placements: list[tuple[int, str, int | None]] = []
        for handle, placement_type, slot_id in self.placements:
            normalized_type = str(placement_type).strip().casefold()
            normalized_slot = None if slot_id is None else int(slot_id)
            if normalized_type not in {"slot", "belt", "ruck"}:
                raise ValueError("placement type must be slot, belt, or ruck")
            if normalized_type == "slot":
                if normalized_slot is None:
                    raise ValueError("slot placement requires a slot id")
                if not 1 <= normalized_slot <= 13:
                    raise ValueError("placement slot must be in the range 1…13")
            elif normalized_slot is not None:
                raise ValueError("belt/ruck placement must not include a slot id")
            normalized_placements.append((int(handle), normalized_type, normalized_slot))
        placements = tuple(normalized_placements)

        if len({handle for handle, _ in stacks}) != len(stacks):
            raise ValueError("Duplicate stack handle in edit plan")
        if len({handle for handle, _, _ in moves}) != len(moves):
            raise ValueError("Duplicate move handle in edit plan")
        if len({handle for handle, _ in detach}) != len(detach):
            raise ValueError("Duplicate detach handle in edit plan")
        removed = {handle for handle, _ in detach}
        edited = (
            {handle for handle, _ in stacks}
            | {handle for handle, _ in durability}
            | {handle for handle, _ in upgrades}
            | {handle for handle, *_ in placements}
            | {handle for handle, *_ in moves}
        )
        if removed & edited:
            # The writer would edit an object it has just removed.
            raise ValueError("Edit plan changes an item that it also removes")
        if len({handle for handle, *_ in attach}) != len(attach):
            raise ValueError("Duplicate attach handle in edit plan")
        if len({(item_key, destination) for item_key, _, destination in adds}) != len(adds):
            raise ValueError("Duplicate add item/destination in edit plan")
        if len({handle for handle, _ in durability}) != len(durability):
            raise ValueError("Duplicate durability handle in edit plan")
        if len({key for key, _ in faction_relations}) != len(faction_relations):
            raise ValueError("Duplicate faction relation in edit plan")
        if len({handle for handle, _ in upgrades}) != len(upgrades):
            raise ValueError("Duplicate upgrade handle in edit plan")
        if len({handle for handle, *_ in placements}) != len(placements):
            raise ValueError("Duplicate placement handle in edit plan")
        for handle, _keys in upgrades:
            if not 1 <= handle <= 0xFFFE:
                raise ValueError("Upgrade handle must be in the range 1…65534")
        for handle, _placement_type, _slot_id in placements:
            if not 1 <= handle <= 0xFFFE:
                raise ValueError("Placement handle must be in the range 1…65534")
        for key, goodwill in faction_relations:
            if not key:
                raise ValueError("faction key must be non-empty")
            if "\x00" in key:
                raise ValueError("faction key must not contain NUL")
            if not -0x80000000 <= goodwill <= 0x7FFFFFFF:
                raise ValueError("faction goodwill must fit a signed 32-bit value")
        if player_faction is not None:
            if not player_faction:
                raise ValueError("player faction key must be non-empty")
            if "\x00" in player_faction:
                raise ValueError("player faction key must not contain NUL")
        for handle, condition in durability:
            if not 1 <= handle <= 0xFFFFFFFF:
                raise ValueError("Durability handle must be in the range 1…4294967295")
            if not math.isfinite(condition) or not 0.0 <= condition <= 1.0:
                raise ValueError("Durability value must be finite and in the range 0…1")
        for item_key, quantity, destination in adds:
            if not item_key.strip():
                raise ValueError("Added item key must be non-empty")
            if quantity < 1:
                raise ValueError("Added item quantity must be positive")
            if destination != "inventory":
                raise ValueError("Added item destination must be 'inventory'")

        object.__setattr__(self, "stacks", stacks)
        object.__setattr__(self, "moves", moves)
        object.__setattr__(self, "detach", detach)
        object.__setattr__(self, "attach", attach)
        object.__setattr__(self, "raw", raw)
        object.__setattr__(self, "adds", adds)
        object.__setattr__(self, "durability", durability)
        object.__setattr__(self, "faction_relations", faction_relations)
        object.__setattr__(self, "player_faction", player_faction)
        object.__setattr__(self, "upgrades", upgrades)
        object.__setattr__(self, "placements", placements)
        stash_takes = tuple(int(handle) for handle in self.stash_takes)
        if len(set(stash_takes)) != len(stash_takes):
            raise ValueError("Duplicate stash item in edit plan")
        if set(stash_takes) & removed:
            raise ValueError("Edit plan takes an item from a stash that it also removes")
        object.__setattr__(self, "stash_takes", stash_takes)


@dataclass(frozen=True)
class PreparedEdit:
    """Round-trip-verified bytes produced from one :class:`EditPlan`."""

    plan: EditPlan
    data: bytes
    output_sha256: str


@dataclass(frozen=True)
class CloudReceipt:
    """Result of one cloud transaction after its local recovery artifacts exist."""

    status: Literal["verified", "uncertain"]
    remote_path: str
    backup_path: Path
    recovery_path: Path
    output_sha256: str
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.status not in ("verified", "uncertain"):
            raise ValueError(f"Unsupported cloud receipt status: {self.status!r}")
        if not isinstance(self.remote_path, str) or not self.remote_path.strip():
            raise ValueError("Cloud receipt remote_path must be non-empty")
        if not isinstance(self.output_sha256, str) or not _SHA256_RE.fullmatch(
            self.output_sha256
        ):
            raise ValueError("Cloud receipt output SHA256 must be 64 hex characters")
        if self.status == "uncertain" and not self.reason:
            raise ValueError("Uncertain cloud receipt requires a reason")
