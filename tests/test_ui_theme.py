from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from editor.service import EditorService
from save_format import inspect_save
from ui.main_window import LocalSnapshot, MainWindow


def test_stalker_shell_exposes_zone_navigation_and_empty_metadata(qtbot) -> None:
    window = MainWindow(EditorService())
    qtbot.addWidget(window)

    assert window.app_title.text() == "S.T.A.L.K.E.R. 2 Save Editor"
    assert window.version_badge.text().startswith("v")
    assert window.file_source_badge.text() == "ФАЙЛ НЕ ВЫБРАН"
    assert window.meta_filename.text() == "Сейв не выбран"
    assert window.integrity_badge.text() == "CRC-32: —"
    assert window.format_badge.text() == "UE5 GVAS: —"
    assert window.tabs.tabBar().isHidden()
    assert window.sidebar.objectName() == "sidebar"
    assert [button.text() for button in window.nav_buttons] == [
        "Обзор",
        "Инвентарь",
        "Изменения",
        "Резервные копии",
        "Steam Cloud",
        "Найденные сейвы",
    ]
    assert "#111516" in QApplication.instance().styleSheet()

    qtbot.mouseClick(window.nav_buttons[1], Qt.MouseButton.LeftButton)
    assert window.tabs.currentIndex() == 1
    assert window.nav_buttons[1].isChecked()


def test_stalker_shell_metadata_tracks_real_snapshot(
    qtbot, synthetic_save: bytes, tmp_path: Path
) -> None:
    source = tmp_path / "локальный.sav"
    info = inspect_save(synthetic_save, with_inventory=True)
    window = MainWindow(EditorService())
    qtbot.addWidget(window)

    window._render_snapshot(
        LocalSnapshot(path=source, data=synthetic_save, info=info)
    )

    assert window.file_source_badge.text() == "ЛОКАЛЬНЫЙ ФАЙЛ"
    assert window.meta_filename.text() == source.name
    assert f"SHA {info.sha256[:12]}" in window.meta_details.text()
    assert window.integrity_badge.text() == "CRC-32: PASS"
    assert window.format_badge.text() == "UE5 GVAS: НЕ ПОДТВЕРЖДЁН"
    assert window.money_card_value.text() == "100"
    assert window.inventory_card_value.text() == "2"
