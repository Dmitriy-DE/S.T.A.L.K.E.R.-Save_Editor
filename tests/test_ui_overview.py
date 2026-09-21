"""Overview tab: parser-backed metadata table, readable summary, nav counters.

The Zone reference shows a technical metadata table and a badge per section.
U07 brought the palette and the shell; the tab body below the metric cards was
still a QFormLayout that clipped its own wrapped text and left the rest of the
window empty.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from editor.service import EditorService
from save_format import inspect_save
from ui.main_window import LocalSnapshot, MainWindow


def _snapshot(synthetic_save: bytes, tmp_path: Path) -> LocalSnapshot:
    path = tmp_path / "slot.sav"
    path.write_bytes(synthetic_save)
    return LocalSnapshot(path=path, data=synthetic_save, info=inspect_save(synthetic_save))


def _rows(window: MainWindow) -> dict[str, tuple[str, str]]:
    table = window.metadata_table
    out: dict[str, tuple[str, str]] = {}
    for row in range(table.rowCount()):
        name = table.item(row, 0).text()
        out[name] = (table.item(row, 1).text(), table.item(row, 2).text())
    return out


def test_empty_state_table_claims_nothing(qtbot) -> None:
    window = MainWindow(EditorService())
    qtbot.addWidget(window)

    rows = _rows(window)
    assert rows["Файл"][0] == "—"
    assert rows["CRC-32"] == ("—", "не проверен")
    assert rows["SHA-256"][0] == "—"


def test_metadata_table_is_filled_from_the_snapshot(
    qtbot, synthetic_save: bytes, tmp_path: Path
) -> None:
    window = MainWindow(EditorService())
    qtbot.addWidget(window)
    snapshot = _snapshot(synthetic_save, tmp_path)

    window._render_snapshot(snapshot)
    rows = _rows(window)

    assert rows["SHA-256"][0] == snapshot.info.sha256
    assert rows["CRC-32"][1] == "PASS"
    assert rows["Баланс купонов"] == ("100", "редактируется")
    assert rows["Объекты инвентаря"][0] == str(len(snapshot.info.inventory))
    assert rows["Unresolved handles"][0] == str(len(snapshot.info.unresolved_handles))


def test_unproven_schema_is_reported_as_unproven(
    qtbot, synthetic_save: bytes, tmp_path: Path
) -> None:
    window = MainWindow(EditorService())
    qtbot.addWidget(window)

    window._render_snapshot(_snapshot(synthetic_save, tmp_path))
    value, status = _rows(window)["UE5 GVAS schema"]

    # The reference mock shows a confirmed GVAS version. The parser cannot
    # prove one, so the table must not imply it does.
    assert value == "не разобрана"
    assert "не подтверждена" in status
    assert window.format_badge.text() == "UE5 GVAS: НЕ ПОДТВЕРЖДЁН"


def test_navigation_counters_follow_inventory_and_staged_edits(
    qtbot, synthetic_save: bytes, tmp_path: Path
) -> None:
    window = MainWindow(EditorService())
    qtbot.addWidget(window)
    assert [button.text() for button in window.nav_buttons] == list(window.nav_labels)

    window._render_snapshot(_snapshot(synthetic_save, tmp_path))
    inventory_count = len(window.snapshot.info.inventory)
    assert window.nav_buttons[1].text().endswith(str(inventory_count))
    assert window.nav_buttons[2].text() == "Изменения"

    window.money_spin.setValue(900_000)
    window._stage_money()
    assert window.nav_buttons[2].text().endswith("1")


def test_summary_text_is_not_clipped(qtbot, synthetic_save: bytes, tmp_path: Path) -> None:
    window = MainWindow(EditorService())
    qtbot.addWidget(window)
    window._render_snapshot(_snapshot(synthetic_save, tmp_path))

    label = window.summary_label
    container = label.parentWidget()
    assert label.wordWrap()
    # A wrapped label inside a QFormLayout reports a one-line height hint and
    # renders over its neighbour; the container must reserve the wrapped height.
    assert container.sizeHint().height() >= label.heightForWidth(label.width())


def test_main_window_exposes_one_save_action_without_manual_preview_controls(qtbot) -> None:
    window = MainWindow(EditorService())
    qtbot.addWidget(window)

    assert window.preview_button.isHidden()
    assert window.changes_view.preview_button.isHidden()
    assert window.changes_view.apply_button.isHidden()
    assert window.changes_view.replace_button.isHidden()
    assert window.changes_view.destination_edit.isHidden()
    assert window.changes_view.choose_output_button.isHidden()
