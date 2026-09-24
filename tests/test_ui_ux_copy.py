from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QAbstractButton,
    QComboBox,
    QLabel,
    QLineEdit,
    QTableView,
    QTableWidget,
    QWidget,
)

from editor.capability_types import CapabilitySupport
from editor.equipment import EquipmentItem
from editor.service import EditorService
from editor.storage import BackupRecord, ExportReceipt
from editor.update_manifest import ArtifactSpec
from editor.updater import InstallationInfo, UpdateCheckResult
from save_format import inspect_save
from ui.backup_controller import BackupController
from ui.character_view import CharacterView
from ui.cloud_controller import CloudController
from ui.cloud_library_view import CloudLibraryView
from ui.diagnostics_dialog import DiagnosticsDialog
from ui.editor_view import EditorView
from ui.history_view import HistoryView
from ui.main_window import LocalSnapshot, MainWindow
from ui.save_result_view import SaveResultView
from ui.support_dialog import SupportDialog
from ui.update_dialog import UpdateDialog
from ui.ux_copy import (
    ERROR_COPY,
    classify_analysis_error,
    classify_operation_error,
    format_error_details,
    present_error,
)


def _snapshot(synthetic_save: bytes, tmp_path: Path) -> LocalSnapshot:
    path = tmp_path / "save.sav"
    path.write_bytes(synthetic_save)
    return LocalSnapshot(
        path=path,
        data=synthetic_save,
        info=inspect_save(synthetic_save, with_inventory=True),
    )


def test_library_and_editor_use_plain_language_for_search_and_integrity(
    qtbot, synthetic_save: bytes, tmp_path: Path
) -> None:
    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)
    window._render_snapshot(_snapshot(synthetic_save, tmp_path), show_editor=False)

    assert window.library_view.search_edit.placeholderText() == "Поиск предметов…"
    assert window.editor_view.header_status.text() == "РЕДАКТИРУЕМЫЙ"
    assert window.editor_view.integrity_label.text() == "Файл проверен"


def test_open_failure_uses_short_copy_and_keeps_diagnostic_details(
    qtbot, synthetic_save: bytes, tmp_path: Path
) -> None:
    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)
    window._render_snapshot(_snapshot(synthetic_save, tmp_path), show_editor=False)
    details = "CRC mismatch while parsing save; SHA-256=deadbeef"

    window._on_analysis_failed(details)

    assert window.snapshot is not None
    assert window.library_view.preview_status.text() == "НЕ УДАЛОСЬ ОТКРЫТЬ"
    assert window.error_label.text() == (
        "Файл не прошёл проверку. Редактирование отключено, "
        "чтобы не повредить его ещё сильнее."
    )
    assert "Технические детали" in window.error_label.toolTip()
    assert details in window.error_label.toolTip()
    dialog = window.findChild(type(window._error_dialog), "uxErrorDialog")
    assert dialog is window._error_dialog
    assert dialog.text() == "Сохранение повреждено"
    assert {button.text() for button in dialog.buttons()} >= {
        "Выбрать другой файл",
        "Подробнее",
    }


def test_local_receipt_shows_user_result_and_keeps_hash_in_details(
    qtbot, tmp_path: Path
) -> None:
    view = SaveResultView()
    qtbot.addWidget(view)
    digest = "a" * 64
    view.set_receipt(
        ExportReceipt(
            output_path=tmp_path / "edited.sav",
            backup_path=tmp_path / "original.sav",
            output_sha256=digest,
        )
    )

    visible = " ".join(
        [view.heading_label.text(), view.subtitle.text(), view.status_chip.text()]
        + [
            view.receipt_table.item(row, column).text()
            for row in range(view.receipt_table.rowCount())
            for column in range(view.receipt_table.columnCount())
            if view.receipt_table.item(row, column) is not None
        ]
    )
    assert "Изменения сохранены" in visible
    assert "Сохранение записано и проверено." in visible
    assert "SHA" not in visible
    assert "Технические детали" in view.receipt_table.toolTip()
    assert digest in view.receipt_table.toolTip()


def test_success_receipt_says_what_changed_without_showing_internal_hashes(
    qtbot, tmp_path: Path
) -> None:
    view = SaveResultView()
    qtbot.addWidget(view)
    view.set_receipt(
        ExportReceipt(
            output_path=tmp_path / "edited.sav",
            backup_path=tmp_path / "original.sav",
            output_sha256="a" * 64,
        ),
        change_count=3,
    )

    rows = [
        (view.receipt_table.item(row, 0).text(), view.receipt_table.item(row, 1).text())
        for row in range(view.receipt_table.rowCount())
    ]
    assert view.heading_label.text() == "Изменения сохранены"
    assert view.subtitle.text() == "Сохранение записано и проверено. Резервная копия создана."
    assert rows == [
        ("Изменено", "3 параметра"),
        ("Резервная копия", "Создана"),
        ("Проверка", "Успешно"),
    ]
    visible = " ".join((view.heading_label.text(), view.subtitle.text(), *(cell for row in rows for cell in row)))
    assert "SHA" not in visible
    assert "Технические детали" in view.receipt_table.toolTip()


