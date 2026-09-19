from __future__ import annotations

from test_xray_durability import _condition_fixture

from editor.capabilities import FormatCapabilities
from editor.catalog import ItemDefinition, catalog_from_items
from editor.equipment import (
    equipment_items,
    equipment_support_for_release,
    helmet_category_supported,
)
from editor.xray_save import COP_FORMAT, parse_xray
from save_format import InventoryItem


def _item(
    type_key: str,
    category: str,
    *,
    storage: str | None = None,
    condition: float | None = None,
    condition_editable: bool = False,
    placement_type: str | None = None,
) -> InventoryItem:
    return InventoryItem(
        handle=0x1000 + len(type_key),
        x=None,
        y=None,
        width=None,
        height=None,
        cells=(),
        count=1,
        total_weight=None,
        unit_weight=None,
        kind_code=1,
        category=category,
        record_offset=0,
        record_end_guess=64,
        fingerprint="f" * 64,
        type_key=type_key,
        editable_count=False,
        display_name=type_key,
        condition=condition,
        condition_editable=condition_editable,
        storage=storage,  # type: ignore[arg-type]
        placement_type=placement_type,  # type: ignore[arg-type]
    )


def _catalog(*definitions: tuple[str, str, str | None]) :
    return catalog_from_items(
        "stalker-cop",
        tuple(
            ItemDefinition(
                key=key,
                display_name=key,
                category=category,
                unit_weight=None,
                width=None,
                height=None,
                max_stack=None,
                slots=(),
                prototype=None,
                source="fixture",
                serialization_family=family,
            )
            for key, category, family in definitions
        ),
    )


def test_equipment_projection_separates_category_family_and_location() -> None:
    catalog = _catalog(
        ("wpn_ak", "weapon", "weapon_magazined"),
        ("outfit_stalker", "outfit", "outfit"),
        ("helm_battle", "outfit", "outfit"),
    )

    rows = equipment_items(
        (
            _item("wpn_ak", "Оружие", storage="equipped", condition=0.5, condition_editable=True),
            _item("outfit_stalker", "Броня/экипировка", storage="inventory", condition=0.75),
            _item("helm_battle", "Броня/экипировка", storage="equipped", condition=1.0),
        ),
        release_id="stalker-cop",
        catalog=catalog,
    )

    assert [row.category for row in rows] == ["weapon", "armor", "helmet"]
    assert [row.serializer_family for row in rows] == [
        "weapon_magazined",
        "outfit",
        "outfit",
    ]
    assert [row.location for row in rows] == ["equipped", "inventory", "equipped"]
    assert rows[0].condition == 0.5
    assert rows[0].condition_editable is True


def test_unknown_equipment_never_gets_a_guessed_category_or_location() -> None:
    row = equipment_items(
        (_item("opaque_thing", "Разное", condition=0.5),),
        release_id="stalker2",
    )[0]

    assert row.category == "other"
    assert row.location == "unknown"
    assert row.serializer_family is None
    assert row.durability_editable is False
    assert row.durability.reason


def test_catalog_name_and_icon_are_used_for_a_cop_helmet() -> None:
    catalog = catalog_from_items(
        "stalker-cop",
        (
            ItemDefinition(
                key="helm_battle",
                display_name="Battle Helmet",
                category="outfit",
                unit_weight=None,
                width=None,
                height=None,
                max_stack=None,
                slots=("helmet",),
                prototype=None,
                source="official/items.ltx#helm_battle",
                serialization_family="outfit",
                icon_x=4,
                icon_y=5,
                icon_texture="ui_icon_equipment",
            ),
        ),
    )

    row = equipment_items(
        (_item("helm_battle", "Броня/экипировка", storage="equipped"),),
        release_id="stalker-cop",
        catalog=catalog,
    )[0]

    assert row.name == "Battle Helmet"
    assert row.icon_x == 4
    assert row.icon_y == 5
    assert row.icon_texture == "ui_icon_equipment"
    assert row.category == "helmet"
    assert row.serializer_family == "outfit"


def test_xray_helmet_keeps_outfit_serializer_family() -> None:
    parsed = parse_xray(
        _condition_fixture(version=128, outer=6, name="helm_battle"),
        COP_FORMAT,
    )
    row = equipment_items(parsed.inventory, release_id="stalker-cop")[0]

    assert row.category == "helmet"
    assert row.serializer_family == "outfit"
    assert row.condition == 0.25
    assert row.durability_editable is True


def test_separate_helmet_taxonomy_is_release_scoped() -> None:
    helmet = (_item("helm_battle", "Броня/экипировка", condition=0.5),)

    assert helmet_category_supported("stalker-cop") is True
    assert helmet_category_supported("stalker-soc") is False
    assert helmet_category_supported("stalker-cs") is False
    assert helmet_category_supported("stalker-cop-ee") is False
    assert helmet_category_supported("stalker2") is True
    assert equipment_items(helmet, release_id="stalker-cop")[0].category == "helmet"
    assert equipment_items(helmet, release_id="stalker-soc")[0].category == "armor"
    assert equipment_items(helmet, release_id="stalker-cs")[0].category == "armor"
    assert equipment_items(helmet, release_id="stalker-cop-ee")[0].category == "armor"


def test_belt_location_is_distinct_from_backpack() -> None:
    row = equipment_items(
        (_item("wpn_test", "Оружие", storage="inventory", placement_type="belt"),),
        release_id="stalker-cop",
    )[0]

    assert row.location == "belt"


def test_release_support_is_explicit_for_s2_original_and_enhanced_profiles() -> None:
    s2 = equipment_support_for_release("stalker2")
    cop = equipment_support_for_release("stalker-cop")
    ee = equipment_support_for_release("stalker-cop-ee")

    assert s2.durability.maturity == "research"
    assert s2.durability.reason
    assert cop.durability.maturity == "experimental"
    assert cop.upgrades.maturity == "experimental"
    assert ee.durability.maturity == "unsupported"
    assert ee.durability.reason


def test_capability_json_contains_shared_equipment_maturity() -> None:
    payload = FormatCapabilities(
        read_inventory=True,
        equipment=equipment_support_for_release("stalker2"),
    ).as_dict()

    assert payload["equipment"]["durability"]["maturity"] == "research"
    assert payload["equipment"]["placement"]["maturity"] == "unsupported"
