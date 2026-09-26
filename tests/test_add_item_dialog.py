"""Add-item dialog: variants with one official name stay distinguishable."""

from __future__ import annotations

from editor.catalog import ItemCatalog, ItemDefinition
from ui.add_item_dialog import AddItemDialog


def _item(key: str, name: str) -> ItemDefinition:
    return ItemDefinition(key, name, "weapon", 3.0, 5, 2, None, (), None, "test")


def test_duplicate_official_names_show_their_keys(qtbot) -> None:
    catalog = ItemCatalog(
        "stalker-cs",
        None,
        (_item("wpn_ak74", "АКМ-74/2"), _item("wpn_ak74_m1", "АКМ-74/2"), _item("wpn_val", "Вал")),
    )
    dialog = AddItemDialog(catalog)
    qtbot.addWidget(dialog)
    labels = [dialog.item_list.item(index).text() for index in range(dialog.item_list.count())]
    assert "АКМ-74/2  ·  wpn_ak74" in labels
    assert "АКМ-74/2  ·  wpn_ak74_m1" in labels
    assert "Вал" in labels
