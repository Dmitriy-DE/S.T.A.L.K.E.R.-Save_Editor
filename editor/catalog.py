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


class CatalogLookupError(LookupError):
    """An exact catalog key is not present in the selected release."""


@dataclass(frozen=True)
class FactionDefinition:
    """One community identifier read from an official X-Ray resource."""

    key: str
    display_name: str | None
    source: str
    release_id: str
    numeric_id: int | None = None

    def __post_init__(self) -> None:
        if not self.key.strip():
            raise ValueError("faction key must not be empty")
        if not self.source.strip():
            raise ValueError("faction source must not be empty")
        if not self.release_id.strip():
            raise ValueError("faction release_id must not be empty")
        if self.display_name is not None:
            object.__setattr__(self, "display_name", self.display_name.strip() or None)
        if self.numeric_id is not None and self.numeric_id < 0:
            raise ValueError("faction numeric_id must not be negative")


@dataclass(frozen=True)
class FactionCatalog:
    """Immutable, release-scoped X-Ray community catalog.

    ``relations`` contains defaults from ``[communities_relations]``.  They
    describe resource defaults only; they are deliberately not presented as
    the current relation values from a save until a save codec proves that
    distinction.
    """

    release_id: str
    source_root: Path | None
    factions: tuple[FactionDefinition, ...]
    relations: tuple[tuple[str, str, int], ...] = ()
    goodwill_min: int | None = None
    goodwill_max: int | None = None
    attitude_neutral_threshold: int | None = None
    attitude_friend_threshold: int | None = None

    def __post_init__(self) -> None:
        if not self.release_id.strip():
            raise ValueError("faction catalog release_id must not be empty")
        factions = tuple(self.factions)
        keys = [faction.key for faction in factions]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate faction key in catalog")
        if any(faction.release_id != self.release_id for faction in factions):
            raise ValueError("faction release_id does not match catalog release_id")
        relation_values = tuple(
            (str(source), str(target), int(value))
            for source, target, value in self.relations
        )
        known = set(keys)
        if any(source not in known or target not in known for source, target, _ in relation_values):
            raise ValueError("faction relation references an unknown community")
        if len({(source, target) for source, target, _ in relation_values}) != len(relation_values):
            raise ValueError("duplicate faction relation in catalog")
        numeric_ids = tuple(
            faction.numeric_id for faction in factions if faction.numeric_id is not None
        )
        if len(numeric_ids) != len(set(numeric_ids)):
            raise ValueError("duplicate faction numeric_id in catalog")
        for field_name in (
            "goodwill_min",
            "goodwill_max",
            "attitude_neutral_threshold",
            "attitude_friend_threshold",
        ):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, int) or isinstance(value, bool)):
                raise TypeError(f"{field_name} must be an int or None")
        if (
            self.goodwill_min is not None
            and self.goodwill_max is not None
            and self.goodwill_min > self.goodwill_max
        ):
            raise ValueError("goodwill_min must not exceed goodwill_max")
        object.__setattr__(self, "factions", factions)
        object.__setattr__(self, "relations", relation_values)
        if self.source_root is not None:
            object.__setattr__(self, "source_root", Path(self.source_root))

    def resolve(self, key: str) -> FactionDefinition:
        """Resolve an exact community key or refuse the foreign/missing key."""

        for faction in self.factions:
            if faction.key == key:
                return faction
        raise CatalogLookupError(
            f"faction key {key!r} отсутствует в catalog release {self.release_id!r}"
        )

    def resolve_numeric(self, numeric_id: int) -> FactionDefinition | None:
        """Resolve an engine community index without inventing a key."""

        if not isinstance(numeric_id, int) or isinstance(numeric_id, bool):
            return None
        return next(
            (faction for faction in self.factions if faction.numeric_id == numeric_id),
            None,
        )

    def relation_address(self, source: str, target: str) -> tuple[int, int]:
        """Return the engine's row/column address for two exact keys."""

        source_faction = self.resolve(source)
        target_faction = self.resolve(target)
        if source_faction.numeric_id is None or target_faction.numeric_id is None:
            raise CatalogLookupError(
                f"catalog release {self.release_id!r} has no numeric relation address "
                f"for {source!r} -> {target!r}"
            )
        return source_faction.numeric_id, target_faction.numeric_id

    def default_relation(self, source: str, target: str) -> int | None:
        """Return a resource default, never a current save value."""

        self.resolve(source)
        self.resolve(target)
        for relation_source, relation_target, value in self.relations:
            if relation_source == source and relation_target == target:
                return value
        return None

    @property
    def relation_addresses(self) -> tuple[tuple[str, str, int, int, int], ...]:
        """Return serializable resource relation metadata in catalog order."""

        rows: list[tuple[str, str, int, int, int]] = []
        for source, target, value in self.relations:
            row, column = self.relation_address(source, target)
            rows.append((source, target, row, column, value))
        return tuple(rows)


