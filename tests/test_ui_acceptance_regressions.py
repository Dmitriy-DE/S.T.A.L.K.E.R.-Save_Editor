from __future__ import annotations

import hashlib
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QApplication, QCheckBox, QDialog, QLabel, QWidget

from editor.models import CloudReceipt, EditPlan, PreparedEdit, SourceRef
from editor.releases import is_xray_original_release, release_by_id
from editor.service import EditorService
from editor.storage import BackupRecord, ExportReceipt
from editor.xray_save import COP_FORMAT, inspect_xray
from save_format import inspect_save
from steam_cloud import CloudFile
from ui.cloud_controller import CloudController, CloudSnapshot
from ui.library_view import LibraryView
from ui.main_window import LocalSnapshot, MainWindow
from ui.save_discovery import SaveDiscovery, SaveSlot, UnsupportedSaveReason
from ui.save_result_view import SaveResultView


def test_library_constructs_with_no_discovered_saves(qtbot) -> None:
    view = LibraryView()
    qtbot.addWidget(view)

    assert view.save_table.rowCount() == 0


def test_enhanced_edition_library_candidate_is_read_only(qtbot, tmp_path: Path) -> None:
    descriptor = release_by_id("stalker-soc-ee")
    slot = SaveSlot(
        path=tmp_path / "enhanced.sav",
        candidate_game_id=descriptor.family,
        candidate_game_title=descriptor.title,
        size=1024,
        modified_ns=1,
        candidate_release_id=descriptor.id,
        unsupported_reason=UnsupportedSaveReason(
            "unsupported_release", "Кандидат Enhanced Edition не поддерживается"
        ),
    )
    view = LibraryView()
    qtbot.addWidget(view)
    view.set_discovery(SaveDiscovery((slot,), (tmp_path,)))

    assert view.save_table.item(0, 1).text() == "Shadow of Chornobyl\nEnhanced Edition"
    status_cell = view.save_table.cellWidget(0, 4)
    assert status_cell is not None
    labels = [label.text() for label in status_cell.findChildren(QLabel)]
    assert "Только просмотр" in labels
    assert "Экспериментальный" in labels
    assert "Редактируемый" not in labels


@pytest.mark.parametrize("release_id", ("stalker-soc", "stalker-cs", "stalker-cop"))
def test_official_xray_release_ids_expose_character_route(
    qtbot, synthetic_save: bytes, tmp_path: Path, release_id: str
) -> None:
    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)
    snapshot = LocalSnapshot(
        path=tmp_path / f"{release_id}.sav",
        data=synthetic_save,
        info=inspect_save(synthetic_save, with_inventory=True),
        release_id=release_id,
        format_id=release_id,
        format_title=release_id,
    )
    window._render_snapshot(snapshot)

    assert is_xray_original_release(release_id)
    assert not window.editor_view.character_button.isHidden()
    window._show_character_state()
    assert window.reference_stack.currentWidget() is window.character_view


def test_s2_release_does_not_expose_character_route(
    qtbot, synthetic_save: bytes, tmp_path: Path
) -> None:
    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)
    window._render_snapshot(
        LocalSnapshot(
            path=tmp_path / "stalker2.sav",
            data=synthetic_save,
            info=inspect_save(synthetic_save, with_inventory=True),
            release_id="stalker2",
            format_id="stalker2",
        )
    )

    assert not is_xray_original_release("stalker2")
    assert window.editor_view.character_button.isHidden()


def test_entering_editor_focuses_the_inventory_selection(
    qtbot, synthetic_save: bytes, tmp_path: Path
) -> None:
    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)
    window.show()
    window._render_snapshot(
        LocalSnapshot(
            path=tmp_path / "selected.sav",
            data=synthetic_save,
            info=inspect_save(synthetic_save, with_inventory=True),
            release_id="stalker2",
            format_id="stalker2",
        )
    )
    window._show_reference_editor()

    qtbot.waitUntil(lambda: window.editor_view.table.hasFocus())
    assert window.editor_view.table.selectionModel().selectedRows()


@pytest.mark.parametrize("index", range(7))
def test_settings_category_indices_use_one_canonical_order(qtbot, index: int) -> None:
    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)
    view = window.settings_reference_view

    assert tuple(view.settings_stack._pages) == tuple(view._settings_pages)
    view.category_buttons[index].click()
    assert view.settings_stack.currentWidget() is view._settings_pages[index]


