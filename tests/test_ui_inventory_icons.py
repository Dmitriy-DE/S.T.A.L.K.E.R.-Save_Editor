from __future__ import annotations

import struct
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QImage

from editor.catalog import ItemDefinition, catalog_from_items
from save_format import inspect_save
from ui.inventory_model import InventoryTableModel
from ui.xray_assets import XRayIconResolver, category_icon


def _rgba_dds(width: int, height: int, color_at: tuple[int, int, QColor]) -> bytes:
    """Build a tiny uncompressed DDS fixture with one coloured pixel."""

    header = bytearray(128)
    header[:4] = b"DDS "
    struct.pack_into("<I", header, 4, 124)
    struct.pack_into("<I", header, 8, 0x0002100F)
    struct.pack_into("<I", header, 12, height)
    struct.pack_into("<I", header, 16, width)
    struct.pack_into("<I", header, 20, width * 4)
    struct.pack_into("<I", header, 76, 32)
    struct.pack_into("<I", header, 80, 0x41)
    struct.pack_into("<I", header, 88, 32)
    struct.pack_into("<I", header, 92, 0x00FF0000)
    struct.pack_into("<I", header, 96, 0x0000FF00)
    struct.pack_into("<I", header, 100, 0x000000FF)
    struct.pack_into("<I", header, 104, 0xFF000000)
    pixels = bytearray(width * height * 4)
    x, y, color = color_at
    pixels[(y * width + x) * 4 : (y * width + x + 1) * 4] = bytes(
        (color.blue(), color.green(), color.red(), color.alpha())
    )
    return bytes(header) + bytes(pixels)


def test_xray_icon_resolver_crops_official_style_atlas(tmp_path: Path, qtbot) -> None:
    root = tmp_path / "gamedata"
    atlas_path = root / "textures" / "ui" / "ui_icon_equipment.dds"
    atlas_path.parent.mkdir(parents=True)
    atlas_path.write_bytes(_rgba_dds(100, 50, (75, 25, QColor("#d4a64b"))))
    definition = ItemDefinition(
        key="wpn_fixture",
        display_name="Fixture weapon",
        category="weapon",
        unit_weight=None,
        width=1,
        height=1,
        max_stack=None,
        slots=(),
        prototype=None,
        source="gamedata/config/items.ltx#wpn_fixture",
        icon_x=1,
        icon_y=0,
        icon_texture="ui_icon_equipment",
    )
    catalog = catalog_from_items("stalker-cop", (definition,), source_root=root)

    icon = XRayIconResolver(catalog).icon_for(definition, size=24)
    assert not icon.isNull()
    pixmap = icon.pixmap(24, 24)
    assert not pixmap.isNull()
    assert pixmap.toImage().pixelColor(12, 12).red() > 120


def test_xray_icon_resolver_reads_loose_icon_by_unique_display_name(
    tmp_path: Path, qtbot
) -> None:
    root = tmp_path / "stalker2"
    image_path = root / "Content" / "GameLite" / "UI" / "Icons" / "Bandage.png"
    image_path.parent.mkdir(parents=True)
    image = QImage(12, 12, QImage.Format.Format_RGBA8888)
    image.fill(QColor("#d44a6a"))
    assert image.save(str(image_path))
    definition = ItemDefinition(
        key="Bandage",
        display_name="UI_Item_Bandage",
        category="consumable",
        unit_weight=None,
        width=None,
        height=None,
        max_stack=10,
        slots=(),
        prototype=None,
        source="Content/GameLite/GameData/ItemPrototypes/Consumable.cfg#Bandage",
        icon_texture="UI/Icons/Bandage",
    )
    catalog = catalog_from_items("stalker2", (definition,), source_root=root)

    icon = XRayIconResolver(catalog).icon_for_item(
        "opaque-save-key",
        "UI_Item_Bandage",
        "consumable",
        size=24,
    )

    assert not icon.isNull()
    assert icon.pixmap(24, 24).toImage().pixelColor(12, 12).red() > 150


def test_xray_icon_resolver_reads_s2_unreal_texture_path(tmp_path: Path, qtbot) -> None:
    root = tmp_path / "stalker2"
    image_path = root / "Content" / "GameLite" / "UI" / "Icons" / "Armor.png"
    image_path.parent.mkdir(parents=True)
    image = QImage(12, 12, QImage.Format.Format_RGBA8888)
    image.fill(QColor("#4a9bd4"))
    assert image.save(str(image_path))
    definition = ItemDefinition(
        key="Armor_Test",
        display_name="Armor Test",
        category="outfit",
        unit_weight=None,
        width=None,
        height=None,
        max_stack=None,
        slots=(),
        prototype=None,
        source="Content/GameLite/GameData/ItemPrototypes/Armor.cfg#Armor_Test",
        icon_texture="Texture2D'/Game/GameLite/UI/Icons/Armor.Armor'",
    )
    catalog = catalog_from_items("stalker2", (definition,), source_root=root)

    icon = XRayIconResolver(catalog).icon_for(definition, size=24)

    assert not icon.isNull()
    assert icon.pixmap(24, 24).toImage().pixelColor(12, 12).blue() > 150


def test_inventory_model_exposes_a_zone_icon_for_each_item(synthetic_save: bytes, qtbot) -> None:
    model = InventoryTableModel()
    model.set_icon_provider(lambda _item: category_icon("weapon", size=24))
    model.set_items(inspect_save(synthetic_save, with_inventory=True).inventory)

    value = model.data(model.index(0, model.NAME_COLUMN), Qt.ItemDataRole.DecorationRole)
    assert isinstance(value, QIcon)
    assert not value.isNull()
