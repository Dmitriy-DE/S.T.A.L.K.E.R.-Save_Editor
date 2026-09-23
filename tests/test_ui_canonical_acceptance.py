from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QWidget

from editor.capabilities import FormatCapabilities
from editor.service import EditorService
from editor.storage import ExportReceipt
from save_format import inspect_save
from ui.editor_view import EditorView
from ui.fonts import REFERENCE_FONT_FILES, load_reference_fonts
from ui.item_detail_view import ItemDetailView
from ui.main_window import MainWindow
from ui.save_result_view import SaveResultView


def test_main_window_does_not_construct_legacy_frontend(qtbot) -> None:
    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)

    forbidden_classes = {
        "LauncherView",
        "InventoryView",
        "EquipmentView",
        "ChangesView",
        "BackupView",
        "SaveSlotsView",
        "FactionView",
    }
    assert not forbidden_classes.intersection(
        child.__class__.__name__ for child in window.findChildren(QWidget)
    )
    for forbidden_attribute in ("mode_stack", "workbench", "tabs"):
        assert not hasattr(window, forbidden_attribute)
    assert isinstance(window.editor_view, EditorView)


def test_reference_fonts_are_packaged_and_loaded() -> None:
    assert REFERENCE_FONT_FILES
    assert all(path.is_file() for path in REFERENCE_FONT_FILES)
    family = load_reference_fonts()
    assert family
    assert "Liberation Sans Narrow" in family


def test_save_result_does_not_invent_verified_or_crc_for_local_receipt(qtbot, tmp_path) -> None:
    view = SaveResultView()
    qtbot.addWidget(view)
    receipt = ExportReceipt(
        output_path=tmp_path / "edited.sav",
        backup_path=tmp_path / "original.sav",
        output_sha256="a" * 64,
    )

    view.set_receipt(receipt)

    assert view.status_chip.text() != "VERIFIED"
    labels = [
        view.receipt_table.item(row, 0).text()
        for row in range(view.receipt_table.rowCount())
    ]
    assert "CRC" not in " ".join(labels).upper()
    assert "SHA" in " ".join(labels).upper()


def test_s2_item_detail_hides_unsupported_remove_control(
    qtbot, synthetic_save: bytes, tmp_path
) -> None:
    info = inspect_save(synthetic_save, with_inventory=True)
    view = ItemDetailView()
    qtbot.addWidget(view)
    view.set_item(
        info.inventory[0],
        FormatCapabilities(read_inventory=True),
    )

    assert not view.remove_button.isVisible()
    assert not view.count_spin.isEnabled()
