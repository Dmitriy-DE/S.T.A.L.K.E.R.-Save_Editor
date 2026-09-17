from __future__ import annotations

import struct
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon

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


def test_inventory_model_exposes_a_zone_icon_for_each_item(synthetic_save: bytes, qtbot) -> None:
    model = InventoryTableModel()
    model.set_icon_provider(lambda _item: category_icon("weapon", size=24))
    model.set_items(inspect_save(synthetic_save, with_inventory=True).inventory)

    value = model.data(model.index(0, model.NAME_COLUMN), Qt.ItemDataRole.DecorationRole)
    assert isinstance(value, QIcon)
    assert not value.isNull()