def test_settings_safety_policies_are_stated_not_drawn_as_dead_switches(qtbot) -> None:
    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)
    view = window.settings_reference_view

    assert view.findChildren(QCheckBox, "settingsToggle") == []
    labels = [label.text() for label in view.safety_labels]
    assert labels == [
        "Проверка обновлений при запуске",
        "Подтверждение перед записью сохранения",
        "Проверенная резервная копия перед записью",
    ]
    assert not any("последний источник" in label for label in labels)


def test_settings_category_rail_has_the_canonical_zone_illustration(qtbot) -> None:
    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)
    rail = window.settings_reference_view.findChild(QWidget, "settingsCategoryRail")

    assert rail is not None
    zone = rail.findChild(QWidget, "settingsZoneDecoration")
    assert zone is not None
    assert zone.minimumHeight() == 70
    assert zone.maximumHeight() == 286
    assert not zone._texture.isNull()
    note = zone.findChild(QLabel, "settingsZoneDecorationText")
    assert note is not None
    assert note.text() == "ОДНИ СОХРАНЯЮТ\nИГРЫ.\nМЫ СОХРАНЯЕМ\nИСТОРИИ."


def test_settings_shortcuts_open_backup_log_copy_and_preserve_update_action(
    qtbot, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr("ui.settings_view.backup_dirs", lambda: (tmp_path,))
    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)
    window.show()
    view = window.settings_reference_view
    actions: list[str] = []
    view.backup_folder_requested.connect(lambda: actions.append("backup"))
    view.journal_requested.connect(lambda: actions.append("journal"))
    view.copy_diagnostics_requested.connect(lambda: actions.append("copy"))
    view.update_requested.connect(lambda: actions.append("update"))

    assert view.backup_folder_button.isEnabled()
    view.backup_folder_button.click()
    view.diagnostics_action_button.click()
    view.copy_diagnostics_button.click()
    view.backup_folder_button.menu().actions()[0].trigger()

    assert actions == ["backup", "journal", "copy", "update"]


def test_settings_advanced_paths_action_opens_truthful_read_only_details(
    qtbot, tmp_path: Path
) -> None:
    window = MainWindow(EditorService(), settings_path=tmp_path / "settings.json", auto_update_check=False)
    qtbot.addWidget(window)
    window.show()
    view = window.settings_reference_view

    view.advanced_paths_button.click()
    dialog = view.findChild(QDialog, "advancedPathsDialog")

    assert dialog is not None and dialog.isVisible()
    assert "Расширенные пути" in dialog.windowTitle()
    dialog.close()


def test_settings_copy_diagnostics_puts_only_redacted_log_text_on_clipboard(
    qtbot, tmp_path: Path, monkeypatch
) -> None:
    import editor.diagnostics as diagnostics

    (tmp_path / diagnostics.LOG_FILENAME).write_text(
        "INFO token=do-not-copy-this\n", encoding="utf-8"
    )
    monkeypatch.setattr(diagnostics, "log_directory", lambda: tmp_path)
    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)

    window._copy_diagnostics_to_clipboard()
    copied = QApplication.clipboard().text()

    assert "token=<redacted>" in copied
    assert "do-not-copy-this" not in copied


def test_settings_log_action_opens_the_real_local_journal(
    qtbot, tmp_path: Path, monkeypatch
) -> None:
    import ui.main_window as main_window_module

    journal = tmp_path / "save-editor.log"
    journal.write_text("INFO: local journal\n", encoding="utf-8")
    opened: list[QUrl] = []
    monkeypatch.setattr(main_window_module, "log_directory", lambda: tmp_path)
    monkeypatch.setattr(
        main_window_module.QDesktopServices,
        "openUrl",
        lambda url: opened.append(url) or True,
    )
    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)

    window._open_diagnostics_log()

    assert len(opened) == 1
    # QUrl reports "C:/..." on Windows; compare paths, not separators.
    assert Path(opened[0].toLocalFile()) == journal


def test_settings_backup_action_opens_an_existing_backup_directory(
    qtbot, tmp_path: Path, monkeypatch
) -> None:
    import ui.main_window as main_window_module

    opened: list[Path] = []
    monkeypatch.setattr(main_window_module, "backup_dirs", lambda: (tmp_path,))
    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)
    window._open_backup_folder = lambda path: opened.append(path)

    window._open_settings_backup_folder()

    assert opened == [tmp_path]


