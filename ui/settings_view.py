"""Manual save-location settings for the Qt shell."""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path

from PySide6.QtCore import QEvent, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from editor.i18n import LANGUAGES, current_language, resolve_language, tr, tr_in
from editor.platforms import backup_dirs, installed_games, save_directories, steam_roots
from editor.preferences import load_preferences
from editor.releases import official_releases
from editor.settings import PathSettings, missing_manual_paths, save_settings

from .effects import Effects
from .style_components import TextureFrame, action_button, panel, section_header
from .technical_details_dialog import TechnicalDetailsDialog
from .ux_copy import technical_details

_SHELL_ICONS = Path(__file__).resolve().parents[1] / "assets" / "ui" / "shell_icons"


def _display_path(path: Path) -> str:
    expanded = Path(path).expanduser()
    try:
        relative = expanded.relative_to(Path.home())
    except ValueError:
        return str(expanded)
    return str(Path("~") / relative)


class _SettingsCategoryStack:
    """Small compatibility facade for the former stacked settings page.

    The reference surface renders all canonical sections together and uses
    the category rail as anchors.  Existing integrations still inspect
    ``settings_stack.currentWidget()`` after selecting a category, so this
    state-only facade preserves that contract without hiding the sections in
    a second visual stack.
    """

    def __init__(self) -> None:
        self._pages: list[QWidget] = []
        self._current_index = -1

    def addWidget(self, page: QWidget) -> None:  # noqa: N802
        self._pages.append(page)
        if self._current_index < 0:
            self._current_index = 0

    def count(self) -> int:
        return len(self._pages)

    def setCurrentIndex(self, index: int) -> None:  # noqa: N802
        if 0 <= index < len(self._pages):
            self._current_index = index

    def currentWidget(self) -> QWidget | None:  # noqa: N802
        if 0 <= self._current_index < len(self._pages):
            return self._pages[self._current_index]
        return None