@dataclass(frozen=True)
class UpgradeDefinition:
    """One selectable equipment/weapon upgrade from an official X-Ray LTX."""

    key: str
    display_name: str | None
    category: str | None
    item_key: str | None
    source: str
    release_id: str
    section: str | None = None
    property_name: str | None = None
    icon: str | None = None
    applicable_item_keys: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.key.strip():
            raise ValueError("upgrade key must not be empty")
        if not self.source.strip():
            raise ValueError("upgrade source must not be empty")
        if not self.release_id.strip():
            raise ValueError("upgrade release_id must not be empty")
        for field_name in ("display_name", "item_key", "section", "property_name", "icon"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, value.strip() or None)
        applicable = tuple(
            dict.fromkeys(
                str(value).strip()
                for value in self.applicable_item_keys
                if str(value).strip()
            )
        )
        if self.item_key is not None and self.item_key not in applicable:
            applicable = (self.item_key, *applicable)
        object.__setattr__(self, "applicable_item_keys", applicable)

    def applies_to(self, item_key: str) -> bool:
        """Return whether official resource metadata names this exact item."""

        return item_key in self.applicable_item_keys


@dataclass(frozen=True)
class UpgradeCatalog:
    """Immutable, release-scoped upgrade definitions from official resources."""

    release_id: str
    source_root: Path | None
    upgrades: tuple[UpgradeDefinition, ...]

    def __post_init__(self) -> None:
        if not self.release_id.strip():
            raise ValueError("upgrade catalog release_id must not be empty")
        upgrades = tuple(self.upgrades)
        keys = [upgrade.key for upgrade in upgrades]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate upgrade key in catalog")
        if any(upgrade.release_id != self.release_id for upgrade in upgrades):
            raise ValueError("upgrade release_id does not match catalog release_id")
        object.__setattr__(self, "upgrades", upgrades)
        if self.source_root is not None:
            object.__setattr__(self, "source_root", Path(self.source_root))

    def resolve(self, key: str) -> UpgradeDefinition | None:
        """Resolve an exact serialized upgrade id."""

        return next((upgrade for upgrade in self.upgrades if upgrade.key == key), None)

    def for_item(self, item_key: str) -> tuple[UpgradeDefinition, ...]:
        """Return only upgrades whose resource source names this exact item."""

        return tuple(
            upgrade
            for upgrade in self.upgrades
            if upgrade.applies_to(item_key)
        )


@dataclass(frozen=True)
class GameCatalog:
    """The item, upgrade and faction catalogs for exactly one release."""

    release_id: str
    items: ItemCatalog
    factions: FactionCatalog
    upgrades: UpgradeCatalog | None = None

    def __post_init__(self) -> None:
        if not self.release_id.strip():
            raise ValueError("game catalog release_id must not be empty")
        if self.items.release_id != self.release_id:
            raise ValueError("item catalog release_id does not match game catalog")
        if self.factions.release_id != self.release_id:
            raise ValueError("faction catalog release_id does not match game catalog")
        if self.upgrades is not None and self.upgrades.release_id != self.release_id:
            raise ValueError("upgrade catalog release_id does not match game catalog")


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
    icon_x: int | None = None
    icon_y: int | None = None
    icon_texture: str | None = None
    # S2 config files commonly store a localization key in DisplayName. Keep
    # that key beside the translated label so save-local rows can resolve both
    # forms without pretending that a translated string is the prototype SID.
    display_name_key: str | None = None

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
        if self.icon_texture is not None:
            texture = self.icon_texture.strip().replace("\\", "/")
            object.__setattr__(self, "icon_texture", texture or None)
        if self.display_name_key is not None:
            object.__setattr__(
                self,
                "display_name_key",
                self.display_name_key.strip() or None,
            )
        object.__setattr__(self, "slots", tuple(str(slot) for slot in self.slots))
        if self.unit_weight is not None and self.unit_weight < 0:
            raise ValueError("item weight must not be negative")
        for field_name in ("width", "height", "max_stack", "icon_x", "icon_y"):
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
        # The table resolves names on every repaint; keep lookups O(1).
        object.__setattr__(self, "_by_key", {item.key: item for item in items})
        if self.source_root is not None:
            object.__setattr__(self, "source_root", Path(self.source_root))

    def resolve(self, key: str) -> ItemDefinition | None:
        """Return the exact serialized key, without fuzzy/SID guessing."""

        return self._by_key.get(key)  # type: ignore[attr-defined]

    def resolve_display_name(self, display_name: str) -> ItemDefinition | None:
        """Resolve one unique official display name without fuzzy matching.

        A save-local name can be useful for presentation, but it must not be
        treated as a prototype SID when several definitions share that label.
        Ambiguous labels therefore return ``None`` and keep the row on the
        category/read-only fallback path.
        """

        normalized = str(display_name).strip().casefold()
        if not normalized:
            return None
        matches = tuple(
            item
            for item in self.items
            if item.display_name is not None
            and item.display_name.strip().casefold() == normalized
        )
        return matches[0] if len(matches) == 1 else None

    def resolve_key_or_display_name(self, value: str | None) -> ItemDefinition | None:
        """Resolve an exact SID, localization key, or unique translated label."""

        normalized = str(value or "").strip()
        if not normalized:
            return None
        exact = self.resolve(normalized)
        if exact is not None:
            return exact
        key_matches = tuple(
            item
            for item in self.items
            if item.display_name_key is not None
            and item.display_name_key.casefold() == normalized.casefold()
        )
        if len(key_matches) == 1:
            return key_matches[0]
        return self.resolve_display_name(normalized)


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
    "CatalogLookupError",
    "CatalogProvider",
    "FactionCatalog",
    "FactionDefinition",
    "GameCatalog",
    "ItemCatalog",
    "ItemDefinition",
    "UpgradeCatalog",
    "UpgradeDefinition",
    "catalog_from_items",
]