def test_cloud_review_rows_show_names_and_formatted_times_without_writing(qtbot) -> None:
    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)
    file = CloudFile(
        name="Stalker2/Saved/Steam/auto_save_12.sav",
        size=512,
        timestamp=1_758_600_000,
        is_persisted=True,
        exists=True,
        source="native_remote_storage",
    )

    window.cloud_controller.set_review_files((file,))

    view = window.cloud_reference_view
    view.save_table.selectRow(0)
    assert view.save_table.item(0, 0).text() == "auto_save_12.sav"
    assert view.save_table.item(0, 0).toolTip() == ""
    assert view.save_table.item(0, 2).text() != str(file.timestamp)
    assert view.detail_name.text() == "auto_save_12.sav"
    assert view.details_button.isEnabled()
    view.details_button.click()
    assert view._details_dialog is not None
    assert f"Путь в Steam Cloud: {file.name}" in view._details_dialog.text.toPlainText()
    assert not view.upload_button.isEnabled()


def _visible_text(window: MainWindow) -> str:
    values: list[str] = []
    for widget in window.findChildren(QWidget):
        if not widget.isVisible():
            continue
        text = getattr(widget, "text", None)
        if callable(text):
            value = text()
            if value:
                values.append(str(value))
    return "\n".join(values)


def test_visible_normal_workflow_has_no_internal_stage_or_preview_terms(
    qtbot, synthetic_save: bytes, tmp_path: Path
) -> None:
    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)
    window._render_snapshot(
        LocalSnapshot(
            path=tmp_path / "stalker-soc.sav",
            data=synthetic_save,
            info=inspect_save(synthetic_save, with_inventory=True),
            release_id="stalker-soc",
            format_id="stalker-soc",
        )
    )
    forbidden = re.compile(r"staged|stage|застейджить|preview", re.IGNORECASE)
    for show_screen in (
        window._show_reference_library,
        window._show_reference_editor,
        window._show_cloud,
        window._show_history,
        window._show_settings,
        window._show_character_state,
    ):
        show_screen()
        qtbot.wait(5)
        assert not forbidden.search(_visible_text(window)), show_screen.__name__


def test_money_edit_updates_shared_draft_without_field_apply_button(
    qtbot, synthetic_save: bytes, tmp_path: Path
) -> None:
    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)
    window._render_snapshot(
        LocalSnapshot(
            path=tmp_path / "fixture.sav",
            data=synthetic_save,
            info=inspect_save(synthetic_save, with_inventory=True),
        )
    )

    assert not hasattr(window.editor_view, "money_stage_button")
    window.editor_view.money_spin.setValue(900)
    assert window.staged_money == 900
    assert window.editor_view.save_button.text() == "СОХРАНИТЬ 1 ИЗМЕНЕНИЕ"


def test_library_inspector_never_reuses_a_different_snapshot(qtbot, tmp_path: Path) -> None:
    view = LibraryView()
    qtbot.addWidget(view)
    selected = tmp_path / "selected.sav"
    view.set_discovery(
        SaveDiscovery(
            slots=(
                SaveSlot(
                    path=selected,
                    candidate_game_id="stalker2",
                    candidate_game_title="S.T.A.L.K.E.R. 2",
                    size=128,
                    modified_ns=1_758_600_000_000_000_000,
                    format_id="stalker2",
                    format_title="S.T.A.L.K.E.R. 2: Heart of Chornobyl",
                ),
            ),
            searched_paths=(),
        )
    )
    view.set_snapshot(
        SimpleNamespace(
            path=tmp_path / "previous.sav",
            info=SimpleNamespace(money=999, inventory=(), crc_ok=True),
            capabilities=None,
        )
    )

    assert view.preview_game_value.text() == "S.T.A.L.K.E.R. 2: Heart of Chornobyl"
    assert view.preview_source_value.text() == "Локальное сохранение"
    assert view.preview_integrity_value.text() == "Не проверено"
    assert view.money_summary.text() == "—"


def test_library_refreshes_snapshot_summary_when_discovery_arrives_later(
    qtbot, tmp_path: Path
) -> None:
    view = LibraryView()
    qtbot.addWidget(view)
    selected = tmp_path / "selected.sav"
    view.set_snapshot(
        SimpleNamespace(
            path=selected,
            info=SimpleNamespace(money=321, inventory=(), crc_ok=True),
            capabilities=None,
        )
    )
    assert view.money_summary.text() == "—"

    view.set_discovery(
        SaveDiscovery(
            slots=(
                SaveSlot(
                    path=selected,
                    candidate_game_id="stalker2",
                    candidate_game_title="S.T.A.L.K.E.R. 2",
                    size=128,
                    modified_ns=1_758_600_000_000_000_000,
                    format_id="stalker2",
                    format_title="S.T.A.L.K.E.R. 2: Heart of Chornobyl",
                ),
            ),
            searched_paths=(),
        )
    )

    assert view.money_summary.text() == "321 ₽"
    assert view.preview_integrity_value.text() == "Сохранение проверено"


