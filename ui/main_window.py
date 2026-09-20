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

from PySide6.QtCore import Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from editor.capabilities import FormatCapabilities
from editor.catalog import CatalogLookupError, GameCatalog, ItemCatalog
from editor.equipment import EquipmentItem, equipment_items, equipment_support_for_release
from editor.equipment_edits import RepairStageResult, stage_bulk_repair, stage_repair
from editor.formats import FormatDetectionError
from editor.models import EditPlan, PreparedEdit, SourceRef
from editor.platforms import backup_dirs, installed_releases
from editor.service import EditorService
from editor.settings import PathSettings, load_settings, search_paths_for_settings
from editor.updater import InstallationInfo, UpdateCheckResult, UpdateClient, detect_installation
from save_format import SaveError, SaveInfo

from .backups_view import BackupView, RestoreWorker
from .changes_view import ChangesView
from .cloud_view import CloudSnapshot, CloudView
from .equipment_view import EquipmentView
from .faction_view import FactionView
from .inventory_view import InventoryView
from .launcher_view import LauncherView, _slot_family
from .operation_worker import OperationWorker
from .save_slots_view import (
    GAME_TITLES,
    RELEASE_IDS,
    SaveSlot,
    SaveSlotsView,
    SlotDiscoveryFn,
    discover_save_slots,
)
from .settings_view import SettingsView
from .support_dialog import SupportDialog
from .theme import apply_theme
from .update_dialog import UpdateCheckWorker, UpdateDialog


def _default_s2_capabilities() -> FormatCapabilities:
    return FormatCapabilities(
        read_inventory=True,
        edit_money=True,
        edit_stacks=True,
        equipment=equipment_support_for_release("stalker2"),
        experimental_fields=frozenset({"edit_money"}),
    )


