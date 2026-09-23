"""Manual save-location settings for the Qt shell."""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from editor.platforms import installed_games, save_directories, steam_roots
from editor.releases import official_releases
from editor.settings import PathSettings, missing_manual_paths, save_settings

from .style_components import action_button, panel, section_header


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
    diagnostics_requested = Signal()
    support_requested = Signal()

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
        # Safety switches are policy, not preferences.  The visible rows below
        # are deliberately labels, so no caller can turn off backup, warning,
        # confirmation, or uncertain-write protection through this page.
        self.core_safety_read_only = True
        self._build_ui()
        self._load_fields()
        self._refresh_warning()

    def _build_ui(self) -> None:
        self.setObjectName("settingsView")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 20, 0, 0)
        layout.setSpacing(10)

        heading = QHBoxLayout()
        heading.addWidget(QLabel("НАСТРОЙКИ", self))
        subtitle = QLabel("Обычно ничего менять не нужно — редактор находит всё автоматически.", self)
        subtitle.setObjectName("screenSubtitle")
        heading.addWidget(subtitle)
        heading.addStretch(1)
        layout.addLayout(heading)

        body = QHBoxLayout()
        body.setSpacing(10)
        rail = panel(self, object_name="settingsCategoryRail")
        rail_layout = QVBoxLayout(rail)
        rail_layout.setContentsMargins(10, 12, 10, 12)
        rail_layout.addWidget(QLabel("РАЗДЕЛЫ", rail))
        rule = QFrame(rail)
        rule.setFrameShape(QFrame.Shape.HLine)
        rail_layout.addWidget(rule)
        self.category_buttons: list[QPushButton] = []
        category_names = (
            "ОБЩИЕ",
            "ПУТИ И АВТОПОИСК",
            "РЕЗЕРВНЫЕ КОПИИ",
            "STEAM CLOUD",
            "ОБНОВЛЕНИЯ И ДИАГНОСТИКА",
            "ИНТЕРФЕЙС",
            "ПОДДЕРЖКА",
        )
        for index, name in enumerate(category_names):
            button = QPushButton(name, rail)
            button.setObjectName("settingsCategoryButton")
            button.setCheckable(True)
            button.setAutoExclusive(True)
            button.clicked.connect(lambda _checked=False, selected=index: self._select_category(selected))
            rail_layout.addWidget(button)
            self.category_buttons.append(button)
        rail_layout.addStretch(1)
        body.addWidget(rail, 17)

        self.settings_stack = _SettingsCategoryStack()
        self.settings_scroll = QScrollArea(self)
        self.settings_scroll.setObjectName("settingsScroll")
        self.settings_scroll.setWidgetResizable(True)
        self.settings_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.settings_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.settings_scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.settings_content = QWidget(self.settings_scroll)
        self.settings_content.setObjectName("settingsContent")
        settings_sections = QVBoxLayout(self.settings_content)
        settings_sections.setContentsMargins(0, 0, 0, 0)
        settings_sections.setSpacing(10)
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
        self._build_simple_panel(self.interface_panel, "ИНТЕРФЕЙС", "Размеры и визуальная тема следуют каноническому интерфейсу.")
        self._build_simple_panel(self.support_panel, "ПОДДЕРЖКА", "Спасибо, что сохраняешь историю Зоны. Кнопка поддержки доступна в верхней панели.")
        self.support_action_button = action_button("ПОДДЕРЖАТЬ ПРОЕКТ", self.support_panel, kind="primary")
        self.support_action_button.clicked.connect(self.support_requested)
        support_layout = self.support_panel.layout()
        if support_layout is None:
            raise RuntimeError("support settings panel has no layout")
        support_layout.addWidget(self.support_action_button)
        for page in (
            self.general_panel,
            self.paths_panel,
            self.cloud_panel,
            self.diagnostics_panel,
            self.backups_panel,
            self.interface_panel,
            self.support_panel,
        ):
            self.settings_stack.addWidget(page)
            settings_sections.addWidget(page)
        for page in (self.backups_panel, self.interface_panel, self.support_panel):
            page.setVisible(False)
        settings_sections.addStretch(1)
        self.settings_scroll.setWidget(self.settings_content)
        self._settings_pages = (
            self.general_panel,
            self.paths_panel,
            self.backups_panel,
            self.cloud_panel,
            self.diagnostics_panel,
            self.interface_panel,
            self.support_panel,
        )
        body.addWidget(self.settings_scroll, 83)
        body.setStretch(0, 17)
        body.setStretch(1, 83)
        layout.addLayout(body, 1)

        actions = QHBoxLayout()
        self.save_button = action_button("СОХРАНИТЬ НАСТРОЙКИ", self, kind="primary")
        self.save_button.clicked.connect(self.save)
        actions.addWidget(self.save_button, 2)
        self.reset_button = action_button("СБРОСИТЬ", self)
        self.reset_button.clicked.connect(self._reset_fields)
        actions.addWidget(self.reset_button, 1)
        self.defaults_button = action_button("ПО УМОЛЧАНИЮ", self)
        self.defaults_button.clicked.connect(self._set_defaults)
        actions.addWidget(self.defaults_button, 1)
        self.cancel_button = action_button("ОТМЕНА", self)
        self.cancel_button.clicked.connect(self._cancel_changes)
        actions.addWidget(self.cancel_button, 1)
        layout.addLayout(actions)
        self._select_category(0)

    def _build_general_panel(self) -> None:
        layout = QVBoxLayout(self.general_panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.addWidget(section_header("ОБЩИЕ", "УПРАВЛЕНИЕ ОСНОВНЫМ ПОВЕДЕНИЕМ РЕДАКТОРА", self.general_panel))
        intro = QLabel(
            "Ручные пути имеют приоритет: папка сохранений → папка игры → корень Steam. "
            "Пути сохраняются локально; программа ничего не пишет в каталог игры."
        )
        intro.setWordWrap(True)
        # The helper remains available in the widget tree for accessibility,
        # while the canonical overview keeps the compact reference density.
        intro.setVisible(False)
        self.safety_labels = []
        for text in (
            "Автоматически проверять обновления — включено",
            "Показывать технические предупреждения — включено",
            "Подтверждать запись перед сохранением — включено",
            "При uncertain write не повторять автоматически — включено",
        ):
            label = QLabel("●  " + text, self.general_panel)
            label.setObjectName("settingsSafetyRow")
            self.safety_labels.append(label)
            layout.addWidget(label)
        layout.addStretch(1)

    def _build_paths_panel(self) -> None:
        layout = QVBoxLayout(self.paths_panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.addWidget(section_header("ПУТИ И АВТОПОИСК", "ПУТИ К ИГРАМ, СОХРАНЕНИЯМ И РЕСУРСАМ", self.paths_panel))
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.steam_root_edit = QLineEdit()
        self.steam_root_edit.setPlaceholderText("Не задано — использовать автопоиск")
        self.steam_hint = self._hint_label()
        form.addRow("Корень Steam", self._path_row(self.steam_root_edit, self.steam_hint))
        self.catalog_root_edit = QLineEdit()
        self.catalog_root_edit.setPlaceholderText("Не задано — использовать установленную игру/автопоиск")
        self.catalog_hint = self._hint_label()
        form.addRow("Каталог S.T.A.L.K.E.R. 2 (Zone Kit / Workshop)", self._path_row(self.catalog_root_edit, self.catalog_hint))
        layout.addLayout(form)
        found_heading = QLabel("Автопоиск нашёл (все игры сразу — выбирать не нужно):")
        found_heading.setVisible(False)
        layout.addWidget(found_heading)
        self.found_all_label = QLabel("Сканирую…")
        self.found_all_label.setObjectName("discoveryResults")
        self.found_all_label.setWordWrap(True)
        self.found_all_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.found_all_label.setVisible(False)
        layout.addWidget(self.found_all_label)
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.status_label)
        self.warning_label = QLabel("")
        self.warning_label.setWordWrap(True)
        self.warning_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.warning_label)
        layout.addStretch(1)

    def _build_backups_panel(self) -> None:
        layout = QVBoxLayout(self.backups_panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.addWidget(section_header("РЕЗЕРВНЫЕ КОПИИ", "ПРОВЕРЕННЫЙ BACKUP ПЕРЕД ЗАПИСЬЮ", self.backups_panel))
        label = QLabel("Каждая запись создаёт backup и journal с SHA-256. Восстановление доступно только после проверки записи.", self.backups_panel)
        label.setWordWrap(True)
        layout.addWidget(label)
        layout.addStretch(1)

    def _build_cloud_panel(self) -> None:
        layout = QVBoxLayout(self.cloud_panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.addWidget(section_header("STEAM CLOUD", "ИНТЕГРАЦИЯ СО STEAM CLOUD", self.cloud_panel))
        for text in (
            "Подключение: доступно по явному действию пользователя",
            "Режим: только по явному подтверждению",
            "Поведение при uncertain write: никогда не повторять автоматически",
        ):
            label = QLabel("●  " + text, self.cloud_panel)
            label.setObjectName("settingsSafetyRow")
            layout.addWidget(label)
        layout.addStretch(1)

    def _build_diagnostics_panel(self) -> None:
        layout = QVBoxLayout(self.diagnostics_panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.addWidget(section_header("ОБНОВЛЕНИЯ И ДИАГНОСТИКА", "ИНСТРУМЕНТЫ ДЛЯ ПОДДЕРЖКИ", self.diagnostics_panel))
        self.update_action_button = action_button("ПРОВЕРИТЬ ОБНОВЛЕНИЯ", self.diagnostics_panel)
        self.diagnostics_action_button = action_button("ПОКАЗАТЬ ЖУРНАЛ", self.diagnostics_panel)
        self.copy_diagnostics_button = action_button("СКОПИРОВАТЬ ДИАГНОСТИКУ", self.diagnostics_panel)
        self.update_action_button.clicked.connect(self.update_requested)
        self.diagnostics_action_button.clicked.connect(self.diagnostics_requested)
        self.copy_diagnostics_button.clicked.connect(self.diagnostics_requested)
        actions = QHBoxLayout()
        actions.setSpacing(8)
        actions.addWidget(self.update_action_button, 1)
        actions.addWidget(self.diagnostics_action_button, 1)
        actions.addWidget(self.copy_diagnostics_button, 1)
        layout.addLayout(actions)
        layout.addStretch(1)

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
        self._settings_pages[index].setVisible(True)
        if hasattr(self, "settings_scroll"):
            if index == 0:
                self.settings_scroll.verticalScrollBar().setValue(0)
            else:
                self.settings_scroll.ensureWidgetVisible(self._settings_pages[index], 0, 10)

    def _reset_fields(self) -> None:
        self.steam_root_edit.clear()
        self.catalog_root_edit.clear()
        self.status_label.setText("Пути сброшены в поля; нажми «Сохранить настройки», чтобы записать изменения.")

    def _set_defaults(self) -> None:
        self.steam_root_edit.clear()
        self.catalog_root_edit.clear()
        self.status_label.setText("Восстановлены значения по умолчанию; нажми «Сохранить настройки», чтобы применить их.")

    def _cancel_changes(self) -> None:
        self._load_fields()
        self.status_label.setText("Изменения отменены; сохранённые настройки восстановлены.")

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
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(edit, 1)
        browse = QPushButton("Выбрать…")
        browse.clicked.connect(lambda: self._choose_directory(edit))
        layout.addWidget(browse)
        clear = QPushButton("Очистить")
        clear.clicked.connect(edit.clear)
        layout.addWidget(clear)
        outer.addWidget(row)
        if hint is not None:
            outer.addWidget(hint)
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
            label.setText("●  НАЙДЕНО")
            label.setToolTip(f"Автопоиск: {discovered}")
        else:
            label.setText("●  НЕ НАЙДЕНО — использовать автопоиск")
            label.setToolTip("Автопоиск ничего не нашёл; можно задать путь вручную.")

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
        lines = [f"Корень Steam: {steam}" if steam else "Корень Steam: не найден"]
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
                parts.append(f"сейвы: {save}")
            if game is not None:
                parts.append(f"игра: {game}")
            if catalog is not None:
                parts.append(f"каталог: {catalog}")
            lines.append(" — ".join(parts))
        if len(lines) == 1:
            lines.append("Установленных игр не найдено.")
        details = "\n".join(lines)
        self.found_all_label.setToolTip(details)
        found_count = max(0, len(lines) - 1)
        self.found_all_label.setText(
            f"Автопоиск: Steam {'найден' if steam else 'не найден'} · "
            f"игр найдено: {found_count} (подробности — во всплывающей подсказке)"
        )

    def _choose_directory(self, edit: QLineEdit) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Выбрать каталог")
        if selected:
            edit.setText(selected)

    @staticmethod
    def _path_from_text(text: str, field: str) -> Path | None:
        value = text.strip()
        if not value:
            return None
        path = Path(value).expanduser()
        if not path.is_absolute():
            raise ValueError(f"{field}: укажи абсолютный путь")
        return path

    def _collect_settings(self) -> PathSettings:
        settings = self.settings.with_steam_root(
            self._path_from_text(self.steam_root_edit.text(), "Корень Steam")
        )
        return settings.with_catalog_root(
            "stalker2",
            self._path_from_text(
                self.catalog_root_edit.text(),
                "Каталог S.T.A.L.K.E.R. 2",
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
                f"Сохранённый путь исчез: {paths}. Выбери каталог заново; "
                "автопоиск снова доступен."
            )
        if not messages:
            messages.append(
                "Автопоиск используется, если ручной путь не задан или недоступен."
            )
        self.warning_label.setText("\n".join(messages))
        self.warning_label.setVisible(bool(self.load_error or missing))

    def save(self) -> None:
        try:
            settings = self._collect_settings()
            save_settings(settings, path=self.settings_path)
        except (OSError, TypeError, ValueError) as exc:
            message = f"Настройки не сохранены: {exc}"
            self.status_label.setText(message)
            self.save_failed.emit(message)
            return

        self.settings = settings
        self.load_error = None
        self._refresh_warning()
        self.status_label.setText(f"Настройки сохранены: {self.settings_path}")
        self.settings_changed.emit(settings)


__all__ = ["SettingsView"]
