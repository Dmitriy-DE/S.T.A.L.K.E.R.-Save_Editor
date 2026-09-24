"""Shared release-aware equipment semantics for desktop and web front ends.

The parser's ``InventoryItem`` intentionally stays format-shaped.  This
module adds the product vocabulary on top of it without treating a category,
type-key, or scalar observation as proof of a writable save field.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from save_format import InventoryItem

from .capability_types import CapabilityMaturity, CapabilitySupport
from .catalog import ItemCatalog, ItemDefinition
from .equipment_matrix import EquipmentFeature, equipment_profile_for_release

EquipmentCategory = Literal[
    "weapon",
    "armor",
    "helmet",
    "module",
    "device",
    "consumable",
    "ammo",
    "artifact",
    "quest",
    "other",
]
EquipmentLocation = Literal["equipped", "inventory", "belt", "unknown"]
DeviceSubtype = Literal["nvg", "binocular", "detector", "other", "unknown"]
EquipmentProvenance = Literal["owned", "unknown"]
ObservationState = Literal["installed", "available", "applicable", "unknown"]
EquipmentObservationSource = Literal["actor_inventory", "grid", "equipped"]
SupportMaturity = CapabilityMaturity
FeatureSupport = CapabilitySupport

_FEATURE_NAMES: tuple[EquipmentFeature, ...] = (
    "durability",
    "upgrades",
    "placement",
    "add",
    "remove",
)


@dataclass(frozen=True)
class EquipmentSupport:
    """Release-scoped support metadata shared by Qt and web."""

    durability: FeatureSupport
    upgrades: FeatureSupport
    placement: FeatureSupport
    add: FeatureSupport
    remove: FeatureSupport
    categories: tuple[str, ...] = ()
    device_subtypes: tuple[str, ...] = ()
    icon_source: str | None = None

    def feature(self, name: str) -> FeatureSupport:
        if name not in _FEATURE_NAMES:
            raise KeyError(f"unknown equipment feature: {name!r}")
        return getattr(self, name)

    def as_dict(self) -> dict[str, object]:
        return {
            name: self.feature(name).as_dict()
            for name in _FEATURE_NAMES
        } | {
            "categories": list(self.categories),
            "device_subtypes": list(self.device_subtypes),
            "icon_source": self.icon_source,
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
    modules: tuple[str, ...] | None = None
    icon_x: int | None = None
    icon_y: int | None = None
    icon_texture: str | None = None
    device_subtype: DeviceSubtype | None = None
    provenance: EquipmentProvenance = "owned"
    observation_source: EquipmentObservationSource = "actor_inventory"
    module_states: tuple[tuple[str, ObservationState], ...] | None = None
    upgrade_states: tuple[tuple[str, ObservationState], ...] | None = None

    @property
    def handle_hex(self) -> str:
        return f"0x{self.handle:08X}"

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
            "modules": None if self.modules is None else list(self.modules),
            "icon_x": self.icon_x,
            "icon_y": self.icon_y,
            "icon_texture": self.icon_texture,
            "device_subtype": self.device_subtype,
            "provenance": self.provenance,
            "observation_source": self.observation_source,
            "module_states": (
                None
                if self.module_states is None
                else [
                    {"key": key, "state": state}
                    for key, state in self.module_states
                ]
            ),
            "upgrade_states": (
                None
                if self.upgrade_states is None
                else [
                    {"key": key, "state": state}
                    for key, state in self.upgrade_states
                ]
            ),
        }


def _definition(catalog: ItemCatalog | None, key: str) -> ItemDefinition | None:
    if catalog is None:
        return None
    return catalog.resolve(key)


def _s2_name_category(name: str | None) -> EquipmentCategory | None:
    """Classify only the exact save-local suffixes observed for S2 items."""

    if not name:
        return None
    normalized = re.sub(r"\s+", "_", name.strip()).casefold()
    if normalized.startswith(("nvg_", "binocular", "binoculars")):
        return "device"
    # S2 serializes armour upgrades/perks as separate rows with names such as
    # ``..._Armor_protection...`` and can assign them opaque kind codes that
    # otherwise look like weapons.  The embedded ``_Armor_``/``_Helmet_``
    # segment is a stronger product signal than that generic kind code.
    if "_armor_" in normalized or "_helmet_" in normalized:
        return "module"
    if "_upgrade_" in normalized or "_attachment_" in normalized:
        return "module"
    if normalized.startswith(("ammo_", "ammunition_")):
        return "ammo"
    if normalized.startswith(("artifact_", "artefact_")):
        return "artifact"
    if normalized.startswith(("quest_", "questitem_")):
        return "quest"
    if normalized.startswith(("consumable_", "food_", "med_")):
        return "consumable"
    if normalized.endswith("_helmet"):
        return "helmet"
    if normalized.endswith("_armor"):
        return "armor"
    return None


_S2_ARTIFACT_RE = re.compile(r"^[a-z]artifact[a-z]")
_S2_AMMO_RE = re.compile(r"^(?:[ap]\d{3}|apg7|grenade)")
_S2_QUEST_RE = re.compile(r"pda$|pda_|_pda|keycard|(?:^|_)keys?(?:_|$)|keys$")
_S2_MODULE_RE = re.compile(r"_mag[a-z]*$|silen|scope|toprail")


def _s2_observed_category(name: str | None) -> EquipmentCategory | None:
    """Classify save-local S2 SIDs whose serializer kind code is misleading.

    Observed on real saves: artifacts arrive as ``GArtifactBud``, rounds as
    ``A762NATOS``, quest PDAs and keys with weapon/ammo kind codes, and
    magazines/suppressors/scopes as consumables.  Presentation only.
    """

    normalized = re.sub(r"\s+", "_", (name or "").strip()).casefold()
    if not normalized:
        return None
    if _S2_ARTIFACT_RE.match(normalized):
        return "artifact"
    if _S2_AMMO_RE.match(normalized):
        return "ammo"
    if _S2_QUEST_RE.search(normalized):
        return "quest"
    if _S2_MODULE_RE.search(normalized):
        return "module"
    return None


def _name_category(name: str | None) -> EquipmentCategory | None:
    """Map an observed serialized name to a safe product category."""

    category = _s2_name_category(name)
    if category is not None:
        return category
    normalized = re.sub(r"\s+", "_", (name or "").strip()).casefold()
    if normalized.startswith(("device_", "detector_")):
        return "device"
    # X-Ray serialises binoculars through the weapon class, but players see
    # them as a device in the binocular slot, not as a gun.
    if normalized.startswith("wpn_binoc"):
        return "device"
    if normalized.startswith(("attach_", "attachment_", "addon_", "upgrade_")):
        return "module"
    return None


def _device_subtype(name: str | None) -> DeviceSubtype:
    """Classify an owned S2 device without treating its name as ownership proof."""

    normalized = re.sub(r"\s+", "_", (name or "").strip()).casefold()
    if normalized.startswith(
        ("nvg_", "nvg", "nightvision", "night_vision", "пнв")
    ):
        return "nvg"
    if normalized.startswith(("binocular", "binoculars", "бинокл", "wpn_binoc")):
        return "binocular"
    if "detector" in normalized or "scanner" in normalized or "детектор" in normalized:
        return "detector"
    return "unknown" if not normalized else "other"


def _device_subtype_for_item(
    item: InventoryItem,
    definition: ItemDefinition | None,
) -> DeviceSubtype:
    """Resolve a device subtype from owned-row/name metadata only."""

    candidates = (
        item.display_name,
        definition.display_name if definition is not None else None,
        definition.key if definition is not None else None,
        item.type_key,
    )
    has_name = False
    for candidate in candidates:
        has_name = has_name or bool(str(candidate or "").strip())
        subtype = _device_subtype(candidate)
        if subtype in {"nvg", "binocular", "detector"}:
            return subtype
    return "other" if has_name else "unknown"


def _text_category(value: str | None) -> EquipmentCategory | None:
    """Map exact catalog/parser vocabulary to the shared product taxonomy."""

    normalized = str(value or "").strip().casefold()
    if not normalized:
        return None
    if normalized in {"weapon", "gun", "оружие"} or "оруж" in normalized:
        return "weapon"
    if normalized in {"armor", "outfit", "броня"} or "брон" in normalized:
        return "armor"
    if normalized in {"helmet", "шлем"} or "шлем" in normalized:
        return "helmet"
    if normalized in {"module", "upgrade", "attachment"} or any(
        token in normalized for token in ("модул", "улучш", "attachment")
    ):
        return "module"
    if normalized in {"device", "detector", "устройство"} or any(
        token in normalized for token in ("устрой", "детектор", "device")
    ):
        return "device"
    # The X-Ray and S2 parsers label rounds "Патроны" and grenade stacks
    # "Гранаты/стак"; both belong to the ammunition tab, not "other".
    if normalized in {"ammo", "ammunition"} or any(
        token in normalized for token in ("боеприп", "патрон", "гранат", "grenade")
    ):
        return "ammo"
    if normalized in {"artifact", "артефакт"} or "артеф" in normalized:
        return "artifact"
    if normalized in {"quest", "quest_item"} or "квест" in normalized:
        return "quest"
    if normalized in {"consumable", "расходник"} or any(
        token in normalized for token in ("расход", "медицин", "еда", "consum")
    ):
        return "consumable"
    return None


def _is_helmet_key(
    key: str,
    definition: ItemDefinition | None,
    *,
    release_id: str,
    display_name: str | None = None,
) -> bool:
    if not helmet_category_supported(release_id):
        return False
    lowered = key.casefold()
    if lowered.startswith(("helm_", "helmet_")) or lowered.endswith(
        ("_helmet", "_helm")
    ):
        return True
    if _s2_name_category(display_name) == "helmet":
        return True
    if definition is None:
        return False
    category = (definition.category or "").casefold()
    slot_text = " ".join(definition.slots).casefold()
    return category == "helmet" or "helmet" in slot_text or "head" in slot_text


def _classify(
    item: InventoryItem,
    definition: ItemDefinition | None,
    *,
    release_id: str,
) -> EquipmentCategory:
    key = item.type_key.casefold()
    catalog_category = (definition.category if definition is not None else "") or ""
    catalog_category = catalog_category.casefold()
    parser_category = item.category.casefold()
    if _is_helmet_key(
        item.type_key,
        definition,
        release_id=release_id,
        display_name=item.display_name,
    ):
        return "helmet"
    named_category = next(
        (
            category
            for candidate in (item.display_name, item.type_key)
            for category in (_name_category(candidate),)
            if category is not None
        ),
        None,
    )
    if named_category is not None:
        return named_category
    catalog_named_category = _text_category(definition.category if definition else None)
    if catalog_named_category is not None:
        return catalog_named_category
    parser_named_category = _text_category(item.category)
    if release_id != "stalker2" and parser_named_category is not None:
        return parser_named_category
    if release_id == "stalker2" and definition is None:
        observed = _s2_observed_category(item.display_name)
        if observed is not None:
            return observed
        if item.category == "Расходник":
            return "consumable"
        if key.startswith(("ammo_", "ammunition_")):
            return "ammo"
        if key.startswith(("artifact_", "artefact_")):
            return "artifact"
        if key.startswith(("quest_", "questitem_")):
            return "quest"
        if key.startswith(("consumable_", "food_", "med_")):
            return "consumable"
        if item.category == "Устройство":
            return "device"
        if item.category == "Модуль/улучшение":
            return "module"
        if key.startswith(("wpn_", "weapon_")):
            return "weapon"
        if item.kind_code == 0:
            return "weapon"
        return "other"
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
    if item.kind_code == 0 or item.category == "Оружие":
        return "weapon"
    if key.startswith(("outfit_", "scientific_", "helm_", "armor_")):
        return "outfit"
    if _s2_name_category(item.display_name) in {"armor", "helmet"}:
        return "outfit"
    return None


def _location(item: InventoryItem) -> EquipmentLocation:
    if item.placement_type == "belt":
        return "belt"
    if item.storage == "equipped":
        return "equipped"
    if item.storage == "inventory":
        return "inventory"
    return "unknown"


def _item_durability_support(
    item: InventoryItem,
    release_support: EquipmentSupport,
    *,
    category: EquipmentCategory,
    release_id: str,
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
    if release_id == "stalker2" and category not in {"armor", "weapon"}:
        return FeatureSupport(
            "research",
            "S2 condition для этой категории не подтверждён; оставлено read-only.",
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
        if definition is None and catalog is not None and item.display_name:
            definition = catalog.resolve_display_name(item.display_name)
        category = _classify(item, definition, release_id=release_id)
        condition_editable = item.condition_editable and not (
            release_id == "stalker2" and category not in {"armor", "weapon"}
        )
        result.append(
            EquipmentItem(
                handle=item.handle,
                name=(
                    definition.display_name
                    if definition is not None and definition.display_name
                    else item.display_name
                    or f"Неизвестный предмет · {item.handle_hex}"
                ),
                type_key=item.type_key,
                category=category,
                location=_location(item),
                serializer_family=_serializer_family(item, definition),
                condition=item.condition,
                condition_editable=condition_editable,
                durability=_item_durability_support(
                    item,
                    release_support,
                    category=category,
                    release_id=release_id,
                ),
                upgrades=item.upgrades,
                upgrades_editable=item.upgrades_editable
                and release_support.upgrades.writable,
                modules=item.modules,
                icon_x=definition.icon_x if definition is not None else None,
                icon_y=definition.icon_y if definition is not None else None,
                icon_texture=definition.icon_texture if definition is not None else None,
                device_subtype=(
                    _device_subtype_for_item(item, definition)
                    if category == "device"
                    else None
                ),
                provenance="owned",
                observation_source=item.observation_source,
                module_states=(
                    None
                    if item.modules is None
                    else tuple((key, "unknown") for key in item.modules)
                ),
                upgrade_states=(
                    None
                    if item.upgrades is None
                    else tuple((key, "unknown") for key in item.upgrades)
                ),
            )
        )
    return tuple(result)


EQUIPMENT_CATEGORY_LABELS: dict[str, str] = {
    "weapon": "Оружие",
    "armor": "Броня",
    "helmet": "Шлем",
    "module": "Модуль",
    "device": "Устройство",
    "consumable": "Расходник",
    "ammo": "Боеприпасы",
    "artifact": "Артефакт",
    "quest": "Квестовый предмет",
    "other": "Прочее",
}


def category_label(category: str | None) -> str:
    """Return the Russian product label shared by the desktop and web UIs."""

    return EQUIPMENT_CATEGORY_LABELS.get(str(category or "other"), "Прочее")


def helmet_category_supported(release_id: str) -> bool:
    """Return whether this release has a separate helmet product category."""

    try:
        profile = equipment_profile_for_release(release_id)
    except KeyError:
        return False
    return "helmet" in profile.categories


def _unsupported(reason: str) -> FeatureSupport:
    return FeatureSupport("unsupported", reason)


def equipment_support_for_release(release_id: str) -> EquipmentSupport:
    """Return the single matrix entry used by every front end."""

    try:
        profile = equipment_profile_for_release(release_id)
    except KeyError:
        unsupported = _unsupported(f"Релиз {release_id!r} не зарегистрирован.")
        return EquipmentSupport(unsupported, unsupported, unsupported, unsupported, unsupported)
    support_values = tuple(profile.support(feature) for feature in _FEATURE_NAMES)
    return EquipmentSupport(
        durability=support_values[0],
        upgrades=support_values[1],
        placement=support_values[2],
        add=support_values[3],
        remove=support_values[4],
        categories=profile.categories,
        device_subtypes=profile.device_subtypes,
        icon_source=profile.icon_source,
    )


__all__ = [
    "EQUIPMENT_CATEGORY_LABELS",
    "DeviceSubtype",
    "EquipmentCategory",
    "EquipmentItem",
    "EquipmentLocation",
    "EquipmentObservationSource",
    "EquipmentProvenance",
    "EquipmentSupport",
    "FeatureSupport",
    "ObservationState",
    "SupportMaturity",
    "category_label",
    "equipment_items",
    "equipment_support_for_release",
    "helmet_category_supported",
]
