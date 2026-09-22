from __future__ import annotations

from test_xray_durability import _condition_fixture

from editor.capabilities import CapabilitySupport, FormatCapabilities
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
    display_name: str | None = None,
    modules: tuple[str, ...] | None = None,
    upgrades: tuple[str, ...] | None = None,
    observation_source: str = "actor_inventory",
    kind_code: int = 1,
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
        kind_code=kind_code,
        category=category,
        record_offset=0,
        record_end_guess=64,
        fingerprint="f" * 64,
        type_key=type_key,
        editable_count=False,
        display_name=display_name or type_key,
        condition=condition,
        condition_editable=condition_editable,
        storage=storage,  # type: ignore[arg-type]
        placement_type=placement_type,  # type: ignore[arg-type]
        modules=modules,
        upgrades=upgrades,
        observation_source=observation_source,  # type: ignore[arg-type]
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


def test_s2_equipment_uses_save_names_instead_of_opaque_kind_codes() -> None:
    rows = equipment_items(
        (
            _item(
                "052c01",
                "Оружие",
                storage="inventory",
                display_name="Heavy_Dolg_Armor",
            ),
            _item(
                "05e300",
                "Оружие",
                storage="equipped",
                display_name="Heavy_Svoboda_Helmet",
            ),
            _item(
                "056f01",
                "Броня/экипировка",
                storage="equipped",
                condition=0.75,
                condition_editable=True,
                display_name="GunBucket_MagIncreased",
            ),
            _item(
                "05c600",
                "Броня/экипировка",
                storage="inventory",
                display_name="Exoskeleton_Monolith_Armor_PSY_Left_2_2",
            ),
        ),
        release_id="stalker2",
    )

    assert [row.category for row in rows] == ["armor", "helmet", "other", "module"]
    assert rows[2].durability_editable is False
    assert rows[2].durability.maturity == "research"
    assert rows[3].durability_editable is False
    assert rows[3].condition is None


def test_s2_armor_perk_rows_are_modules_even_when_kind_code_looks_like_weapon() -> None:
    rows = equipment_items(
        (
            _item(
                "05d000",
                "Разное",
                storage="equipped",
                display_name="Exoskeleton_Monolith_Armor_rad_container_Left_2_1",
                kind_code=0,
            ),
            _item(
                "05ce00",
                "Разное",
                storage="equipped",
                display_name="Exoskeleton_Monolith_Armor_protectionElectrical_Left_2_2",
                kind_code=0,
            ),
        ),
        release_id="stalker2",
    )

    assert [row.category for row in rows] == ["module", "module"]
    assert all(row.durability_editable is False for row in rows)


def test_s2_devices_and_weapon_modules_keep_separate_product_semantics() -> None:
    rows = equipment_items(
        (
            _item(
                "057601",
                "Устройство",
                storage="inventory",
                display_name="NVG_NPC_Gen3",
            ),
            _item(
                "041a01",
                "Оружие",
                storage="equipped",
                condition=0.92,
                condition_editable=True,
                display_name="GunKharod_ST",
                modules=("GunKharod_MagDefault", "HP_Laser_1"),
                upgrades=("GunKharod_Upgrade_Stock_1",),
                kind_code=0,
            ),
        ),
        release_id="stalker2",
    )

    assert [row.category for row in rows] == ["device", "weapon"]
    assert rows[0].condition is None
    assert rows[0].durability_editable is False
    assert rows[1].modules == ("GunKharod_MagDefault", "HP_Laser_1")
    assert rows[1].upgrades == ("GunKharod_Upgrade_Stock_1",)
    assert rows[1].durability_editable is True