def test_analysis_failure_is_attached_and_does_not_route_to_editor(
    qtbot, tmp_path: Path
) -> None:
    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)
    window.show()
    window._start_inspect(tmp_path / "missing.sav")
    qtbot.waitUntil(lambda: window.error_label.isVisible(), timeout=3000)

    assert window.reference_stack.currentWidget() is window.library_view
    assert window.error_label.parent() is window.library_view
    assert window.error_label.text() == (
        "Файл повреждён, не поддерживается или изменён другой программой."
    )
    assert window.error_label.toolTip() == ""
    details_button = next(
        button for button in window._error_dialog.buttons() if button.text() == "Подробнее"
    )
    details_button.click()
    assert window._details_dialog is not None
    assert "missing.sav" in window._details_dialog.text.toPlainText()


def test_completed_analysis_leaves_a_friendly_ready_status(
    qtbot, synthetic_save: bytes, tmp_path: Path
) -> None:
    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)
    window._render_snapshot(
        LocalSnapshot(
            path=tmp_path / "slot.sav",
            data=synthetic_save,
            info=inspect_save(synthetic_save, with_inventory=True),
        )
    )

    assert window.status_label.text() == "Редактор готов"


def test_verified_local_save_reinspects_written_slot_and_clears_draft(
    qtbot, tmp_path: Path
) -> None:
    from test_xray_save import _fixture

    data = _fixture()
    output = tmp_path / "written.scop"
    output.write_bytes(data)
    info = inspect_xray(data, COP_FORMAT)
    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)
    window._render_snapshot(
        LocalSnapshot(
            path=tmp_path / "source.scop",
            data=data,
            info=info,
            format_id=COP_FORMAT.id,
            format_title=COP_FORMAT.title,
            release_id=COP_FORMAT.id,
            edition="original",
        )
    )
    window.staged_counts[info.inventory[0].handle] = 3
    window._render_changes()
    receipt = ExportReceipt(
        output_path=output,
        backup_path=tmp_path / "backup.sav",
        output_sha256=hashlib.sha256(data).hexdigest(),
    )

    window._operation_kind = "replace"
    window._on_apply_ready(receipt)
    qtbot.waitUntil(lambda: window._post_save_reinspect_thread is None, timeout=5000)

    assert window.snapshot is not None
    assert window.snapshot.path == output
    assert window.snapshot.info.sha256 == hashlib.sha256(data).hexdigest()
    assert window.staged_counts == {}
    assert window.staged_money is None
    assert window.editor_view.save_button.text() == "СОХРАНИТЬ 0 ИЗМЕНЕНИЙ"
    assert not window.editor_view.save_button.isEnabled()
    assert tuple(window.editor_view.model.source_items) == tuple(window.snapshot.info.inventory)
    assert window.library_view._snapshot is window.snapshot
    window.save_result_view.editor_button.click()
    assert window.reference_stack.currentWidget() is window.editor_view
    assert not window.editor_view.save_button.isEnabled()


def test_footer_actions_are_real_shortcuts(qtbot) -> None:
    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)
    window.show()
    qtbot.wait(20)

    window._show_reference_library()
    assert {action.key for action in window.app_shell.footer_actions} >= {"Enter", "I", "R", "F"}
    assert all(action.shortcut is not None for action in window.app_shell.footer_actions)
    filter_action = next(action for action in window.app_shell.footer_actions if action.key == "F")
    filter_action.shortcut.activated.emit()
    assert filter_action.shortcut.key().toString() == "F"
    assert filter_action.callback.__self__ is window.library_view.search_edit
    assert filter_action.callback.__name__ == "setFocus"

    window._show_settings()
    next(action for action in window.app_shell.footer_actions if action.key == "D").shortcut.activated.emit()
    assert window.settings_reference_view.category_buttons[0].isChecked()


def _cloud_receipt(tmp_path: Path, *, status: str, sha: str, reason: str | None = None) -> CloudReceipt:
    return CloudReceipt(
        status=status,  # type: ignore[arg-type]
        remote_path="slot.sav",
        backup_path=tmp_path / "cloud-original.sav",
        recovery_path=tmp_path / "cloud-edited.sav",
        output_sha256=sha,
        reason=reason,
    )