class SettingsView(QWidget):
    """Edit and persist manual Steam/game/save roots without touching game files."""

    settings_changed = Signal(object)
    save_failed = Signal(str)
    update_requested = Signal()
    backup_folder_requested = Signal()
    journal_requested = Signal()
    copy_diagnostics_requested = Signal()
    support_requested = Signal()
    restart_requested = Signal()
    report_requested = Signal()
    effects_changed = Signal()

    def __init__(
        self,
        settings: PathSettings,
        *,
        settings_path: Path,
        load_error: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.settings = settings
        self.settings_path = Path(settings_path).expanduser()
        self.load_error = load_error
        self._language_prompt: QMessageBox | None = None
        self._advanced_paths_dialog: QDialog | None = None
        self._discovery_details_dialog: TechnicalDetailsDialog | None = None
        self._discovery_detail_text = ""
        # Safety switches are policy, not preferences.  Their visual state is
        # represented by disabled semantic controls so users can inspect the
        # enforced value without being able to weaken it here.
        self.core_safety_read_only = True
        self._build_ui()
        self._load_fields()
        self._refresh_warning()

    def _build_ui(self) -> None:
        self.setObjectName("settingsView")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 6, 0, 11)
        layout.setHorizontalSpacing(33)
        layout.setVerticalSpacing(6)

        heading = QHBoxLayout()
        heading.setContentsMargins(0, 16, 0, 8)
        title = QLabel(tr("НАСТРОЙКИ"), self)
        title.setObjectName("screenTitle")
        heading.addWidget(title)
        heading.addSpacing(30)
        subtitle = QLabel(tr("Обычно ничего менять не нужно — редактор находит всё автоматически."), self)
        subtitle.setObjectName("screenSubtitle")
        heading.addWidget(subtitle)
        heading.addStretch(1)
        layout.setRowMinimumHeight(0, 33)
        layout.addLayout(heading, 0, 1)

        rail = panel(self, object_name="settingsCategoryRail")
        rail_layout = QVBoxLayout(rail)
        rail_layout.setContentsMargins(4, 18, 4, 12)
        rail_layout.setSpacing(1)
        rail_heading = QLabel(tr("РАЗДЕЛЫ"), rail)
        rail_heading.setIndent(11)
        rail_layout.addWidget(rail_heading)
        rule = QFrame(rail)
        rule.setFrameShape(QFrame.Shape.HLine)
        rail_layout.addWidget(rule)
        rail_layout.addSpacing(16)
        self.category_buttons: list[QPushButton] = []
        self.category_names = (
            tr("ОБЩИЕ"),
            tr("ПУТИ И АВТОПОИСК"),
            tr("РЕЗЕРВНЫЕ КОПИИ"),
            "STEAM CLOUD",
            tr("ОБНОВЛЕНИЯ И ДИАГНОСТИКА"),
            tr("ИНТЕРФЕЙС"),
            tr("ПОДДЕРЖКА"),
        )
        category_icons = ("settings", "paths", "backups", "cloud", "diagnostics", "interface", "support")
        for index, name in enumerate(self.category_names):
            button = QPushButton(name.replace("ОБНОВЛЕНИЯ И ДИАГНОСТИКА", "ОБНОВЛЕНИЯ И\nДИАГНОСТИКА"), rail)
            button.setObjectName("settingsCategoryButton")
            button.setAccessibleName(name)
            button.setIcon(QIcon(str(_SHELL_ICONS / f"{category_icons[index]}.svg")))
            button.setIconSize(QSize(24, 24))
            button.setFixedHeight(61)
            button.setCheckable(True)
            button.setAutoExclusive(True)
            button.clicked.connect(lambda _checked=False, selected=index: self._select_category(selected))
            rail_layout.addWidget(button)
            self.category_buttons.append(button)
        self.zone_decoration = TextureFrame(
            rail,
            asset="rail_zone.png",
            overlay_alpha=0,
            image_height_ratio=0.66,
        )
        self.zone_decoration.setObjectName("settingsZoneDecoration")
        self.zone_decoration.setMinimumHeight(70)
        self.zone_decoration.setMaximumHeight(286)
        self.zone_decoration.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        zone_layout = QVBoxLayout(self.zone_decoration)
        zone_layout.setContentsMargins(12, 1, 8, 1)
        zone_layout.addStretch(1)
        zone_note = QLabel(
            tr("ЗОНА НЕ ПРОЩАЕТ\nОШИБОК.\nРЕЗЕРВНАЯ КОПИЯ\nПРОЩАЕТ."),
            self.zone_decoration,
        )
        zone_note.setObjectName("settingsZoneDecorationText")
        zone_note.setWordWrap(True)
        zone_layout.addWidget(zone_note)
        rail_layout.addWidget(self.zone_decoration, 1)
        rail.setFixedWidth(267)
        rail.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        self.settings_stack = _SettingsCategoryStack()
        self.settings_scroll = QScrollArea(self)
        self.settings_scroll.setObjectName("settingsScroll")
        self.settings_scroll.setWidgetResizable(True)
        self.settings_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.settings_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.settings_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.settings_scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.settings_content = QWidget(self.settings_scroll)
        self.settings_content.setObjectName("settingsContent")
        settings_sections = QVBoxLayout(self.settings_content)
        settings_sections.setContentsMargins(0, 0, 0, 0)
        settings_sections.setSpacing(11)
        self.general_panel = panel(self.settings_content, object_name="generalSettingsPanel")
        self.paths_panel = panel(self.settings_content, object_name="pathsSettingsPanel")
        self.backups_panel = panel(self.settings_content, object_name="backupsSettingsPanel")
        self.cloud_panel = panel(self.settings_content, object_name="cloudSettingsPanel")
        self.diagnostics_panel = panel(self.settings_content, object_name="diagnosticsSettingsPanel")
        self.interface_panel = panel(self.settings_content, object_name="interfaceSettingsPanel")
        self.support_panel = panel(self.settings_content, object_name="supportSettingsPanel")
        self._build_general_panel()
        self._build_paths_panel()
        self._build_backups_panel()
        self._build_cloud_panel()
        self._build_diagnostics_panel()
        self._build_interface_panel()
        self._build_simple_panel(self.support_panel, tr("ПОДДЕРЖКА"), tr("Спасибо, что сохраняешь историю Зоны. Кнопка поддержки доступна в верхней панели."))
        self.support_action_button = action_button(tr("ПОДДЕРЖАТЬ ПРОЕКТ"), self.support_panel, kind="primary")
        self.support_action_button.clicked.connect(self.support_requested)
        support_layout = self.support_panel.layout()
        if support_layout is None:
            raise RuntimeError("support settings panel has no layout")
        support_layout.addWidget(self.support_action_button)
        canonical_pages = (
            self.general_panel,
            self.paths_panel,
            self.backups_panel,
            self.cloud_panel,
            self.diagnostics_panel,
            self.interface_panel,
            self.support_panel,
        )
        for page in canonical_pages:
            self.settings_stack.addWidget(page)
            settings_sections.addWidget(page)
        settings_sections.addStretch(1)
        self.settings_scroll.setWidget(self.settings_content)
        self._settings_pages = canonical_pages
        layout.addWidget(rail, 0, 0, 3, 1)
        layout.addWidget(self.settings_scroll, 1, 1)
        layout.setRowStretch(1, 1)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(16)
        self.save_button = action_button(tr("СОХРАНИТЬ НАСТРОЙКИ"), self, kind="primary")
        self.save_button.clicked.connect(self.save)
        self.save_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        actions.addWidget(self.save_button, 403)
        self.reset_button = action_button(tr("СБРОСИТЬ"), self)
        self.reset_button.clicked.connect(self._reset_fields)
        self.reset_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        actions.addWidget(self.reset_button, 272)
        self.defaults_button = action_button(tr("ПО УМОЛЧАНИЮ"), self)
        self.defaults_button.clicked.connect(self._set_defaults)
        self.defaults_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        actions.addWidget(self.defaults_button, 272)
        self.cancel_button = action_button(tr("ОТМЕНА"), self)
        self.cancel_button.clicked.connect(self._cancel_changes)
        self.cancel_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        actions.addWidget(self.cancel_button, 232)
        for button in (self.save_button, self.reset_button, self.defaults_button, self.cancel_button):
            button.setMinimumHeight(42)
        layout.addLayout(actions, 2, 1)
        self._select_category(0)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        compact = event.size().height() < 700
        if not hasattr(self, "zone_decoration"):
            return
        if self.zone_decoration.property("compact") == compact:
            return
        self.zone_decoration.setProperty("compact", compact)
        self.zone_decoration.style().unpolish(self.zone_decoration)
        self.zone_decoration.style().polish(self.zone_decoration)
        note = self.zone_decoration.findChild(QLabel, "settingsZoneDecorationText")
        if note is not None:
            note.style().unpolish(note)
            note.style().polish(note)
            note.updateGeometry()
        self.zone_decoration.updateGeometry()

    @staticmethod
    def _settings_section_header(
        title: str,
        subtitle: str,
        parent: QWidget,
        icon_name: str,
    ) -> QWidget:
        header = section_header(title, subtitle, parent, icon_name=icon_name)
        header_layout = header.layout()
        if header_layout is not None:
            header_layout.setContentsMargins(20, 0, 12, 0)
            header_layout.setSpacing(26)
        header.setFixedHeight(38)
        return header

    def _build_general_panel(self) -> None:
        layout = QVBoxLayout(self.general_panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._settings_section_header(
            tr("ОБЩИЕ"), tr("УПРАВЛЕНИЕ ОСНОВНЫМ ПОВЕДЕНИЕМ РЕДАКТОРА"), self.general_panel, "settings"
        ))
        intro = QLabel(
            tr("Ручные пути имеют приоритет: папка сохранений → папка игры → корень Steam. Пути сохраняются локально; программа ничего не пишет в каталог игры.")
        )
        intro.setWordWrap(True)
        # The helper remains available in the widget tree for accessibility,
        # while the canonical overview keeps the compact reference density.
        intro.setVisible(False)
        self.safety_labels = []
        # Fixed safety policies, stated as facts.  They used to be drawn as
        # switches that could not be switched, one of them for a feature that
        # does not exist.
        for text, policy in (
            (tr("Проверка обновлений при запуске"), tr("Включена")),
            (tr("Подтверждение перед записью сохранения"), tr("Всегда")),
            (tr("Проверенная резервная копия перед записью"), tr("Всегда")),
        ):
            row = QFrame(self.general_panel)
            row.setObjectName("settingsSafetyRowFrame")
            row.setFixedHeight(34)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(44, 1, 20, 1)
            label = QLabel(text, row)
            label.setObjectName("settingsSafetyRow")
            self.safety_labels.append(label)
            row_layout.addWidget(label, 1)
            status_host = QWidget(row)
            status_layout = QHBoxLayout(status_host)
            status_layout.setContentsMargins(0, 0, 0, 0)
            status_layout.setSpacing(8)
            status_host.setFixedWidth(153)
            status_layout.setSpacing(21)
            enabled = QLabel(policy, status_host)
            enabled.setObjectName("settingsRowStatus")
            enabled.setProperty("enabledState", "on")
            enabled.setToolTip(tr("Правило безопасности редактора; не отключается"))
            status_layout.addStretch(1)
            status_layout.addWidget(enabled)
            row_layout.addWidget(status_host)
            layout.addWidget(row)
        self.general_panel.setFixedHeight(145)

    def _build_paths_panel(self) -> None:
        layout = QVBoxLayout(self.paths_panel)
        layout.setContentsMargins(0, 0, 0, 8)
        layout.setSpacing(4)
        layout.addWidget(self._settings_section_header(
            tr("ПУТИ И АВТОПОИСК"), tr("ПУТИ К ИГРАМ, СОХРАНЕНИЯМ И РЕСУРСАМ"), self.paths_panel, "library"
        ))
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        # Keep the label/value split at the same stable column as the
        # canonical sheet.  Letting QFormLayout derive it from the narrow
        # font collapses the path controls toward the left edge.
        form.setContentsMargins(44, 0, 0, 0)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(4)
        self.steam_root_edit = QLineEdit()
        self.steam_root_edit.setPlaceholderText(tr("Не задано — использовать автопоиск"))
        self.steam_hint = self._hint_label()
        form.addRow(tr("Корень Steam"), self._path_row(self.steam_root_edit, self.steam_hint))
        backup_locations = backup_dirs()
        backup_value = QLabel(
            _display_path(backup_locations[0])
            if backup_locations
            else tr("Не найдено — будет создано при первой записи"),
            self.paths_panel,
        )
        backup_value.setObjectName("settingsBackupPathValue")
        backup_value.setFixedHeight(29)
        backup_value.setToolTip(backup_value.text())
        backup_row = QWidget(self.paths_panel)
        backup_layout = QHBoxLayout(backup_row)
        backup_layout.setContentsMargins(0, 0, 0, 0)
        backup_layout.setSpacing(8)
        self.backup_path_button = QPushButton(backup_row)
        self.backup_path_button.setObjectName("settingsBackupPathButton")
        self.backup_path_button.setIcon(QIcon(str(_SHELL_ICONS / "paths.svg")))
        self.backup_path_button.setIconSize(QSize(18, 18))
        self.backup_path_button.setFixedSize(38, 29)
        self.backup_path_button.setToolTip(tr("Открыть папку резервных копий"))
        self.backup_path_button.setEnabled(
            bool(backup_locations) and backup_locations[0].is_dir()
        )
        self.backup_path_button.clicked.connect(self.backup_folder_requested.emit)
        self.backup_path_status = QLabel(backup_row)
        self.backup_path_status.setObjectName("settingsPathStatus")
        backup_ready = bool(backup_locations) and backup_locations[0].is_dir()
        self.backup_path_status.setText(tr("● ГОТОВО") if backup_ready else tr("● БУДЕТ СОЗДАНО"))
        self.backup_path_status.setProperty(
            "discoveryState", "found" if backup_ready else "pending"
        )
        self.backup_path_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.backup_path_status.setFixedHeight(29)
        self.backup_path_status.setMinimumWidth(153)
        self.backup_path_status.setToolTip(
            tr("Папка резервных копий доступна.")
            if backup_ready
            else tr("Папка будет создана при первой записи.")
        )
        backup_layout.addWidget(backup_value, 1)
        backup_layout.addWidget(self.backup_path_button)
        backup_layout.addWidget(self.backup_path_status)
        form.addRow(tr("Папка резервных копий"), backup_row)
        self.catalog_root_edit = QLineEdit()
        self.catalog_root_edit.setPlaceholderText(tr("Не задано — использовать установленную игру/автопоиск"))
        self.catalog_hint = self._hint_label()
        form.addRow(tr("Каталог S.T.A.L.K.E.R. 2 (Zone Kit / Workshop)"), self._path_row(self.catalog_root_edit, self.catalog_hint))
        self.advanced_paths_button = action_button(
            tr("ПОКАЗАТЬ РАСШИРЕННЫЕ  ›"),
            self.paths_panel,
            object_name="settingsAdvancedPathsButton",
        )
        self.advanced_paths_button.setFixedSize(270, 35)
        self.advanced_paths_button.clicked.connect(self._show_advanced_paths)
        form.addRow(tr("Ручные пути"), self.advanced_paths_button)
        for row_index in range(form.rowCount()):
            label_item = form.itemAt(row_index, QFormLayout.ItemRole.LabelRole)
            label_widget = label_item.widget() if label_item is not None else None
            if label_widget is not None:
                label_widget.setMinimumWidth(390)
        layout.addLayout(form)
        found_heading = QLabel(tr("Автопоиск нашёл (все игры сразу — выбирать не нужно):"))
        found_heading.setVisible(False)
        layout.addWidget(found_heading)
        self.found_all_label = QLabel(tr("Сканирую…"))
        self.found_all_label.setObjectName("discoveryResults")
        self.found_all_label.setWordWrap(True)
        self.found_all_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.found_all_label.setVisible(False)
        found_row = QHBoxLayout()
        found_row.addWidget(self.found_all_label, 1)
        self.discovery_details_button = action_button(
            tr("ТЕХНИЧЕСКИЕ ДЕТАЛИ"), self.paths_panel
        )
        self.discovery_details_button.setObjectName("settingsDiscoveryDetailsButton")
        self.discovery_details_button.setVisible(False)
        self.discovery_details_button.clicked.connect(self._show_discovery_details)
        found_row.addWidget(self.discovery_details_button)
        layout.addLayout(found_row)
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.status_label)
        self.warning_label = QLabel("")
        self.warning_label.setWordWrap(True)
        self.warning_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.warning_label)
        layout.addStretch(1)
        # The rows need their own height; a smaller fixed box made the path
        # fields, status chips and buttons overlap.
        self.paths_panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

    def _build_backups_panel(self) -> None:
        layout = QVBoxLayout(self.backups_panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.addWidget(section_header(tr("РЕЗЕРВНЫЕ КОПИИ"), tr("АВТОМАТИЧЕСКАЯ ЗАЩИТА"), self.backups_panel, icon_name="history"))
        label = QLabel(
            tr("Резервная копия создаётся автоматически перед каждым сохранением."),
            self.backups_panel,
        )
        label.setWordWrap(True)
        layout.addWidget(label)
        layout.addStretch(1)
        self.backups_panel.setFixedHeight(132)

    def _build_cloud_panel(self) -> None:
        layout = QVBoxLayout(self.cloud_panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._settings_section_header(
            "STEAM CLOUD", tr("ИНТЕГРАЦИЯ СО STEAM CLOUD"), self.cloud_panel, "cloud"
        ))
        for label_text, value_text in (
            (tr("Подключение"), tr("Только по явному действию пользователя")),
            (tr("Режим"), tr("Только после подтверждения")),
            (
                tr("Если Steam не подтвердил запись,"),
                tr("редактор сначала проверит состояние облака."),
            ),
        ):
            row = QFrame(self.cloud_panel)
            row.setObjectName("settingsCloudRow")
            row.setFixedHeight(32)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(32, 0, 20, 0)
            row_layout.setSpacing(0)
            label = QLabel(label_text, row)
            label.setObjectName("settingsCloudLabel")
            label.setMinimumWidth(400)
            value = QLabel(value_text, row)
            value.setObjectName(
                "settingsCloudConnectionValue"
                if label_text == "Подключение"
                else "settingsCloudValue"
            )
            row_layout.addWidget(label)
            row_layout.addWidget(value, 1)
            layout.addWidget(row)
        self.cloud_panel.setFixedHeight(139)

    def _build_diagnostics_panel(self) -> None:
        layout = QVBoxLayout(self.diagnostics_panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self._settings_section_header(
            tr("ОБНОВЛЕНИЯ И ДИАГНОСТИКА"), tr("ИНСТРУМЕНТЫ ДЛЯ ПОДДЕРЖКИ"), self.diagnostics_panel, "history"
        ))
        self.backup_folder_button = QToolButton(self.diagnostics_panel)
        self.backup_folder_button.setObjectName("settingsBackupFolderButton")
        self.backup_folder_button.setText(tr("ОТКРЫТЬ ПАПКУ РЕЗЕРВНЫХ КОПИЙ"))
        self.backup_folder_button.setIcon(QIcon(str(_SHELL_ICONS / "backups.svg")))
        self.backup_folder_button.setIconSize(QSize(18, 18))
        self.backup_folder_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.backup_folder_button.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.backup_folder_button.setEnabled(
            any(path.is_dir() for path in backup_dirs())
        )
        if not self.backup_folder_button.isEnabled():
            self.backup_folder_button.setToolTip(
                tr("Папка появится после создания первой резервной копии")
            )
        update_menu = QMenu(self.backup_folder_button)
        update_action = update_menu.addAction(tr("Проверить обновления"))
        update_action.triggered.connect(self.update_requested.emit)
        self.backup_folder_button.setMenu(update_menu)
        self.backup_folder_button.clicked.connect(self.backup_folder_requested.emit)
        self.diagnostics_action_button = action_button(tr("ОТКРЫТЬ ЖУРНАЛ ОШИБОК"), self.diagnostics_panel)
        self.copy_diagnostics_button = action_button(tr("СКОПИРОВАТЬ ДИАГНОСТИКУ"), self.diagnostics_panel)
        self.report_button = action_button(tr("ОТПРАВИТЬ ОТЧЁТ"), self.diagnostics_panel, kind="primary")
        self.report_button.setToolTip(
            tr("Отправить разработчику короткий обезличенный журнал. Сохранения не отправляются.")
        )
        self.diagnostics_action_button.clicked.connect(self.journal_requested)
        self.copy_diagnostics_button.clicked.connect(self.copy_diagnostics_requested)
        self.report_button.clicked.connect(self.report_requested)
        self.report_button.setMinimumHeight(40)
        actions = QHBoxLayout()
        actions.setSpacing(8)
        actions.addWidget(self.backup_folder_button, 1)
        actions.addWidget(self.diagnostics_action_button, 1)
        actions.addWidget(self.copy_diagnostics_button, 1)
        layout.addLayout(actions)
        layout.addWidget(self.report_button)
        note = QLabel(
            tr("Диагностика не нужна для обычного использования, но полезна для отчётов об ошибках."),
            self.diagnostics_panel,
        )
        note.setObjectName("settingsDiagnosticsNote")
        layout.addWidget(note)
        layout.addStretch(1)
        self.diagnostics_panel.setFixedHeight(131)

    def _show_advanced_paths(self) -> None:
        if self._advanced_paths_dialog is not None and self._advanced_paths_dialog.isVisible():
            self._advanced_paths_dialog.raise_()
            self._advanced_paths_dialog.activateWindow()
            return

        dialog = QDialog(self)
        dialog.setObjectName("advancedPathsDialog")
        dialog.setWindowTitle(tr("Расширенные пути"))
        dialog.resize(940, 620)
        layout = QVBoxLayout(dialog)
        intro = QLabel(
            tr("Для каждого официального выпуска показан ручной путь, если он задан, иначе — результат автопоиска. Здесь ничего не записывается в каталог игры."),
            dialog,
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        scroll = QScrollArea(dialog)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget(scroll)
        form = QFormLayout(content)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        for release in official_releases():
            game_path = self.settings.game_root(release.id) or self._discover_game_root(release.id)
            save_path = self.settings.save_root(release.id) or self._discover_save_root(release.id)
            game_source = tr("Ручной путь") if self.settings.game_root(release.id) else tr("Автопоиск")
            save_source = tr("Ручной путь") if self.settings.save_root(release.id) else tr("Автопоиск")
            form.addRow(
                tr("{0} · игра", release.title),
                self._advanced_path_value(game_path, game_source, content),
            )
            form.addRow(
                tr("{0} · сохранения", release.title),
                self._advanced_path_value(save_path, save_source, content),
            )
            if release.id == "stalker2":
                catalog = self.settings.catalog_root(release.id) or self._discover_catalog_root()
                source = tr("Ручной путь") if self.settings.catalog_root(release.id) else tr("Автопоиск")
                form.addRow(
                    tr("{0} · каталог ресурсов", release.title),
                    self._advanced_path_value(catalog, source, content),
                )
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, dialog)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        self._advanced_paths_dialog = dialog
        dialog.finished.connect(lambda _result: self._clear_advanced_paths_dialog(dialog))
        dialog.open()

    @staticmethod
    def _advanced_path_value(path: Path | None, source: str, parent: QWidget) -> QLineEdit:
        value = QLineEdit(parent)
        value.setReadOnly(True)
        value.setText(f"{source}: {path}" if path is not None else tr("{0}: не найдено", source))
        value.setToolTip(value.text())
        value.setMinimumWidth(560)
        return value

    def _clear_advanced_paths_dialog(self, dialog: QDialog) -> None:
        if self._advanced_paths_dialog is dialog:
            self._advanced_paths_dialog = None

    def _build_interface_panel(self) -> None:
        page = self.interface_panel
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        layout.addWidget(section_header(tr("ИНТЕРФЕЙС"), tr("ЯЗЫК, ЗВУК И АНИМАЦИИ"), page, icon_name="interface"))
        form = QFormLayout()
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(10)
        self.language_combo = QComboBox(page)
        self.language_combo.setObjectName("languageCombo")
        # Scrolling the page over the combo must not silently switch language.
        self.language_combo.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.language_combo.installEventFilter(self)
        self.language_combo.addItem(tr("Как в системе"), None)
        for code, name in LANGUAGES.items():
            self.language_combo.addItem(name, code)
        saved = load_preferences().language
        index = self.language_combo.findData(saved) if saved else 0
        self.language_combo.setCurrentIndex(max(0, index))
        self.language_combo.currentIndexChanged.connect(self._language_changed)
        form.addRow(tr("Язык интерфейса"), self.language_combo)
        effects = Effects.instance()
        self.sound_check = QCheckBox(tr("Звуки интерфейса"), page)
        self.sound_check.setChecked(effects.sound_enabled)
        self.sound_check.toggled.connect(self._sound_changed)
        form.addRow("", self.sound_check)
        self.volume_slider = QSlider(Qt.Orientation.Horizontal, page)
        self.volume_slider.setObjectName("soundVolume")
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(effects.preferences.sound_volume)
        self.volume_slider.setEnabled(effects.sound_enabled)
        self.volume_slider.sliderReleased.connect(self._volume_changed)
        form.addRow(tr("Громкость"), self.volume_slider)
        self.music_check = QCheckBox(tr("Музыка из главного меню игры"), page)
        self.music_check.setObjectName("menuMusicCheck")
        self.music_check.setToolTip(
            tr("Тихо играет тему главного меню той игры, чьё сохранение открыто. Берётся из установленной игры.")
        )
        self.music_check.setChecked(effects.music_enabled)
        self.music_check.setEnabled(effects.sound_enabled)
        self.music_check.toggled.connect(self._music_changed)
        form.addRow("", self.music_check)
        self.music_note = QLabel(
            tr("Играет тему меню ТЧ, ЧН или ЗП, когда открыто или выбрано сохранение этой игры и сама игра установлена. Для S.T.A.L.K.E.R. 2 музыки пока нет."),
            page,
        )
        self.music_note.setWordWrap(True)
        self.music_note.setObjectName("settingsHint")
        form.addRow("", self.music_note)
        self.motion_check = QCheckBox(tr("Анимации переходов"), page)
        self.motion_check.setChecked(effects.motion_enabled)
        self.motion_check.toggled.connect(self._motion_changed)
        form.addRow("", self.motion_check)
        layout.addLayout(form)
        self.language_note = QLabel(
            tr("Язык сменится после перезапуска. Названия предметов — официальные, из самих игр; звуки и музыка меню берутся из установленной игры."),
            page,
        )
        self.language_note.setWordWrap(True)
        self.language_note.setObjectName("settingsHint")
        layout.addWidget(self.language_note)
        self.restart_button = action_button(tr("ПЕРЕЗАПУСТИТЬ СЕЙЧАС"), page)
        self.restart_button.setVisible(False)
        self.restart_button.clicked.connect(self.restart_requested)
        layout.addWidget(self.restart_button)
        layout.addStretch(1)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt override
        combo = getattr(self, "language_combo", None)
        if (
            combo is not None
            and watched is combo
            and event.type() == QEvent.Type.Wheel
            and not combo.hasFocus()
        ):
            event.ignore()
            return True
        return super().eventFilter(watched, event)

    def _language_changed(self, _index: int) -> None:
        code = self.language_combo.currentData()
        effects = Effects.instance()
        effects._store(effects.preferences.with_(language=code))
        target = resolve_language(code)
        pending = target != current_language()
        self.restart_button.setVisible(pending)
        if pending:
            self._prompt_language_restart(target)

    def _prompt_language_restart(self, target: str) -> None:
        """Offer an immediate restart, worded in the language just chosen."""

        if self._language_prompt is not None:
            self._language_prompt.close()
        box = QMessageBox(self)
        box.setObjectName("languageRestartPrompt")
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(tr_in(target, "Язык интерфейса"))
        box.setText(tr_in(target, "Язык сменится после перезапуска. Перезапустить сейчас?"))
        box.setInformativeText(tr_in(target, "Несохранённые изменения останутся: перед перезапуском редактор спросит о них."))
        restart = box.addButton(tr_in(target, "ПЕРЕЗАПУСТИТЬ СЕЙЧАС"), QMessageBox.ButtonRole.AcceptRole)
        box.addButton(tr_in(target, "Позже"), QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(restart)

        def _finished(_result: int) -> None:
            self._language_prompt = None
            if box.clickedButton() is restart:
                self.restart_requested.emit()

        box.finished.connect(_finished)
        self._language_prompt = box
        box.open()  # window-modal but non-blocking

    def _music_changed(self, enabled: bool) -> None:
        Effects.instance().set_music_enabled(enabled)

    def _sound_changed(self, enabled: bool) -> None:
        Effects.instance().set_sound_enabled(enabled)
        self.volume_slider.setEnabled(enabled)
        self.music_check.setEnabled(enabled)
        self.effects_changed.emit()

    def _volume_changed(self) -> None:
        effects = Effects.instance()
        effects.set_volume(self.volume_slider.value())
        effects.play("click")

    def _motion_changed(self, enabled: bool) -> None:
        Effects.instance().set_motion_enabled(enabled)
        self.effects_changed.emit()

    def sync_effects(self) -> None:
        effects = Effects.instance()
        for check, value in ((self.sound_check, effects.sound_enabled), (self.motion_check, effects.motion_enabled)):
            check.blockSignals(True)
            check.setChecked(value)
            check.blockSignals(False)
        self.volume_slider.setEnabled(effects.sound_enabled)
        self.music_check.setEnabled(effects.sound_enabled)

    @staticmethod
    def _build_simple_panel(page: QWidget, title: str, text: str) -> None:
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.addWidget(section_header(title, parent=page))
        label = QLabel(text, page)
        label.setWordWrap(True)
        layout.addWidget(label)
        layout.addStretch(1)

    def _select_category(self, index: int) -> None:
        if not hasattr(self, "settings_stack") or not 0 <= index < self.settings_stack.count():
            return
        self.settings_stack.setCurrentIndex(index)
        for button_index, button in enumerate(self.category_buttons):
            button.setChecked(button_index == index)
        # One section at a time: a rail click always visibly changes the page.
        for page_index, page in enumerate(self._settings_pages):
            page.setVisible(page_index == index)
        if hasattr(self, "settings_scroll"):
            self.settings_scroll.verticalScrollBar().setValue(0)
            Effects.instance().fade_in(self._settings_pages[index])

    def _reset_fields(self) -> None:
        self.steam_root_edit.clear()
        self.catalog_root_edit.clear()
        self.status_label.setText(tr("Пути сброшены в поля; нажми «Сохранить настройки», чтобы записать изменения."))

    def reset(self) -> None:
        """Reset editable fields for the footer shortcut."""

        self._reset_fields()

    def _set_defaults(self) -> None:
        self.steam_root_edit.clear()
        self.catalog_root_edit.clear()
        self.status_label.setText(tr("Восстановлены значения по умолчанию; нажми «Сохранить настройки», чтобы применить их."))

    def defaults(self) -> None:
        """Restore defaults for the footer shortcut."""

        self._set_defaults()

    def _cancel_changes(self) -> None:
        self._load_fields()
        self.status_label.setText(tr("Изменения отменены; сохранённые настройки восстановлены."))

    def cancel(self) -> None:
        """Cancel editable field changes for the footer shortcut."""

        self._cancel_changes()

    def _hint_label(self) -> QLabel:
        label = QLabel("")
        label.setWordWrap(True)
        label.setObjectName("discoveryHint")
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        font = label.font()
        font.setPointSizeF(max(7.0, font.pointSizeF() - 1.0))
        label.setFont(font)
        return label

    def _path_row(self, edit: QLineEdit, hint: QLabel | None = None) -> QWidget:
        container = QWidget()
        outer = QVBoxLayout(container)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(2)
        row = QWidget()
        row.setMinimumHeight(29)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(edit, 1)
        browse = QPushButton(row)
        browse.setObjectName("settingsBrowseButton")
        browse.setIcon(QIcon(str(_SHELL_ICONS / "paths.svg")))
        browse.setIconSize(QSize(18, 18))
        browse.setToolTip(tr("Выбрать папку"))
        browse.setFixedWidth(38)
        edit.setMinimumHeight(29)
        browse.setMinimumHeight(29)
        browse.clicked.connect(lambda: self._choose_directory(edit))
        layout.addWidget(browse)
        if hint is not None:
            hint.setMinimumWidth(168)
            hint.setFixedHeight(29)
            hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(hint)
        outer.addWidget(row)
        return container

    def _load_fields(self) -> None:
        self.steam_root_edit.setText(
            str(self.settings.steam_root) if self.settings.steam_root is not None else ""
        )
        catalog_root = self.settings.catalog_root("stalker2")
        self.catalog_root_edit.setText(str(catalog_root) if catalog_root is not None else "")
        # Autodiscovery scans Steam libraries on disk; keep it off the
        # construction/critical path so the shell stays responsive.
        QTimer.singleShot(0, self._refresh_hints)

    @staticmethod
    def _first_existing(paths: Iterable[Path]) -> Path | None:
        for path in paths:
            candidate = Path(path)
            if candidate.is_dir():
                return candidate
        return None

    def _discover_steam_root(self) -> Path | None:
        try:
            return self._first_existing(steam_roots())
        except Exception:
            return None

    def _discover_game_root(self, game_id: str) -> Path | None:
        try:
            for game in installed_games():
                if game.game_id == game_id and Path(game.install_dir).is_dir():
                    return Path(game.install_dir)
        except Exception:
            return None
        return None

    def _discover_save_root(self, game_id: str) -> Path | None:
        try:
            dirs = save_directories(game_id)
        except Exception:
            return None
        return Path(dirs[0]) if dirs else None

    def _discover_catalog_root(self) -> Path | None:
        for key in ("STALKER2_ZONE_KIT_ROOT", "ZONE_KIT_ROOT", "STALKER2_WORKSHOP_ROOT"):
            for raw in os.environ.get(key, "").split(os.pathsep):
                if raw.strip():
                    candidate = Path(raw).expanduser()
                    if candidate.is_dir():
                        return candidate
        return None

    def _set_hint(self, label: QLabel, discovered: Path | None) -> None:
        if discovered is not None:
            label.setText(tr("●  НАЙДЕНО"))
            label.setProperty("discoveryState", "found")
            label.setToolTip(tr("Автопоиск: {0}", discovered))
        else:
            label.setText(tr("●  НЕ НАЙДЕНО"))
            label.setProperty("discoveryState", "missing")
            label.setToolTip(tr("Автопоиск ничего не нашёл; можно задать путь вручную."))
        label.style().unpolish(label)
        label.style().polish(label)

    def _refresh_hints(self) -> None:
        try:
            self._set_hint(self.steam_hint, self._discover_steam_root())
            self._set_hint(
                self.catalog_hint,
                self.settings.catalog_root("stalker2") or self._discover_catalog_root(),
            )
            self._refresh_found_all()
        except RuntimeError:
            # The deferred timer can fire after the view (and its Qt labels)
            # were torn down; a deleted C++ object is not an error worth raising.
            return

    def _refresh_found_all(self) -> None:
        steam = self._discover_steam_root()
        lines = [tr("Корень Steam: {0}", steam) if steam else tr("Корень Steam: не найден")]
        for release in official_releases():
            game = self._discover_game_root(release.id)
            save = self._discover_save_root(release.id)
            catalog = (
                self.settings.catalog_root(release.id)
                if release.id == "stalker2"
                else None
            )
            if catalog is None and release.id == "stalker2":
                catalog = self._discover_catalog_root()
            if game is None and save is None and catalog is None:
                continue
            parts = [release.title]
            if save is not None:
                parts.append(tr("сохранения: {0}", save))
            if game is not None:
                parts.append(tr("игра: {0}", game))
            if catalog is not None:
                parts.append(tr("каталог: {0}", catalog))
            lines.append(" — ".join(parts))
        if len(lines) == 1:
            lines.append(tr("Установленных игр не найдено."))
        details = "\n".join(lines)
        self._discovery_detail_text = technical_details(details)
        self.discovery_details_button.setVisible(True)
        found_count = max(0, len(lines) - 1)
        self.found_all_label.setText(
            tr("Автопоиск: Steam {0} · игр найдено: {1}", tr("найден") if steam else tr("не найден"), found_count)
        )

    def _show_discovery_details(self) -> None:
        if not self._discovery_detail_text:
            return
        if self._discovery_details_dialog is not None:
            self._discovery_details_dialog.close()
        self._discovery_details_dialog = TechnicalDetailsDialog(
            self._discovery_detail_text, self
        )
        self._discovery_details_dialog.open()

    def _choose_directory(self, edit: QLineEdit) -> None:
        selected = QFileDialog.getExistingDirectory(self, tr("Выбрать каталог"))
        if selected:
            edit.setText(selected)

    @staticmethod
    def _path_from_text(text: str, field: str) -> Path | None:
        value = text.strip()
        if not value:
            return None
        path = Path(value).expanduser()
        if not path.is_absolute():
            raise ValueError(tr("{0}: укажи абсолютный путь", field))
        return path

    def _collect_settings(self) -> PathSettings:
        settings = self.settings.with_steam_root(
            self._path_from_text(self.steam_root_edit.text(), tr("Корень Steam"))
        )
        return settings.with_catalog_root(
            "stalker2",
            self._path_from_text(
                self.catalog_root_edit.text(),
                tr("Каталог S.T.A.L.K.E.R. 2"),
            ),
        )

    def _refresh_warning(self) -> None:
        messages: list[str] = []
        if self.load_error:
            messages.append(self.load_error)
        missing = missing_manual_paths(self.settings)
        if missing:
            paths = ", ".join(str(path) for path in missing)
            messages.append(
                tr("Сохранённый путь исчез: {0}. Выбери каталог заново; автопоиск снова доступен.", paths)
            )
        if not messages:
            messages.append(
                tr("Автопоиск используется, если ручной путь не задан или недоступен.")
            )
        self.warning_label.setText("\n".join(messages))
        self.warning_label.setVisible(bool(self.load_error or missing))

    def save(self) -> None:
        try:
            settings = self._collect_settings()
            save_settings(settings, path=self.settings_path)
        except (OSError, TypeError, ValueError) as exc:
            message = tr("Настройки не сохранены: {0}", exc)
            self.status_label.setText(message)
            self.save_failed.emit(message)
            return

        self.settings = settings
        self.load_error = None
        self._refresh_warning()
        self.status_label.setText(tr("Настройки сохранены: {0}", self.settings_path))
        self.settings_changed.emit(settings)


__all__ = ["SettingsView"]