def _human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size} B"


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

    def __init__(self, service: EditorService, path: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service = service
        self.path = path

    def run(self) -> None:
        try:
            data = self.path.read_bytes()
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
        self.edit_actions_enabled = False
        self._inspect_thread: QThread | None = None
        self._inspect_worker: InspectWorker | None = None
        self._pending_path: Path | None = None
        self._operation_thread: QThread | None = None
        self._operation_kind: str | None = None
        self._cloud_busy = False
        self._support_dialog: SupportDialog | None = None
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

        self.mode_stack = QStackedWidget()
        self.mode_stack.setObjectName("modeStack")
        self.launcher_view = LauncherView()
        self.launcher_view.set_installed_families(
            game.game_id for game in installed_releases()
        )
        self.mode_stack.addWidget(self.launcher_view)

        workbench = QWidget()
        workbench.setObjectName("workbench")
        self.workbench = workbench
        layout = QVBoxLayout(workbench)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        title_bar = QFrame()
        title_bar.setObjectName("titleBar")
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(18, 12, 18, 12)
        title_layout.setSpacing(10)
        self.app_title = QLabel("S.T.A.L.K.E.R. Save Editor")
        self.app_title.setObjectName("appTitle")
        title_layout.addWidget(self.app_title)
        self.version_badge = QLabel(f"v{_version_text()}")
        self.version_badge.setObjectName("versionBadge")
        title_layout.addWidget(self.version_badge)
        title_layout.addStretch(1)
        ui_hint = QLabel("ZONE / SAVE WORKBENCH")
        ui_hint.setObjectName("sidebarStatus")
        title_layout.addWidget(ui_hint)
        self.launcher_button = QPushButton("← ЗОНА")
        self.launcher_button.setObjectName("launcherBackButton")
        self.launcher_button.setToolTip("Вернуться к библиотеке игр и сохранений")
        self.launcher_button.clicked.connect(self._show_launcher)
        title_layout.addWidget(self.launcher_button)
        self.update_button = QPushButton("Обновления")
        self.update_button.setObjectName("updateButton")
        self.update_button.setToolTip("Проверить новую версию")
        self.update_button.clicked.connect(lambda: self.check_for_updates(manual=True))
        title_layout.addWidget(self.update_button)
        self.support_button = QPushButton("♡ Support project")
        self.support_button.setObjectName("supportButton")
        self.support_button.setToolTip("Поддержать проект")
        self.support_button.clicked.connect(self._show_support_dialog)
        title_layout.addWidget(self.support_button)
        layout.addWidget(title_bar)

        meta_bar = QFrame()
        meta_bar.setObjectName("metaBar")
        meta_layout = QHBoxLayout(meta_bar)
        meta_layout.setContentsMargins(18, 9, 18, 9)
        meta_layout.setSpacing(10)
        self.file_source_badge = QLabel("ФАЙЛ НЕ ВЫБРАН")
        self.file_source_badge.setObjectName("sourceBadge")
        meta_layout.addWidget(self.file_source_badge)
        meta_text = QVBoxLayout()
        meta_text.setSpacing(1)
        self.meta_filename = QLabel("Сейв не выбран")
        self.meta_filename.setObjectName("metaFilename")
        meta_text.addWidget(self.meta_filename)
        self.meta_details = QLabel("Открой локальный сейв для проверки формата и структуры")
        self.meta_details.setObjectName("metaDetails")
        self.meta_details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        meta_text.addWidget(self.meta_details)
        meta_layout.addLayout(meta_text, 1)
        self.integrity_badge = QLabel("CRC-32: —")
        self.integrity_badge.setObjectName("integrityBadge")
        meta_layout.addWidget(self.integrity_badge)
        self.format_badge = QLabel("ФОРМАТ: —")
        self.format_badge.setObjectName("formatBadge")
        meta_layout.addWidget(self.format_badge)
        self.open_button = QPushButton("Открыть сейв…")
        self.open_button.setObjectName("openButton")
        self.open_button.clicked.connect(self.open_local)
        meta_layout.addWidget(self.open_button)
        layout.addWidget(meta_bar)

        # Retain the original public label for small integrations and tests;
        # the shell presents the same facts as structured metadata above.
        self.source_label = QLabel("Сейв не выбран")
        self.source_label.setObjectName("sourceLabel")
        self.source_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.source_label.setVisible(False)

        self.status_label = QLabel("Готово к локальному анализу")
        self.status_label.setObjectName("statusLabel")
        status_layout = QHBoxLayout()
        status_layout.setContentsMargins(18, 8, 18, 8)
        status_layout.addWidget(self.status_label)
        layout.addLayout(status_layout)
        self.error_label = QLabel("")
        self.error_label.setObjectName("errorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.setVisible(False)
        error_layout = QHBoxLayout()
        error_layout.setContentsMargins(18, 0, 18, 8)
        error_layout.addWidget(self.error_label)
        layout.addLayout(error_layout)

        body = QHBoxLayout()
        body.setContentsMargins(18, 0, 18, 12)
        body.setSpacing(12)

        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(218)
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(10, 12, 10, 10)
        sidebar_layout.setSpacing(5)
        sidebar_heading = QLabel("РАЗДЕЛЫ")
        sidebar_heading.setObjectName("sidebarHeading")
        sidebar_layout.addWidget(sidebar_heading)

        content_panel = QFrame()
        content_panel.setObjectName("contentPanel")
        content_layout = QVBoxLayout(content_panel)
        content_layout.setContentsMargins(12, 8, 12, 10)
        content_layout.setSpacing(0)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("contentTabs")
        # Stack-style tabs (a vertical column of cards) get one predictable
        # scroll each so their content never squashes or overlaps on a short
        # window.  Table-centric tabs manage their own scrolling and are added
        # directly to avoid a nested scroll area.
        self.tabs.addTab(self._scrollable(self._build_overview_tab()), "Обзор")
        self.tabs.addTab(self._build_inventory_tab(), "Инвентарь")
        self.tabs.addTab(self._build_changes_tab(), "Изменения")
        self.tabs.addTab(self._build_backups_tab(), "Резервные копии")
        self.tabs.addTab(self._scrollable(self._build_cloud_tab()), "Steam Cloud")
        self.tabs.addTab(self._build_slots_tab(), "Найденные сейвы")
        self.tabs.addTab(self._scrollable(self._build_settings_tab()), "Настройки")
        self.tabs.addTab(self._build_equipment_tab(), "Оборудование")
        self.tabs.tabBar().setVisible(False)
        content_layout.addWidget(self.tabs, 1)

        self.nav_buttons: list[QPushButton] = []
        self.nav_labels: tuple[str, ...] = (
            "Обзор",
            "Инвентарь",
            "Изменения",
            "Резервные копии",
            "Steam Cloud",
            "Найденные сейвы",
            "Настройки",
            "Оборудование",
        )
        for index, label in enumerate(self.nav_labels):
            button = QPushButton(label)
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.setAutoExclusive(True)
            button.clicked.connect(lambda _checked=False, i=index: self._select_tab(i))
            sidebar_layout.addWidget(button)
            self.nav_buttons.append(button)
        sidebar_layout.addStretch(1)
        self.decoder_status = QLabel("CORE: READY\nCRC / SHA / BACKUP включены")
        self.decoder_status.setObjectName("sidebarStatus")
        self.decoder_status.setWordWrap(True)
        sidebar_layout.addWidget(self.decoder_status)

        body.addWidget(self.sidebar)
        body.addWidget(content_panel, 1)
        layout.addLayout(body, 1)

        actions = QHBoxLayout()
        actions.setContentsMargins(18, 0, 18, 14)
        actions.addStretch(1)
        self.preview_button = QPushButton("Предпросмотр")
        self.preview_button.setEnabled(False)
        self.preview_button.setToolTip("Подготовить immutable preview из staged edits")
        self.preview_button.clicked.connect(self._start_preview)
        actions.addWidget(self.preview_button)
        self.save_copy_button = QPushButton("Сохранить")
        self.save_copy_button.setEnabled(False)
        self.save_copy_button.setToolTip(
            "Проверяет и сохраняет одним нажатием; бэкап исходного файла делается сам"
        )
        self.save_copy_button.clicked.connect(self._save_one_click)
        actions.addWidget(self.save_copy_button)
        layout.addLayout(actions)

        self.tabs.currentChanged.connect(self._sync_nav_state)
        self._sync_nav_state(0)

        self.setTabOrder(self.open_button, self.nav_buttons[0])
        self.setTabOrder(self.tabs, self.preview_button)
        self.setTabOrder(self.preview_button, self.save_copy_button)

        self.mode_stack.addWidget(workbench)
        root_layout.addWidget(self.mode_stack, 1)
        self.launcher_view.import_requested.connect(self.open_local)
        self.launcher_view.open_requested.connect(self._start_inspect)
        self.launcher_view.cloud_requested.connect(self._show_cloud)
        self.launcher_view.refresh_requested.connect(self.save_slots_view.refresh)
        self.mode_stack.setCurrentWidget(self.launcher_view)

    def _show_launcher(self) -> None:
        """Show the read-only library without discarding the current snapshot."""

        if hasattr(self, "mode_stack"):
            self.mode_stack.setCurrentWidget(self.launcher_view)

    def _show_workbench(self) -> None:
        if hasattr(self, "mode_stack"):
            self.mode_stack.setCurrentWidget(self.workbench)

    def _show_cloud(self) -> None:
        """Enter the remote-save flow without requiring a local game save."""

        self._show_workbench()
        self.tabs.setCurrentIndex(self.nav_labels.index("Steam Cloud"))

    def _select_tab(self, index: int) -> None:
        if 0 <= index < self.tabs.count():
            self.tabs.setCurrentIndex(index)

    def _show_support_dialog(self) -> None:
        if self._support_dialog is not None and self._support_dialog.isVisible():
            self._support_dialog.raise_()
            self._support_dialog.activateWindow()
            return
        dialog = SupportDialog(self)
        self._support_dialog = dialog
        dialog.finished.connect(lambda _result: self._clear_support_dialog(dialog))
        dialog.open()

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
        kind = "package" if installation.kind == "package" else "portable"
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

    def _sync_nav_state(self, index: int) -> None:
        for button_index, button in enumerate(getattr(self, "nav_buttons", [])):
            button.setChecked(button_index == index)

    def _sync_nav_counters(self) -> None:
        """Show inventory and staged-change counts next to the section names.

        The visual reference carries a badge per section.  Only counts the
        parser or the staging state actually knows are shown; a section with
        nothing to count keeps its bare name.
        """

        buttons = getattr(self, "nav_buttons", [])
        if not buttons:
            return
        inventory = len(self.snapshot.info.inventory) if self.snapshot is not None else None
        staged = (
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
        equipment_count = len(getattr(self, "equipment_rows", ())) if inventory is not None else 0
        equipment = equipment_count or None
        counters: dict[int, int | None] = {
            1: inventory,
            2: staged or None,
            7: equipment,
        }
        for index, button in enumerate(buttons):
            count = counters.get(index)
            label = self.nav_labels[index]
            button.setText(label if count is None else f"{label}  ·  {count}")

    def _build_overview_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(10)

        layout.addWidget(self._build_quick_switcher())

        cards = QFrame()
        cards_layout = QGridLayout(cards)
        cards_layout.setContentsMargins(0, 0, 0, 0)
        cards_layout.setHorizontalSpacing(8)
        cards_layout.setVerticalSpacing(8)

        def add_card(column: int, caption: str, initial: str) -> QLabel:
            card = QFrame()
            card.setObjectName("metricCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(12, 9, 12, 9)
            card_layout.setSpacing(4)
            caption_label = QLabel(caption)
            caption_label.setObjectName("metricCaption")
            card_layout.addWidget(caption_label)
            value_label = QLabel(initial)
            value_label.setObjectName("metricValue")
            value_label.setWordWrap(True)
            value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            card_layout.addWidget(value_label)
            cards_layout.setColumnStretch(column, 1)
            cards_layout.addWidget(card, 0, column)
            return value_label

        self.location_card_value = add_card(0, "Локация", "—")
        self.time_card_value = add_card(1, "Время", "—")
        self.money_card_value = add_card(2, "Деньги", "—")
        self.inventory_card_value = add_card(3, "Предметы", "—")
        layout.addWidget(cards)

        # A word-wrapped QLabel inside a QFormLayout reports a height hint for a
        # single line, so the summary used to render clipped and overlapping.
        # Plain vertical layouts with expanding labels lay wrapped text out
        # correctly.
        details = QFrame()
        details.setObjectName("metricCard")
        details_layout = QVBoxLayout(details)
        details_layout.setContentsMargins(12, 10, 12, 10)
        details_layout.setSpacing(6)
        summary_caption = QLabel("Сводка")
        summary_caption.setObjectName("metricCaption")
        details_layout.addWidget(summary_caption)
        self.summary_label = QLabel("Открой локальный сейв для проверки формата и структуры.")
        self.summary_label.setWordWrap(True)
        self.summary_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        details_layout.addWidget(self.summary_label)
        self.support_label = QLabel("Редактирование отключено до успешного анализа.")
        self.support_label.setWordWrap(True)
        details_layout.addWidget(self.support_label)
        layout.addWidget(details)

        money_box = QGroupBox("Баланс (staged до preview)")
        money_layout = QVBoxLayout(money_box)
        money_layout.setSpacing(6)
        self.money_status_label = QLabel("Баланс не определён")
        self.money_status_label.setWordWrap(True)
        money_layout.addWidget(self.money_status_label)
        money_row = QHBoxLayout()
        money_row.addWidget(QLabel("Новая сумма"))
        self.money_spin = QSpinBox()
        self.money_spin.setRange(0, 2_000_000_000)
        self.money_spin.setEnabled(False)
        self.money_spin.valueChanged.connect(self._on_money_value_changed)
        money_row.addWidget(self.money_spin, 1)
        self.money_stage_button = QPushButton("Застейджить баланс")
        self.money_stage_button.setEnabled(False)
        self.money_stage_button.clicked.connect(self._stage_money)
        money_row.addWidget(self.money_stage_button)
        self.money_clear_button = QPushButton("Очистить")
        self.money_clear_button.setEnabled(False)
        self.money_clear_button.clicked.connect(self._clear_money)
        money_row.addWidget(self.money_clear_button)
        money_layout.addLayout(money_row)
        layout.addWidget(money_box)

        self.faction_view = FactionView(self)
        self.faction_view.relation_stage_requested.connect(self._stage_faction_relation)
        self.faction_view.player_faction_stage_requested.connect(
            self._stage_player_faction
        )
        layout.addWidget(self.faction_view)

        metadata_box = QGroupBox("Технические метаданные контейнера")
        metadata_layout = QVBoxLayout(metadata_box)
        metadata_layout.setContentsMargins(10, 10, 10, 10)
        self.metadata_table = QTableWidget(0, 3)
        self.metadata_table.setObjectName("metadataTable")
        self.metadata_table.setHorizontalHeaderLabels(
            ["Параметр", "Значение в сохранении", "Статус"]
        )
        self.metadata_table.verticalHeader().setVisible(False)
        self.metadata_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.metadata_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.metadata_table.setAlternatingRowColors(False)
        header = self.metadata_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(False)
        # The page already scrolls (the tab is wrapped in a QScrollArea), so the
        # table shows every row without a competing inner scrollbar.
        self.metadata_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.metadata_table.setSizeAdjustPolicy(
            QTableWidget.SizeAdjustPolicy.AdjustToContents
        )
        metadata_layout.addWidget(self.metadata_table)
        layout.addWidget(metadata_box)
        layout.addStretch(1)
        self._render_metadata_rows(None)
        return tab

    # Rows are parser-backed only.  The visual reference shows GVAS fields this
    # parser cannot prove; inventing them would make an unverified claim look
    # confirmed, so unknown values stay out of the table entirely.
    def _metadata_rows(self, snapshot: LocalSnapshot | None) -> tuple[tuple[str, str, str], ...]:
        if snapshot is None:
            return (
                ("Файл", "—", "не открыт"),
                ("CRC-32", "—", "не проверен"),
                ("SHA-256", "—", "не вычислен"),
            )
        info = snapshot.info
        money = "неизвестно" if info.money is None else str(info.money)
        money_status = (
            "редактируется"
            if (
                snapshot.capabilities.edit_money
                and info.money is not None
                and info.money_anchor_count == 1
            )
            else f"read-only (anchor × {info.money_anchor_count})"
        )
        unresolved = len(info.unresolved_handles)
        common_rows = (
            ("Файл", snapshot.path.name, _human_size(len(snapshot.data))),
            ("Формат", snapshot.format_id, snapshot.format_title),
            (
                "Релиз",
                snapshot.release_id or snapshot.format_id,
                f"edition={snapshot.edition or 'unknown'}",
            ),
            ("SHA-256", info.sha256, "исходный снимок"),
            (
                "Размер контейнера",
                f"{_human_size(info.packed_size)} → {_human_size(info.unpacked_size)}",
                "Kraken распакован" if info.crc_present else "LZO1X распакован",
            ),
            ("Баланс купонов", money, money_status),
        )
        if info.crc_present:
            rows = list(common_rows[:2])
            rows.append(
                (
                    "CRC-32",
                    f"{info.stored_crc32:08X}",
                    "PASS" if info.crc_ok else f"FAIL (вычислено {info.computed_crc32:08X})",
                )
            )
            rows.extend(common_rows[2:])
            rows.extend(
                (
                    ("Owned handles", str(len(info.owned_handles)), "прочитано"),
                    (
                        "Grid handles",
                        f"{len({item.handle for item in info.inventory})} / {info.grid_handle_count}",
                        "разобрано / объявлено",
                    ),
                    ("Grid cells", str(info.grid_cell_count), "прочитано"),
                    ("Объекты инвентаря", str(len(info.inventory)), "в сетке"),
                    ("Orphan handles", str(len(info.orphans)), "вне сетки"),
                    (
                        "Unresolved handles",
                        str(unresolved),
                        "read-only" if unresolved else "нет",
                    ),
                    (
                        "UE5 GVAS schema",
                        "не разобрана",
                        "контейнер валиден, схема не подтверждена",
                    ),
                )
            )
            return tuple(rows)
        return (*common_rows,
            ("Actor objects", f"{len(info.inventory)} / {len(info.owned_handles)}", "прочитано по parent actor"),
            ("Grid cells", "0", "в X-Ray не используется"),
            ("Целостность", info.integrity_name, "проверен контейнер и LZO payload"),
            ("X-Ray outer version", str(info.container_version), "подтверждён"),
            ("Actor spawn version", str(info.format_version), "подтверждён"),
            ("Время игры", "неизвестно" if info.game_time is None else str(info.game_time), "прочитано"),
            ("Уровень", info.level_name or "неизвестно", "прочитано из SPAWN" if info.level_name else "не найден"),
            ("Unresolved handles", str(len(info.unresolved_handles)), "read-only" if info.unresolved_handles else "нет"),
        )

    def _render_metadata_rows(self, snapshot: LocalSnapshot | None) -> None:
        rows = self._metadata_rows(snapshot)
        self.metadata_table.setRowCount(len(rows))
        for index, (name, value, status) in enumerate(rows):
            for column, text in enumerate((name, value, status)):
                item = QTableWidgetItem(text)
                item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                self.metadata_table.setItem(index, column, item)
        self._fit_table_height(self.metadata_table)

    @staticmethod
    def _fit_table_height(table: QTableWidget) -> None:
        table.resizeRowsToContents()
        height = table.horizontalHeader().height() + 2 * table.frameWidth()
        for row in range(table.rowCount()):
            height += table.rowHeight(row)
        table.setMinimumHeight(height)
        table.setMaximumHeight(height)

    def _build_quick_switcher(self) -> QWidget:
        """Compact game+save picker inside the workbench for on-the-fly switching."""

        self._switcher_slots: tuple[SaveSlot, ...] = ()
        frame = QFrame()
        frame.setObjectName("metricCard")
        row = QHBoxLayout(frame)
        row.setContentsMargins(12, 8, 12, 8)
        row.setSpacing(8)
        row.addWidget(QLabel("Игра"))
        self.switcher_game_combo = QComboBox()
        self.switcher_game_combo.setMinimumWidth(200)
        self.switcher_game_combo.currentIndexChanged.connect(self._on_switcher_game_changed)
        row.addWidget(self.switcher_game_combo)
        row.addWidget(QLabel("Сейв"))
        self.switcher_save_combo = QComboBox()
        self.switcher_save_combo.setMinimumWidth(260)
        row.addWidget(self.switcher_save_combo, 1)
        self.switcher_open_button = QPushButton("Открыть")
        self.switcher_open_button.setEnabled(False)
        self.switcher_open_button.clicked.connect(self._open_switcher_selection)
        row.addWidget(self.switcher_open_button)
        return frame

    def _populate_switcher(self, discovery: object) -> None:
        slots = tuple(getattr(discovery, "slots", ()) or ())
        self._switcher_slots = slots
        families: list[str] = []
        for slot in slots:
            family = _slot_family(slot)
            if family and family not in families:
                families.append(family)
        self.switcher_game_combo.blockSignals(True)
        self.switcher_game_combo.clear()
        for family in families:
            self.switcher_game_combo.addItem(GAME_TITLES.get(family, family), family)
        self.switcher_game_combo.blockSignals(False)
        selected_family = self.snapshot.format_id if self.snapshot is not None else None
        selected_index = (
            self.switcher_game_combo.findData(selected_family)
            if selected_family is not None
            else -1
        )
        if selected_index < 0 and families:
            selected_index = 0
        if selected_index >= 0:
            self.switcher_game_combo.setCurrentIndex(selected_index)
        self._on_switcher_game_changed()

    def _sync_switcher_to_snapshot(self, snapshot: LocalSnapshot) -> None:
        """Keep the quick picker aligned with the file currently in the editor."""

        index = self.switcher_game_combo.findData(snapshot.format_id)
        if index < 0:
            return
        self.switcher_game_combo.blockSignals(True)
        self.switcher_game_combo.setCurrentIndex(index)
        self.switcher_game_combo.blockSignals(False)
        self._on_switcher_game_changed(index)

    def _on_switcher_game_changed(self, _index: int = -1) -> None:
        family = self.switcher_game_combo.currentData()
        self.switcher_save_combo.clear()
        for slot in self._switcher_slots:
            if _slot_family(slot) == family:
                self.switcher_save_combo.addItem(Path(slot.path).name, str(slot.path))
        self.switcher_open_button.setEnabled(self.switcher_save_combo.count() > 0)

    def _open_switcher_selection(self) -> None:
        path = self.switcher_save_combo.currentData()
        if path:
            self._start_inspect(Path(path))

    def _build_inventory_tab(self) -> QWidget:
        self.inventory_view = InventoryView(self)
        self.inventory_view.stage_requested.connect(self._stage_stack_change)
        self.inventory_view.clear_selected_requested.connect(self._clear_selected_stack)
        self.inventory_view.clear_all_requested.connect(self._clear_all_stacks)
        self.inventory_view.add_requested.connect(self._stage_item_add)
        self.inventory_view.remove_selected_requested.connect(self._stage_item_remove)
        self.inventory_view.durability_stage_requested.connect(self._stage_item_durability)
        self.inventory_view.durability_clear_requested.connect(self._clear_item_durability)
        self.inventory_view.upgrades_stage_requested.connect(self._stage_item_upgrades)
        self.inventory_view.upgrades_clear_requested.connect(self._clear_item_upgrades)
        self.inventory_view.placement_stage_requested.connect(self._stage_item_placement)
        self.inventory_view.placement_clear_requested.connect(self._clear_item_placement)
        # Keep the old attribute available to small integrations while the
        # actual view now uses a stable-handle QAbstractTableModel.
        self.inventory_table = self.inventory_view.table
        self.inventory_model = self.inventory_view.model
        return self.inventory_view

    def _build_equipment_tab(self) -> QWidget:
        self.equipment_view = EquipmentView(self)
        self.equipment_view.repair_requested.connect(self._stage_equipment_repair)
        self.equipment_view.reset_requested.connect(self._reset_equipment_repair)
        self.equipment_view.bulk_repair_requested.connect(self._stage_equipment_bulk_repair)
        return self.equipment_view

    def _build_changes_tab(self) -> QWidget:
        self.changes_view = ChangesView(self)
        self.changes_view.preview_requested.connect(self._start_preview)
        self.changes_view.apply_requested.connect(self._choose_and_start_apply)
        self.changes_view.replace_requested.connect(self._confirm_and_start_replace)
        self.changes_view.choose_output_requested.connect(self._choose_output)
        return self.changes_view

    def _build_backups_tab(self) -> QWidget:
        self.backups_view = BackupView(backup_dirs=backup_dirs(), parent=self)
        self.backups_view.restore_requested.connect(self._start_restore)
        self.backups_view.restore_in_place_requested.connect(self._start_restore_in_place)
        self.backups_view.folder_open_requested.connect(self._open_backup_folder)
        self.backups_view.refresh()
        return self.backups_view

    def _build_cloud_tab(self) -> QWidget:
        self.cloud_view = CloudView(self.service, backup_dir=backup_dirs()[0], parent=self)
        self.cloud_view.snapshot_ready.connect(self._on_cloud_snapshot_ready)
        self.cloud_view.upload_ready.connect(self._on_cloud_upload_ready)
        self.cloud_view.operation_failed.connect(self._on_cloud_operation_failed)
        self.cloud_view.operation_progress.connect(self._on_cloud_progress)
        self.cloud_view.busy_changed.connect(self._on_cloud_busy)
        return self.cloud_view

    def _build_slots_tab(self) -> QWidget:
        self.save_slots_view = SaveSlotsView(self.slot_discovery, parent=self)
        self.save_slots_view.open_requested.connect(self._start_inspect)
        self.save_slots_view.discovery_failed.connect(self._on_slot_discovery_failed)
        self.save_slots_view.discovery_ready.connect(self.launcher_view.set_discovery)
        self.save_slots_view.discovery_ready.connect(self._populate_switcher)
        self.save_slots_view.discovery_failed.connect(self.launcher_view.set_error)
        # Discovery is asynchronous and read-only.  No path is opened as a
        # side effect; the user still has to double-click a row or use the
        # manual file picker above.
        self.save_slots_view.refresh()
        return self.save_slots_view

    def _discover_slots(self):
        return discover_save_slots(
            release_ids=RELEASE_IDS,
            search_paths_fn=lambda release_id: search_paths_for_settings(
                release_id, self.settings
            )
        )

    def _build_settings_tab(self) -> QWidget:
        self.settings_view = SettingsView(
            self.settings,
            settings_path=self.settings_path,
            load_error=self.settings_load.error,
            parent=self,
        )
        self.settings_view.settings_changed.connect(self._on_settings_changed)
        return self.settings_view

    def _on_settings_changed(self, settings: PathSettings) -> None:
        self.settings = settings
        self.status_label.setText("Настройки обновлены; обновляю список сохранений…")
        self.save_slots_view.refresh()

    def _on_slot_discovery_failed(self, message: str) -> None:
        self.status_label.setText(f"Поиск слотов не выполнен: {message}")

    @staticmethod
    def _scrollable(content: QWidget) -> QScrollArea:
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        area.setWidget(content)
        return area

    @staticmethod
    def _placeholder(text: str) -> QWidget:
        box = QGroupBox()
        layout = QVBoxLayout(box)
        label = QLabel(text)
        label.setWordWrap(True)
        layout.addWidget(label)
        layout.addStretch(1)
        return box

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

        # Selecting a library row or importing a file enters the workbench
        # immediately, so a failed/unsupported file is reported on-screen
        # instead of leaving the user on a stale launcher state.
        self._show_workbench()
        self._pending_path = path
        self.open_button.setEnabled(False)
        if self.snapshot is None:
            self.file_source_badge.setText("ЧТЕНИЕ ФАЙЛА")
            self.meta_filename.setText(path.name)
            self.meta_details.setText("Проверка формата, SHA и структуры…")
            self.integrity_badge.setText("CRC-32: …")
            self.format_badge.setText("ФОРМАТ: анализ…")
        self.status_label.setText(f"Анализ: {path.name}…")
        self.error_label.clear()
        self.error_label.setVisible(False)

        thread = InspectWorker(self.service, path, self)
        thread.completed.connect(self._on_analysis_ready)
        thread.failed.connect(self._on_analysis_failed)
        thread.finished.connect(self._on_inspect_thread_finished)
        thread.finished.connect(thread.deleteLater)
        self._inspect_thread = thread
        self._inspect_worker = thread
        thread.start()

    def _on_analysis_ready(self, snapshot: LocalSnapshot) -> None:
        self.snapshot = snapshot
        self._render_snapshot(snapshot)
        self._show_workbench()
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
        # Keep the render helper safe for direct synthetic/UI tests as well as
        # the signal path, where _on_analysis_ready already assigned it.
        self.snapshot = snapshot
        self._sync_switcher_to_snapshot(snapshot)
        info = snapshot.info
        self.staged_counts.clear()
        self.staged_money = None
        self.staged_adds.clear()
        self.staged_detach.clear()
        self.staged_durability.clear()
        self.staged_faction_relations.clear()
        self.staged_player_faction = None
        self.staged_upgrades.clear()
        self.staged_placements.clear()
        self.equipment_rows = ()
        self.prepared_edit = None
        self.cloud_view.set_prepared(None)
        if snapshot.source_kind == "cloud":
            self.save_copy_button.setText("Сохранить и загрузить в облако")
            self.save_copy_button.setToolTip(
                "Проверить staged-правки и загрузить их в выбранный Steam Cloud slot"
            )
        else:
            self.save_copy_button.setText("Сохранить")
            self.save_copy_button.setToolTip(
                "Проверяет и сохраняет одним нажатием; бэкап исходного файла делается сам"
            )
        crc = "OK" if info.crc_ok else "FAIL"
        money = "unknown" if info.money is None else str(info.money)
        source_label = "Steam Cloud" if snapshot.source_kind == "cloud" else "локальный"
        self.source_label.setText(
            f"Сейв: {snapshot.path.name} • {source_label} • Формат {snapshot.format_id} • "
            f"{_human_size(len(snapshot.data))} • SHA {info.sha256[:12]}…"
        )
        self.file_source_badge.setText(
            "STEAM CLOUD" if snapshot.source_kind == "cloud" else "ЛОКАЛЬНЫЙ ФАЙЛ"
        )
        self.meta_filename.setText(snapshot.path.name)
        self.meta_details.setText(
            f"{_human_size(len(snapshot.data))} • SHA {info.sha256[:12]}…"
        )
        self.integrity_badge.setText(
            f"CRC-32: {'PASS' if info.crc_ok else 'FAIL'}"
            if info.crc_present
            else f"{info.integrity_name}: OK"
        )
        self.format_badge.setText(
            "UE5 GVAS: НЕ ПОДТВЕРЖДЁН"
            if info.crc_present
            else f"ФОРМАТ: {snapshot.format_title}"
        )
        gvas_hint = (
            "UE5 GVAS-схема S.T.A.L.K.E.R. 2 в этом релизе не разбирается — "
            "поле недоступно (не потеряно)."
        )
        if info.level_name:
            self.location_card_value.setText(info.level_name)
            self.location_card_value.setToolTip("Уровень прочитан из сейва")
        else:
            self.location_card_value.setText("—")
            self.location_card_value.setToolTip(gvas_hint)
        if info.game_time is None:
            self.time_card_value.setText("—")
            self.time_card_value.setToolTip(gvas_hint)
        else:
            self.time_card_value.setText(str(info.game_time))
            self.time_card_value.setToolTip("Игровое время прочитано из сейва")
        self.money_card_value.setText(money)
        self.inventory_card_value.setText(str(len(info.inventory)))
        integrity = f"CRC: {crc}" if info.crc_present else f"{info.integrity_name}: OK"
        self.summary_label.setText(
            f"{integrity}    Money: {money}    Inventory: {len(info.inventory)}    "
            f"Grid cells: {info.grid_cell_count}    Orphans: {len(info.orphans)}"
        )
        warnings = " ".join(info.warnings)
        support = (
            "Поддержанные данные: CRC, money, inventory snapshot. "
            if info.crc_present
            else "Поддержанные данные: X-Ray container, money, actor inventory snapshot. "
        ) + "Неизвестные handles остаются read-only."
        if snapshot.capabilities.is_experimental("edit_money"):
            support += (
                " Изменение денег экспериментальное: round-trip редактора проверен, "
                "загрузка и пересохранение игрой ещё не подтверждены."
            )
        equipment_support = snapshot.capabilities.equipment
        if equipment_support is not None:
            support += (
                " Оборудование: "
                f"прочность {equipment_support.durability.maturity}, "
                f"улучшения {equipment_support.upgrades.maturity}, "
                f"позиция {equipment_support.placement.maturity}."
            )
        if warnings:
            support += f" Предупреждения: {warnings}"
        self.support_label.setText(support)
        self._render_metadata_rows(snapshot)
        self._sync_nav_counters()
        self._render_money(info)
        self._render_inventory(info)
        self._render_equipment(info)
        self._render_factions(info)
        self.changes_view.set_staged(
            info,
            self.staged_money,
            self.staged_counts,
            self.staged_adds,
            self.staged_detach,
            self.staged_durability,
            self.staged_faction_relations,
            snapshot.game_catalog.factions if snapshot.game_catalog is not None else None,
            staged_player_faction=self.staged_player_faction,
            staged_upgrades=self.staged_upgrades,
            staged_placements=self.staged_placements,
            upgrade_catalog=(
                snapshot.game_catalog.upgrades
                if snapshot.game_catalog is not None
                else None
            ),
            capabilities=snapshot.capabilities,
        )
        self.changes_view.invalidate_preview("изменений ещё нет")
        self.status_label.setText("Анализ завершён; snapshot готов")
        self.error_label.clear()
        self.error_label.setVisible(False)
        self.edit_actions_enabled = True
        self._update_action_buttons()
        self._show_workbench()

    def _render_inventory(self, info: SaveInfo) -> None:
        self.inventory_view.set_items(info.inventory)
        capabilities = self.snapshot.capabilities if self.snapshot is not None else None
        self.inventory_view.set_editing_enabled(
            capabilities is None or capabilities.edit_stacks,
            reason=(
                "Только чтение: формат не разрешает редактирование количества"
                if capabilities is not None and not capabilities.edit_stacks
                else None
            ),
        )
        self.inventory_view.set_staged_counts(self.staged_counts)
        catalog = self.snapshot.catalog if self.snapshot is not None else None
        can_add = bool(
            capabilities is not None
            and capabilities.add_items
            and catalog is not None
        )
        self.inventory_view.set_catalog(
            catalog,
            enabled=can_add,
            reason=(
                "Добавление доступно только для официального каталога выбранной игры"
                if capabilities is not None and capabilities.add_items and catalog is None
                else "Формат не разрешает добавление предметов"
                if capabilities is not None and not capabilities.add_items
                else None
            ),
        )
        self.inventory_view.set_remove_enabled(
            bool(capabilities is not None and capabilities.remove_items),
            reason=(
                "Формат не разрешает удаление предметов"
                if capabilities is not None and not capabilities.remove_items
                else None
            ),
        )
        self.inventory_view.set_removed_handles(self.staged_detach)
        can_edit_durability = bool(
            capabilities is not None and capabilities.edit_durability
        )
        self.inventory_view.set_durability_enabled(
            can_edit_durability,
            reason=(
                "Только чтение: правка прочности не подтверждена для этого релиза"
                if capabilities is not None and not capabilities.edit_durability
                else (
                    "Экспериментально: S2 STATE f32 armor anchor; backup обязателен"
                    if self.snapshot is not None
                    and self.snapshot.format_id == "stalker2"
                    else "Экспериментально: STATE/UPDATE/client-data mirrors; backup обязателен"
                )
                if capabilities is not None and capabilities.is_experimental("edit_durability")
                else None
            ),
        )
        self.inventory_view.set_staged_durability(self.staged_durability)
        game_catalog = self.snapshot.game_catalog if self.snapshot is not None else None
        can_edit_upgrades = bool(
            capabilities is not None
            and capabilities.edit_upgrades
            and game_catalog is not None
            and game_catalog.upgrades is not None
        )
        self.inventory_view.set_upgrades_enabled(
            can_edit_upgrades,
            game_catalog.upgrades if game_catalog is not None else None,
            reason=(
                "Добавление/удаление улучшений доступно только для официального каталога ЧС/ЗП"
                if capabilities is not None
                and capabilities.edit_upgrades
                and (game_catalog is None or game_catalog.upgrades is None)
                else "Только чтение: улучшения не подтверждены для этого релиза"
                if capabilities is not None and not capabilities.edit_upgrades
                else "Экспериментально: STATE m_upgrades vector; backup обязателен"
                if capabilities is not None and capabilities.is_experimental("edit_upgrades")
                else None
            ),
        )
        self.inventory_view.set_staged_upgrades(self.staged_upgrades)
        can_edit_placement = bool(
            capabilities is not None and capabilities.edit_placement
        )
        self.inventory_view.set_placement_enabled(
            can_edit_placement,
            reason=(
                "Экспериментально: client-data SInvItemPlace; backup обязателен"
                if capabilities is not None
                and capabilities.is_experimental("edit_placement")
                else "Только чтение: правка позиции не подтверждена для этого релиза"
                if capabilities is not None and not capabilities.edit_placement
                else None
            ),
        )
        self.inventory_view.set_staged_placements(self.staged_placements)
        self.inventory_card_value.setText(str(len(info.inventory)))

    def _render_equipment(self, info: SaveInfo) -> None:
        snapshot = self.snapshot
        if snapshot is None:
            self.equipment_rows = ()
            self.equipment_view.set_release(None)
            self.equipment_view.set_items(())
            return
        release_id = snapshot.release_id or snapshot.format_id
        self.equipment_view.set_release(release_id)
        self.equipment_rows = equipment_items(
            info.inventory,
            release_id=release_id,
            catalog=snapshot.catalog,
        )
        self.equipment_view.set_items(self.equipment_rows)
        self.equipment_view.set_catalog(snapshot.catalog)
        self.equipment_view.set_staged_durability(self.staged_durability)

    def _render_factions(self, info: SaveInfo) -> None:
        capabilities = self.snapshot.capabilities if self.snapshot is not None else None
        catalog = (
            self.snapshot.game_catalog.factions
            if self.snapshot is not None and self.snapshot.game_catalog is not None
            else None
        )
        self.faction_view.set_catalog(
            catalog,
            relation_enabled=bool(
                capabilities is not None
                and capabilities.edit_relations
                and info.faction_relations_editable
            ),
            player_enabled=bool(
                capabilities is not None
                and capabilities.edit_player_faction
                and info.player_faction_editable
            ),
            reason=(
                "Экспериментально: Relation registry X-Ray; backup обязателен"
                if capabilities is not None
                and capabilities.edit_relations
                and info.faction_relations_editable
                and capabilities.is_experimental("edit_relations")
                else "Только чтение: actor relation row не подтверждён"
                if capabilities is not None
                and capabilities.edit_relations
                and not info.faction_relations_editable
                else "Только чтение: отношения не подтверждены для этого релиза"
                if capabilities is not None and not capabilities.edit_relations
                else None
            ),
        )
        self.faction_view.set_state(
            info,
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
            self.money_card_value.setText(
                "неизвестно" if info.money is None else str(info.money)
            )
            reason = (
                "формат не разрешает редактирование денег"
                if self.snapshot is not None and not self.snapshot.capabilities.edit_money
                else f"wallet anchor найден {info.money_anchor_count} раз(а)"
            )
            self.money_status_label.setText(f"Только чтение: {reason}")
            self.money_spin.setEnabled(False)
            self.money_stage_button.setEnabled(False)
            self.money_clear_button.setEnabled(False)
            return
        assert info.money is not None
        effective = self.staged_money if self.staged_money is not None else info.money
        self.money_card_value.setText(str(effective))
        suffix = " • экспериментально" if self.snapshot and self.snapshot.capabilities.is_experimental("edit_money") else ""
        self.money_status_label.setText(f"{info.money} → {effective}{suffix}")
        self.money_spin.blockSignals(True)
        self.money_spin.setEnabled(True)
        self.money_spin.setValue(effective)
        self.money_spin.blockSignals(False)
        self.money_stage_button.setEnabled(True)
        self.money_clear_button.setEnabled(self.staged_money is not None)

    def _on_money_value_changed(self, _value: int) -> None:
        if self.snapshot is None or self.snapshot.info.money is None:
            return
        suffix = (
            " • экспериментально"
            if self.snapshot.capabilities.is_experimental("edit_money")
            else ""
        )
        self.money_status_label.setText(
            f"{self.snapshot.info.money} → {self.money_spin.value()}{suffix}"
        )

    def _stage_money(self) -> None:
        if self.snapshot is None:
            return
        info = self.snapshot.info
        value = self.money_spin.value()
        if not self.snapshot.capabilities.edit_money:
            self.money_status_label.setText("Только чтение: формат не разрешает редактирование денег")
            return
        if info.money is None or info.money_anchor_count != 1:
            self.money_status_label.setText("Только чтение: wallet anchor не подтверждён")
            return
        if not (0 <= value <= 2_000_000_000):
            self.money_status_label.setText("Сумма отклонена: допустим диапазон 0..2000000000")
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
        self.status_label.setText("Staged balance очищен; bytes сейва не изменены")

    def _find_inventory_item(self, handle: int):
        if self.snapshot is None:
            return None
        return next(
            (item for item in self.snapshot.info.inventory if item.handle == int(handle)),
            None,
        )

    def _stage_stack_change(self, handle: int, new_count: int) -> None:
        if self.snapshot is not None and not self.snapshot.capabilities.edit_stacks:
            self.inventory_view.show_editability_message(
                "Только чтение: формат не разрешает редактирование stack count"
            )
            return
        item = self._find_inventory_item(handle)
        if item is None:
            self.inventory_view.show_editability_message(
                f"Только чтение: handle 0x{int(handle):08X} не найден в текущем snapshot"
            )
            return
        max_count = item.count_max
        if not (1 <= int(new_count) <= max_count):
            self.inventory_view.show_editability_message(
                f"Новое количество отклонено: допустимый диапазон 1..{max_count}"
            )
            return
        if not item.editable_count:
            reason = (
                "count не извлечён"
                if item.count is None
                else (
                "count=1"
                if item.count <= 1
                else f"неподтверждённый kind={item.kind_code}"
                )
            )
            self.inventory_view.show_editability_message(f"Только чтение: {reason}")
            return

        value = int(new_count)
        if value == item.count:
            self.staged_counts.pop(item.handle, None)
        else:
            self.staged_counts[item.handle] = value
        self.inventory_view.set_staged_counts(self.staged_counts)
        self._render_changes()
        self._invalidate_preview("изменилось staged значение stack")
        self.status_label.setText(
            f"Staged: {len(self.staged_counts)}; bytes сейва не изменены — нужен preview"
        )

    def _stage_item_add(self, item_key: str, quantity: int) -> None:
        if self.snapshot is None:
            return
        if not self.snapshot.capabilities.add_items:
            self.inventory_view.show_editability_message(
                "Только чтение: формат не разрешает добавление предметов"
            )
            return
        catalog = self.snapshot.catalog
        definition = catalog.resolve(item_key) if catalog is not None else None
        if definition is None:
            self.inventory_view.show_editability_message(
                f"Предмет {item_key!r} отсутствует в официальном каталоге"
            )
            return
        value = int(quantity)
        if value < 1 or value > 65535:
            self.inventory_view.show_editability_message(
                "Количество нового предмета должно быть в диапазоне 1..65535"
            )
            return
        if (
            definition.serialization_family == "ammo"
            and definition.max_stack is not None
            and value > definition.max_stack
        ):
            self.inventory_view.show_editability_message(
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
            self.inventory_view.show_editability_message(
                "Только чтение: формат не разрешает удаление предметов"
            )
            return
        item = self._find_inventory_item(handle)
        if item is None:
            self.inventory_view.show_editability_message(
                f"Только чтение: handle 0x{int(handle):04X} не найден"
            )
            return
        if not item.remove_editable:
            self.inventory_view.show_editability_message(
                item.remove_reason
                or "Только чтение: удаление этого объекта заблокировано"
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
        self.inventory_view.set_staged_counts(self.staged_counts)
        self.inventory_view.set_removed_handles(self.staged_detach)
        self._render_changes()
        self._invalidate_preview("изменился staged список удалений")
        self.status_label.setText(f"{message}; bytes сейва не изменены — нужен preview")

    def _stage_item_durability(self, handle: int, condition: float) -> None:
        if self.snapshot is None:
            return
        if not self.snapshot.capabilities.edit_durability:
            self.inventory_view.show_editability_message(
                "Только чтение: формат не разрешает редактирование прочности"
            )
            return
        item = self._find_inventory_item(handle)
        if item is None or not item.condition_editable or item.condition is None:
            self.inventory_view.show_editability_message(
                f"Только чтение: handle 0x{int(handle):04X} не имеет подтверждённого condition"
            )
            return
        value = float(condition)
        if not math.isfinite(value) or not 0.0 <= value <= 1.0:
            self.inventory_view.show_editability_message(
                "Прочность должна быть в диапазоне 0…100%"
            )
            return
        if math.isclose(value, item.condition, rel_tol=0.0, abs_tol=1e-6):
            self.staged_durability.pop(item.handle, None)
        else:
            self.staged_durability[item.handle] = value
        self.inventory_view.set_staged_durability(self.staged_durability)
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
        self.inventory_view.set_staged_durability(self.staged_durability)
        self._render_changes()
        self._invalidate_preview("staged прочность очищена")
        self.status_label.setText(
            f"Прочность очищена для {item.type_key}; bytes сейва не изменены"
        )

    def _finish_equipment_repair(
        self,
        result: RepairStageResult,
        *,
        action: str,
    ) -> None:
        for handle, value in result.changes:
            self.staged_durability[int(handle)] = float(value)
        for skipped in result.skipped:
            if skipped.reason.startswith("no-op:"):
                self.staged_durability.pop(skipped.handle, None)
        self.equipment_view.set_staged_durability(self.staged_durability)
        self.inventory_view.set_staged_durability(self.staged_durability)
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
        self.equipment_view.show_repair_result(". ".join(parts))
        self.status_label.setText(
            "Оборудование staged; bytes сейва не изменены — нужен preview"
        )

    def _stage_equipment_repair(self, handle: int, percentage: float) -> None:
        result = stage_repair(self.equipment_rows, (int(handle),), percentage)
        self._finish_equipment_repair(result, action="Ремонт предмета")

    def _stage_equipment_bulk_repair(self, filter_name: str, percentage: float) -> None:
        result = stage_bulk_repair(
            self.equipment_rows,
            filter_name,  # type: ignore[arg-type]
            percentage,
        )
        self._finish_equipment_repair(result, action=f"Массовый ремонт ({filter_name})")

    def _reset_equipment_repair(self, handle: int) -> None:
        self.staged_durability.pop(int(handle), None)
        self.equipment_view.set_staged_durability(self.staged_durability)
        self.inventory_view.set_staged_durability(self.staged_durability)
        self._render_changes()
        self._invalidate_preview("staged прочность оборудования очищена")
        self.status_label.setText("Staged прочность очищена; bytes сейва не изменены")

    def _stage_item_upgrades(self, handle: int, values: object) -> None:
        if self.snapshot is None:
            return
        capabilities = self.snapshot.capabilities
        if not capabilities.edit_upgrades:
            self.inventory_view.show_editability_message(
                "Только чтение: правка улучшений не подтверждена для этого релиза"
            )
            return
        item = self._find_inventory_item(handle)
        if item is None or item.upgrades is None or not item.upgrades_editable:
            self.inventory_view.show_editability_message(
                f"Только чтение: handle 0x{int(handle):08X} не имеет подтверждённого upgrades vector"
            )
            return
        if not isinstance(values, (tuple, list)):
            self.inventory_view.show_editability_message("Список улучшений отклонён")
            return
        desired = tuple(str(value) for value in values)
        if desired == item.upgrades:
            self.staged_upgrades.pop(item.handle, None)
        else:
            self.staged_upgrades[item.handle] = desired
        self.inventory_view.set_staged_upgrades(self.staged_upgrades)
        self._render_changes()
        self._invalidate_preview("изменился staged список улучшений")
        self.status_label.setText(
            f"Улучшения staged для {item.type_key}; bytes сейва не изменены — нужен preview"
        )

    def _clear_item_upgrades(self, handle: int) -> None:
        if self.snapshot is None:
            return
        item = self._find_inventory_item(handle)
        if item is None:
            return
        self.staged_upgrades.pop(item.handle, None)
        self.inventory_view.set_staged_upgrades(self.staged_upgrades)
        self._render_changes()
        self._invalidate_preview("staged улучшения очищены")
        self.status_label.setText(
            f"Улучшения очищены для {item.type_key}; bytes сейва не изменены"
        )

    def _stage_item_placement(
        self,
        handle: int,
        placement_type: str,
        slot_id: object,
    ) -> None:
        if self.snapshot is None:
            return
        if not self.snapshot.capabilities.edit_placement:
            self.inventory_view.show_editability_message(
                "Только чтение: формат не разрешает редактирование позиции"
            )
            return
        item = self._find_inventory_item(handle)
        if item is None or not item.placement_editable or item.placement_type is None:
            self.inventory_view.show_editability_message(
                f"Только чтение: handle 0x{int(handle):04X} не имеет подтверждённого client-data place"
            )
            return
        normalized_type = str(placement_type).strip().casefold()
        if slot_id is None:
            normalized_slot = None
        elif isinstance(slot_id, int):
            normalized_slot = slot_id
        else:
            self.inventory_view.show_editability_message(
                "Только чтение: номер слота имеет неподдержанный тип"
            )
            return
        current = (
            item.placement_type,
            item.placement_slot if item.placement_type == "slot" else None,
        )
        desired = (normalized_type, normalized_slot)
        if desired == current:
            self.staged_placements.pop(item.handle, None)
            message = f"Позиция очищена для {item.type_key}"
        else:
            self.staged_placements[item.handle] = desired
            message = f"Позиция staged для {item.type_key}: {normalized_type}"
        self.inventory_view.set_staged_placements(self.staged_placements)
        self._render_changes()
        self._invalidate_preview("изменилось staged размещение предмета")
        self.status_label.setText(f"{message}; bytes сейва не изменены — нужен preview")

    def _clear_item_placement(self, handle: int) -> None:
        if self.snapshot is None:
            return
        item = self._find_inventory_item(handle)
        if item is None:
            return
        self.staged_placements.pop(item.handle, None)
        self.inventory_view.set_staged_placements(self.staged_placements)
        self._render_changes()
        self._invalidate_preview("staged размещение очищено")
        self.status_label.setText(
            f"Позиция очищена для {item.type_key}; bytes сейва не изменены"
        )

    def _stage_faction_relation(self, key: str, goodwill: int) -> None:
        if self.snapshot is None:
            return
        capabilities = self.snapshot.capabilities
        if not capabilities.edit_relations or not self.snapshot.info.faction_relations_editable:
            self.faction_view.status_label.setText(
                "Только чтение: формат не разрешает редактирование отношений"
            )
            return
        game_catalog = self.snapshot.game_catalog
        if game_catalog is None:
            self.faction_view.status_label.setText(
                "Только чтение: официальный faction catalog не найден"
            )
            return
        try:
            faction = game_catalog.factions.resolve(key)
        except CatalogLookupError as exc:
            self.faction_view.status_label.setText(str(exc))
            return
        if faction.numeric_id is None:
            self.faction_view.status_label.setText(
                f"Только чтение: у {key} нет подтверждённого numeric community id"
            )
            return
        minimum = game_catalog.factions.goodwill_min
        maximum = game_catalog.factions.goodwill_max
        if minimum is None or maximum is None or not minimum <= goodwill <= maximum:
            self.faction_view.status_label.setText(
                f"Goodwill отклонён: допустим диапазон {minimum}…{maximum}"
            )
            return
        current = dict(self.snapshot.info.faction_relations).get(faction.numeric_id, 0)
        if int(goodwill) == current:
            self.staged_faction_relations.pop(key, None)
        else:
            self.staged_faction_relations[key] = int(goodwill)
        self.faction_view.set_state(
            self.snapshot.info,
            self.staged_faction_relations,
            self.staged_player_faction,
        )
        self._render_changes()
        self._invalidate_preview("изменилось staged отношение группировки")
        self.status_label.setText(
            f"Отношение staged: {key} → {goodwill}; bytes сейва не изменены — нужен preview"
        )

    def _stage_player_faction(self, key: str) -> None:
        if self.snapshot is None:
            return
        capabilities = self.snapshot.capabilities
        if not capabilities.edit_player_faction or not self.snapshot.info.player_faction_editable:
            self.faction_view.status_label.setText(
                "Только чтение: принадлежность игрока не подтверждена для этого сейва"
            )
            return
        game_catalog = self.snapshot.game_catalog
        if game_catalog is None:
            self.faction_view.status_label.setText(
                "Только чтение: официальный faction catalog не найден"
            )
            return
        try:
            faction = game_catalog.factions.resolve(key)
        except CatalogLookupError as exc:
            self.faction_view.status_label.setText(str(exc))
            return
        if faction.numeric_id is None:
            self.faction_view.status_label.setText(
                f"Только чтение: у {key} нет подтверждённого numeric community id"
            )
            return
        current = self.snapshot.info.player_faction_index
        if faction.numeric_id == current:
            self.staged_player_faction = None
        else:
            self.staged_player_faction = key
        self.faction_view.set_state(
            self.snapshot.info,
            self.staged_faction_relations,
            self.staged_player_faction,
        )
        self._render_changes()
        self._invalidate_preview("изменилось staged принадлежность игрока")
        self.status_label.setText(
            f"Принадлежность игрока staged: {key}; bytes сейва не изменены — нужен preview"
        )

    def _clear_selected_stack(self, handle: int) -> None:
        self.staged_counts.pop(int(handle), None)
        self.inventory_view.set_staged_counts(self.staged_counts)
        self._render_changes()
        self._invalidate_preview("staged stack очищен")
        self.status_label.setText(
            f"Staged: {len(self.staged_counts)}; bytes сейва не изменены — нужен preview"
        )

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
        self.inventory_view.set_staged_counts(self.staged_counts)
        self.inventory_view.set_staged_durability(self.staged_durability)
        self.equipment_view.set_staged_durability(self.staged_durability)
        self.inventory_view.set_staged_upgrades(self.staged_upgrades)
        self.inventory_view.set_staged_placements(self.staged_placements)
        self.inventory_view.set_removed_handles(self.staged_detach)
        self._render_changes()
        self._invalidate_preview("все staged-правки очищены")
        self.status_label.setText("Все staged-правки очищены; bytes сейва не изменены")

    def _render_changes(self) -> None:
        self._sync_nav_counters()
        self.inventory_view.set_clear_all_enabled(self._has_staged_changes())
        self.equipment_view.set_staged_durability(self.staged_durability)
        if self.snapshot is None:
            return
        self.changes_view.set_staged(
            self.snapshot.info,
            self.staged_money,
            self.staged_counts,
            self.staged_adds,
            self.staged_detach,
            self.staged_durability,
            self.staged_faction_relations,
            self.snapshot.game_catalog.factions
            if self.snapshot.game_catalog is not None
            else None,
            staged_player_faction=self.staged_player_faction,
            staged_upgrades=self.staged_upgrades,
            staged_placements=self.staged_placements,
            upgrade_catalog=(
                self.snapshot.game_catalog.upgrades
                if self.snapshot.game_catalog is not None
                else None
            ),
            capabilities=self.snapshot.capabilities,
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

    def _update_action_buttons(self) -> None:
        local_busy = self._operation_thread is not None and self._operation_thread.isRunning()
        busy = local_busy or self._cloud_busy
        has_changes = self.edit_actions_enabled and self._has_staged_changes()
        can_preview = has_changes
        can_apply = self.prepared_edit is not None
        can_replace = bool(
            can_apply
            and self.snapshot is not None
            and self.snapshot.source_kind == "local"
        )
        self.preview_button.setEnabled(can_preview and not busy)
        # One-click save: enabled as soon as there are staged changes. The
        # click runs preview+apply internally, so it no longer waits for a
        # separate preview step.
        self.save_copy_button.setEnabled((can_preview or can_apply) and not busy)
        self.changes_view.set_actions_enabled(
            preview=can_preview,
            apply=can_apply,
            replace=can_replace,
            busy=busy,
        )
        self.backups_view.set_busy(busy)
        self.cloud_view.set_external_busy(local_busy if not self._cloud_busy else False)

    def _show_operation_error(self, message: str) -> None:
        self.status_label.setText("Операция не выполнена")
        self.error_label.setText(message)
        self.error_label.setVisible(True)
        self.changes_view.set_error(message)
        self.backups_view.set_error(message)
        self.cloud_view.set_error(message)
        self.operation_failed.emit(message)

    def _invalidate_preview(self, reason: str) -> None:
        self.prepared_edit = None
        self.changes_view.invalidate_preview(reason)
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
            self._show_operation_error(str(exc))
            return

        self.prepared_edit = None
        self._operation_kind = "preview"
        self.changes_view.clear_error()
        self.changes_view.set_progress("Запуск preview…")
        self.status_label.setText("Preview: подготовка…")
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
        self.changes_view.set_preview(prepared)
        self.cloud_view.set_prepared(prepared)
        self.preview_ready.emit(prepared)
        # One-click save chains straight into the write once the internal
        # preview is ready, so the user never sees a separate preview step.
        if getattr(self, "_pending_cloud_upload", False):
            self._pending_cloud_upload = False
            self._start_cloud_upload()
        elif self._pending_apply_path is not None:
            self._continue_pending_apply()
        else:
            self.status_label.setText("Проверено; можно сохранить")

    def _on_operation_progress(self, message: str) -> None:
        self.status_label.setText(message)
        self.changes_view.set_progress(message)
        self.backups_view.set_progress(message)

    def _on_operation_failed(self, message: str) -> None:
        # A failed step must not leave a queued one-click apply behind.
        self._pending_apply_path = None
        self._pending_cloud_upload = False
        if "SHA256" in message or "Источник изменился" in message:
            self.prepared_edit = None
            self.changes_view.invalidate_preview("source SHA изменился")
        self._show_operation_error(message)

    def _on_operation_finished(self) -> None:
        self._operation_thread = None
        self._operation_kind = None
        self.changes_view.set_busy(False)
        self.backups_view.set_busy(False)
        self._update_action_buttons()

    def _choose_output(self) -> None:
        path = self.changes_view.choose_output()
        if path is not None:
            self.changes_view.set_destination(path)

    def _save_one_click(self) -> None:
        """Preview and write in a single click, with an automatic backup.

        The integrity checks (immutable preview, source-SHA, CRC) still run —
        they are just no longer a manual step the user has to perform first.
        """

        if self._busy_now():
            self.status_label.setText("Дождись завершения текущей операции")
            return
        if self.snapshot is None:
            self._show_operation_error("Сначала открой сейв")
            return
        if self.snapshot.source_kind == "cloud":
            # Cloud has its own fail-closed upload path; keep using it.
            if self.prepared_edit is None:
                self._pending_apply_path = None
                self._start_preview()
                self._pending_cloud_upload = True
                return
            self._start_cloud_upload()
            return
        value = self.changes_view.destination_edit.text().strip()
        if value:
            path = Path(value).expanduser()
        else:
            source = Path(self.snapshot.path)
            path = source.with_name(f"{source.stem}-edited{source.suffix or '.sav'}")
            self.changes_view.set_destination(path)
        self._pending_apply_path = path
        self.status_label.setText("Сохраняю…")
        if self.prepared_edit is not None:
            self._continue_pending_apply()
        else:
            self._start_preview()

    def _continue_pending_apply(self) -> None:
        path = self._pending_apply_path
        self._pending_apply_path = None
        if path is not None:
            self._start_apply(path)

    def _choose_and_start_apply(self) -> None:
        if self.prepared_edit is None:
            self._show_operation_error("Сначала создай preview; запись без него запрещена")
            return
        if self.snapshot is not None and self.snapshot.source_kind == "cloud":
            self._start_cloud_upload()
            return
        value = self.changes_view.destination_edit.text().strip()
        if not value:
            path = self.changes_view.choose_output()
            if path is None:
                return
        else:
            path = Path(value)
        self._start_apply(path)

    def _start_apply(self, output_path: Path, backup_dir: Path | None = None) -> None:
        if self._busy_now():
            self.status_label.setText("Дождись завершения текущей операции")
            return
        if self.prepared_edit is None:
            self._show_operation_error("Сначала создай preview; запись без него запрещена")
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
            self._show_operation_error("Preview устарел после изменения формы; создай его заново")
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
        self.changes_view.set_destination(output_path)
        self.changes_view.set_progress("Запуск local export…")
        self.status_label.setText("Сохранение копии…")
        self._update_action_buttons()
        worker.start()

    def _confirm_and_start_replace(self) -> None:
        if self._busy_now():
            self.status_label.setText("Дождись завершения текущей операции")
            return
        if self.prepared_edit is None:
            self._show_operation_error("Сначала создай preview; запись без него запрещена")
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
            self._show_operation_error("Preview устарел после изменения формы; создай его заново")
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
            self._show_operation_error("Сначала создай preview; запись без него запрещена")
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
            self._show_operation_error("Preview устарел после изменения формы; создай его заново")
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
        self.changes_view.set_progress("Запуск замены исходного слота…")
        self.status_label.setText("Замена исходного слота…")
        self._update_action_buttons()
        worker.start()

    def _on_apply_ready(self, receipt) -> None:
        was_replace = self._operation_kind == "replace"
        self.prepared_edit = None
        if was_replace:
            self.changes_view.mark_replaced(receipt)
            self.status_label.setText(f"Исходный слот заменён: {receipt.output_path}")
        else:
            self.changes_view.mark_applied(receipt)
            self.status_label.setText(
                f"Сохранено: {receipt.output_path} · бэкап исходного сделан"
            )
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
        self.backups_view.set_progress("Запуск restore…")
        self.status_label.setText("Восстановление копии…")
        self._update_action_buttons()
        worker.start()

    def _on_restore_ready(self, receipt) -> None:
        self.backups_view.mark_restored(receipt)
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
        self.backups_view.set_progress("Запуск отката исходного слота…")
        self.status_label.setText("Восстановление исходного слота…")
        self._update_action_buttons()
        worker.start()

    def _on_restore_in_place_ready(self, receipt) -> None:
        self.backups_view.mark_in_place_restored(receipt)
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
        )
        self._render_snapshot(local_snapshot)
        self.analysis_ready.emit(local_snapshot)
        self.status_label.setText(
            f"Cloud snapshot готов: {snapshot.name}; выбери изменения и создай preview"
        )

    def _start_cloud_upload(self) -> None:
        if self.prepared_edit is None:
            self._show_operation_error("Сначала создай preview cloud-сейва")
            return
        self.status_label.setText("Cloud upload: подготовка…")
        self.cloud_view.start_upload()

    def _on_cloud_upload_ready(self, receipt) -> None:
        self.prepared_edit = None
        self.status_label.setText(
            "Cloud: verified" if receipt.status == "verified" else "Cloud: uncertain — требуется reconciliation"
        )
        self._update_action_buttons()
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
        if self.cloud_view.is_busy and not self.cloud_view.stop_worker(30_000):
            self.status_label.setText(
                "Cloud operation ещё выполняется; окно закрыто не будет"
            )
            event.ignore()
            return
        if not self.save_slots_view.wait_for_worker():
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
        self.cloud_view.close()
        event.accept()


__all__ = ["InspectWorker", "LocalSnapshot", "MainWindow"]