def test_analysis_crc_failure_uses_corrupt_save_copy_and_error_code(
    qtbot, synthetic_save: bytes, tmp_path: Path
) -> None:
    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)
    window._render_snapshot(_snapshot(synthetic_save, tmp_path), show_editor=False)

    window._on_analysis_failed("CRC mismatch: stored=1234 actual=5678")

    assert window._error_dialog.text() == "Сохранение повреждено"
    assert window._error_dialog.informativeText() == (
        "Файл не прошёл проверку. Редактирование отключено, чтобы не повредить его ещё сильнее."
    )
    assert {button.text() for button in window._error_dialog.buttons()} >= {
        "Выбрать другой файл",
        "Подробнее",
    }
    details_button = next(
        button for button in window._error_dialog.buttons() if button.text() == "Подробнее"
    )
    details_button.click()
    assert window._details_dialog.informativeText().startswith(
        "Технические детали:\nКод ошибки: SAVE_CORRUPT"
    )
    assert classify_analysis_error("CRC mismatch: stored=1234 actual=5678") == "corrupt"
    assert ERROR_COPY["corrupt"].error_code == "SAVE_CORRUPT"


def test_error_presentation_keeps_stable_code_severity_and_secondary_action() -> None:
    copy = ERROR_COPY["source_changed"]
    assert copy.error_code == "SOURCE_CHANGED"
    assert copy.severity == "error"
    assert copy.primary_action == "Открыть заново"
    assert copy.secondary_action == "Подробнее"
    assert copy.technical_details is None
    detailed = present_error("source_changed", "source SHA changed")
    assert format_error_details(detailed) == (
        "Технические детали:\nКод ошибки: SOURCE_CHANGED\nsource SHA changed"
    )


@pytest.mark.parametrize(
    ("kind", "error_code"),
    (
        ("open", "ANALYSIS_FAILED"),
        ("source_changed", "SOURCE_CHANGED"),
        ("backup", "BACKUP_FAILED"),
        ("verify", "VERIFY_FAILED"),
        ("unsupported", "FORMAT_UNSUPPORTED"),
        ("cloud_unavailable", "CLOUD_UNAVAILABLE"),
        ("cloud_uncertain", "CLOUD_WRITE_UNCERTAIN"),
        ("corrupt", "SAVE_CORRUPT"),
    ),
)
def test_central_error_codes_are_stable(kind: str, error_code: str) -> None:
    assert ERROR_COPY[kind].error_code == error_code


def test_settings_and_character_warnings_use_requested_plain_copy(qtbot) -> None:
    character = CharacterView()
    qtbot.addWidget(character)
    assert character.warning_label.text() == (
        "Изменение отношений — экспериментальная функция. "
        "Перед сохранением будет создана резервная копия."
    )

    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)
    cloud_copy = [
        label.text()
        for label in window.settings_reference_view.cloud_panel.findChildren(QLabel)
    ]
    assert "Если Steam не подтвердил запись," in cloud_copy
    assert "редактор сначала проверит состояние облака." in cloud_copy
    assert window.save_review_view.warning_label.text() == (
        "Если Steam не подтвердил запись, редактор сначала проверит состояние облака."
    )
    backup_copy = [
        label.text()
        for label in window.settings_reference_view.backups_panel.findChildren(QLabel)
    ]
    assert "Резервная копия создаётся автоматически перед каждым сохранением." in backup_copy
    cloud_surface_copy = [
        label.text() for label in window.cloud_reference_view.findChildren(QLabel)
    ]
    assert any(
        "Перед записью создаётся резервная копия. Если Steam не подтвердил запись, "
        "редактор сначала проверит состояние облака."
        in text
        for text in cloud_surface_copy
    )


def test_history_paths_are_only_exposed_as_labeled_technical_details(qtbot, tmp_path: Path) -> None:
    source_path = tmp_path / "saves" / "slot.sav"
    record = BackupRecord(
        journal_path=tmp_path / "backup.json",
        backup_path=tmp_path / "backup.sav",
        created_at="2026-09-24T10:00:00+00:00",
        source_path=str(source_path),
        source_sha256="a" * 64,
        output_path=None,
        output_sha256=None,
        operation={"mode": "export"},
        status="verified",
    )
    controller = BackupController()
    controller._records = (record,)
    view = HistoryView(controller)
    qtbot.addWidget(view)
    view._render()
    view.table.selectRow(0)

    assert view.detail_name.text() == "slot.sav"
    assert view.detail_name.toolTip().startswith("Технические детали:")
    assert str(source_path) in view.detail_name.toolTip()


