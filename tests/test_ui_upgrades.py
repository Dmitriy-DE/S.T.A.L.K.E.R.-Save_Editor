from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import Qt
from test_xray_upgrades import _upgrade_fixture

from editor.catalog import UpgradeCatalog, UpgradeDefinition
from editor.xray_save import COP_FORMAT, inspect_xray
from ui.inventory_view import InventoryView


def test_qt_upgrade_editor_stages_catalog_values_and_keeps_unknown_ids(qtbot) -> None:
    data = _upgrade_fixture()
    info = inspect_xray(data, COP_FORMAT)
    catalog = UpgradeCatalog(
        release_id=COP_FORMAT.id,
        source_root=None,
        upgrades=(
            UpgradeDefinition(
                key="up_a_wpn_test",
                display_name="Factory upgrade",
                category="weapon",
                item_key="wpn_test",
                source="fixture",
                release_id=COP_FORMAT.id,
            ),
            UpgradeDefinition(
                key="up_c_wpn_test",
                display_name="Catalog upgrade",
                category="weapon",
                item_key="wpn_test",
                source="fixture",
                release_id=COP_FORMAT.id,
            ),
        ),
    )

    view = InventoryView()
    qtbot.addWidget(view)
    view.set_items(info.inventory)
    view.set_upgrades_enabled(True, catalog)
    view.table.selectRow(0)
    qtbot.waitUntil(lambda: view.selected_handle == info.inventory[0].handle)

    assert view.upgrade_list.isEnabled()
    assert view.upgrade_list.count() == 3
    labels = [view.upgrade_list.item(index).text() for index in range(view.upgrade_list.count())]
    assert any("Factory upgrade" in label for label in labels)
    assert any("Неизвестный ID" in label for label in labels)

    catalog_item = next(
        view.upgrade_list.item(index)
        for index in range(view.upgrade_list.count())
        if view.upgrade_list.item(index).data(Qt.ItemDataRole.UserRole) == "up_c_wpn_test"
    )
    catalog_item.setCheckState(Qt.CheckState.Checked)
    with qtbot.waitSignal(view.upgrades_stage_requested, timeout=1000) as signal:
        qtbot.mouseClick(view.upgrade_stage_button, Qt.MouseButton.LeftButton)

    assert signal.args == [
        info.inventory[0].handle,
        ("up_a_wpn_test", "legacy_unknown", "up_c_wpn_test"),
    ]
