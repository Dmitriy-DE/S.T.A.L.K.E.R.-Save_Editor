"""Shared release-aware equipment semantics for desktop and web front ends.

The parser's ``InventoryItem`` intentionally stays format-shaped.  This
module adds the product vocabulary on top of it without treating a category,
type-key, or scalar observation as proof of a writable save field.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from save_format import InventoryItem

from .catalog import ItemCatalog, ItemDefinition

EquipmentCategory = Literal["weapon", "armor", "helmet", "other"]
EquipmentLocation = Literal["equipped", "inventory", "unknown"]
SupportMaturity = Literal["unsupported", "research", "experimental", "verified"]

_FEATURE_NAMES = ("durability", "upgrades", "placement", "add", "remove")
_ORIGINAL_RELEASES = frozenset({"stalker-soc", "stalker-cs", "stalker-cop"})
_EE_RELEASES = frozenset(
    {"stalker-soc-ee", "stalker-cs-ee", "stalker-cop-ee"}
)


@dataclass(frozen=True)
class FeatureSupport:
    """Evidence maturity and user-facing reason for one operation."""

    maturity: SupportMaturity
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.maturity not in {
            "unsupported",
            "research",
            "experimental",
            "verified",
        }:
            raise ValueError(f"unsupported maturity: {self.maturity!r}")
        if self.reason is not None:
            normalized = str(self.reason).strip()
            object.__setattr__(self, "reason", normalized or None)

    @property
    def writable(self) -> bool:
        """Return whether a source-backed writer may stage this operation."""

        return self.maturity in {"experimental", "verified"}

    def as_dict(self) -> dict[str, str | None]:
        return {"maturity": self.maturity, "reason": self.reason}


@dataclass(frozen=True)
class EquipmentSupport:
    """Release-scoped support metadata shared by Qt and web."""

    durability: FeatureSupport
    upgrades: FeatureSupport
    placement: FeatureSupport
    add: FeatureSupport
    remove: FeatureSupport

    def feature(self, name: str) -> FeatureSupport:
        if name not in _FEATURE_NAMES:
            raise KeyError(f"unknown equipment feature: {name!r}")
        return getattr(self, name)

    def as_dict(self) -> dict[str, dict[str, str | None]]:
        return {
            name: self.feature(name).as_dict()
            for name in _FEATURE_NAMES
        }


@dataclass(frozen=True)
class EquipmentItem:
    """One product-facing equipment row projected from an inventory item."""

    handle: int
    name: str
    type_key: str
    category: EquipmentCategory
    location: EquipmentLocation
    serializer_family: str | None
    condition: float | None
    condition_editable: bool
    durability: FeatureSupport
    upgrades: tuple[str, ...] | None
    upgrades_editable: bool
    icon_x: int | None = None
    icon_y: int | None = None
    icon_texture: str | None = None

    @property
    def durability_editable(self) -> bool:
        return self.condition_editable and self.durability.writable

    @property
    def damaged(self) -> bool:
        return self.condition is not None and self.condition < 1.0

    def as_dict(self) -> dict[str, object]:
        return {
            "handle": self.handle,
            "handle_hex": f"0x{self.handle:08X}",
            "name": self.name,
            "type_key": self.type_key,
            "category": self.category,
            "location": self.location,
            "serializer_family": self.serializer_family,
            "condition": self.condition,
            "condition_editable": self.condition_editable,
            "durability_editable": self.durability_editable,
            "durability": self.durability.as_dict(),
            "damaged": self.damaged,
            "upgrades": None if self.upgrades is None else list(self.upgrades),
            "upgrades_editable": self.upgrades_editable,
            "icon_x": self.icon_x,
            "icon_y": self.icon_y,
            "icon_texture": self.icon_texture,
        }


def _definition(catalog: ItemCatalog | None, key: str) -> ItemDefinition | None:
    if catalog is None:
        return None
    return catalog.resolve(key)


def _is_helmet_key(key: str, definition: ItemDefinition | None) -> bool:
    lowered = key.casefold()
    if lowered.startswith(("helm_", "helmet_")) or lowered.endswith(
        ("_helmet", "_helm")
    ):
        return True
    if definition is None:
        return False
    category = (definition.category or "").casefold()
    slot_text = " ".join(definition.slots).casefold()
    return category == "helmet" or "helmet" in slot_text or "head" in slot_text


def _classify(item: InventoryItem, definition: ItemDefinition | None) -> EquipmentCategory:
    key = item.type_key.casefold()
    catalog_category = (definition.category if definition is not None else "") or ""
    catalog_category = catalog_category.casefold()
    parser_category = item.category.casefold()
    if _is_helmet_key(item.type_key, definition):
        return "helmet"
    if catalog_category == "weapon" or key.startswith(("wpn_", "weapon_")):
        return "weapon"
    if catalog_category in {"armor", "outfit"} or "брон" in parser_category:
        return "armor"
    if "оруж" in parser_category:
        return "weapon"
    return "other"


def _serializer_family(
    item: InventoryItem,
    definition: ItemDefinition | None,
) -> str | None:
    if definition is not None and definition.serialization_family:
        return definition.serialization_family
    key = item.type_key.casefold()
    if key.startswith("ammo_"):
        return "ammo"
    if key.startswith(("wpn_", "weapon_")):
        return "weapon"
    if key.startswith(("outfit_", "scientific_", "helm_", "armor_")):
        return "outfit"
    return None


def _location(item: InventoryItem) -> EquipmentLocation:
    if item.storage == "equipped":
        return "equipped"
    if item.storage == "inventory":
        return "inventory"
    return "unknown"


def _item_durability_support(
    item: InventoryItem,
    release_support: EquipmentSupport,
) -> FeatureSupport:
    if item.condition is None:
        return FeatureSupport(
            "unsupported",
            "В сейве нет подтверждённого поля прочности для этого предмета.",
        )
    if not item.condition_editable:
        return FeatureSupport(
            "research",
            "Прочность прочитана, но точный writer-anchor отсутствует или неоднозначен.",
        )
    return release_support.durability


def equipment_items(
    items: tuple[InventoryItem, ...] | list[InventoryItem],
    *,
    release_id: str,
    catalog: ItemCatalog | None = None,
) -> tuple[EquipmentItem, ...]:
    """Project parser rows into the shared Equipment product model."""

    release_support = equipment_support_for_release(release_id)
    result: list[EquipmentItem] = []
    for item in items:
        definition = _definition(catalog, item.type_key)
        result.append(
            EquipmentItem(
                handle=item.handle,
                name=item.display_name or f"Неизвестный предмет · {item.handle_hex}",
                type_key=item.type_key,
                category=_classify(item, definition),
                location=_location(item),
                serializer_family=_serializer_family(item, definition),
                condition=item.condition,
                condition_editable=item.condition_editable,
                durability=_item_durability_support(item, release_support),
                upgrades=item.upgrades,
                upgrades_editable=item.upgrades_editable
                and release_support.upgrades.writable,
                icon_x=definition.icon_x if definition is not None else None,
                icon_y=definition.icon_y if definition is not None else None,
                icon_texture=definition.icon_texture if definition is not None else None,
            )
        )
    return tuple(result)


def _unsupported(reason: str) -> FeatureSupport:
    return FeatureSupport("unsupported", reason)


def equipment_support_for_release(release_id: str) -> EquipmentSupport:
    """Return explicit maturity metadata for every official release profile."""

    if release_id in _ORIGINAL_RELEASES:
        durability = FeatureSupport(
            "experimental",
            "X-Ray STATE/UPDATE condition anchors подтверждены структурно; game load/re-save ещё не принят.",
        )
        upgrades = (
            FeatureSupport(
                "experimental",
                "m_upgrades vector подтверждён структурно для Clear Sky/Call of Pripyat; game load/re-save ещё не принят.",
            )
            if release_id in {"stalker-cs", "stalker-cop"}
            else _unsupported("m_upgrades writer не подтверждён для этого релиза.")
        )
        placement = FeatureSupport(
            "experimental",
            "SInvItemPlace anchor подтверждён структурно; game load/re-save ещё не принят.",
        )
        structural = FeatureSupport(
            "experimental",
            "Структурный writer существует; принятие игрой требует отдельного load/re-save evidence.",
        )
        return EquipmentSupport(durability, upgrades, placement, structural, structural)

    if release_id == "stalker2":
        return EquipmentSupport(
            FeatureSupport(
                "research",
                "Нет детерминированного condition codec для weapon/armor/helmet и game load/re-save evidence.",
            ),
            FeatureSupport(
                "research",
                "Official CFG metadata не связывает prototype SID с compact save type-key.",
            ),
            _unsupported("S2 placement serialization не подтверждена."),
            _unsupported("S2 add/clone constructor не подтверждён."),
            _unsupported("S2 safe remove/reference graph не подтверждён."),
        )

    if release_id in _EE_RELEASES:
        reason = "Для Enhanced Edition нет принятого parser/equipment format sample."
        unsupported = _unsupported(reason)
        return EquipmentSupport(unsupported, unsupported, unsupported, unsupported, unsupported)

    reason = f"Релиз {release_id!r} не зарегистрирован как Equipment profile."
    unsupported = _unsupported(reason)
    return EquipmentSupport(unsupported, unsupported, unsupported, unsupported, unsupported)


__all__ = [
    "EquipmentCategory",
    "EquipmentItem",
    "EquipmentLocation",
    "EquipmentSupport",
    "FeatureSupport",
    "SupportMaturity",
    "equipment_items",
    "equipment_support_for_release",
]
