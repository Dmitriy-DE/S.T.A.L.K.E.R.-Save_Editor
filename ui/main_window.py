"""Small responsive Qt shell for local save inspection.

The window deliberately owns no parser or writer rules.  It asks
``EditorService`` to inspect bytes in a worker thread and keeps the last valid
snapshot visible when a later file is malformed.
"""

from __future__ import annotations

import gzip
import math
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Literal

from PySide6.QtCore import QEvent, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QGridLayout,
    QMainWindow,
    QMessageBox,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from editor.capabilities import FormatCapabilities
from editor.catalog import CatalogLookupError, GameCatalog, ItemCatalog
from editor.diagnostics import LOG_FILENAME, collect_log_bundle, log_directory
from editor.equipment import EquipmentItem
from editor.equipment_edits import RepairStageResult, stage_bulk_repair, stage_repair
from editor.formats import STALKER2_FORMAT, FormatDetectionError
from editor.models import EditPlan, PreparedEdit, SourceRef
from editor.platforms import backup_dirs, installed_releases
from editor.releases import is_xray_original_release
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
from .formatting import human_money, human_size
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
from .ux_copy import (
    ERROR_COPY,
    ErrorKind,
    classify_analysis_error,
    classify_operation_error,
    format_error_details,
    present_error,
    technical_details,
)


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
        self._post_save_reinspect_thread: QThread | None = None
        self._post_save_receipt = None
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
        self._error_dialog: QMessageBox | None = None
        self._details_dialog: QMessageBox | None = None
        self._update_client = update_client
        self._auto_update_check = auto_update_check
        self._update_thread: UpdateCheckWorker | None = None
        self._update_dialog: UpdateDialog | None = None
        self._update_installation: InstallationInfo | None = None
        self._session_activity: list[tuple[str, str, str, str]] = []
        self._reference_modal_view: QWidget | None = None

        # QApplication.instance() is typed as the base QCoreApplication.
        application = QApplication.instance()
        apply_theme(application if isinstance(application, QApplication) else None)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
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
            self.slot_discovery,
            parent=self,
        )
        self.app_shell = AppShell(self)
        self.app_shell.destination_requested.connect(self._on_reference_destination)
        self.app_shell.support_requested.connect(self._show_support_dialog)
        self.app_shell.close_requested.connect(self.close)

        self.reference_stack = QStackedWidget(self.app_shell)
        self.reference_stack.setObjectName("referenceScreenStack")
        self.reference_stack.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
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
        self.settings_reference_view.backup_folder_requested.connect(
            self._open_settings_backup_folder
        )
        self.settings_reference_view.journal_requested.connect(self._open_diagnostics_log)
        self.settings_reference_view.copy_diagnostics_requested.connect(
            self._copy_diagnostics_to_clipboard
        )
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
        # Modal states keep the last valid screen alive beneath a real dimming
        # layer.  The focused card is a normal Qt widget; no screenshot is
        # used as a background and no domain state is duplicated.
        self.reference_host = QWidget(self.app_shell)
        self.reference_host.setObjectName("referenceHost")
        self.reference_host.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        reference_host_layout = QGridLayout(self.reference_host)
        reference_host_layout.setContentsMargins(0, 0, 0, 0)
        reference_host_layout.setSpacing(0)
        reference_host_layout.addWidget(self.reference_stack, 0, 0)
        self.reference_modal_layer = QWidget(self.reference_host)
        self.reference_modal_layer.setObjectName("referenceModalLayer")
        self.reference_modal_layer.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.reference_modal_layer.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        modal_layer_layout = QGridLayout(self.reference_modal_layer)
        modal_layer_layout.setContentsMargins(0, 0, 0, 0)
        modal_layer_layout.setSpacing(0)
        self.reference_modal_card = QFrame(self.reference_modal_layer)
        self.reference_modal_card.setObjectName("referenceModalCard")
        self.reference_modal_card.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Preferred,
        )
        self.reference_modal_card_layout = QVBoxLayout(self.reference_modal_card)
        self.reference_modal_card_layout.setContentsMargins(0, 0, 0, 0)
        self.reference_modal_card_layout.setSpacing(0)
        modal_layer_layout.addWidget(
            self.reference_modal_card,
            0,
            Qt.AlignmentFlag.AlignCenter,
        )
        reference_host_layout.addWidget(self.reference_modal_layer, 0, 0)
        self.reference_modal_layer.hide()
        self.app_shell.set_content(self.reference_host)
        root_layout.addWidget(self.app_shell, 1)

        # These handles point at canonical surfaces, not a second hidden UI.
        # ``status_label`` is the shell footer status; analysis errors belong to
        # the library surface so a failed open cannot leave an unattached label.
        self.status_label = self.app_shell.footer_status
        self.error_label = self.library_view.error_label
        self.open_button = self.library_view.open_button
        self.save_copy_button = self.editor_view.save_button
        self.preview_button = self.editor_view.save_button
        self.library_view.import_requested.connect(self.open_local)
        self.library_view.open_requested.connect(self._start_inspect)
        self.library_view.restore_requested.connect(self._show_history_for_source)
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
        self.save_result_view.reconcile_requested.connect(self.cloud_controller.reconcile_remote)
        self.unsupported_view.back_requested.connect(self._show_library)
        self.unsupported_view.diagnostics_requested.connect(self._show_diagnostics_dialog)
        self.discovery_controller.discovery_ready.connect(self.library_view.set_discovery)
        self.discovery_controller.discovery_failed.connect(self.library_view.set_error)
        self.cloud_controller.snapshot_ready.connect(self._on_cloud_snapshot_ready)
        self.cloud_controller.reconciliation_ready.connect(self._on_cloud_reconciliation_ready)
        self.cloud_controller.reconciliation_failed.connect(self._on_cloud_reconciliation_failed)
        self.cloud_controller.upload_ready.connect(self._on_cloud_upload_ready)
        self.cloud_controller.operation_failed.connect(self._on_cloud_operation_failed)
        self.cloud_controller.operation_progress.connect(self._on_cloud_progress)
        self.cloud_controller.busy_changed.connect(self._on_cloud_busy)
        self.backup_controller.records_changed.connect(self._on_backup_records_changed)
        self.backup_controller.refresh()
        self.discovery_controller.refresh()
        self._show_reference_library()

    def _on_backup_records_changed(self, records) -> None:
        journal_entries = [
            (
                "Резервная копия",
                PurePosixPath(record.source_path.replace("\\", "/")).name
                if record.source_path
                else record.backup_path.name,
                record.created_at,
                {
                    "verified": "Файл проверен",
                    "missing": "Резервная копия недоступна",
                    "corrupt": "Резервная копия повреждена",
                }.get(record.status, "Требует проверки"),
            )
            for record in tuple(records or ())
        ]
        self.library_view.set_recent_activity((*journal_entries, *self._session_activity))

    def _record_recent_activity(self, label: str, target: str, status: str) -> None:
        visible_name = PurePosixPath(str(target).replace("\\", "/")).name or str(target)
        occurred_at = datetime.now().astimezone().isoformat(timespec="minutes")
        self._session_activity.append((label, visible_name, occurred_at, status))
        self._on_backup_records_changed(self.backup_controller.records)

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
            self._hide_reference_modal()
            self.reference_stack.setCurrentWidget(self.library_view)
            self.app_shell.set_active_destination("library")
            self.app_shell.set_footer_actions(
                (
                    ("Enter", "Открыть", self.library_view.open_selected),
                    ("I", "Импорт", self.open_local),
                    ("R", "Обновить", self.discovery_controller.refresh),
                    ("F", "Фильтр", self.library_view.search_edit.setFocus),
                )
            )

    def _show_reference_editor(self) -> None:
        if hasattr(self, "reference_stack"):
            self._hide_reference_modal()
            self.reference_stack.setCurrentWidget(self.editor_view)
            table = self.editor_view.table
            if table.model().rowCount() and not table.selectionModel().selectedRows():
                table.selectRow(0)
            table.setFocus(Qt.FocusReason.OtherFocusReason)
            self.app_shell.set_active_destination(
                "cloud" if self.snapshot is not None and self.snapshot.source_kind == "cloud" else "library"
            )
            actions = [
                ("S", "Сохранить", self._request_reference_save),
                ("F", "Фильтр", self.editor_view.search_edit.setFocus),
                ("Esc", "Назад", self._show_library),
            ]
            if self.editor_view.detail_view.remove_button.isEnabled():
                actions.insert(2, ("Del", "Удалить", self.editor_view.detail_view._emit_remove))
            self.app_shell.set_footer_actions(actions)

    def _show_history(self) -> None:
        if hasattr(self, "reference_stack"):
            self._hide_reference_modal()
            self.reference_stack.setCurrentWidget(self.history_reference_view)
            self.app_shell.set_active_destination("history")
            self.app_shell.set_footer_actions(
                (
                    ("Enter", "Проверить копию", self.history_reference_view.preview_selected),
                    ("R", "Обновить", self.history_reference_view.refresh),
                    ("Esc", "Назад", self._show_library),
                )
            )

    def _show_history_for_source(self, source: Path) -> None:
        self._show_history()
        self.history_reference_view.select_for_source(source)

    def _show_settings(self) -> None:
        if hasattr(self, "reference_stack"):
            self._hide_reference_modal()
            self.reference_stack.setCurrentWidget(self.settings_reference_view)
            self.app_shell.set_active_destination("settings")
            self.app_shell.set_footer_actions(
                (
                    ("Enter", "Сохранить", self.settings_reference_view.save),
                    ("Ctrl+S", "Сохранить", self.settings_reference_view.save),
                    ("R", "Сбросить", self.settings_reference_view.reset),
                    ("D", "По умолчанию", self.settings_reference_view.defaults),
                    ("Esc", "Отмена", self.settings_reference_view.cancel),
                )
            )

    def _show_character_state(self) -> None:
        """Show the X-Ray-only character state without changing the editor draft."""

        if self.snapshot is None:
            return
        release = (self.snapshot.release_id or self.snapshot.format_id).casefold()
        if not is_xray_original_release(release):
            self.status_label.setText(
                "Персонаж и группировки доступны только для сохранений X-Ray."
            )
            return
        self.character_view.set_snapshot(self.snapshot)
        self.character_view.set_state(
            self.staged_faction_relations,
            self.staged_player_faction,
        )
        self._hide_reference_modal()
        self.reference_stack.setCurrentWidget(self.character_view)
        self.app_shell.set_active_destination(
            "cloud" if self.snapshot.source_kind == "cloud" else "library",
            emit=False,
        )
        self.app_shell.set_footer_actions(
            (
                ("S", "Сохранить", self._request_reference_save),
                ("Esc", "Назад", self._show_reference_editor),
            )
        )

    def _reference_change_rows(self) -> tuple[tuple[str, str, str], ...]:
        """Build review rows from staged values already accepted by the controller."""

        if self.snapshot is None:
            return ()
        rows: list[tuple[str, str, str]] = []
        info = self.snapshot.info
        if self.staged_money is not None:
            before = human_money(info.money) if info.money is not None else "—"
            rows.append(("Баланс", f"{before} ₽", f"{human_money(self.staged_money)} ₽"))
        for handle, value in sorted(self.staged_counts.items()):
            item = self._find_inventory_item(handle)
            name = self._item_name(item)
            rows.append((f"{name} · количество", str(item.count if item is not None else "—"), str(value)))
        for handle, durability_value in sorted(self.staged_durability.items()):
            item = self._find_inventory_item(handle)
            name = self._item_name(item)
            before = "—" if item is None or item.condition is None else f"{item.condition * 100:.0f}%"
            rows.append((f"{name} · состояние", before, f"{durability_value * 100:.0f}%"))
        for handle in sorted(self.staged_detach):
            item = self._find_inventory_item(handle)
            name = self._item_name(item)
            rows.append((name, "в сохранении", "удалить"))
        for item_key, quantity in sorted(self.staged_adds.items()):
            definition = self.snapshot.catalog.resolve(item_key) if self.snapshot.catalog else None
            rows.append((definition.display_name if definition and definition.display_name else "Предмет", "нет", f"добавить × {quantity}"))
        for key, value in sorted(self.staged_faction_relations.items()):
            faction = (
                self.snapshot.game_catalog.factions.resolve(key)
                if self.snapshot.game_catalog is not None
                else None
            )
            faction_name = faction.display_name if faction and faction.display_name else "Группировка"
            rows.append((f"Отношение: {faction_name}", "текущее", str(value)))
        for handle, values in sorted(self.staged_upgrades.items()):
            item = self._find_inventory_item(handle)
            rows.append((self._item_name(item), "модификации", ", ".join(values) or "нет"))
        for handle, (placement, slot) in sorted(self.staged_placements.items()):
            item = self._find_inventory_item(handle)
            target = {"ruck": "Рюкзак", "belt": "Пояс", "slot": f"Слот {slot}"}.get(placement, "Инвентарь")
            rows.append((self._item_name(item), "размещение", target))
        if self.staged_player_faction is not None:
            faction = (
                self.snapshot.game_catalog.factions.resolve(self.staged_player_faction)
                if self.snapshot.game_catalog is not None
                else None
            )
            faction_name = faction.display_name if faction and faction.display_name else "Группировка"
            rows.append(("Группировка игрока", "текущая", faction_name))
        return tuple(rows)

    @staticmethod
    def _item_name(item) -> str:
        return item.display_name or "Неизвестный предмет" if item is not None else "Неизвестный предмет"

    def _request_reference_save(self) -> None:
        """Enter the visible review state; the legacy method remains test/API compatible."""

        if self.snapshot is None or not self._has_staged_changes():
            self._save_one_click()
            return
        rows = self._reference_change_rows()
        self.save_review_view.set_source(
            f"Источник: {self.snapshot.path.name} · "
            f"Подготовлено {len(rows)} изменений. Оригинальный файл пока не изменён."
        )
        self.save_review_view.set_changes(rows)
        self._show_reference_modal(self.save_review_view, base_widget=self.editor_view)
        self.app_shell.set_active_destination(
            "cloud" if self.snapshot.source_kind == "cloud" else "library",
            emit=False,
        )
        self.app_shell.set_footer_actions(
            (
                ("Enter", "Подтвердить", self._confirm_reference_save),
                ("Esc", "Отмена", self._cancel_reference_save),
            )
        )

    def _confirm_reference_save(self) -> None:
        self._hide_reference_modal()
        self.reference_stack.setCurrentWidget(self.editor_view)
        self._review_confirmed = True
        self._save_one_click()

    def _cancel_reference_save(self) -> None:
        self.status_label.setText("Сохранение отменено. Черновик изменений сохранён.")
        self._show_reference_editor()

    def _show_reference_modal(self, view: QWidget, *, base_widget: QWidget | None = None) -> None:
        """Show a focused state over a live, dimmed application surface."""

        if view not in {
            self.save_review_view,
            self.save_result_view,
            self.unsupported_view,
        }:
            raise ValueError("unsupported reference modal")
        if self._reference_modal_view is not None:
            self._hide_reference_modal()
        base = base_widget or self.reference_stack.currentWidget()
        if base in {view, self.save_review_view, self.save_result_view, self.unsupported_view}:
            base = self.editor_view if self.snapshot is not None else self.library_view
        if base is not None and self.reference_stack.indexOf(base) >= 0:
            self.reference_stack.setCurrentWidget(base)
        if self.reference_stack.indexOf(view) >= 0:
            self.reference_stack.removeWidget(view)
        view.setParent(self.reference_modal_card)
        limits = {
            self.save_review_view: (960, 540),
            self.save_result_view: (900, 500),
            self.unsupported_view: (960, 540),
        }
        max_width, max_height = limits[view]
        self.reference_modal_card.setMaximumSize(max_width, max_height)
        self.reference_modal_card.setMinimumSize(0, 0)
        view.setMaximumSize(max_width - 2, max_height - 2)
        view.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.reference_modal_card_layout.addWidget(view)
        self._reference_modal_view = view
        self.reference_modal_layer.show()
        self.reference_modal_card.show()
        view.show()
        self.reference_modal_layer.raise_()
        self.reference_modal_card.adjustSize()

    def _hide_reference_modal(self) -> None:
        view = self._reference_modal_view
        if view is None:
            return
        self.reference_modal_card_layout.removeWidget(view)
        view.setParent(self.reference_stack)
        view.hide()
        self.reference_stack.addWidget(view)
        self.reference_modal_card.hide()
        self.reference_modal_layer.hide()
        self._reference_modal_view = None

    def _show_save_result(self, receipt, *, cloud_reconciliation: bool = False) -> None:
        self.save_result_view.set_receipt(
            receipt,
            status=getattr(receipt, "status", None),
            change_count=self._draft_change_count(),
        )
        # The receipt is visible immediately, but the editor may only be
        # reopened after the actual published bytes have been re-inspected (or
        # Cloud has completed remote reconciliation).
        pending_message = (
            "Steam проверяет результат записи. Редактор откроется после подтверждения."
            if getattr(receipt, "remote_path", None) is not None
            else "Запись завершена. Проверяем сохранённое состояние…"
        )
        self.save_result_view.set_editor_ready(False, pending_message)
        if cloud_reconciliation and getattr(receipt, "status", None) == "verified":
            self.save_result_view.subtitle.setText(
                "Запись подтверждена. Обновляем список Steam Cloud…"
            )
        base = self.reference_stack.currentWidget()
        if base in {
            self.save_review_view,
            self.save_result_view,
            self.unsupported_view,
        }:
            base = self.editor_view if self.snapshot is not None else self.library_view
        self._show_reference_modal(self.save_result_view, base_widget=base)
        self.app_shell.set_active_destination(
                "cloud" if self.snapshot is not None and self.snapshot.source_kind == "cloud" else "library",
            emit=False,
        )
        self.app_shell.set_footer_actions(
            (
                ("Esc", "К библиотеке", self._show_library),
            )
        )

    def _enable_verified_result_editor(self, message: str) -> None:
        self.save_result_view.set_editor_ready(True, message)
        self.app_shell.set_footer_actions(
            (
                ("Enter", "К редактору", self._show_reference_editor),
                ("Esc", "К библиотеке", self._show_library),
            )
        )

    def _show_unsupported(self, snapshot: LocalSnapshot, reason: str) -> None:
        self.unsupported_view.set_snapshot(snapshot, reason)
        self._show_reference_modal(self.unsupported_view, base_widget=self.library_view)
        self.app_shell.set_active_destination("library", emit=False)
        self.app_shell.set_footer_actions(
            (
                ("D", "Диагностика", self._show_diagnostics_dialog),
                ("Esc", "К библиотеке", self._show_library),
            )
        )

    def _show_library(self) -> None:
        """Show the library without discarding the current snapshot."""
        self._show_reference_library()

    def _show_editor(self) -> None:
        self._show_reference_editor()

    def _show_cloud(self) -> None:
        """Enter the remote-save flow without requiring a local game save."""

        if hasattr(self, "reference_stack"):
            self._hide_reference_modal()
            self.reference_stack.setCurrentWidget(self.cloud_reference_view)
            self.app_shell.set_active_destination("cloud")
            self.app_shell.set_footer_actions(
                (
                    ("Enter", "Скачать и открыть", self.cloud_reference_view.analyze_selected),
                    ("R", "Обновить", self.cloud_reference_view.refresh),
                    ("Esc", "Назад", self._show_library),
                )
            )

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

    def _open_settings_backup_folder(self) -> None:
        folder = next((path for path in backup_dirs() if path.is_dir()), None)
        if folder is None:
            self._show_operation_error(
                "Папка резервных копий появится после создания первого backup."
            )
            return
        self._open_backup_folder(folder)

    def _open_diagnostics_log(self) -> None:
        path = log_directory() / LOG_FILENAME
        if not path.is_file():
            QMessageBox.information(
                self,
                "Журнал приложения",
                "Журнал пока пуст. Он появится после первой записи события приложения.",
            )
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            self._show_operation_error(f"Не удалось открыть журнал приложения: {path}")

    def _copy_diagnostics_to_clipboard(self) -> None:
        try:
            redacted_text = gzip.decompress(collect_log_bundle()).decode(
                "utf-8", errors="replace"
            )
        except (OSError, ValueError, gzip.BadGzipFile) as exc:
            self._show_operation_error(f"Не удалось подготовить диагностику: {exc}")
            return
        if not redacted_text.strip():
            self.status_label.setText("Журнал пуст — нечего копировать")
            return
        clipboard = QApplication.clipboard()
        if clipboard is None:
            self._show_operation_error("Буфер обмена недоступен")
            return
        clipboard.setText(redacted_text)
        self.status_label.setText("ОБЕЗЛИЧЕННАЯ ДИАГНОСТИКА СКОПИРОВАНА")

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
                    "Автообновления доступны только в установленной версии приложения."
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
        self.status_label.setText("Не удалось обновить список сохранений.")
        self.status_label.setToolTip(technical_details(message))

    def open_local(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Открыть сохранение S.T.A.L.K.E.R.",
            "",
            "Сохранения S.T.A.L.K.E.R. (*.sav *.scop *.scs);;Все файлы (*)",
        )
        if filename:
            self._start_inspect(Path(filename))

    def _start_inspect(self, path: Path) -> None:
        path = Path(path).expanduser()
        if self._inspect_thread is not None and self._inspect_thread.isRunning():
            return

        # Keep the library visible while the worker runs. The editor is only
        # entered after a successful, fully inspected snapshot is published.
        self._show_library()
        self._pending_path = path
        self.open_button.setEnabled(False)
        self.library_view.set_analysis_state(f"АНАЛИЗ: {path.name}…")
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
                "Диагностика доступна; запись и редактирование отключены.",
            )
            self.analysis_ready.emit(snapshot)
            return
        self._render_snapshot(snapshot)
        self._show_editor()
        self.analysis_ready.emit(snapshot)

    def _on_analysis_failed(self, message: str) -> None:
        kind = classify_analysis_error(message)
        copy = ERROR_COPY[kind]
        self.status_label.setText(copy.title)
        self.library_view.set_analysis_error(copy.message, details=message)
        self.error_label.setText(copy.message)
        self.error_label.setToolTip(format_error_details(present_error(kind, message)))
        self.error_label.setVisible(True)
        self._show_library()
        self._show_copy_error(kind, message, self.open_local)
        self.analysis_failed.emit(message)

    def _on_inspect_thread_finished(self) -> None:
        self.open_button.setEnabled(True)
        self._inspect_thread = None
        self._inspect_worker = None

    def _render_snapshot(self, snapshot: LocalSnapshot, *, show_editor: bool = True) -> None:
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
            f"ДЕНЬГИ  {human_money(info.money) if info.money is not None else '—'} ₽"
        )
        self.library_view.set_snapshot(snapshot)
        self.character_view.set_snapshot(snapshot)
        self.character_view.set_state(
            self.staged_faction_relations,
            self.staged_player_faction,
        )
        self.library_view.status_label.setText(
            f"{snapshot.path.name} · {human_size(len(snapshot.data))} · файл проверен"
        )
        self.library_view.status_label.setToolTip(
            technical_details(f"SHA-256: {info.sha256}\nCRC: {'PASS' if info.crc_ok else 'FAIL'}")
        )
        self.status_label.setText("Редактор готов")
        self.error_label.clear()
        self.error_label.setVisible(False)
        self.edit_actions_enabled = True
        self._update_action_buttons()
        if show_editor:
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
            self.editor_view.money_clear_button.setEnabled(False)
            return
        assert info.money is not None
        effective = self.staged_money if self.staged_money is not None else info.money
        self.editor_view.set_money_draft(effective)
        self.editor_view.money_spin.setEnabled(True)
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
                "Редактирование баланса недоступно для этого сохранения."
            )
            return
        if info.money is None or info.money_anchor_count != 1:
            self.editor_view.show_capability_message(
                "Это значение нельзя изменить."
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
        self._invalidate_preview("изменилось значение баланса")
        self.status_label.setText(
            f"Подготовлено {len(self.staged_counts) + int(self.staged_money is not None)} изменений. "
            "Оригинальный файл пока не изменён."
        )

    def _clear_money(self) -> None:
        self.staged_money = None
        if self.snapshot is not None:
            self._render_money(self.snapshot.info)
            self._render_changes()
            self._invalidate_preview("черновик баланса очищен")
        self.status_label.setText("Баланс возвращён к исходному значению. Оригинальный файл пока не изменён.")

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
                "Редактирование количества недоступно для этого сохранения."
            )
            return
        item = self._find_inventory_item(handle)
        if item is None:
            self.editor_view.show_capability_message(
                "Предмет больше не найден в открытом сохранении."
            )
            return
        value = int(new_count)
        if not (1 <= value <= item.count_max):
            self.editor_view.show_capability_message(
                f"Новое количество отклонено: допустимый диапазон 1..{item.count_max}"
            )
            return
        if not item.editable_count:
            self.editor_view.show_capability_message("Это значение нельзя изменить.")
            return
        if value == item.count:
            self.staged_counts.pop(item.handle, None)
        else:
            self.staged_counts[item.handle] = value
        self._render_changes()
        self._invalidate_preview("изменилось значение количества")
        self.status_label.setText(
            f"Подготовлено {len(self.staged_counts)} изменений. Оригинальный файл пока не изменён."
        )

    def _stage_item_add(self, item_key: str, quantity: int) -> None:
        if self.snapshot is None:
            return
        if not self.snapshot.capabilities.add_items:
            self.editor_view.show_capability_message(
                "Добавление предметов недоступно для этого сохранения."
            )
            return
        catalog = self.snapshot.catalog
        definition = catalog.resolve(item_key) if catalog is not None else None
        if definition is None:
            self.editor_view.show_capability_message(
                "Этот предмет отсутствует в каталоге и не может быть добавлен."
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
                f"Для {definition.display_name or 'этого предмета'} допустимо не больше "
                f"{definition.max_stack} за одну группу."
            )
            return
        self.staged_adds[item_key] = value
        self._render_changes()
        self._invalidate_preview("изменилось добавление предмета")
        self.status_label.setText(
            f"Подготовлено добавление предмета: {definition.display_name or 'предмет'} × {value}. "
            "Оригинальный файл пока не изменён."
        )

    def _stage_item_remove(self, handle: int) -> None:
        if self.snapshot is None:
            return
        if not self.snapshot.capabilities.remove_items:
            self.editor_view.show_capability_message(
                "Удаление предметов недоступно для этого сохранения."
            )
            return
        item = self._find_inventory_item(handle)
        if item is None:
            self.editor_view.show_capability_message(
                "Предмет больше не найден в открытом сохранении."
            )
            return
        if not item.remove_editable:
            self.editor_view.show_capability_message(
                "Этот предмет нельзя удалить в текущем сохранении."
            )
            return
        handle = int(handle)
        if handle in self.staged_detach:
            self.staged_detach.pop(handle, None)
            message = f"Удаление отменено для {item.display_name or 'предмета'}"
        else:
            self.staged_detach[handle] = True
            self.staged_counts.pop(handle, None)
            message = f"Подготовлено удаление: {item.display_name or 'предмет'}"
        self._render_changes()
        self._invalidate_preview("изменился список удалений")
        self.status_label.setText(f"{message}. Оригинальный файл пока не изменён.")

    def _stage_item_durability(self, handle: int, condition: float) -> None:
        if self.snapshot is None:
            return
        if not self.snapshot.capabilities.edit_durability:
            self.editor_view.show_capability_message(
                "Редактирование состояния недоступно для этого сохранения."
            )
            return
        item = self._find_inventory_item(handle)
        if item is None or not item.condition_editable or item.condition is None:
            self.editor_view.show_capability_message(
                "Это значение нельзя изменить."
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
        self._invalidate_preview("изменилось значение прочности")
        self.status_label.setText(
            f"Подготовлено изменение состояния: {item.display_name or 'предмет'}. "
            "Оригинальный файл пока не изменён."
        )

    def _clear_item_durability(self, handle: int) -> None:
        if self.snapshot is None:
            return
        item = self._find_inventory_item(handle)
        if item is None:
            return
        self.staged_durability.pop(item.handle, None)
        self._render_changes()
        self._invalidate_preview("черновик прочности очищен")
        self.status_label.setText(
            f"Изменение состояния отменено для {item.display_name or 'предмета'}. "
            "Оригинальный файл пока не изменён."
        )

    def _finish_equipment_repair(self, result: RepairStageResult, *, action: str) -> None:
        for handle, value in result.changes:
            self.staged_durability[int(handle)] = float(value)
        for skipped in result.skipped:
            if skipped.reason.startswith("no-op:"):
                self.staged_durability.pop(skipped.handle, None)
        self._render_changes()
        self._invalidate_preview("изменилось оборудование")
        parts = [f"{action}: подготовлено {len(result.changes)}"]
        if result.skipped:
            parts.append(f"пропущено {len(result.skipped)}")
        details = "; ".join(
            f"0x{item.handle:04X}: {item.reason}" for item in result.skipped[:3]
        )
        self.editor_view.show_capability_message(". ".join(parts))
        if details:
            self.editor_view.detail_view.module_status.setToolTip(technical_details(details))
        self.status_label.setText("Изменения снаряжения подготовлены. Оригинальный файл пока не изменён.")

    def _stage_equipment_repair(self, handle: int, percentage: float) -> None:
        result = stage_repair(self.equipment_rows, (int(handle),), percentage)
        self._finish_equipment_repair(result, action="Ремонт предмета")

    def _stage_equipment_bulk_repair(self, filter_name: str, percentage: float) -> None:
        result = stage_bulk_repair(self.equipment_rows, filter_name, percentage)  # type: ignore[arg-type]
        self._finish_equipment_repair(result, action="Массовый ремонт")

    def _reset_equipment_repair(self, handle: int) -> None:
        self.staged_durability.pop(int(handle), None)
        self._render_changes()
        self._invalidate_preview("черновик прочности оборудования очищен")
        self.status_label.setText("Изменения состояния отменены. Оригинальный файл пока не изменён.")

    def _stage_item_upgrades(self, handle: int, values: object) -> None:
        if self.snapshot is None:
            return
        capabilities = self.snapshot.capabilities
        if not capabilities.edit_upgrades:
            self.editor_view.show_capability_message(
                "Данные о модификациях недоступны для этого сохранения."
            )
            return
        item = self._find_inventory_item(handle)
        if item is None or item.upgrades is None or not item.upgrades_editable:
            self.editor_view.show_capability_message(
                "Это значение нельзя изменить."
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
        self._invalidate_preview("изменился список улучшений")
        self.status_label.setText(
            f"Подготовлены изменения модификаций: {item.display_name or 'предмет'}. "
            "Оригинальный файл пока не изменён."
        )

    def _clear_item_upgrades(self, handle: int) -> None:
        if self.snapshot is None:
            return
        item = self._find_inventory_item(handle)
        if item is None:
            return
        self.staged_upgrades.pop(item.handle, None)
        self._render_changes()
        self._invalidate_preview("черновик улучшений очищен")
        self.status_label.setText(
            f"Изменения модификаций отменены для {item.display_name or 'предмета'}. "
            "Оригинальный файл пока не изменён."
        )

    def _stage_item_placement(self, handle: int, placement_type: str, slot_id: object) -> None:
        if self.snapshot is None:
            return
        if not self.snapshot.capabilities.edit_placement:
            self.editor_view.show_capability_message(
                "Изменение размещения недоступно для этого сохранения."
            )
            return
        item = self._find_inventory_item(handle)
        if item is None or not item.placement_editable or item.placement_type is None:
            self.editor_view.show_capability_message(
                "Это значение нельзя изменить."
            )
            return
        normalized_type = str(placement_type).strip().casefold()
        if slot_id is None:
            normalized_slot = None
        elif isinstance(slot_id, int):
            normalized_slot = slot_id
        else:
            self.editor_view.show_capability_message("Это значение нельзя изменить.")
            return
        current = (item.placement_type, item.placement_slot if item.placement_type == "slot" else None)
        desired = (normalized_type, normalized_slot)
        if desired == current:
            self.staged_placements.pop(item.handle, None)
            message = f"Размещение сброшено для {item.display_name or 'предмета'}"
        else:
            self.staged_placements[item.handle] = desired
            message = f"Подготовлено изменение размещения: {item.display_name or 'предмет'}"
        self._render_changes()
        self._invalidate_preview("изменилось размещение предмета")
        self.status_label.setText(f"{message}. Оригинальный файл пока не изменён.")

    def _clear_item_placement(self, handle: int) -> None:
        if self.snapshot is None:
            return
        item = self._find_inventory_item(handle)
        if item is None:
            return
        self.staged_placements.pop(item.handle, None)
        self._render_changes()
        self._invalidate_preview("черновик размещения очищен")
        self.status_label.setText(
            f"Размещение сброшено для {item.display_name or 'предмета'}. "
            "Оригинальный файл пока не изменён."
        )

    def _stage_faction_relation(self, key: str, goodwill: int) -> None:
        if self.snapshot is None:
            return
        capabilities = self.snapshot.capabilities
        if not capabilities.edit_relations or not self.snapshot.info.faction_relations_editable:
            self.character_view.status_label.setText("Отношения доступны только для просмотра.")
            return
        game_catalog = self.snapshot.game_catalog
        if game_catalog is None:
            self.character_view.status_label.setText("Данные о группировках недоступны для этого сохранения.")
            return
        try:
            faction = game_catalog.factions.resolve(key)
        except CatalogLookupError as exc:
            self.character_view.status_label.setText("Не удалось найти эту группировку.")
            self.character_view.status_label.setToolTip(technical_details(exc))
            return
        if faction.numeric_id is None:
            self.character_view.status_label.setText("Изменение недоступно для этой группировки.")
            return
        minimum = game_catalog.factions.goodwill_min
        maximum = game_catalog.factions.goodwill_max
        if minimum is None or maximum is None or not minimum <= goodwill <= maximum:
            self.character_view.status_label.setText(
                f"Отношение должно быть от {minimum} до {maximum}."
            )
            return
        current = dict(self.snapshot.info.faction_relations).get(faction.numeric_id, 0)
        if int(goodwill) == current:
            self.staged_faction_relations.pop(key, None)
        else:
            self.staged_faction_relations[key] = int(goodwill)
        self.character_view.set_state(self.staged_faction_relations, self.staged_player_faction)
        self._render_changes()
        self._invalidate_preview("изменилось отношение группировки")
        self.status_label.setText(
            f"Подготовлено изменение отношения: {faction.display_name or 'группировка'}. "
            "Оригинальный файл пока не изменён."
        )

    def _stage_player_faction(self, key: str) -> None:
        if self.snapshot is None:
            return
        capabilities = self.snapshot.capabilities
        if not capabilities.edit_player_faction or not self.snapshot.info.player_faction_editable:
            self.character_view.status_label.setText("Принадлежность игрока доступна только для просмотра.")
            return
        game_catalog = self.snapshot.game_catalog
        if game_catalog is None:
            self.character_view.status_label.setText("Данные о группировках недоступны для этого сохранения.")
            return
        try:
            faction = game_catalog.factions.resolve(key)
        except CatalogLookupError as exc:
            self.character_view.status_label.setText("Не удалось найти эту группировку.")
            self.character_view.status_label.setToolTip(technical_details(exc))
            return
        if faction.numeric_id is None:
            self.character_view.status_label.setText("Изменение недоступно для этой группировки.")
            return
        self.staged_player_faction = None if faction.numeric_id == self.snapshot.info.player_faction_index else key
        self.character_view.set_state(self.staged_faction_relations, self.staged_player_faction)
        self._render_changes()
        self._invalidate_preview("изменилось принадлежность игрока")
        self.status_label.setText("Подготовлено изменение группировки. Оригинальный файл пока не изменён.")

    def _clear_selected_stack(self, handle: int) -> None:
        self.staged_counts.pop(int(handle), None)
        self._render_changes()
        self._invalidate_preview("черновик количества очищен")
        self.status_label.setText(
            f"Подготовлено {len(self.staged_counts)} изменений. Оригинальный файл пока не изменён."
        )

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
        self.status_label.setText("Изменения предмета отменены. Оригинальный файл пока не изменён.")

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
        self._invalidate_preview("все черновики очищены")
        self.status_label.setText("Все изменения отменены. Оригинальный файл пока не изменён.")

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
        kind = classify_operation_error(message)
        actions = {
            "source_changed": lambda: self._start_inspect(Path(self.snapshot.path))
            if self.snapshot is not None
            else self.open_local(),
            "backup": self._show_settings,
            "verify": self._show_reference_editor,
            "cloud_unavailable": self.cloud_controller.start_connect,
            "cloud_write_unavailable": self.cloud_controller.start_connect,
            "cloud_uncertain": self.cloud_controller.reconcile_remote,
        }
        self.status_label.setText(ERROR_COPY[kind].title)
        self._show_copy_error(kind, message, actions.get(kind, self._show_reference_editor))
        if hasattr(self, "history_reference_view"):
            self.history_reference_view.set_error(message)
        if (self.snapshot is not None and self.snapshot.source_kind == "cloud") or kind.startswith("cloud_"):
            self.cloud_controller.set_error(message)
        self.operation_failed.emit(message)

    def _show_copy_error(
        self,
        kind: ErrorKind,
        details: str,
        action,
    ) -> None:
        """Show short copy with a working primary action and opt-in diagnostics."""

        copy = present_error(kind, details)
        self.error_label.setText(copy.message)
        detail_text = format_error_details(copy)
        self.error_label.setToolTip(detail_text)
        self.error_label.setVisible(True)
        previous = self._error_dialog
        if previous is not None:
            previous.close()
        dialog = QMessageBox(self)
        dialog.setObjectName("uxErrorDialog")
        icon = {
            "info": QMessageBox.Icon.Information,
            "success": QMessageBox.Icon.Information,
            "warning": QMessageBox.Icon.Warning,
            "error": QMessageBox.Icon.Critical,
        }[copy.severity]
        dialog.setIcon(icon)
        dialog.setText(copy.title)
        dialog.setInformativeText(copy.message)
        primary = dialog.addButton(copy.primary_action, QMessageBox.ButtonRole.AcceptRole)
        details_button = None
        if copy.secondary_action is not None and copy.technical_details is not None:
            details_button = dialog.addButton(
                copy.secondary_action,
                QMessageBox.ButtonRole.ActionRole,
            )

        def clicked(button) -> None:
            if button is primary:
                action()
            elif button is details_button:
                self._show_technical_details(detail_text)

        dialog.buttonClicked.connect(clicked)
        dialog.finished.connect(
            lambda _result, current=dialog: setattr(self, "_error_dialog", None)
            if self._error_dialog is current
            else None
        )
        self._error_dialog = dialog
        dialog.open()

    def _show_technical_details(self, details: str) -> None:
        if self._details_dialog is not None:
            self._details_dialog.close()
        dialog = QMessageBox(self)
        dialog.setObjectName("technicalDetailsDialog")
        dialog.setIcon(QMessageBox.Icon.Information)
        dialog.setWindowTitle("Технические детали")
        dialog.setText("Технические детали")
        dialog.setInformativeText(details)
        dialog.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        dialog.setStandardButtons(QMessageBox.StandardButton.Close)
        dialog.finished.connect(
            lambda _result, current=dialog: setattr(self, "_details_dialog", None)
            if self._details_dialog is current
            else None
        )
        self._details_dialog = dialog
        dialog.open()

    def _invalidate_preview(self, reason: str) -> None:
        self.prepared_edit = None
        self.editor_view.show_capability_message(
            "Проверка перед сохранением сброшена. Проверь изменения ещё раз."
        )
        self.editor_view.detail_view.module_status.setToolTip(technical_details(reason))
        self.cloud_controller.set_prepared(None)
        if hasattr(self, "cloud_reference_view"):
            self.cloud_reference_view.set_prepared(None)
        self._update_action_buttons()

    def _build_edit_plan(self) -> EditPlan:
        if self.snapshot is None:
            raise SaveError("Сначала проанализируй сейв")
        if not self._has_staged_changes():
            raise SaveError("Нет подготовленных изменений")
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
            self._on_operation_failed("Черновик изменился во время проверки; повтори проверку")
            return
        self.prepared_edit = prepared
        self.editor_view.show_capability_message("Проверка готова. Можно сохранить изменения.")
        self.editor_view.detail_view.module_status.setToolTip(
            technical_details(f"SHA-256 результата: {prepared.output_sha256}")
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
        value = str(message).casefold()
        if "восстановление" in value:
            display = "Восстанавливаем резервную копию…"
        elif "backup" in value or "sha" in value or "round-trip" in value:
            display = "Проверяем изменения и резервную копию…"
        else:
            display = "Сохраняем изменения…"
        self.status_label.setText(display)
        self.status_label.setToolTip(technical_details(message))
        if hasattr(self, "history_reference_view"):
            self.history_reference_view.set_progress(message)

    def _on_operation_failed(self, message: str) -> None:
        # A failed step must not leave a queued one-click apply behind.
        self._pending_apply_path = None
        self._pending_cloud_upload = False
        self._pending_replace = False
        if "SHA256" in message or "Источник изменился" in message:
            self.prepared_edit = None
            self.editor_view.show_capability_message("Файл изменился после открытия.")
            self.editor_view.detail_view.module_status.setToolTip(technical_details(message))
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
            "Сохранить копию сохранения",
            str(Path(self.snapshot.path).with_name(f"{Path(self.snapshot.path).stem}-edited.sav")),
            "Сохранения S.T.A.L.K.E.R. (*.sav *.scop *.scs);;Все файлы (*)",
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
                "Изменения будут проверены и загружены в выбранное сохранение Steam Cloud.\n\n"
                "Перед записью автоматически создаются резервная и дополнительная копии. "
                "Продолжить?"
            )
        else:
            title = "Сохранить изменения?"
            message = (
                f"Изменения будут записаны в открытое сохранение:\n{self.snapshot.path}\n\n"
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
            self._show_operation_error("Сначала открой сохранение.")
            return
        if not self._has_staged_changes() and self.prepared_edit is None:
            self._show_operation_error("Нет подготовленных изменений")
            return
        if not review_confirmed and not self._confirm_save():
            self.status_label.setText("Сохранение отменено")
            return
        if self.snapshot.source_kind == "cloud":
            if self.cloud_controller.reconciliation_pending:
                self._show_operation_error(
                    "Cloud upload заблокирован до reconciliation; обнови состояние Cloud"
                )
                return
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
            self.status_label.setText("Сохранение записано. Проверяем результат…")
        else:
            self.status_label.setText("Проверенная копия сохранена. Проверяем результат…")
        self._post_save_receipt = receipt
        self._start_post_save_reinspect(Path(receipt.output_path))
        self.backup_controller.refresh()
        self._record_recent_activity(
            "Локальное сохранение",
            str(receipt.output_path),
            "Сохранение проверено",
        )
        self._show_save_result(receipt)
        self.apply_ready.emit(receipt)

    def _start_post_save_reinspect(self, path: Path) -> None:
        """Read the bytes that were actually published before returning to edit mode."""

        if self._post_save_reinspect_thread is not None and self._post_save_reinspect_thread.isRunning():
            return
        catalog_root = self.settings.catalog_root("stalker2")
        worker = InspectWorker(
            self.service,
            Path(path).expanduser(),
            self,
            catalog_roots=(catalog_root,) if catalog_root is not None else (),
        )
        worker.completed.connect(self._on_post_save_reinspect_ready)
        worker.failed.connect(self._on_post_save_reinspect_failed)
        worker.finished.connect(self._on_post_save_reinspect_finished)
        worker.finished.connect(worker.deleteLater)
        self._post_save_reinspect_thread = worker
        self.status_label.setText("Проверяем сохранённый файл…")
        worker.start()

    def _on_post_save_reinspect_ready(self, snapshot: LocalSnapshot) -> None:
        self._render_snapshot(snapshot, show_editor=False)
        self.status_label.setText("Сохранение проверено. Подготовлено 0 изменений.")
        self._enable_verified_result_editor(
            "Сохранение записано и проверено. Резервная копия создана."
        )
        self._record_recent_activity(
            "Повторная проверка локального слота",
            str(snapshot.path),
            "Сохранение проверено",
        )

    def _on_post_save_reinspect_failed(self, message: str) -> None:
        # The local receipt already proves the writer's read-back. Keep the
        # previous snapshot rather than presenting it as the newly written one,
        # and make the reconciliation failure visible on the library surface.
        display = ERROR_COPY["post_save_check"].message
        self.status_label.setText("Не удалось повторно проверить сохранение")
        self.save_result_view.set_editor_ready(
            False,
            "Сохранение записано, но повторная проверка не завершилась; редактор пока заблокирован.",
        )
        self.app_shell.set_footer_actions((("Esc", "К библиотеке", self._show_library),))
        self.error_label.setText(display)
        self.error_label.setToolTip(technical_details(message))
        self.error_label.setVisible(True)
        self.library_view.set_analysis_error(display, details=message)
        path = (
            Path(self._post_save_receipt.output_path)
            if self._post_save_receipt is not None
            else (Path(self.snapshot.path) if self.snapshot is not None else None)
        )
        self._show_copy_error(
            "post_save_check",
            message,
            lambda: self._start_inspect(path) if path is not None else self.open_local(),
        )

    def _on_post_save_reinspect_finished(self) -> None:
        self._post_save_reinspect_thread = None

    def changeEvent(self, event: QEvent) -> None:  # noqa: N802 - Qt override
        """Keep custom chrome state truthful after OS or header state changes."""

        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange and hasattr(self, "app_shell"):
            self.app_shell._sync_maximize_button()

    def _start_restore(self, record, output_path: Path) -> None:
        if self._operation_thread is not None and self._operation_thread.isRunning():
            return
        if getattr(record, "status", None) != "verified":
            self._show_operation_error("Резервная копия не прошла проверку")
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
        self.status_label.setText("Резервная копия восстановлена и проверена.")
        self._record_recent_activity(
            "Восстановление копии",
            str(receipt.output_path),
            "Резервная копия проверена",
        )
        self.restore_ready.emit(receipt)

    def _start_restore_in_place(self, record) -> None:
        if self._operation_thread is not None and self._operation_thread.isRunning():
            return
        if getattr(record, "status", None) != "verified":
            self._show_operation_error("Резервная копия не прошла проверку")
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
        self.status_label.setText("Исходное сохранение восстановлено и проверено.")
        self._record_recent_activity(
            "Восстановление исходного слота",
            str(receipt.output_path),
            "Сохранение проверено",
        )
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
            f"Сохранение из Steam Cloud открыто: {snapshot.name}. Выбери изменения для сохранения."
        )
        self._record_recent_activity(
            "Cloud скачивание",
            snapshot.name,
            "Сохранение проверено" if snapshot.info.crc_ok else "Файл повреждён или изменён",
        )

    def _start_cloud_upload(self) -> None:
        if self.prepared_edit is None:
            self._show_operation_error("Сначала проверь сохранение из Steam Cloud.")
            return
        self.status_label.setText("Подготовка сохранения в Steam Cloud…")
        self.cloud_controller.start_upload()

    def _on_cloud_upload_ready(self, receipt) -> None:
        self.status_label.setText(
            "Запись проверена. Обновляем список Steam Cloud…"
            if receipt.status == "verified"
            else ERROR_COPY["cloud_uncertain"].title
        )
        self._update_action_buttons()
        self._post_save_receipt = receipt
        self._show_save_result(receipt, cloud_reconciliation=True)
        self._record_recent_activity(
            "Cloud запись",
            receipt.remote_path,
            "Запись успешно проверена"
            if receipt.status == "verified"
            else "Steam не подтвердил запись",
        )
        self.apply_ready.emit(receipt)

    def _on_cloud_reconciliation_ready(self, snapshot: CloudSnapshot) -> None:
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
        self._render_snapshot(local_snapshot, show_editor=False)
        self.status_label.setText("Запись успешно проверена. Подготовлено 0 изменений.")
        self._enable_verified_result_editor(
            "Сохранение записано и проверено. Резервная копия создана."
        )
        self._record_recent_activity(
            "Cloud запись и проверка",
            snapshot.name,
            "Запись успешно проверена",
        )

    def _on_cloud_reconciliation_failed(self, message: str) -> None:
        self.save_result_view.set_editor_ready(
            False,
            ERROR_COPY["cloud_uncertain"].message,
        )
        self.app_shell.set_footer_actions((("Esc", "К библиотеке", self._show_library),))
        self.status_label.setText(ERROR_COPY["cloud_uncertain"].title)
        self._show_copy_error(
            "cloud_uncertain",
            message,
            self.cloud_controller.reconcile_remote,
        )

    def _on_cloud_operation_failed(self, message: str) -> None:
        self._show_operation_error(message)

    def _on_cloud_progress(self, message: str) -> None:
        value = str(message).casefold()
        display = (
            "Проверяем сохранение в Steam Cloud…"
            if any(term in value for term in ("sha", "read", "persist", "reconcil"))
            else "Выполняется действие в Steam Cloud…"
        )
        self.status_label.setText(display)
        self.status_label.setToolTip(technical_details(message))

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
                "Сохранение ещё выполняется. Дождись его завершения перед закрытием."
            )
            event.ignore()
            return
        if self.cloud_controller.is_busy and not self.cloud_controller.stop_worker(30_000):
            self.status_label.setText(
                "Действие в Steam Cloud ещё выполняется. Дождись его завершения перед закрытием."
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
                    "Проверка обновлений ещё выполняется. Дождись её завершения перед закрытием."
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
