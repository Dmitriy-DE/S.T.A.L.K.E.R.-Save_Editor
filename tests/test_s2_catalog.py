from __future__ import annotations

from pathlib import Path

from editor.formats import STALKER2_FORMAT, by_id
from editor.releases import release_by_id
from editor.s2_catalog import S2CatalogProvider


def _write_s2_resources(root: Path) -> Path:
    directory = root / "Content" / "GameLite" / "GameData" / "ItemPrototypes"
    directory.mkdir(parents=True)
    (directory / "ConsumablePrototypes.cfg").write_text(
        """
BaseConsumable : struct.begin
    Type = EItemPrototypeType::Consumable
    Weight = 0.10
    MaxStackCount = 5
struct.end

InheritedConsumable : struct.begin {refkey=BaseConsumable}
    SID = InheritedConsumable
    ItemSlotType = EItemSlotType::QuickUse
struct.end

Bandage : struct.begin {refkey=BaseConsumable}
    SID = Bandage
    Type = EItemPrototypeType::Consumable
    Weight = 0.05
    MaxStackCount = 10
    ItemSlotType = EItemSlotType::QuickUse
    UpgradePrototypeSIDs : struct.begin
        [0] = Bandage_Upgrade_Test
    struct.end
struct.end
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (directory / "WeaponPrototypes.cfg").write_text(
        """
GunAKU : struct.begin
    SID = GunAKU
    Type = EItemPrototypeType::Weapon
    Weight = 2.75
    ItemSlotType = EInventoryEquipmentSlot::PrimaryWeapon
    UpgradePrototypeSID = GunAKU_Upgrade_Rail
    UpgradePrototypeSID = GunAKU_Upgrade_Muzzle
struct.end
""".strip()
        + "\n",
        encoding="utf-8",
    )
    upgrades = directory.parent / "Upgrades"
    upgrades.mkdir()
    (upgrades / "ConsumableUpgrades.cfg").write_text(
        """
Bandage_Upgrade_Standalone : struct.begin
    SID = Bandage_Upgrade_Standalone
    ItemPrototypeSID = Bandage
struct.end

GunAKU_Upgrade_Attachment : struct.begin
    SID = GunAKU_Upgrade_Attachment
    ItemPrototypeSID = GunAKU
struct.end
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return directory


def test_s2_catalog_reads_official_cfg_metadata_without_save_mapping(tmp_path: Path) -> None:
    _write_s2_resources(tmp_path)

    bundle = S2CatalogProvider().load_bundle(release_by_id("stalker2"), tmp_path)

    assert bundle is not None
    bandage = bundle.items.resolve("Bandage")
    assert bandage is not None
    assert bandage.display_name is None
    assert bandage.category == "consumable"
    assert bandage.unit_weight == 0.05
    assert bandage.max_stack == 10
    assert bandage.slots == ("QuickUse",)
    assert bandage.serialization_family is None
    assert bandage.prototype is None
    assert bandage.source.endswith("ConsumablePrototypes.cfg#Bandage")

    inherited = bundle.items.resolve("InheritedConsumable")
    assert inherited is not None
    assert inherited.unit_weight == 0.1
    assert inherited.max_stack == 5
    assert inherited.slots == ("QuickUse",)

    weapon = bundle.items.resolve("GunAKU")
    assert weapon is not None
    assert weapon.category == "weapon"
    assert weapon.unit_weight == 2.75
    assert weapon.slots == ("PrimaryWeapon",)

    assert bundle.upgrades is not None
    assert [item.key for item in bundle.upgrades.for_item("GunAKU")] == [
        "GunAKU_Upgrade_Attachment",
        "GunAKU_Upgrade_Muzzle",
        "GunAKU_Upgrade_Rail",
    ]
    assert [item.key for item in bundle.upgrades.for_item("Bandage")] == [
        "Bandage_Upgrade_Standalone",
        "Bandage_Upgrade_Test",
    ]
    assert not bundle.factions.factions


def test_s2_provider_walks_from_save_path_but_never_enables_save_writer(
    tmp_path: Path,
) -> None:
    _write_s2_resources(tmp_path)
    save_path = tmp_path / "Saved" / "slot.sav"
    save_path.parent.mkdir()
    save_path.write_bytes(b"placeholder")

    catalog = STALKER2_FORMAT.catalog_for_source(str(save_path))

    assert catalog is not None
    assert catalog.resolve("Bandage") is not None
    assert STALKER2_FORMAT.capabilities.catalog is True
    assert STALKER2_FORMAT.capabilities.add_items is False


def test_s2_provider_rejects_mod_overlay_root_and_nested_files(tmp_path: Path) -> None:
    mod_root = tmp_path / "Mods"
    _write_s2_resources(mod_root)
    assert S2CatalogProvider().load(release_by_id("stalker2"), mod_root) is None

    official_root = tmp_path / "official"
    directory = _write_s2_resources(official_root)
    mod_file = directory / "~mods" / "Injected.cfg"
    mod_file.parent.mkdir()
    mod_file.write_text(
        "Injected : struct.begin\n SID = Injected\n Type = EItemPrototypeType::Weapon\nstruct.end\n",
        encoding="utf-8",
    )
    catalog = S2CatalogProvider().load(release_by_id("stalker2"), official_root)
    assert catalog is not None
    assert catalog.resolve("Injected") is None


def test_format_registry_points_at_s2_adapter() -> None:
    assert by_id("stalker2") is STALKER2_FORMAT