def test_unknown_equipment_uses_a_friendly_name_not_its_internal_key(qtbot) -> None:
    view = EditorView()
    qtbot.addWidget(view)
    view.equipment_rows = (
        EquipmentItem(
            handle=7,
            name="",
            type_key="wpn_internal_variant_7",
            category="weapon",
            location="equipped",
            serializer_family=None,
            condition=None,
            condition_editable=False,
            durability=CapabilitySupport("unsupported"),
            upgrades=None,
            upgrades_editable=False,
        ),
    )

    view._render_equipment_summary()

    names = [
        label.text()
        for label in view.equipment_content.findChildren(QLabel)
        if label.objectName() == "equipmentSlotName"
    ]
    assert names == ["Неизвестный предмет"]


def test_cloud_result_copy_is_plain_and_preserves_diagnostics(qtbot) -> None:
    backend = CloudController(EditorService(), helper_finder=lambda: None)
    view = CloudLibraryView(backend)
    qtbot.addWidget(view)
    digest = "b" * 64
    snapshot = SimpleNamespace(
        name="cloud.sav",
        info=SimpleNamespace(crc_ok=True, sha256=digest),
    )

    view._on_snapshot_ready(snapshot)

    assert view.result_label.text() == "Файл проверен"
    assert "Технические детали" in view.result_label.toolTip()
    assert digest in view.result_label.toolTip()


def test_cloud_failure_keeps_raw_transport_error_out_of_visible_copy(qtbot) -> None:
    backend = CloudController(EditorService(), helper_finder=lambda: None)
    view = CloudLibraryView(backend)
    qtbot.addWidget(view)
    detail = "Steam Cloud transport unavailable: ECONNRESET"

    view._on_error(detail)

    assert view.status_chip.text() == "STEAM CLOUD НЕДОСТУПЕН"
    assert view.result_label.text() == (
        "Не удалось подключиться к Steam Cloud. "
        "Локальные сохранения по-прежнему доступны."
    )
    assert detail in view.result_label.toolTip()


def test_update_dialog_hides_technical_manifest_data_until_requested(qtbot, tmp_path: Path) -> None:
    dialog = UpdateDialog(
        UpdateCheckResult("available", artifact=_artifact()),
        installation=_installation(tmp_path),
        client=object(),
    )
    qtbot.addWidget(dialog)

    assert "SHA" not in dialog.status_label.text()
    assert dialog.details_label.isHidden()
    assert dialog.details_button.text() == "Технические детали"
    assert _artifact().sha256 in dialog.details_label.text()

    dialog.details_button.click()
    assert not dialog.details_label.isHidden()


def test_error_classifier_distinguishes_cloud_uncertainty_and_backup_verification() -> None:
    assert classify_operation_error("Source SHA changed after inspection") == "source_changed"
    assert classify_operation_error("Не удалось создать backup: permission denied") == "backup"
    assert classify_operation_error("Резервная копия не прошла проверку") == "verify"
    assert classify_operation_error("Cloud uncertain: WriteFile result not confirmed") == "cloud_uncertain"
    assert classify_operation_error("Cloud writer unavailable") == "cloud_write_unavailable"


def test_requested_error_copy_is_short_and_exact() -> None:
    assert (
        ERROR_COPY["open"].title,
        ERROR_COPY["open"].message,
        ERROR_COPY["open"].primary_action,
    ) == (
        "Не удалось открыть сохранение",
        "Файл повреждён, не поддерживается или изменён другой программой.",
        "Выбрать другой файл",
    )
    assert (ERROR_COPY["source_changed"].title, ERROR_COPY["source_changed"].message) == (
        "Не удалось сохранить изменения",
        "Файл изменился после открытия. Открой его заново и повтори изменения.",
    )
    assert ERROR_COPY["unsupported"].message == (
        "Сохранение распознано, но безопасное редактирование для этой версии ещё не готово."
    )
    assert ERROR_COPY["cloud_write_unavailable"].message == (
        "Запись в Steam Cloud сейчас недоступна."
    )


