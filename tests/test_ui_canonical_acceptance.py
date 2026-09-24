from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QFontDatabase, QIcon, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QListWidget, QWidget

from editor.capabilities import FormatCapabilities
from editor.service import EditorService
from editor.storage import ExportReceipt
from save_format import inspect_save
from ui.editor_view import EditorView
from ui.fonts import REFERENCE_FONT_FILES, load_reference_fonts
from ui.item_detail_view import ItemDetailView
from ui.main_window import MainWindow
from ui.save_result_view import SaveResultView
from ui.style_components import reference_game_rail
from ui.theme import TYPOGRAPHY, apply_theme


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


def test_editor_breadcrumb_has_the_canonical_back_divider_gap(qtbot) -> None:
    apply_theme(QApplication.instance())
    view = EditorView()
    qtbot.addWidget(view)
    view.resize(1530, 808)
    view.show()
    qtbot.wait(20)

    back_end = view.back_button.x() + view.back_button.width()
    assert view.breadcrumb_separator is not None
    assert view.breadcrumb_separator.x() >= back_end + 16
    assert view.breadcrumb.x() >= view.breadcrumb_separator.x() + 28
    assert view.status_column.x() == 0
    assert view.status_column.width() == 362
    assert view.inventory_column.x() == 362
    assert view.back_button.height() == 33
    assert view.breadcrumb.height() == 38
    assert view.status_column.y() == 51


def test_reference_fonts_are_packaged_and_loaded(qtbot) -> None:
    assert REFERENCE_FONT_FILES
    assert all(path.is_file() for path in REFERENCE_FONT_FILES)
    family = load_reference_fonts()
    assert family
    assert "Liberation Sans Narrow" in family
    display_font = Path(__file__).resolve().parents[1] / "assets" / "fonts" / "Oswald[wght].ttf"
    assert display_font.is_file()
    assert "Oswald" in QFontDatabase.families()
    assert TYPOGRAPHY["heading"] == '"Oswald"'


def test_selection_texture_uses_the_reference_parchment_tone() -> None:
    texture_path = Path(__file__).resolve().parents[1] / "assets" / "ui" / "s2_shell" / "selection_paper.png"
    texture = QImage(str(texture_path))
    assert not texture.isNull()

    channel_means = [
        sum(
            texture.pixelColor(x, y).getRgb()[channel]
            for y in range(texture.height())
            for x in range(texture.width())
        )
        / (texture.width() * texture.height())
        for channel in range(3)
    ]
    assert all(
        abs(actual - expected) <= 6
        for actual, expected in zip(channel_means, (201, 194, 178), strict=True)
    )


def test_secondary_game_rail_selection_uses_parchment_not_flat_amber(qtbot) -> None:
    app = QApplication.instance()
    apply_theme(app)
    rail = reference_game_rail(active_family="stalker2")
    rail.resize(246, 790)
    qtbot.addWidget(rail)
    rail.show()
    qtbot.wait(20)
    games = rail.findChild(QListWidget, "referenceSecondaryGameList")
    assert games is not None
    selected_rect = games.visualItemRect(games.currentItem())
    sample = games.grab().toImage().pixelColor(selected_rect.right() - 8, selected_rect.center().y())

    assert sample.red() > 180
    assert sample.green() > 160
    assert sample.blue() > 130


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
    assert "SHA" not in " ".join(labels).upper()
    assert "Технические детали:" in view.receipt_table.toolTip()
    assert receipt.output_sha256 in view.receipt_table.toolTip()


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


def test_item_detail_preview_fills_the_canonical_wide_art_slot(qtbot) -> None:
    from ui.item_detail_view import _wide_detail_pixmap

    source = QPixmap(80, 80)
    source.fill(Qt.GlobalColor.transparent)
    painter = QPainter(source)
    painter.fillRect(source.rect(), QColor(180, 180, 180, 32))
    painter.fillRect(10, 30, 60, 20, QColor("#eeeeee"))
    painter.end()

    result = _wide_detail_pixmap(QIcon(source))

    assert result.size() == QSize(355, 80)
    image = result.toImage()
    opaque = [
        (x, y)
        for y in range(image.height())
        for x in range(image.width())
        if image.pixelColor(x, y).alpha() > 200
    ]
    assert min(x for x, _y in opaque) <= 5
    assert max(x for x, _y in opaque) >= 349
    assert min(y for _x, y in opaque) <= 5
    assert max(y for _x, y in opaque) >= 74
