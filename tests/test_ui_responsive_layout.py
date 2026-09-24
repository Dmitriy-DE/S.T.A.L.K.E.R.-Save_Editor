from __future__ import annotations

from itertools import pairwise
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, QRect, QSize
from PySide6.QtWidgets import QApplication, QWidget

from tools.render_ui_review import _fixture_bytes, _prepare_window


@pytest.fixture
def compact_review_window(qtbot, tmp_path: Path, monkeypatch):
    # Keep both discovery and backup-journal reads inside this test's sandbox.
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg-data"))
    app = QApplication.instance()
    assert app is not None
    window, _local, xray = _prepare_window(
        app, _fixture_bytes(), tmp_path, show_window=False
    )
    qtbot.addWidget(window)
    window.resize(1366, 768)
    window.show()
    qtbot.wait(40)
    assert window.size() == QSize(1366, 768)
    yield window, xray
    window.discovery_controller.wait_for_worker()
    window.close()


def _rect_in(widget: QWidget, ancestor: QWidget) -> QRect:
    return QRect(widget.mapTo(ancestor, QPoint(0, 0)), widget.size())


def test_compact_header_navigation_buttons_do_not_overlap(compact_review_window) -> None:
    window, _xray = compact_review_window
    assert window.discovery_controller.discovery_fn is window.slot_discovery
    assert len(window.library_view._slots) == 7
    shell = window.app_shell
    header = shell.header
    controls = [
        _rect_in(button, header)
        for button in shell.navigation_buttons
    ]
    support_host = shell.support_button.parentWidget()
    controls.append(_rect_in(support_host, header))

    assert all(
        left.right() < right.left()
        for left, right in pairwise(controls)
    ), controls


def test_compact_library_preview_scrolls_without_covering_title_or_actions(
    compact_review_window,
) -> None:
    window, _xray = compact_review_window
    view = window.library_view
    window._show_reference_library()
    QApplication.processEvents()

    assert view.preview_scroll.verticalScrollBar().maximum() > 0
    image_rect = _rect_in(view.preview_image, view.preview_body)
    name_rect = _rect_in(view.preview_name, view.preview_body)
    metadata_rect = _rect_in(view.preview_metadata, view.preview_body)
    assert name_rect.top() >= image_rect.bottom()
    assert metadata_rect.top() >= name_rect.bottom()
    preview_rect = view.preview_panel.rect()
    for button in (view.open_button, view.import_button, view.refresh_button, view.restore_button):
        assert preview_rect.contains(_rect_in(button, view.preview_panel))


def test_long_library_release_title_wraps_and_keeps_full_tooltip(
    compact_review_window,
) -> None:
    window, _xray = compact_review_window
    window._show_reference_library()
    QApplication.processEvents()
    value = window.library_view.preview_game_value

    assert value.wordWrap()
    assert value.toolTip() == value.text()
    assert value.height() >= value.minimumSizeHint().height()


def test_compact_editor_scrolls_equipment_and_detail_while_pinning_save(
    compact_review_window,
) -> None:
    window, xray = compact_review_window
    window._render_snapshot(xray, show_editor=False)
    window._show_reference_editor()
    QApplication.processEvents()
    view = window.editor_view

    assert view.equipment_scroll.verticalScrollBar().maximum() > 0
    equipment_rows = [
        view.equipment_list.itemAt(index).widget()
        for index in range(view.equipment_list.count())
    ]
    assert len(equipment_rows) >= 3
    ordered_rows = sorted(equipment_rows, key=lambda row: row.y())
    assert all(
        upper.geometry().bottom() < lower.geometry().top()
        for upper, lower in pairwise(ordered_rows)
    )

    detail = view.detail_view
    assert detail.detail_scroll.verticalScrollBar().maximum() > 0
    detail_rect = detail.rect()
    for button in (detail.save_button, detail.reset_button):
        assert detail_rect.contains(button.geometry())


def test_compact_settings_actions_fit_and_content_has_visible_scroll(
    compact_review_window,
) -> None:
    window, _xray = compact_review_window
    window._show_settings()
    QApplication.processEvents()
    view = window.settings_reference_view
    actions = (view.save_button, view.reset_button, view.defaults_button, view.cancel_button)
    rectangles = [_rect_in(button, window) for button in actions]

    assert all(window.rect().contains(rectangle) for rectangle in rectangles)
    assert all(
        left.right() < right.left()
        for left, right in pairwise(rectangles)
    )
    assert view.settings_scroll.verticalScrollBar().maximum() > 0
    assert view.settings_scroll.verticalScrollBar().isVisible()
    if view.settings_content.width() > view.settings_scroll.viewport().width():
        horizontal = view.settings_scroll.horizontalScrollBar()
        assert horizontal.isVisible()
        assert horizontal.maximum() > 0
    zone_text = view.zone_decoration.findChild(QWidget, "settingsZoneDecorationText")
    assert zone_text is not None
    assert zone_text.height() >= zone_text.minimumSizeHint().height()


def test_compact_cloud_details_do_not_overlap_selected_filename(
    compact_review_window,
) -> None:
    window, _xray = compact_review_window
    window._show_cloud()
    QApplication.processEvents()
    view = window.cloud_reference_view

    image_rect = _rect_in(view.detail_image, view.detail_panel)
    name_rect = _rect_in(view.detail_name, view.detail_panel)
    metadata_rect = _rect_in(view.detail_meta, view.detail_panel)
    assert name_rect.top() >= image_rect.bottom()
    assert metadata_rect.top() >= name_rect.bottom()


def test_compact_history_detail_text_stays_below_thumbnail(
    compact_review_window,
) -> None:
    window, _xray = compact_review_window
    window._show_history()
    QApplication.processEvents()
    view = window.history_reference_view

    image_rect = _rect_in(view.detail_image, view.detail_panel)
    name_rect = _rect_in(view.detail_name, view.detail_panel)
    status_rect = _rect_in(view.detail_status, view.detail_panel)
    assert name_rect.top() >= image_rect.bottom()
    assert status_rect.top() >= name_rect.bottom()


def test_long_history_destination_keeps_full_tooltip(compact_review_window, tmp_path: Path) -> None:
    window, _xray = compact_review_window
    window._show_history()
    QApplication.processEvents()
    view = window.history_reference_view
    full_path = str(tmp_path / ("a-very-long-save-destination-name-" * 5 + "restored.sav"))
    view.destination_edit.setText(full_path)
    view._destination_changed()

    assert view.destination_edit.toolTip() == full_path


def test_compact_editor_does_not_show_a_partially_clipped_section_title(
    compact_review_window,
) -> None:
    window, xray = compact_review_window
    window._render_snapshot(xray, show_editor=False)
    window._show_reference_editor()
    QApplication.processEvents()
    detail = window.editor_view.detail_view
    heading = detail.detail_content.findChild(QWidget, "detailUpgradesHeading")
    assert heading is not None
    heading_rect = _rect_in(heading, detail.detail_scroll.viewport())
    visible_part = heading_rect.intersected(detail.detail_scroll.viewport().rect())
    assert visible_part.isNull() or visible_part.height() == heading_rect.height()