def test_diagnostics_errors_are_short_until_technical_details_are_opened(qtbot) -> None:
    dialog = DiagnosticsDialog()
    qtbot.addWidget(dialog)
    detail = "TimeoutError: diagnostics endpoint returned 503"

    dialog._on_failed(detail)

    assert dialog.status_label.text() == "Не удалось отправить журналы. Попробуй позже."
    assert dialog.details_label.isHidden()
    assert detail in dialog.details_label.text()
    dialog.details_button.click()
    assert not dialog.details_label.isHidden()
    assert dialog.details_label.text().startswith("Технические детали:")


def test_support_dialog_uses_the_app_language(qtbot) -> None:
    dialog = SupportDialog()
    qtbot.addWidget(dialog)

    text = [widget.text() for widget in dialog.findChildren(QAbstractButton)]
    text.extend(label.text() for label in dialog.findChildren(QLabel))
    assert dialog.windowTitle() == "Поддержать проект"
    assert "Если проект оказался полезен, поддержи его развитие." in text
    assert "Закрыть" in text
    assert "Копировать" in text


def test_normal_desktop_widget_copy_avoids_internal_terminology(
    qtbot, synthetic_save: bytes, tmp_path: Path
) -> None:
    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)
    window._render_snapshot(_snapshot(synthetic_save, tmp_path), show_editor=False)
    visible_copy: list[str] = []
    tooltips: list[str] = []
    visible_copy.extend(action.text() for action in window.findChildren(QAction))
    for widget in window.findChildren(QWidget):
        if isinstance(widget, (QAbstractButton, QLabel)):
            visible_copy.append(widget.text())
        elif isinstance(widget, QLineEdit):
            visible_copy.append(widget.placeholderText())
        elif isinstance(widget, QComboBox):
            visible_copy.extend(widget.itemText(index) for index in range(widget.count()))
        elif isinstance(widget, QTableWidget):
            visible_copy.extend(
                widget.horizontalHeaderItem(column).text()
                for column in range(widget.columnCount())
                if widget.horizontalHeaderItem(column) is not None
            )
            visible_copy.extend(
                widget.item(row, column).text()
                for row in range(widget.rowCount())
                for column in range(widget.columnCount())
                if widget.item(row, column) is not None
            )
            tooltips.extend(
                widget.item(row, column).toolTip()
                for row in range(widget.rowCount())
                for column in range(widget.columnCount())
                if widget.item(row, column) is not None and widget.item(row, column).toolTip()
            )
        elif isinstance(widget, QTableView):
            model = widget.model()
            if model is None:
                continue
            columns = [
                column
                for column in range(model.columnCount())
                if not widget.isColumnHidden(column)
            ]
            visible_copy.extend(
                str(model.headerData(column, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole))
                for column in columns
                if model.headerData(column, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole)
            )
            for row in range(model.rowCount()):
                for column in columns:
                    index = model.index(row, column)
                    value = index.data(Qt.ItemDataRole.DisplayRole)
                    if value is not None:
                        visible_copy.append(str(value))
                    tooltip = index.data(Qt.ItemDataRole.ToolTipRole)
                    if tooltip:
                        tooltips.append(str(tooltip))
    text = "\n".join(visible_copy).casefold()
    forbidden = re.compile(
        r"\bsha(?:-?256)?\b|\bcrc\b|read[- ]only|staged|\bstage\b|\bpreview\b|"
        r"\bhandle\b|type[- ]key|\banchor\b|persisted|reconciliation|"
        r"read[- ]back|\bwriter\b|\bparser\b|\btransport\b|\blocator\b|"
        r"\bpayload\b|serializer|immutable|\bbackend\b|\bbytes\b|"
        r"бэкап|байт|снимок|предпросмотр|застейдж|сейв\w*|thumbnail",
        re.IGNORECASE,
    )
    matches = forbidden.findall(text)
    offenders = [value for value in visible_copy if forbidden.search(value)]
    assert not matches, f"internal terms are visible in normal UI copy: {offenders}"
    tooltips.extend(
        widget.toolTip()
        for widget in window.findChildren(QWidget)
        if widget.toolTip()
    )
    unlabeled_tooltips = [
        tooltip
        for tooltip in tooltips
        if forbidden.search(tooltip) and "Технические детали:" not in tooltip
    ]
    assert not unlabeled_tooltips, f"technical tooltip lacks an explicit detail label: {unlabeled_tooltips}"


def _artifact():
    return ArtifactSpec(
        target="linux-x86_64",
        architecture="x86_64",
        kind="portable",
        file="SaveEditor-linux-x86_64.tar.gz",
        size=128,
        sha256="c" * 64,
        url="https://example.invalid/SaveEditor.tar.gz",
    )


def _installation(tmp_path: Path):
    root = tmp_path / "installed"
    root.mkdir()
    executable = root / "SaveEditor"
    executable.write_bytes(b"app")
    return InstallationInfo("linux", "x86_64", "portable", root, executable)
