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

        if len({handle for handle, _ in stacks}) != len(stacks):
            raise ValueError("Duplicate stack handle in edit plan")
        if len({handle for handle, _, _ in moves}) != len(moves):
            raise ValueError("Duplicate move handle in edit plan")
        if len({handle for handle, _ in detach}) != len(detach):
            raise ValueError("Duplicate detach handle in edit plan")
        if len({handle for handle, *_ in attach}) != len(attach):
            raise ValueError("Duplicate attach handle in edit plan")
        if len({(item_key, destination) for item_key, _, destination in adds}) != len(adds):
            raise ValueError("Duplicate add item/destination in edit plan")
        if len({handle for handle, _ in durability}) != len(durability):
            raise ValueError("Duplicate durability handle in edit plan")
        for handle, condition in durability:
            if not 1 <= handle <= 0xFFFE:
                raise ValueError("Durability handle must be in the range 1…65534")
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
