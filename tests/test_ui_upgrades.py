from __future__ import annotations

from dataclasses import replace

import pytest

pytest.importorskip("PySide6")

from editor.capabilities import FormatCapabilities
from editor.service import EditorService
from save_format import SaveError, inspect_save
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
    assert editor.detail_view.upgrade_status.text() == "Данные о модификациях недоступны."


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
    assert view.upgrade_list.item(0).toolTip() == ""
    view.details_button.click()
    assert view._details_dialog is not None
    assert "up_firsta_ak74" in view._details_dialog.text.toPlainText()
    assert view.upgrade_list.item(0).sizeHint().height() == 26
    assert view.upgrade_list.maximumHeight() >= 110
    assert view.upgrade_status.text() == "Модули и улучшения доступны только для просмотра."


def test_duplicate_upgrade_keys_are_collapsed_before_the_edit_plan(
    qtbot, synthetic_save: bytes, tmp_path
) -> None:
    from editor.capability_types import CapabilitySupport

    info = inspect_save(synthetic_save, with_inventory=True)
    item = replace(info.inventory[0], upgrades=("up_a",), upgrades_editable=True)
    info = replace(info, inventory=(item, *info.inventory[1:]))
    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)
    window._render_snapshot(LocalSnapshot(
        path=tmp_path / "slot.sav",
        data=synthetic_save,
        info=info,
        capabilities=FormatCapabilities(
            read_inventory=True,
            mutation_support={"edit_upgrades": CapabilitySupport("experimental")},
        ),
    ))

    window._stage_item_upgrades(item.handle, ("up_a", "up_b", "up_b"))

    # A repeated key used to escape as ValueError from EditPlan inside a slot.
    assert window.staged_upgrades == {item.handle: ("up_a", "up_b")}
    # Any other plan validation failure is reported as a refused save, which
    # the preview path handles, never as a bare ValueError.  (The synthetic
    # S2 handle is outside the X-Ray upgrade handle range.)
    with pytest.raises(SaveError, match="Upgrade handle"):
        window._build_edit_plan()