def test_shared_projection_keeps_full_category_and_device_state_vocabulary() -> None:
    rows = equipment_items(
        (
            _item(
                "ammo_9x39",
                "Боеприпасы",
                storage="inventory",
                display_name="Ammo_9x39",
            ),
            _item(
                "artifact_blood",
                "Артефакт",
                storage="inventory",
                display_name="Artifact_Blood",
            ),
            _item(
                "quest_key",
                "Квестовый предмет",
                storage="inventory",
                display_name="Quest_Key",
            ),
            _item(
                "057601",
                "Устройство",
                storage="inventory",
                display_name="Binoculars_NPC",
            ),
        ),
        release_id="stalker2",
    )

    assert [row.category for row in rows] == ["ammo", "artifact", "quest", "device"]
    assert rows[3].device_subtype == "binocular"
    assert rows[3].provenance == "owned"
    assert rows[3].condition is None
    assert rows[3].durability_editable is False
    assert rows[3].as_dict()["device_subtype"] == "binocular"


def test_localized_s2_device_labels_keep_their_subtype() -> None:
    row = equipment_items(
        (_item("057601", "Устройство", display_name="ПНВ (3-е поколение)"),),
        release_id="stalker2",
    )[0]

    assert row.category == "device"
    assert row.device_subtype == "nvg"
    assert row.durability_editable is False


def test_projection_preserves_parser_observation_source_for_ui_diagnostics() -> None:
    rows = equipment_items(
        (
            _item(
                "057601",
                "Устройство",
                storage="equipped",
                display_name="NVG_NPC_Gen3",
                observation_source="equipped",
            ),
            _item(
                "ammo_9x39",
                "Боеприпасы",
                storage="inventory",
                display_name="Ammo_9x39",
                observation_source="grid",
            ),
        ),
        release_id="stalker2",
    )

    assert [row.observation_source for row in rows] == ["equipped", "grid"]
    assert rows[0].as_dict()["observation_source"] == "equipped"
    assert rows[1].as_dict()["observation_source"] == "grid"


def test_observed_s2_modules_and_upgrades_are_explicitly_unclassified() -> None:
    row = equipment_items(
        (
            _item(
                "041a01",
                "Оружие",
                storage="equipped",
                condition=0.92,
                condition_editable=True,
                display_name="GunKharod_ST",
                modules=("GunKharod_MagDefault", "HP_Laser_1"),
                upgrades=("GunKharod_Upgrade_Stock_1",),
                kind_code=0,
            ),
        ),
        release_id="stalker2",
    )[0]

    assert row.module_states == (
        ("GunKharod_MagDefault", "unknown"),
        ("HP_Laser_1", "unknown"),
    )
    assert row.upgrade_states == (("GunKharod_Upgrade_Stock_1", "unknown"),)
    assert row.upgrades_editable is False
    assert row.as_dict()["module_states"] == [
        {"key": "GunKharod_MagDefault", "state": "unknown"},
        {"key": "HP_Laser_1", "state": "unknown"},
    ]



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


def test_xray_devices_have_a_category_but_never_a_condition_editor() -> None:
    parsed = parse_xray(
        _condition_fixture(version=128, outer=6, name="device_pda"),
        COP_FORMAT,
    )
    row = equipment_items(parsed.inventory, release_id="stalker-cop")[0]

    assert row.category == "device"
    assert row.device_subtype == "other"
    assert row.condition is None
    assert row.durability_editable is False


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

    assert s2.durability.maturity == "experimental"
    assert s2.durability.reason
    assert cop.durability.maturity == "experimental"
    assert cop.upgrades.maturity == "experimental"
    assert ee.durability.maturity == "unsupported"
    assert ee.durability.reason


def test_capability_json_contains_shared_equipment_maturity() -> None:
    payload = FormatCapabilities(
        read_inventory=True,
        equipment=equipment_support_for_release("stalker2"),
        mutation_support={
            "edit_durability": CapabilitySupport("experimental"),
        },
    ).as_dict()

    assert payload["equipment"]["durability"]["maturity"] == "experimental"
    assert payload["equipment"]["placement"]["maturity"] == "unsupported"
