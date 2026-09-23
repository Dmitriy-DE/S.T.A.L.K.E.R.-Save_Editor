"""Small responsive Qt shell for local save inspection.

The window deliberately owns no parser or writer rules.  It asks
``EditorService`` to inspect bytes in a worker thread and keeps the last valid
snapshot visible when a later file is malformed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from PySide6.QtCore import QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from editor.capabilities import FormatCapabilities
from editor.catalog import CatalogLookupError, GameCatalog, ItemCatalog
from editor.equipment import EquipmentItem
from editor.equipment_edits import RepairStageResult, stage_bulk_repair, stage_repair
from editor.formats import STALKER2_FORMAT, FormatDetectionError
from editor.models import EditPlan, PreparedEdit, SourceRef
from editor.platforms import backup_dirs, installed_releases
from editor.service import EditorService
from editor.settings import PathSettings, load_settings, search_paths_for_settings
from editor.updater import InstallationInfo, UpdateCheckResult, UpdateClient, detect_installation
from save_format import SaveError, SaveInfo

from .app_shell import AppShell
from .backup_controller import BackupController, RestoreWorker
from .character_view import CharacterView
from .cloud_controller import CloudController, CloudSnapshot
from .cloud_library_view import CloudLibraryView
from .diagnostics_dialog import DiagnosticsDialog
from .editor_view import EditorView
from .formatting import human_size
from .history_view import HistoryView
from .library_view import LibraryView
from .operation_worker import OperationWorker
from .save_discovery import (
    RELEASE_IDS,
    SlotDiscoveryController,
    SlotDiscoveryFn,
    discover_save_slots,
)
from .save_result_view import SaveResultView
from .save_review import SaveReviewView
from .settings_view import SettingsView
from .support_dialog import SupportDialog
from .theme import apply_theme
from .unsupported_view import UnsupportedView
from .update_dialog import UpdateCheckWorker, UpdateDialog


def _default_s2_capabilities() -> FormatCapabilities:
    return STALKER2_FORMAT.capabilities


def _version_text() -> str:
    """Read the repository version without introducing a packaging dependency."""

    version_path = Path(__file__).resolve().parents[1] / "VERSION"
    try:
        value = version_path.read_text(encoding="utf-8").strip()
    except OSError:
        value = "0.4.0"
    return value or "0.4.0"


@dataclass(frozen=True)
class LocalSnapshot:
    """Immutable bytes plus inspection result published to the UI thread."""

    path: Path
    data: bytes
    info: SaveInfo
    source_kind: str = "local"
    locator: str | None = None
    format_id: str = "stalker2"
    format_title: str = "S.T.A.L.K.E.R. 2: Heart of Chornobyl"
    release_id: str = ""
    edition: str = ""
    capabilities: FormatCapabilities = field(default_factory=_default_s2_capabilities)
    catalog: ItemCatalog | None = None
    game_catalog: GameCatalog | None = None


class InspectWorker(QThread):
    """Run one local read/inspect operation outside the UI thread."""

    completed = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        service: EditorService,
        path: Path,
        parent: QWidget | None = None,
        *,
        catalog_roots: tuple[Path, ...] = (),
    ) -> None:
        super().__init__(parent)
        self.service = service
        self.path = path
        self.catalog_roots = tuple(catalog_roots)

    def run(self) -> None:
        try:
            data = self.path.read_bytes()
            if self.catalog_roots:
                result = self.service.inspect_result(
                    data,
                    with_inventory=True,
                    source_name=self.path.name,
                    catalog_source=self.path,
                    catalog_roots=self.catalog_roots,
                )
            else:
                result = self.service.inspect_result(
                    data,
                    with_inventory=True,
                    source_name=self.path.name,
                    catalog_source=self.path,
                )
            self.completed.emit(
                LocalSnapshot(
                    path=self.path,
                    data=data,
                    info=result.info,
                    format_id=result.format_id,
                    format_title=result.format_title,
                    release_id=result.release_id,
                    edition=result.edition,
                    capabilities=result.capabilities,
                    catalog=result.catalog,
                    game_catalog=result.game_catalog,
                )
            )
        except FormatDetectionError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class MainWindow(QMainWindow):
    """Qt shell for local analysis, safe edits and local backup restore."""

    analysis_ready = Signal(object)
    analysis_failed = Signal(str)
    preview_ready = Signal(object)
    apply_ready = Signal(object)
    restore_ready = Signal(object)
    operation_failed = Signal(str)

    def __init__(
        self,
        service: EditorService,
        *,
        slot_discovery: SlotDiscoveryFn | None = None,
        settings_path: Path | None = None,
        update_client: UpdateClient | None = None,
        auto_update_check: bool = True,
    ) -> None:
        super().__init__()
        self.service = service
        self.settings_load = load_settings(path=settings_path)
        self.settings_path = self.settings_load.path
        self.settings = self.settings_load.settings
        self.slot_discovery = slot_discovery or self._discover_slots
        self.snapshot: LocalSnapshot | None = None
        self.staged_counts: dict[int, int] = {}
        self.staged_money: int | None = None
        self.staged_adds: dict[str, int] = {}
        self.staged_detach: dict[int, bool] = {}
        self.staged_durability: dict[int, float] = {}
        self.staged_faction_relations: dict[str, int] = {}
        self.staged_player_faction: str | None = None
        self.staged_upgrades: dict[int, tuple[str, ...]] = {}
        self.staged_placements: dict[int, tuple[str, int | None]] = {}
        self.equipment_rows: tuple[EquipmentItem, ...] = ()
        self.prepared_edit: PreparedEdit | None = None
        self._pending_apply_path: Path | None = None
        self._pending_cloud_upload = False
        self._pending_replace = False
        self._review_confirmed = False
        self.edit_actions_enabled = False
        self._inspect_thread: QThread | None = None
        self._inspect_worker: InspectWorker | None = None
        self._pending_path: Path | None = None
        self._operation_thread: QThread | None = None
        self._operation_kind: str | None = None
        self._cloud_busy = False
        self._support_dialog: SupportDialog | None = None
        self._diagnostics_dialog: DiagnosticsDialog | None = None
        self._update_client = update_client
        self._auto_update_check = auto_update_check
        self._update_thread: UpdateCheckWorker | None = None
        self._update_dialog: UpdateDialog | None = None
        self._update_installation: InstallationInfo | None = None

        # QApplication.instance() is typed as the base QCoreApplication.
        application = QApplication.instance()
        apply_theme(application if isinstance(application, QApplication) else None)
        self.setWindowTitle("S.T.A.L.K.E.R. — Save Editor")
        self.resize(1280, 820)
        self.setMinimumSize(960, 620)
        self._build_ui()
        if self._auto_update_check:
            QTimer.singleShot(0, lambda: self.check_for_updates(manual=False))

    def _build_ui(self) -> None:
        root = QWidget(self)
        root.setObjectName("appRoot")
        self.setCentralWidget(root)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        self._build_reference_frontend(root_layout)

    def _build_reference_frontend(self, root_layout: QVBoxLayout) -> None:
        catalog_root = self.settings.catalog_root("stalker2")
        self.cloud_controller = CloudController(
            self.service,
            backup_dir=backup_dirs()[0],
            catalog_roots=(catalog_root,) if catalog_root is not None else (),
            parent=self,
        )
        self.backup_controller = BackupController(backup_dirs=backup_dirs(), parent=self)
        self.discovery_controller = SlotDiscoveryController(
            self._discover_slots,
            parent=self,
        )
        self.app_shell = AppShell(self)
        self.app_shell.destination_requested.connect(self._on_reference_destination)
        self.app_shell.support_requested.connect(self._show_support_dialog)
        self.app_shell.close_requested.connect(self.close)

        self.reference_stack = QStackedWidget(self.app_shell)
        self.reference_stack.setObjectName("referenceScreenStack")
        self.library_view = LibraryView(self.reference_stack)
        self.library_view.set_installed_families(game.game_id for game in installed_releases())
        self.editor_view = EditorView(self.reference_stack)
        self.cloud_reference_view = CloudLibraryView(self.cloud_controller, self.reference_stack)
        self.history_reference_view = HistoryView(self.backup_controller, self.reference_stack)
        self.character_view = CharacterView(self.reference_stack)
        self.save_review_view = SaveReviewView(self.reference_stack)
        self.save_result_view = SaveResultView(self.reference_stack)
        self.unsupported_view = UnsupportedView(self.reference_stack)
        self.settings_reference_view = SettingsView(
            self.settings,
            settings_path=self.settings_path,
            load_error=self.settings_load.error,
            parent=self.reference_stack,
        )
        self.settings_reference_view.settings_changed.connect(self._on_settings_changed)
        self.settings_reference_view.update_requested.connect(lambda: self.check_for_updates(manual=True))
        self.settings_reference_view.diagnostics_requested.connect(self._show_diagnostics_dialog)
        self.settings_reference_view.support_requested.connect(self._show_support_dialog)
        self.settings_reference_view.setObjectName("settingsView")
        for widget in (
            self.library_view,
            self.editor_view,
            self.cloud_reference_view,
            self.history_reference_view,
            self.character_view,
            self.save_review_view,
            self.save_result_view,
            self.unsupported_view,
            self.settings_reference_view,
        ):
            self.reference_stack.addWidget(widget)
        self.app_shell.set_content(self.reference_stack)
        root_layout.addWidget(self.app_shell, 1)

        # These handles point at canonical surfaces, not a second hidden UI.
        # ``status_label`` is the shell footer status; errors stay out of the
        # geometry until a view has a dedicated error surface.
        self.status_label = self.app_shell.footer_status
        self.error_label = QLabel("", self)
        self.error_label.setObjectName("operationError")
        self.error_label.setVisible(False)
        self.open_button = self.library_view.open_button
        self.save_copy_button = self.editor_view.save_button
        self.preview_button = self.editor_view.save_button
        self.library_view.import_requested.connect(self.open_local)
        self.library_view.open_requested.connect(self._start_inspect)
        self.library_view.refresh_requested.connect(self.discovery_controller.refresh)
        self.library_view.cloud_requested.connect(self._show_cloud)
        self.editor_view.back_requested.connect(self._show_library)
        self.editor_view.save_requested.connect(self._request_reference_save)
        self.editor_view.stack_stage_requested.connect(self._stage_stack_change)
        self.editor_view.durability_stage_requested.connect(self._stage_item_durability)
        self.editor_view.placement_stage_requested.connect(self._stage_item_placement)
        self.editor_view.remove_requested.connect(self._stage_item_remove)
        self.editor_view.reset_requested.connect(self._reset_editor_item)
        self.editor_view.character_requested.connect(self._show_character_state)
        self.editor_view.money_stage_requested.connect(self._stage_money)
        self.editor_view.money_clear_requested.connect(self._clear_money)
        self.character_view.back_requested.connect(self._show_reference_editor)
        self.character_view.relation_stage_requested.connect(self._stage_faction_relation)
        self.character_view.player_faction_stage_requested.connect(self._stage_player_faction)
        self.history_reference_view.restore_requested.connect(self._start_restore)
        self.history_reference_view.restore_in_place_requested.connect(self._start_restore_in_place)
        self.history_reference_view.folder_open_requested.connect(self._open_backup_folder)
        self.save_review_view.confirmed.connect(self._confirm_reference_save)
        self.save_review_view.cancelled.connect(self._cancel_reference_save)
        self.save_result_view.back_to_editor_requested.connect(self._show_reference_editor)
        self.save_result_view.history_requested.connect(self._show_history)
        self.save_result_view.library_requested.connect(self._show_library)
        self.unsupported_view.back_requested.connect(self._show_library)
        self.unsupported_view.diagnostics_requested.connect(self._show_diagnostics_dialog)
        self.discovery_controller.discovery_ready.connect(self.library_view.set_discovery)
        self.discovery_controller.discovery_failed.connect(self.library_view.set_error)
        self.cloud_controller.snapshot_ready.connect(self._on_cloud_snapshot_ready)
        self.cloud_controller.upload_ready.connect(self._on_cloud_upload_ready)
        self.cloud_controller.operation_failed.connect(self._on_cloud_operation_failed)
        self.cloud_controller.operation_progress.connect(self._on_cloud_progress)
        self.cloud_controller.busy_changed.connect(self._on_cloud_busy)
        self.backup_controller.refresh()
        self.discovery_controller.refresh()
        self._show_reference_library()

    def _on_reference_destination(self, destination: str) -> None:
        if destination == "library":
            self._show_reference_library()
        elif destination == "cloud":
            self._show_cloud()
        elif destination == "history":
            self._show_history()
        elif destination == "settings":
            self._show_settings()

    def _show_reference_library(self) -> None:
        if hasattr(self, "reference_stack"):
            self.reference_stack.setCurrentWidget(self.library_view)
            self.app_shell.set_active_destination("library")

    def _show_reference_editor(self) -> None:
        if hasattr(self, "reference_stack"):
            self.reference_stack.setCurrentWidget(self.editor_view)
            self.app_shell.set_active_destination(
                "cloud" if self.snapshot is not None and self.snapshot.source_kind == "cloud" else "library"
            )

    def _show_history(self) -> None:
        if hasattr(self, "reference_stack"):
            self.reference_stack.setCurrentWidget(self.history_reference_view)
            self.app_shell.set_active_destination("history")

    def _show_settings(self) -> None:
        if hasattr(self, "reference_stack"):
            self.reference_stack.setCurrentWidget(self.settings_reference_view)
            self.app_shell.set_active_destination("settings")

    def _show_character_state(self) -> None:
        """Show the X-Ray-only character state without changing the editor draft."""

        if self.snapshot is None:
            return
        release = (self.snapshot.release_id or self.snapshot.format_id).casefold()
        if release not in {"soc", "cop", "clear_sky", "xray", "shadow_of_chornobyl", "call_of_pripyat"}:
            self.status_label.setText("Персонаж и группировки доступны только для X-Ray сейвов")
            return
        self.character_view.set_snapshot(self.snapshot)
        self.character_view.set_state(
            self.staged_faction_relations,
            self.staged_player_faction,
        )
        self.reference_stack.setCurrentWidget(self.character_view)
        self.app_shell.set_active_destination(
            "cloud" if self.snapshot.source_kind == "cloud" else "library",
            emit=False,
        )

    def _reference_change_rows(self) -> tuple[tuple[str, str, str], ...]:
        """Build review rows from staged values already accepted by the controller."""

        if self.snapshot is None:
            return ()
        rows: list[tuple[str, str, str]] = []
        info = self.snapshot.info
        if self.staged_money is not None:
            rows.append(("Баланс", str(info.money if info.money is not None else "—"), str(self.staged_money)))
        for handle, value in sorted(self.staged_counts.items()):
            item = self._find_inventory_item(handle)
            rows.append((item.type_key if item is not None else f"0x{handle:08X}", str(item.count if item is not None else "—"), str(value)))
        for handle, durability_value in sorted(self.staged_durability.items()):
            item = self._find_inventory_item(handle)
            before = "—" if item is None or item.condition is None else f"{item.condition * 100:.1f}%"
            rows.append((item.type_key if item is not None else f"0x{handle:08X}", before, f"{durability_value * 100:.1f}%"))
        for handle in sorted(self.staged_detach):
            item = self._find_inventory_item(handle)
            rows.append((item.type_key if item is not None else f"0x{handle:08X}", "в сейве", "удалить"))
        for item_key, quantity in sorted(self.staged_adds.items()):
            rows.append((item_key, "нет", f"добавить × {quantity}"))
        for key, value in sorted(self.staged_faction_relations.items()):
            rows.append((f"goodwill · {key}", "текущее", str(value)))
        for handle, values in sorted(self.staged_upgrades.items()):
            item = self._find_inventory_item(handle)
            rows.append((item.type_key if item is not None else f"0x{handle:08X}", "улучшения", ", ".join(values) or "нет"))
        for handle, (placement, slot) in sorted(self.staged_placements.items()):
            item = self._find_inventory_item(handle)
            target = placement if slot is None else f"{placement}:{slot}"
            rows.append((item.type_key if item is not None else f"0x{handle:08X}", "позиция", target))
        if self.staged_player_faction is not None:
            rows.append(("Группировка игрока", "текущая", self.staged_player_faction))
        return tuple(rows)

    def _request_reference_save(self) -> None:
        """Enter the visible review state; the legacy method remains test/API compatible."""

        if self.snapshot is None or not self._has_staged_changes():
            self._save_one_click()
            return
        rows = self._reference_change_rows()
        self.save_review_view.set_source(
            f"Источник: {self.snapshot.path.name} · "
            f"изменений: {len(rows)} · bytes исходного сейва пока не изменены"
        )
        self.save_review_view.set_changes(rows)
        self.reference_stack.setCurrentWidget(self.save_review_view)
        self.app_shell.set_active_destination(
            "cloud" if self.snapshot.source_kind == "cloud" else "library",
            emit=False,
        )

    def _confirm_reference_save(self) -> None:
        self.reference_stack.setCurrentWidget(self.editor_view)
        self._review_confirmed = True
        self._save_one_click()

    def _cancel_reference_save(self) -> None:
        self.status_label.setText("Сохранение отменено; изменения сохранены в памяти")
        self._show_reference_editor()

    def _show_save_result(self, receipt) -> None:
        self.save_result_view.set_receipt(
            receipt,
            status=getattr(receipt, "status", None),
        )
        self.reference_stack.setCurrentWidget(self.save_result_view)
        self.app_shell.set_active_destination(
            "cloud" if self.snapshot is not None and self.snapshot.source_kind == "cloud" else "library",
            emit=False,
        )

    def _show_unsupported(self, snapshot: LocalSnapshot, reason: str) -> None:
        self.unsupported_view.set_snapshot(snapshot, reason)
        self.reference_stack.setCurrentWidget(self.unsupported_view)
        self.app_shell.set_active_destination("library", emit=False)

    def _show_library(self) -> None:
        """Show the library without discarding the current snapshot."""
        self._show_reference_library()

    def _show_editor(self) -> None:
        self._show_reference_editor()

    def _show_cloud(self) -> None:
        """Enter the remote-save flow without requiring a local game save."""

        if hasattr(self, "reference_stack"):
            self.reference_stack.setCurrentWidget(self.cloud_reference_view)
            self.app_shell.set_active_destination("cloud")

    def _show_support_dialog(self) -> None:
        if self._support_dialog is not None and self._support_dialog.isVisible():
            self._support_dialog.raise_()
            self._support_dialog.activateWindow()
            return
        dialog = SupportDialog(self)
        self._support_dialog = dialog
        dialog.finished.connect(lambda _result: self._clear_support_dialog(dialog))
        dialog.open()

    def _show_diagnostics_dialog(self) -> None:
        if self._diagnostics_dialog is not None and self._diagnostics_dialog.isVisible():
            self._diagnostics_dialog.raise_()
            self._diagnostics_dialog.activateWindow()
            return
        dialog = DiagnosticsDialog(self)
        self._diagnostics_dialog = dialog
        dialog.finished.connect(lambda _result: self._clear_diagnostics_dialog(dialog))
        dialog.open()

    def _clear_diagnostics_dialog(self, dialog: DiagnosticsDialog) -> None:
        if self._diagnostics_dialog is dialog:
            self._diagnostics_dialog = None

    def _update_installation_info(self) -> InstallationInfo | None:
        if self._update_installation is not None:
            return self._update_installation
        try:
            self._update_installation = detect_installation()
        except Exception:
            return None
        return self._update_installation

    def _update_client_for_current_installation(self) -> UpdateClient | object | None:
        if self._update_client is not None:
            return self._update_client
        installation = self._update_installation_info()
        if installation is None or installation.kind == "development":
            return None
        kind = installation.kind if installation.kind in {"installer", "package"} else "portable"
        self._update_client = UpdateClient(
            current_version=_version_text(),
            target=installation.target,
            architecture=installation.architecture,
            kind=kind,
        )
        return self._update_client

    def check_for_updates(self, *, manual: bool = False) -> None:
        """Check releases away from Qt and show only actionable results."""

        if self._update_thread is not None and self._update_thread.isRunning():
            return
        client = self._update_client_for_current_installation()
        if client is None:
            if manual:
                self.status_label.setText(
                    "Автообновления доступны только в portable/package-сборке"
                )
            return
        installation = self._update_installation_info()
        if installation is None:
            if manual:
                self.status_label.setText("Не удалось определить тип установки")
            return
        worker = UpdateCheckWorker(client, self)
        worker.result.connect(lambda result: self._on_update_result(result, manual, installation, client))
        worker.finished.connect(self._on_update_thread_finished)
        worker.finished.connect(worker.deleteLater)
        self._update_thread = worker
        if manual:
            self.status_label.setText("Проверка обновлений…")
        worker.start()

    def _on_update_result(
        self,
        result: UpdateCheckResult,
        manual: bool,
        installation: InstallationInfo,
        client: object,
    ) -> None:
        if not manual and result.state != "available":
            return
        if self._update_dialog is not None and self._update_dialog.isVisible():
            self._update_dialog.raise_()
            self._update_dialog.activateWindow()
            return
        dialog = UpdateDialog(result, installation=installation, client=client, parent=self)
        self._update_dialog = dialog
        dialog.finished.connect(lambda _result: self._clear_update_dialog(dialog))
        dialog.open()

    def _on_update_thread_finished(self) -> None:
        self._update_thread = None

    def _clear_update_dialog(self, dialog: UpdateDialog) -> None:
        if self._update_dialog is dialog:
            self._update_dialog = None

    def _clear_support_dialog(self, dialog: SupportDialog) -> None:
        if self._support_dialog is dialog:
            self._support_dialog = None

    def _discover_slots(self):
        return discover_save_slots(
            release_ids=RELEASE_IDS,
            search_paths_fn=lambda release_id: search_paths_for_settings(
                release_id, self.settings
            )
        )

    def _on_settings_changed(self, settings: PathSettings) -> None:
        self.settings = settings
        catalog_root = settings.catalog_root("stalker2")
        self.cloud_controller.set_catalog_roots(
            (catalog_root,) if catalog_root is not None else ()
        )
        if hasattr(self, "cloud_reference_view"):
            self.cloud_reference_view.set_catalog_roots(
                (catalog_root,) if catalog_root is not None else ()
            )
        self.status_label.setText("Настройки обновлены; обновляю список сохранений…")
        self.discovery_controller.refresh()

    def _on_slot_discovery_failed(self, message: str) -> None:
        self.status_label.setText(f"Поиск слотов не выполнен: {message}")

    def open_local(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Открыть сохранение S.T.A.L.K.E.R.",
            "",
            "S.T.A.L.K.E.R. saves (*.sav *.scop *.scs);;Все файлы (*)",
        )
        if filename:
            self._start_inspect(Path(filename))

    def _start_inspect(self, path: Path) -> None:
        path = Path(path).expanduser()
        if self._inspect_thread is not None and self._inspect_thread.isRunning():
            return

        # Selecting a library row or importing a file enters the editor
        # immediately, so a failed/unsupported file is reported on-screen
        # instead of leaving the user on a stale library state.
        self._show_editor()
        self._pending_path = path
        self.open_button.setEnabled(False)
        self.library_view.status_label.setText(f"Анализ: {path.name}…")
        self.status_label.setText(f"Анализ: {path.name}…")
        self.error_label.clear()
        self.error_label.setVisible(False)

        catalog_root = self.settings.catalog_root("stalker2")
        thread = InspectWorker(
            self.service,
            path,
            self,
            catalog_roots=(catalog_root,) if catalog_root is not None else (),
        )
        thread.completed.connect(self._on_analysis_ready)
        thread.failed.connect(self._on_analysis_failed)
        thread.finished.connect(self._on_inspect_thread_finished)
        thread.finished.connect(thread.deleteLater)
        self._inspect_thread = thread
        self._inspect_worker = thread
        thread.start()

    def _on_analysis_ready(self, snapshot: LocalSnapshot) -> None:
        self.snapshot = snapshot
        if not snapshot.capabilities.read_inventory:
            self._show_unsupported(
                snapshot,
                "Релиз распознан, но безопасный inventory reader/writer для него не подтверждён. "
                "Диагностика доступна; запись и staged-редактирование отключены.",
            )
            self.analysis_ready.emit(snapshot)
            return
        self._render_snapshot(snapshot)
        self._show_editor()
        self.analysis_ready.emit(snapshot)

    def _on_analysis_failed(self, message: str) -> None:
        filename = self._pending_path.name if self._pending_path else "Сейв"
        self.status_label.setText("Анализ не выполнен; предыдущий корректный snapshot сохранён")
        display_message = (
            message
            if message.startswith("Error: Формат файла ")
            else f"{filename}: {message}"
        )
        self.error_label.setText(display_message)
        self.error_label.setVisible(True)
        self.analysis_failed.emit(message)

    def _on_inspect_thread_finished(self) -> None:
        self.open_button.setEnabled(True)
        self._inspect_thread = None
        self._inspect_worker = None

    def _render_snapshot(self, snapshot: LocalSnapshot) -> None:
        self.snapshot = snapshot
        info = snapshot.info
        for mapping in (
            self.staged_counts,
            self.staged_adds,
            self.staged_detach,
            self.staged_durability,
            self.staged_faction_relations,
            self.staged_upgrades,
            self.staged_placements,
        ):
            mapping.clear()
        self.staged_money = None
        self.staged_player_faction = None
        self.prepared_edit = None
        self._pending_apply_path = None
        self._pending_cloud_upload = False
        self._pending_replace = False
        self.cloud_controller.set_prepared(None)
        self.editor_view.set_snapshot(snapshot)
        self.equipment_rows = self.editor_view.equipment_rows
        self.editor_view.set_draft(
            counts=self.staged_counts,
            durability=self.staged_durability,
            removed=self.staged_detach,
            change_count=0,
        )
        self.editor_view.money_label.setText(
            f"◉  {info.money if info.money is not None else '—'} ₽"
        )
        self.library_view.set_snapshot(snapshot)
        self.character_view.set_snapshot(snapshot)
        self.character_view.set_state(
            self.staged_faction_relations,
            self.staged_player_faction,
        )
        self.library_view.status_label.setText(
            f"{snapshot.path.name} · {human_size(len(snapshot.data))} · "
            f"SHA {info.sha256[:12]}…"
        )
        self.status_label.setText("Анализ завершён; snapshot готов")
        self.error_label.clear()
        self.error_label.setVisible(False)
        self.edit_actions_enabled = True
        self._update_action_buttons()
        self._show_editor()

    def _render_factions(self, _info: SaveInfo) -> None:
        self.character_view.set_state(
            self.staged_faction_relations,
            self.staged_player_faction,
        )

    def _render_money(self, info: SaveInfo) -> None:
        can_edit_money = (
            self.snapshot is not None
            and self.snapshot.capabilities.edit_money
            and info.money is not None
            and info.money_anchor_count == 1
        )
        if not can_edit_money:
            self.editor_view.money_spin.setEnabled(False)
            self.editor_view.money_stage_button.setEnabled(False)
            self.editor_view.money_clear_button.setEnabled(False)
            return
        assert info.money is not None
        effective = self.staged_money if self.staged_money is not None else info.money
        self.editor_view.set_money_draft(effective)
        self.editor_view.money_spin.setEnabled(True)
        self.editor_view.money_stage_button.setEnabled(True)
        self.editor_view.money_clear_button.setEnabled(self.staged_money is not None)

    def _on_money_value_changed(self, _value: int) -> None:
        del _value

    def _stage_money(self, value: int | None = None) -> None:
        if self.snapshot is None:
            return
        info = self.snapshot.info
        if value is None:
            value = self.editor_view.money_spin.value()
        if not self.snapshot.capabilities.edit_money:
            self.editor_view.show_capability_message(
                "Только чтение: формат не разрешает редактирование денег"
            )
            return
        if info.money is None or info.money_anchor_count != 1:
            self.editor_view.show_capability_message(
                "Только чтение: wallet anchor не подтверждён"
            )
            return
        if not (0 <= value <= 2_000_000_000):
            self.editor_view.show_capability_message(
                "Сумма отклонена: допустим диапазон 0..2000000000"
            )
            return
        self.staged_money = None if value == info.money else value
        self._render_money(info)
        self._render_changes()
        self._invalidate_preview("изменилось staged значение баланса")
        self.status_label.setText(
            f"Staged: money={'нет' if self.staged_money is None else self.staged_money}, "
            f"stacks={len(self.staged_counts)}; bytes сейва не изменены — нужен preview"
        )

    def _clear_money(self) -> None:
        self.staged_money = None
        if self.snapshot is not None:
            self._render_money(self.snapshot.info)
            self._render_changes()
            self._invalidate_preview("staged баланс очищен")
        self.status_label.setText("Баланс возвращён к исходному значению; bytes сейва не изменены")

    def _find_inventory_item(self, handle: int):
        if self.snapshot is None:
            return None
        return next(
            (item for item in self.snapshot.info.inventory if item.handle == int(handle)),
            None,
        )

    def _stage_stack_change(self, handle: int, new_count: int) -> None:
        if self.snapshot is not None and not self.snapshot.capabilities.edit_stacks:
            self.editor_view.show_capability_message(
                "Только чтение: формат не разрешает редактирование stack count"
            )
            return
        item = self._find_inventory_item(handle)
        if item is None:
            self.editor_view.show_capability_message(
                f"Только чтение: handle 0x{int(handle):08X} не найден в текущем snapshot"
            )
            return
        value = int(new_count)
        if not (1 <= value <= item.count_max):
            self.editor_view.show_capability_message(
                f"Новое количество отклонено: допустимый диапазон 1..{item.count_max}"
            )
            return
        if not item.editable_count:
            reason = "count не извлечён" if item.count is None else (
                "count=1" if item.count <= 1 else f"неподтверждённый kind={item.kind_code}"
            )
            self.editor_view.show_capability_message(f"Только чтение: {reason}")
            return
        if value == item.count:
            self.staged_counts.pop(item.handle, None)
        else:
            self.staged_counts[item.handle] = value
        self._render_changes()
        self._invalidate_preview("изменилось staged значение stack")
        self.status_label.setText(
            f"Staged: {len(self.staged_counts)}; bytes сейва не изменены — нужен preview"
        )

    def _stage_item_add(self, item_key: str, quantity: int) -> None:
        if self.snapshot is None:
            return
        if not self.snapshot.capabilities.add_items:
            self.editor_view.show_capability_message(
                "Только чтение: формат не разрешает добавление предметов"
            )
            return
        catalog = self.snapshot.catalog
        definition = catalog.resolve(item_key) if catalog is not None else None
        if definition is None:
            self.editor_view.show_capability_message(
                f"Предмет {item_key!r} отсутствует в официальном каталоге"
            )
            return
        value = int(quantity)
        if value < 1 or value > 65535:
            self.editor_view.show_capability_message(
                "Количество нового предмета должно быть в диапазоне 1..65535"
            )
            return
        if (
            definition.serialization_family == "ammo"
            and definition.max_stack is not None
            and value > definition.max_stack
        ):
            self.editor_view.show_capability_message(
                f"Для {item_key} допустимо не больше {definition.max_stack} за стак"
            )
            return
        self.staged_adds[item_key] = value
        self._render_changes()
        self._invalidate_preview("изменилось staged добавление предмета")
        self.status_label.setText(
            f"Добавление staged: {item_key} × {value}; bytes сейва не изменены — нужен preview"
        )

    def _stage_item_remove(self, handle: int) -> None:
        if self.snapshot is None:
            return
        if not self.snapshot.capabilities.remove_items:
            self.editor_view.show_capability_message(
                "Только чтение: формат не разрешает удаление предметов"
            )
            return
        item = self._find_inventory_item(handle)
        if item is None:
            self.editor_view.show_capability_message(
                f"Только чтение: handle 0x{int(handle):04X} не найден"
            )
            return
        if not item.remove_editable:
            self.editor_view.show_capability_message(
                item.remove_reason or "Только чтение: удаление этого объекта заблокировано"
            )
            return
        handle = int(handle)
        if handle in self.staged_detach:
            self.staged_detach.pop(handle, None)
            message = f"Удаление отменено для {item.type_key}"
        else:
            self.staged_detach[handle] = True
            self.staged_counts.pop(handle, None)
            message = f"Удаление staged для {item.type_key}"
        self._render_changes()
        self._invalidate_preview("изменился staged список удалений")
        self.status_label.setText(f"{message}; bytes сейва не изменены — нужна проверка")

    def _stage_item_durability(self, handle: int, condition: float) -> None:
        if self.snapshot is None:
            return
        if not self.snapshot.capabilities.edit_durability:
            self.editor_view.show_capability_message(
                "Только чтение: формат не разрешает редактирование прочности"
            )
            return
        item = self._find_inventory_item(handle)
        if item is None or not item.condition_editable or item.condition is None:
            self.editor_view.show_capability_message(
                f"Только чтение: handle 0x{int(handle):04X} не имеет подтверждённого condition"
            )
            return
        value = float(condition)
        if not math.isfinite(value) or not 0.0 <= value <= 1.0:
            self.editor_view.show_capability_message("Прочность должна быть в диапазоне 0…100%")
            return
        if math.isclose(value, item.condition, rel_tol=0.0, abs_tol=1e-6):
            self.staged_durability.pop(item.handle, None)
        else:
            self.staged_durability[item.handle] = value
        self._render_changes()
        self._invalidate_preview("изменилось staged значение прочности")
        self.status_label.setText(
            f"Прочность staged для {item.type_key}; bytes сейва не изменены — нужен preview"
        )

    def _clear_item_durability(self, handle: int) -> None:
        if self.snapshot is None:
            return
        item = self._find_inventory_item(handle)
        if item is None:
            return
        self.staged_durability.pop(item.handle, None)
        self._render_changes()
        self._invalidate_preview("staged прочность очищена")
        self.status_label.setText(f"Прочность очищена для {item.type_key}; bytes сейва не изменены")

    def _finish_equipment_repair(self, result: RepairStageResult, *, action: str) -> None:
        for handle, value in result.changes:
            self.staged_durability[int(handle)] = float(value)
        for skipped in result.skipped:
            if skipped.reason.startswith("no-op:"):
                self.staged_durability.pop(skipped.handle, None)
        self._render_changes()
        self._invalidate_preview("изменилось staged оборудование")
        parts = [f"{action}: staged {len(result.changes)}"]
        if result.skipped:
            parts.append(f"пропущено {len(result.skipped)}")
        details = "; ".join(
            f"0x{item.handle:04X}: {item.reason}" for item in result.skipped[:3]
        )
        if details:
            parts.append(details)
        self.editor_view.show_capability_message(". ".join(parts))
        self.status_label.setText("Оборудование подготовлено; bytes сейва не изменены — нужна проверка")

    def _stage_equipment_repair(self, handle: int, percentage: float) -> None:
        result = stage_repair(self.equipment_rows, (int(handle),), percentage)
        self._finish_equipment_repair(result, action="Ремонт предмета")

    def _stage_equipment_bulk_repair(self, filter_name: str, percentage: float) -> None:
        result = stage_bulk_repair(self.equipment_rows, filter_name, percentage)  # type: ignore[arg-type]
        self._finish_equipment_repair(result, action=f"Массовый ремонт ({filter_name})")

    def _reset_equipment_repair(self, handle: int) -> None:
        self.staged_durability.pop(int(handle), None)
        self._render_changes()
        self._invalidate_preview("staged прочность оборудования очищена")
        self.status_label.setText("Прочность очищена; bytes сейва не изменены")

    def _stage_item_upgrades(self, handle: int, values: object) -> None:
        if self.snapshot is None:
            return
        capabilities = self.snapshot.capabilities
        if not capabilities.edit_upgrades:
            self.editor_view.show_capability_message(
                "Только чтение: правка улучшений не подтверждена для этого релиза"
            )
            return
        item = self._find_inventory_item(handle)
        if item is None or item.upgrades is None or not item.upgrades_editable:
            self.editor_view.show_capability_message(
                f"Только чтение: handle 0x{int(handle):08X} не имеет подтверждённого upgrades vector"
            )
            return
        if not isinstance(values, (tuple, list)):
            self.editor_view.show_capability_message("Список улучшений отклонён")
            return
        desired = tuple(str(value) for value in values)
        if desired == item.upgrades:
            self.staged_upgrades.pop(item.handle, None)
        else:
            self.staged_upgrades[item.handle] = desired
        self._render_changes()
        self._invalidate_preview("изменился staged список улучшений")
        self.status_label.setText(f"Улучшения подготовлены для {item.type_key}; bytes сейва не изменены — нужна проверка")

    def _clear_item_upgrades(self, handle: int) -> None:
        if self.snapshot is None:
            return
        item = self._find_inventory_item(handle)
        if item is None:
            return
        self.staged_upgrades.pop(item.handle, None)
        self._render_changes()
        self._invalidate_preview("staged улучшения очищены")
        self.status_label.setText(f"Улучшения очищены для {item.type_key}; bytes сейва не изменены")

    def _stage_item_placement(self, handle: int, placement_type: str, slot_id: object) -> None:
        if self.snapshot is None:
            return
        if not self.snapshot.capabilities.edit_placement:
            self.editor_view.show_capability_message(
                "Только чтение: формат не разрешает редактирование позиции"
            )
            return
        item = self._find_inventory_item(handle)
        if item is None or not item.placement_editable or item.placement_type is None:
            self.editor_view.show_capability_message(
                f"Только чтение: handle 0x{int(handle):04X} не имеет подтверждённого client-data place"
            )
            return
        normalized_type = str(placement_type).strip().casefold()
        if slot_id is None:
            normalized_slot = None
        elif isinstance(slot_id, int):
            normalized_slot = slot_id
        else:
            self.editor_view.show_capability_message("Только чтение: номер слота имеет неподдержанный тип")
            return
        current = (item.placement_type, item.placement_slot if item.placement_type == "slot" else None)
        desired = (normalized_type, normalized_slot)
        if desired == current:
            self.staged_placements.pop(item.handle, None)
            message = f"Позиция очищена для {item.type_key}"
        else:
            self.staged_placements[item.handle] = desired
            message = f"Позиция staged для {item.type_key}: {normalized_type}"
        self._render_changes()
        self._invalidate_preview("изменилось staged размещение предмета")
        self.status_label.setText(f"{message}; bytes сейва не изменены — нужна проверка")

    def _clear_item_placement(self, handle: int) -> None:
        if self.snapshot is None:
            return
        item = self._find_inventory_item(handle)
        if item is None:
            return
        self.staged_placements.pop(item.handle, None)
        self._render_changes()
        self._invalidate_preview("staged размещение очищено")
        self.status_label.setText(f"Позиция очищена для {item.type_key}; bytes сейва не изменены")

    def _stage_faction_relation(self, key: str, goodwill: int) -> None:
        if self.snapshot is None:
            return
        capabilities = self.snapshot.capabilities
        if not capabilities.edit_relations or not self.snapshot.info.faction_relations_editable:
            self.character_view.status_label.setText("Только чтение: формат не разрешает редактирование отношений")
            return
        game_catalog = self.snapshot.game_catalog
        if game_catalog is None:
            self.character_view.status_label.setText("Только чтение: официальный faction catalog не найден")
            return
        try:
            faction = game_catalog.factions.resolve(key)
        except CatalogLookupError as exc:
            self.character_view.status_label.setText(str(exc))
            return
        if faction.numeric_id is None:
            self.character_view.status_label.setText(f"Только чтение: у {key} нет подтверждённого numeric community id")
            return
        minimum = game_catalog.factions.goodwill_min
        maximum = game_catalog.factions.goodwill_max
        if minimum is None or maximum is None or not minimum <= goodwill <= maximum:
            self.character_view.status_label.setText(f"Goodwill отклонён: допустим диапазон {minimum}…{maximum}")
            return
        current = dict(self.snapshot.info.faction_relations).get(faction.numeric_id, 0)
        if int(goodwill) == current:
            self.staged_faction_relations.pop(key, None)
        else:
            self.staged_faction_relations[key] = int(goodwill)
        self.character_view.set_state(self.staged_faction_relations, self.staged_player_faction)
        self._render_changes()
        self._invalidate_preview("изменилось staged отношение группировки")
        self.status_label.setText(f"Отношение изменено: {key} → {goodwill}; bytes сейва не изменены — нужна проверка")

    def _stage_player_faction(self, key: str) -> None:
        if self.snapshot is None:
            return
        capabilities = self.snapshot.capabilities
        if not capabilities.edit_player_faction or not self.snapshot.info.player_faction_editable:
            self.character_view.status_label.setText("Только чтение: принадлежность игрока не подтверждена для этого сейва")
            return
        game_catalog = self.snapshot.game_catalog
        if game_catalog is None:
            self.character_view.status_label.setText("Только чтение: официальный faction catalog не найден")
            return
        try:
            faction = game_catalog.factions.resolve(key)
        except CatalogLookupError as exc:
            self.character_view.status_label.setText(str(exc))
            return
        if faction.numeric_id is None:
            self.character_view.status_label.setText(f"Только чтение: у {key} нет подтверждённого numeric community id")
            return
        self.staged_player_faction = None if faction.numeric_id == self.snapshot.info.player_faction_index else key
        self.character_view.set_state(self.staged_faction_relations, self.staged_player_faction)
        self._render_changes()
        self._invalidate_preview("изменилось staged принадлежность игрока")
        self.status_label.setText(f"Принадлежность игрока изменена: {key}; bytes сейва не изменены — нужна проверка")

    def _clear_selected_stack(self, handle: int) -> None:
        self.staged_counts.pop(int(handle), None)
        self._render_changes()
        self._invalidate_preview("staged stack очищен")
        self.status_label.setText(f"Подготовлено изменений: {len(self.staged_counts)}; bytes сейва не изменены — нужна проверка")

    def _reset_editor_item(self, handle: int) -> None:
        """Clear draft fields for one item without touching source bytes."""

        handle = int(handle)
        self.staged_counts.pop(handle, None)
        self.staged_durability.pop(handle, None)
        self.staged_detach.pop(handle, None)
        self.staged_upgrades.pop(handle, None)
        self.staged_placements.pop(handle, None)
        self._render_changes()
        self._invalidate_preview("черновик предмета сброшен")
        self.status_label.setText("Черновик предмета сброшен; исходные байты не изменены")

    def _clear_all_stacks(self) -> None:
        self.staged_counts.clear()
        self.staged_money = None
        self.staged_adds.clear()
        self.staged_detach.clear()
        self.staged_durability.clear()
        self.staged_faction_relations.clear()
        self.staged_player_faction = None
        self.staged_upgrades.clear()
        self.staged_placements.clear()
        if self.snapshot is not None:
            self._render_money(self.snapshot.info)
            self._render_factions(self.snapshot.info)
        self._render_changes()
        self._invalidate_preview("все staged-правки очищены")
        self.status_label.setText("Все изменения очищены; bytes сейва не изменены")

    def _render_changes(self) -> None:
        self.editor_view.set_draft(
            counts=self.staged_counts,
            durability=self.staged_durability,
            removed=self.staged_detach,
            change_count=self._draft_change_count(),
        )
        if self.snapshot is not None:
            self.character_view.set_state(
                self.staged_faction_relations,
                self.staged_player_faction,
            )

    def _has_staged_changes(self) -> bool:
        return bool(
            self.staged_money is not None
            or self.staged_counts
            or self.staged_adds
            or self.staged_detach
            or self.staged_durability
            or self.staged_faction_relations
            or self.staged_upgrades
            or self.staged_placements
            or self.staged_player_faction is not None
        )

    def _draft_change_count(self) -> int:
        return (
            len(self.staged_counts)
            + len(self.staged_adds)
            + len(self.staged_detach)
            + len(self.staged_durability)
            + len(self.staged_faction_relations)
            + len(self.staged_upgrades)
            + len(self.staged_placements)
            + (1 if self.staged_player_faction is not None else 0)
            + (1 if self.staged_money is not None else 0)
        )

    def _update_action_buttons(self) -> None:
        local_busy = self._operation_thread is not None and self._operation_thread.isRunning()
        busy = local_busy or self._cloud_busy
        has_changes = self.edit_actions_enabled and self._has_staged_changes()
        can_preview = has_changes
        can_apply = self.prepared_edit is not None
        self.preview_button.setEnabled(can_preview and not busy)
        # One-click save: enabled as soon as there are staged changes. The
        # click runs preview+apply internally, so it no longer waits for a
        # separate preview step.
        self.save_copy_button.setEnabled((can_preview or can_apply) and not busy)
        if hasattr(self, "history_reference_view"):
            self.history_reference_view.set_busy(busy)
        self.cloud_controller.set_external_busy(local_busy if not self._cloud_busy else False)

    def _show_operation_error(self, message: str) -> None:
        self.status_label.setText("Операция не выполнена")
        self.error_label.setText(message)
        self.error_label.setVisible(True)
        if hasattr(self, "history_reference_view"):
            self.history_reference_view.set_error(message)
        self.cloud_controller.set_error(message)
        self.operation_failed.emit(message)

    def _invalidate_preview(self, reason: str) -> None:
        self.prepared_edit = None
        safe_reason = reason.replace("staged", "черновик").replace("preview", "проверка")
        self.editor_view.show_capability_message(f"Проверка сброшена: {safe_reason}")
        self.cloud_controller.set_prepared(None)
        if hasattr(self, "cloud_reference_view"):
            self.cloud_reference_view.set_prepared(None)
        self._update_action_buttons()

    def _build_edit_plan(self) -> EditPlan:
        if self.snapshot is None:
            raise SaveError("Сначала проанализируй сейв")
        if not self._has_staged_changes():
            raise SaveError("Нет staged изменений")
        source_kind = self.snapshot.source_kind
        locator = self.snapshot.locator or str(self.snapshot.path)
        if source_kind not in ("local", "cloud"):
            raise SaveError(f"Неизвестный source kind: {source_kind}")
        kind: Literal["local", "cloud"] = "local" if source_kind == "local" else "cloud"
        return EditPlan(
            source=SourceRef(
                kind=kind,
                locator=locator,
                sha256=self.snapshot.info.sha256,
            ),
            money=self.staged_money,
            stacks=tuple(sorted(self.staged_counts.items())),
            detach=tuple(sorted(self.staged_detach.items())),
            adds=tuple(
                (item_key, quantity, "inventory")
                for item_key, quantity in sorted(self.staged_adds.items())
            ),
            durability=tuple(sorted(self.staged_durability.items())),
            faction_relations=tuple(sorted(self.staged_faction_relations.items())),
            player_faction=self.staged_player_faction,
            upgrades=tuple(sorted(self.staged_upgrades.items())),
            placements=tuple(
                (handle, placement_type, slot_id)
                for handle, (placement_type, slot_id)
                in sorted(self.staged_placements.items())
            ),
        )

    def _busy_now(self) -> bool:
        """True while a local operation or a cloud operation is in flight."""

        local = self._operation_thread is not None and self._operation_thread.isRunning()
        return local or self._cloud_busy

    def _start_preview(self) -> None:
        if self._busy_now():
            # Silence here reads as a dead button; the action buttons are also
            # disabled while busy, so this is the keyboard/automation path.
            self.status_label.setText("Дождись завершения текущей операции")
            return
        try:
            plan = self._build_edit_plan()
        except SaveError as exc:
            # Clear any queued one-click continuation even when plan creation
            # fails synchronously before a worker is started.
            self._on_operation_failed(str(exc))
            return

        self.prepared_edit = None
        self._operation_kind = "preview"
        self.error_label.clear()
        self.error_label.setVisible(False)
        self.status_label.setText("Проверка: подготовка…")
        worker = OperationWorker(
            self.service,
            mode="preview",
            data=self.snapshot.data if self.snapshot is not None else b"",
            plan=plan,
            catalog=self.snapshot.catalog if self.snapshot is not None else None,
            game_catalog=self.snapshot.game_catalog if self.snapshot is not None else None,
            parent=self,
        )
        worker.preview_ready.connect(self._on_preview_ready)
        worker.failed.connect(self._on_operation_failed)
        worker.progress.connect(self._on_operation_progress)
        worker.finished.connect(self._on_operation_finished)
        worker.finished.connect(worker.deleteLater)
        self._operation_thread = worker
        self._update_action_buttons()
        worker.start()

    def _on_preview_ready(self, prepared: PreparedEdit) -> None:
        try:
            current_plan = self._build_edit_plan()
        except SaveError as exc:
            self._on_operation_failed(str(exc))
            return
        if prepared.plan != current_plan:
            self._on_operation_failed("Staged форма изменилась во время preview; повтори preview")
            return
        self.prepared_edit = prepared
        self.editor_view.show_capability_message(
            f"Preview готов: SHA {prepared.output_sha256[:12]}…"
        )
        self.cloud_controller.set_prepared(prepared)
        if hasattr(self, "cloud_reference_view"):
            self.cloud_reference_view.set_prepared(prepared)
        self.preview_ready.emit(prepared)
        # One-click save chains straight into the write once the internal
        # preview is ready, so the user never sees a separate preview step.
        if getattr(self, "_pending_cloud_upload", False):
            self._pending_cloud_upload = False
            self._start_cloud_upload()
        elif self._pending_replace:
            self._pending_replace = False
            self._start_replace()
        elif self._pending_apply_path is not None:
            self._continue_pending_apply()
        else:
            self.status_label.setText("Проверено; можно сохранить")

    def _on_operation_progress(self, message: str) -> None:
        self.status_label.setText(message)
        if hasattr(self, "history_reference_view"):
            self.history_reference_view.set_progress(message)

    def _on_operation_failed(self, message: str) -> None:
        # A failed step must not leave a queued one-click apply behind.
        self._pending_apply_path = None
        self._pending_cloud_upload = False
        self._pending_replace = False
        if "SHA256" in message or "Источник изменился" in message:
            self.prepared_edit = None
            self.editor_view.show_capability_message("Проверка сброшена: SHA источника изменился")
            self.cloud_controller.set_prepared(None)
        self._show_operation_error(message)

    def _on_operation_finished(self) -> None:
        self._operation_thread = None
        self._operation_kind = None
        if hasattr(self, "history_reference_view"):
            self.history_reference_view.set_busy(False)
        self._update_action_buttons()

    def _choose_output(self) -> None:
        if self.snapshot is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить копию сейва",
            str(Path(self.snapshot.path).with_name(f"{Path(self.snapshot.path).stem}-edited.sav")),
            "S.T.A.L.K.E.R. saves (*.sav *.scop *.scs);;Все файлы (*)",
        )
        if path:
            self._start_apply(Path(path))

    def _confirm_save(self) -> bool:
        """Ask once before the internal preview/backup/write pipeline starts."""

        if self.snapshot is None:
            return False
        if self.snapshot.source_kind == "cloud":
            title = "Загрузить изменения в Steam Cloud?"
            message = (
                "Изменения будут проверены и загружены в выбранный cloud-сейв.\n\n"
                "Перед записью автоматически создаётся backup и recovery-копия. "
                "Продолжить?"
            )
        else:
            title = "Сохранить изменения?"
            message = (
                f"Изменения будут записаны в открытый сейв:\n{self.snapshot.path}\n\n"
                "Перед записью автоматически создаётся проверенная резервная копия. "
                "Продолжить?"
            )
        answer = QMessageBox.question(
            self,
            title,
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _save_one_click(self) -> None:
        """Save the open slot after one confirmation, with an automatic backup.

        The integrity checks (immutable preview, source-SHA, CRC) still run —
        they are internal stages and never require a separate preview tab.
        """

        review_confirmed = self._review_confirmed
        self._review_confirmed = False
        if self._busy_now():
            self.status_label.setText("Дождись завершения текущей операции")
            return
        if self.snapshot is None:
            self._show_operation_error("Сначала открой сейв")
            return
        if not self._has_staged_changes() and self.prepared_edit is None:
            self._show_operation_error("Нет подготовленных изменений")
            return
        if not review_confirmed and not self._confirm_save():
            self.status_label.setText("Сохранение отменено")
            return
        if self.snapshot.source_kind == "cloud":
            # Cloud has its own fail-closed upload path; keep using it.
            if self.prepared_edit is None:
                self._pending_apply_path = None
                self._pending_replace = False
                self._pending_cloud_upload = True
                self._start_preview()
                return
            self._start_cloud_upload()
            return
        self._pending_apply_path = None
        self._pending_replace = True
        self.status_label.setText("Сохраняю…")
        if self.prepared_edit is not None:
            self._pending_replace = False
            self._start_replace()
        else:
            self._start_preview()

    def _continue_pending_apply(self) -> None:
        path = self._pending_apply_path
        self._pending_apply_path = None
        if path is not None:
            self._start_apply(path)

    def _choose_and_start_apply(self) -> None:
        if self.prepared_edit is None:
            self._show_operation_error("Сначала выполни проверку; запись без неё запрещена")
            return
        if self.snapshot is not None and self.snapshot.source_kind == "cloud":
            self._start_cloud_upload()
            return
        self._choose_output()

    def _start_apply(self, output_path: Path, backup_dir: Path | None = None) -> None:
        if self._busy_now():
            self.status_label.setText("Дождись завершения текущей операции")
            return
        if self.prepared_edit is None:
            self._show_operation_error("Сначала выполни проверку; запись без неё запрещена")
            return
        if self.snapshot is None:
            self._show_operation_error("Нет текущего snapshot для apply")
            return
        if self.snapshot.source_kind == "cloud":
            self._start_cloud_upload()
            return
        try:
            current_plan = self._build_edit_plan()
        except SaveError as exc:
            self._show_operation_error(str(exc))
            return
        if self.prepared_edit.plan != current_plan:
            self._invalidate_preview("staged форма изменилась после preview")
            self._show_operation_error("Проверка устарела после изменения формы; выполни её заново")
            return

        source_path = Path(self.snapshot.path)
        output_path = Path(output_path).expanduser()
        backup_path = Path(backup_dir).expanduser() if backup_dir is not None else backup_dirs()[0]
        worker = OperationWorker(
            self.service,
            mode="apply",
            data=self.snapshot.data,
            plan=self.prepared_edit.plan,
            source_path=source_path,
            output_path=output_path,
            backup_dir=backup_path,
            catalog=self.snapshot.catalog,
            game_catalog=self.snapshot.game_catalog,
            parent=self,
        )
        worker.set_prepared(self.prepared_edit)
        worker.preview_ready.connect(self._on_preview_ready)
        worker.apply_ready.connect(self._on_apply_ready)
        worker.failed.connect(self._on_operation_failed)
        worker.progress.connect(self._on_operation_progress)
        worker.finished.connect(self._on_operation_finished)
        worker.finished.connect(worker.deleteLater)
        self._operation_kind = "apply"
        self._operation_thread = worker
        self.status_label.setText("Сохранение копии…")
        self._update_action_buttons()
        worker.start()

    def _confirm_and_start_replace(self) -> None:
        if self._busy_now():
            self.status_label.setText("Дождись завершения текущей операции")
            return
        if self.prepared_edit is None:
            self._show_operation_error("Сначала выполни проверку; запись без неё запрещена")
            return
        if self.snapshot is None:
            self._show_operation_error("Нет текущего snapshot для replace")
            return
        if self.snapshot.source_kind != "local":
            self._show_operation_error(
                "Замена исходного слота доступна только для desktop local save"
            )
            return
        try:
            current_plan = self._build_edit_plan()
        except SaveError as exc:
            self._show_operation_error(str(exc))
            return
        if self.prepared_edit.plan != current_plan:
            self._invalidate_preview("staged форма изменилась после preview")
            self._show_operation_error("Проверка устарела после изменения формы; выполни её заново")
            return

        source_path = Path(self.snapshot.path)
        answer = QMessageBox.warning(
            self,
            "Заменить исходный слот?",
            (
                f"Файл будет заменён напрямую:\n{source_path}\n\n"
                "Перед заменой создаётся проверяемый backup. Закрой игру и Steam "
                "Cloud, затем подтверди действие."
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._start_replace()

    def _start_replace(self, backup_dir: Path | None = None) -> None:
        if self._busy_now():
            self.status_label.setText("Дождись завершения текущей операции")
            return
        if self.prepared_edit is None:
            self._show_operation_error("Сначала выполни проверку; запись без неё запрещена")
            return
        if self.snapshot is None:
            self._show_operation_error("Нет текущего snapshot для replace")
            return
        if self.snapshot.source_kind != "local":
            self._show_operation_error(
                "Замена исходного слота доступна только для desktop local save"
            )
            return
        try:
            current_plan = self._build_edit_plan()
        except SaveError as exc:
            self._show_operation_error(str(exc))
            return
        if self.prepared_edit.plan != current_plan:
            self._invalidate_preview("staged форма изменилась после preview")
            self._show_operation_error("Проверка устарела после изменения формы; выполни её заново")
            return

        source_path = Path(self.snapshot.path)
        backup_path = (
            Path(backup_dir).expanduser() if backup_dir is not None else backup_dirs()[0]
        )
        worker = OperationWorker(
            self.service,
            mode="replace",
            data=self.snapshot.data,
            plan=self.prepared_edit.plan,
            source_path=source_path,
            backup_dir=backup_path,
            catalog=self.snapshot.catalog,
            game_catalog=self.snapshot.game_catalog,
            parent=self,
        )
        worker.set_prepared(self.prepared_edit)
        worker.apply_ready.connect(self._on_apply_ready)
        worker.failed.connect(self._on_operation_failed)
        worker.progress.connect(self._on_operation_progress)
        worker.finished.connect(self._on_operation_finished)
        worker.finished.connect(worker.deleteLater)
        self._operation_kind = "replace"
        self._operation_thread = worker
        self.status_label.setText("Сохранение исходного слота…")
        self._update_action_buttons()
        worker.start()

    def _on_apply_ready(self, receipt) -> None:
        was_replace = self._operation_kind == "replace"
        self.prepared_edit = None
        if was_replace:
            self.status_label.setText(
                f"Сохранено: {receipt.output_path} · резервная копия создана"
            )
        else:
            self.status_label.setText(
                f"Сохранено: {receipt.output_path} · бэкап исходного сделан"
            )
        self._show_save_result(receipt)
        self.apply_ready.emit(receipt)

    def _start_restore(self, record, output_path: Path) -> None:
        if self._operation_thread is not None and self._operation_thread.isRunning():
            return
        if getattr(record, "status", None) != "verified":
            self._show_operation_error("Выбранный backup не прошёл проверку SHA256")
            return
        worker = RestoreWorker(self.service, record, Path(output_path), parent=self)
        worker.completed.connect(self._on_restore_ready)
        worker.failed.connect(self._on_operation_failed)
        worker.progress.connect(self._on_operation_progress)
        worker.finished.connect(self._on_operation_finished)
        worker.finished.connect(worker.deleteLater)
        self._operation_kind = "restore"
        self._operation_thread = worker
        self.status_label.setText("Восстановление копии…")
        self._update_action_buttons()
        worker.start()

    def _on_restore_ready(self, receipt) -> None:
        if hasattr(self, "history_reference_view"):
            self.history_reference_view.mark_restored(receipt)
        self.status_label.setText(f"Копия восстановлена: {receipt.output_path}")
        self.restore_ready.emit(receipt)

    def _start_restore_in_place(self, record) -> None:
        if self._operation_thread is not None and self._operation_thread.isRunning():
            return
        if getattr(record, "status", None) != "verified":
            self._show_operation_error("Выбранный backup не прошёл проверку SHA256")
            return
        worker = RestoreWorker(self.service, record, in_place=True, parent=self)
        worker.completed.connect(self._on_restore_in_place_ready)
        worker.failed.connect(self._on_operation_failed)
        worker.progress.connect(self._on_operation_progress)
        worker.finished.connect(self._on_operation_finished)
        worker.finished.connect(worker.deleteLater)
        self._operation_kind = "restore_in_place"
        self._operation_thread = worker
        self.status_label.setText("Восстановление исходного слота…")
        self._update_action_buttons()
        worker.start()

    def _on_restore_in_place_ready(self, receipt) -> None:
        if hasattr(self, "history_reference_view"):
            self.history_reference_view.mark_in_place_restored(receipt)
        self.status_label.setText(f"Исходный слот восстановлен: {receipt.output_path}")
        self.restore_ready.emit(receipt)

    def _on_cloud_snapshot_ready(self, snapshot: CloudSnapshot) -> None:
        local_snapshot = LocalSnapshot(
            path=Path(snapshot.name),
            data=snapshot.data,
            info=snapshot.info,
            source_kind="cloud",
            locator=snapshot.name,
            format_id=snapshot.format_id,
            format_title=snapshot.format_title,
            release_id=snapshot.release_id,
            edition=snapshot.edition,
            capabilities=snapshot.capabilities,
            catalog=snapshot.catalog,
            game_catalog=snapshot.game_catalog,
        )
        self._render_snapshot(local_snapshot)
        self.analysis_ready.emit(local_snapshot)
        self.status_label.setText(
            f"Cloud snapshot готов: {snapshot.name}; выбери изменения и создай preview"
        )

    def _start_cloud_upload(self) -> None:
        if self.prepared_edit is None:
            self._show_operation_error("Сначала выполни проверку cloud-сейва")
            return
        self.status_label.setText("Cloud upload: подготовка…")
        self.cloud_controller.start_upload()

    def _on_cloud_upload_ready(self, receipt) -> None:
        self.prepared_edit = None
        self.status_label.setText(
            "Cloud: verified" if receipt.status == "verified" else "Cloud: uncertain — требуется reconciliation"
        )
        self._update_action_buttons()
        self._show_save_result(receipt)
        self.apply_ready.emit(receipt)

    def _on_cloud_operation_failed(self, message: str) -> None:
        self._show_operation_error(message)

    def _on_cloud_progress(self, message: str) -> None:
        self.status_label.setText(message)

    def _on_cloud_busy(self, busy: bool) -> None:
        self._cloud_busy = busy
        self._update_action_buttons()

    def _open_backup_folder(self, path: Path) -> None:
        folder = Path(path).expanduser()
        if not folder.is_dir():
            self._show_operation_error(f"Папка backup не существует: {folder}")
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder))):
            self._show_operation_error(f"Не удалось открыть папку backup: {folder}")

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._operation_thread is not None and self._operation_thread.isRunning():
            self.status_label.setText(
                "Операция ещё выполняется; закрой окно после завершения, чтобы не оборвать запись"
            )
            event.ignore()
            return
        if self.cloud_controller.is_busy and not self.cloud_controller.stop_worker(30_000):
            self.status_label.setText(
                "Cloud operation ещё выполняется; окно закрыто не будет"
            )
            event.ignore()
            return
        if not self.discovery_controller.wait_for_worker():
            self.status_label.setText(
                "Поиск сохранений ещё выполняется; закрой окно после завершения"
            )
            event.ignore()
            return
        if self._update_thread is not None and self._update_thread.isRunning():
            self._update_thread.requestInterruption()
            self._update_thread.wait(2_000)
            if self._update_thread.isRunning():
                self.status_label.setText(
                    "Проверка обновлений ещё выполняется; окно закрыто не будет"
                )
                event.ignore()
                return
        if self._inspect_thread is not None and self._inspect_thread.isRunning():
            self._inspect_thread.quit()
            self._inspect_thread.wait(10_000)
        # A QThread destroyed while running aborts the process, so the window
        # never closes over one that is still alive.
        if self._operation_thread is not None and self._operation_thread.isRunning():
            self._operation_thread.quit()
            self._operation_thread.wait(10_000)
        self.cloud_controller.close()
        event.accept()


__all__ = ["InspectWorker", "LocalSnapshot", "MainWindow"]