def test_verified_cloud_result_requires_remote_reconciliation(qtbot, tmp_path: Path, synthetic_save: bytes) -> None:
    info = inspect_save(synthetic_save, with_inventory=True)
    controller = CloudController(EditorService(), helper_finder=lambda: None)
    prepared = PreparedEdit(
        plan=EditPlan(source=SourceRef("cloud", "slot.sav", info.sha256)),
        data=synthetic_save,
        output_sha256=info.sha256,
    )
    controller._prepared = prepared
    receipt = _cloud_receipt(tmp_path, status="verified", sha=info.sha256)
    controller._on_upload_ready(receipt)

    assert controller.reconciliation_pending
    assert controller.reconciliation_status == "pending"
    assert controller._prepared is prepared

    file = CloudFile("slot.sav", len(synthetic_save), 1, True, True)
    controller._on_snapshot_ready(
        CloudSnapshot(
            name="slot.sav",
            data=synthetic_save,
            info=info,
            file=file,
        )
    )
    assert controller.reconciliation_status == "verified"
    assert not controller.reconciliation_pending
    assert controller._prepared is None


def test_uncertain_cloud_result_exposes_reconcile_without_retry(qtbot, tmp_path: Path) -> None:
    view = SaveResultView()
    qtbot.addWidget(view)
    view.show()
    receipt = _cloud_receipt(tmp_path, status="uncertain", sha="a" * 64, reason="timeout")
    view.set_receipt(receipt)

    assert view.reconcile_button.isVisible()
    assert not view.editor_button.isEnabled()
    assert view.reconcile_button.text() == "Проверить Steam Cloud"
    assert view.subtitle.text() == (
        "Steam не подтвердил запись. Сначала проверь состояние облачного сохранения."
    )


def test_recent_activity_is_updated_from_session_operation(qtbot) -> None:
    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)
    window._record_recent_activity("Локальное сохранение", "/tmp/slot.sav", "SHA abc…")

    assert window.library_view.activity_table.columnCount() == 4
    assert "Локальное сохранение" in window.library_view.activity_table.item(0, 0).text()
    assert window.library_view.activity_table.item(0, 1).text() == "slot.sav"
    assert window.library_view.activity_table.item(0, 2).text().startswith("Сегодня,")
    assert window.library_view.activity_table.item(0, 3).text() == "SHA abc…"


def test_library_restore_routes_to_matching_history_record(qtbot, tmp_path: Path) -> None:
    source = tmp_path / "autosave.sav"
    backup = tmp_path / "autosave.ORIGINAL.sav"
    journal = tmp_path / "autosave.json"
    record = BackupRecord(
        journal_path=journal,
        backup_path=backup,
        created_at="2026-09-23 01:00:00",
        source_path=str(source),
        source_sha256="a" * 64,
        output_path=str(source),
        output_sha256="b" * 64,
        operation={"mode": "replace"},
        status="verified",
        actual_sha256="a" * 64,
    )
    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)
    window.backup_controller.set_review_records((record,))
    window.library_view.set_discovery(
        SaveDiscovery(
            slots=(SaveSlot(source, "stalker2", "S.T.A.L.K.E.R. 2", 10, 1),),
            searched_paths=(tmp_path,),
        )
    )
    window.library_view.restore_button.click()

    assert window.reference_stack.currentWidget() is window.history_reference_view
    assert window.history_reference_view.source_filter_edit.text() == source.name
    assert window.history_reference_view.table.currentRow() == 0


def test_history_rows_are_dense_and_verified_state_is_a_chip(qtbot, tmp_path: Path) -> None:
    source = tmp_path / "autosave.sav"
    record = BackupRecord(
        journal_path=tmp_path / "autosave.json",
        backup_path=tmp_path / "autosave.ORIGINAL.sav",
        created_at="2026-09-23 01:00:00",
        source_path=str(source),
        source_sha256="a" * 64,
        output_path=str(source),
        output_sha256="b" * 64,
        operation={"mode": "replace"},
        status="verified",
        actual_sha256="a" * 64,
    )
    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)
    window.backup_controller.set_review_records((record,))

    table = window.history_reference_view.table
    chip = table.cellWidget(0, 4)
    assert table.rowHeight(0) == 58
    assert chip is not None
    assert chip.text() == "Готово к восстановлению"
    assert chip.property("tone") == "success"


def test_frameless_chrome_exposes_working_window_controls(qtbot) -> None:
    from PySide6.QtCore import Qt

    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)
    assert window.windowFlags() & Qt.WindowType.FramelessWindowHint
    window.app_shell.minimize_button.click()
    window.showNormal()
    window.app_shell.maximize_button.click()
    assert window.isMaximized()
    window.app_shell.maximize_button.click()
    assert not window.isMaximized()
