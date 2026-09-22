from __future__ import annotations

from pathlib import Path

from editor.formats import STALKER2_FORMAT, by_id
from editor.releases import release_by_id
from editor.s2_catalog import (
    S2CatalogProvider,
    discover_s2_catalog_sources,
)


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
    DisplayName = UI_Item_Bandage
    Icon = UI/Icons/Items/Bandage.png
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
    (directory / "NestedMetadata.cfg").write_text(
        """
NestedMetadata : struct.begin
    Type = EItemPrototypeType::Weapon
    Metadata : struct.begin
        SID = NestedOnly
    struct.end
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
    DisplayName = UI_Upgrade_GunAKU_Attachment
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
    assert bandage.display_name == "UI_Item_Bandage"
    assert bandage.category == "consumable"
    assert bandage.unit_weight == 0.05
    assert bandage.max_stack == 10
    assert bandage.slots == ("QuickUse",)
    assert bandage.serialization_family is None
    assert bandage.icon_texture == "UI/Icons/Items/Bandage.png"
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
    assert bundle.items.resolve("NestedOnly") is None

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
    attachment = bundle.upgrades.resolve("GunAKU_Upgrade_Attachment")
    assert attachment is not None
    assert attachment.display_name == "UI_Upgrade_GunAKU_Attachment"
    assert not bundle.factions.factions
    assert bundle.items.resolve_display_name("UI_Item_Bandage") == bandage


def test_s2_catalog_resolves_zonekit_localization_json(tmp_path: Path) -> None:
    _write_s2_resources(tmp_path)
    localization = tmp_path / "Content" / "Localization" / "en"
    localization.mkdir(parents=True)
    (localization / "Items.json").write_text(
        '{"UI_Item_Bandage": "Bandage", "UI_Upgrade_GunAKU_Attachment": "Rail mount"}\n',
        encoding="utf-8",
    )

    bundle = S2CatalogProvider().load_bundle(release_by_id("stalker2"), tmp_path)

    assert bundle is not None
    assert bundle.items.resolve("Bandage").display_name == "Bandage"  # type: ignore[union-attr]
    upgrade = bundle.upgrades.resolve("GunAKU_Upgrade_Attachment")  # type: ignore[union-attr]
    assert upgrade is not None
    assert upgrade.display_name == "Rail mount"


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


def test_s2_format_reuses_one_catalog_scan_for_items_and_bundle(
    tmp_path: Path, monkeypatch
) -> None:
    _write_s2_resources(tmp_path)
    save_path = tmp_path / "Saved" / "slot.sav"
    save_path.parent.mkdir()
    save_path.write_bytes(b"placeholder")

    provider_type = S2CatalogProvider
    original = provider_type.load_bundle
    calls = 0

    def counted(self, release, game_root=None):
        nonlocal calls
        calls += 1
        return original(self, release, game_root)

    monkeypatch.setattr(provider_type, "load_bundle", counted)
    catalog = STALKER2_FORMAT.catalog_for_source(str(save_path))
    first_calls = calls
    bundle = STALKER2_FORMAT.game_catalog_for_source(str(save_path))

    assert catalog is not None
    assert bundle is not None
    assert first_calls > 0
    assert calls == first_calls


def test_s2_format_discovers_installed_loose_resources_without_save_path(
    tmp_path: Path, monkeypatch
) -> None:
    _write_s2_resources(tmp_path)
    from editor import platforms

    game = platforms.InstalledGame(
        game_id="stalker2",
        app_id=1643320,
        edition="s2",
        library_root=tmp_path,
        install_dir=tmp_path,
    )
    monkeypatch.setattr(platforms, "installed_releases", lambda **_kwargs: (game,))

    catalog = STALKER2_FORMAT.catalog_for_source(None)

    assert catalog is not None
    assert catalog.source_root == tmp_path
    assert catalog.resolve("Bandage") is not None


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


def test_s2_provider_reads_workshop_overlay_only_through_explicit_method(
    tmp_path: Path,
) -> None:
    workshop_item = tmp_path / "workshop" / "123456"
    mod_root = workshop_item / "Stalker2" / "Mods" / "FixtureMod"
    _write_s2_resources(mod_root)

    provider = S2CatalogProvider()
    assert provider.load(release_by_id("stalker2"), workshop_item) is None

    catalog = provider.load_overlay(release_by_id("stalker2"), workshop_item)

    assert catalog is not None
    assert catalog.source_root == mod_root
    assert catalog.resolve("Bandage") is not None


def test_s2_catalog_source_discovery_finds_zonekit_and_workshop_roots(
    tmp_path: Path,
) -> None:
    save_root = tmp_path / "saves"
    save_root.mkdir()
    save_path = save_root / "slot.sav"
    save_path.write_bytes(b"placeholder")
    installed_root = tmp_path / "installed-s2"
    zonekit_root = tmp_path / "zone-kit"
    installed_root.mkdir()
    zonekit_root.mkdir()
    library = tmp_path / "steam-library"
    workshop_item = library / "steamapps" / "workshop" / "content" / "1643320" / "123456"
    workshop_item.mkdir(parents=True)

    sources = discover_s2_catalog_sources(
        str(save_path),
        installed_roots=(installed_root,),
        steam_libraries=(library,),
        environ={"STALKER2_ZONE_KIT_ROOT": str(zonekit_root)},
    )

    assert any(source.root == save_root and source.kind == "official" for source in sources)
    assert any(source.root == installed_root and source.kind == "official" for source in sources)
    assert any(source.root == zonekit_root and source.kind == "zonekit" for source in sources)
    assert any(source.root == workshop_item and source.kind == "workshop" for source in sources)
    assert next(source.kind for source in sources if source.root == workshop_item) == "workshop"


def test_s2_catalog_source_discovery_accepts_explicit_workshop_item_root(
    tmp_path: Path,
) -> None:
    workshop_item = tmp_path / "123456"
    (workshop_item / "Content" / "GameLite" / "GameData").mkdir(parents=True)

    sources = discover_s2_catalog_sources(
        environ={"STALKER2_WORKSHOP_ROOT": str(workshop_item)},
    )

    assert any(source.root == workshop_item and source.kind == "workshop" for source in sources)


def test_s2_catalog_source_discovery_prioritises_explicit_catalog_root(
    tmp_path: Path,
) -> None:
    save_path = tmp_path / "remote" / "slot.sav"
    save_path.parent.mkdir()
    save_path.write_bytes(b"placeholder")
    zonekit_root = tmp_path / "Zone Kit export"
    zonekit_root.mkdir()

    sources = discover_s2_catalog_sources(
        str(save_path),
        catalog_roots=(zonekit_root,),
    )

    assert sources[0].root == zonekit_root
    assert sources[0].kind == "zonekit"


def test_s2_format_uses_loose_workshop_catalog_when_official_tree_is_missing(
    tmp_path: Path, monkeypatch
) -> None:
    library = tmp_path / "steam-library"
    workshop_item = library / "steamapps" / "workshop" / "content" / "1643320" / "123456"
    mod_root = workshop_item / "Stalker2" / "Mods" / "FixtureMod"
    _write_s2_resources(mod_root)
    localization = mod_root / "Content" / "Localization" / "en"
    localization.mkdir(parents=True)
    (localization / "Items.json").write_text(
        '{"UI_Item_Bandage": "Bandage"}\n',
        encoding="utf-8",
    )
    workshop_item.mkdir(parents=True, exist_ok=True)

    from editor import platforms

    monkeypatch.setattr(platforms, "installed_releases", lambda **_kwargs: ())
    monkeypatch.setattr(platforms, "steam_libraries", lambda **_kwargs: (library,))

    bundle = STALKER2_FORMAT.game_catalog_for_source(None)

    assert bundle is not None
    assert bundle.items.source_root == mod_root
    bandage = bundle.items.resolve("Bandage")
    assert bandage is not None
    assert bandage.display_name == "Bandage"


def test_format_registry_points_at_s2_adapter() -> None:
    assert by_id("stalker2") is STALKER2_FORMAT
