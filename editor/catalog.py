"""Source-independent item catalog models.

Catalog entries are deliberately separate from save parsing.  A serialized
object key is useful for diagnostics, but it is not a SID or a proof that an
item can be constructed in a save.  The ``source`` field keeps that boundary
visible to every front end.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .releases import ReleaseDescriptor


@dataclass(frozen=True)
class ItemDefinition:
    """One item definition read from an official release resource tree."""

    key: str
    display_name: str | None
    category: str | None
    unit_weight: float | None
    width: int | None
    height: int | None
    max_stack: int | None
    slots: tuple[str, ...]
    prototype: bytes | None
    source: str
    class_name: str | None = None
    serialization_family: str | None = None

    def __post_init__(self) -> None:
        if not self.key.strip():
            raise ValueError("item key must not be empty")
        if not self.source.strip():
            raise ValueError("item source must not be empty")
        if self.class_name is not None:
            object.__setattr__(self, "class_name", self.class_name.strip() or None)
        if self.serialization_family is not None:
            family = self.serialization_family.strip().casefold()
            object.__setattr__(self, "serialization_family", family or None)
        object.__setattr__(self, "slots", tuple(str(slot) for slot in self.slots))
        if self.unit_weight is not None and self.unit_weight < 0:
            raise ValueError("item weight must not be negative")
        for field_name in ("width", "height", "max_stack"):
            value = getattr(self, field_name)
            if value is not None and value < 0:
                raise ValueError(f"item {field_name} must not be negative")


@dataclass(frozen=True)
class ItemCatalog:
    """Immutable catalog for one release and one selected resource source."""

    release_id: str
    source_root: Path | None
    items: tuple[ItemDefinition, ...]

    def __post_init__(self) -> None:
        if not self.release_id.strip():
            raise ValueError("catalog release_id must not be empty")
        items = tuple(self.items)
        keys = [item.key for item in items]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate item key in catalog")
        object.__setattr__(self, "items", items)
        if self.source_root is not None:
            object.__setattr__(self, "source_root", Path(self.source_root))

    def resolve(self, key: str) -> ItemDefinition | None:
        """Return the exact serialized key, without fuzzy/SID guessing."""

        for item in self.items:
            if item.key == key:
                return item
        return None


class CatalogProvider(Protocol):
    """Provider contract used by desktop and future browser catalog loaders."""

    def load(
        self,
        release: ReleaseDescriptor,
        game_root: Path | None = None,
    ) -> ItemCatalog | None:
        """Load a catalog or return ``None`` when evidence is unavailable."""

    def resolve(self, key: str) -> ItemDefinition | None:
        """Resolve against the most recently loaded catalog."""


def catalog_from_items(
    release_id: str,
    items: Sequence[ItemDefinition],
    *,
    source_root: Path | None = None,
) -> ItemCatalog:
    """Small convenience boundary for tests and generated web catalogs."""

    return ItemCatalog(release_id, source_root, tuple(items))


__all__ = [
    "CatalogProvider",
    "ItemCatalog",
    "ItemDefinition",
    "catalog_from_items",
]
