from __future__ import annotations

from dataclasses import replace

import pytest

pytest.importorskip("PySide6")

from editor.capabilities import FormatCapabilities
from editor.service import EditorService
from save_format import inspect_save
from ui.item_detail_view import ItemDetailView
from ui.main_window import LocalSnapshot, MainWindow


def test_canonical_item_detail_keeps_unconfirmed_upgrades_as_evidence(
    qtbot, synthetic_save: bytes, tmp_path
) -> None:
    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)
    window._render_snapshot(LocalSnapshot(
        path=tmp_path / "slot.sav",
        data=synthetic_save,
        info=inspect_save(synthetic_save, with_inventory=True),
        capabilities=FormatCapabilities(read_inventory=True),
    ))
    editor = window.editor_view
    editor.table.selectRow(0)
    qtbot.waitUntil(lambda: editor.selected_handle is not None)
    assert editor.detail_view.module_status.text() == "Данные о модификациях недоступны."


def test_item_detail_presents_unresolved_upgrade_keys_as_readable_evidence(
    qtbot, synthetic_save: bytes
) -> None:
    info = inspect_save(synthetic_save, with_inventory=True)
    item = replace(
        info.inventory[0],
        upgrades=("up_firsta_ak74", "up_second_ak74"),
        upgrades_editable=True,
    )
    view = ItemDetailView()
    qtbot.addWidget(view)

    view.set_item(item, FormatCapabilities(read_inventory=True))

    labels = [view.upgrade_list.item(row).text() for row in range(view.upgrade_list.count())]
    assert labels == ["Улучшение 1", "Улучшение 2"]
    assert all("up_" not in label for label in labels)
    assert view.upgrade_list.item(0).toolTip() == (
        "Технические детали:\nИдентификатор модификации: up_firsta_ak74"
    )
    assert view.upgrade_list.item(0).sizeHint().height() == 26
    assert view.upgrade_list.maximumHeight() >= 110
    assert view.module_status.text() == "Модули и улучшения доступны только для просмотра."
