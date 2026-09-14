"""Manual save-location settings for the Qt shell."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from editor.settings import PathSettings, missing_manual_paths, save_settings

from .save_slots_view import GAME_IDS, GAME_TITLES


class SettingsView(QWidget):
    """Edit and persist manual Steam/game/save roots without touching game files."""

    settings_changed = Signal(object)
    save_failed = Signal(str)

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
        self._build_ui()
        self._load_game_fields()
        self._refresh_warning()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        intro = QLabel(
            "Ручные пути имеют приоритет: папка сохранений → папка игры → "
            "корень Steam. Пути сохраняются локально; программа ничего не пишет "
            "в каталог игры."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()
        self.steam_root_edit = QLineEdit()
        self.steam_root_edit.setPlaceholderText("Не задано — использовать автопоиск")
        form.addRow("Корень Steam", self._path_row(self.steam_root_edit))

        self.game_combo = QComboBox()
        for game_id in GAME_IDS:
            self.game_combo.addItem(GAME_TITLES[game_id], game_id)
        self.game_combo.currentIndexChanged.connect(self._load_game_fields)
        form.addRow("Игра", self.game_combo)

        self.game_root_edit = QLineEdit()
        self.game_root_edit.setPlaceholderText("Папка установленной игры")
        form.addRow("Папка игры", self._path_row(self.game_root_edit))

        self.save_root_edit = QLineEdit()
        self.save_root_edit.setPlaceholderText("Папка с сохранениями")
        form.addRow("Папка сохранений", self._path_row(self.save_root_edit))
        layout.addLayout(form)

        actions = QHBoxLayout()
        self.save_button = QPushButton("Сохранить настройки")
        self.save_button.clicked.connect(self.save)
        actions.addWidget(self.save_button)
        self.clear_button = QPushButton("Очистить пути выбранной игры")
        self.clear_button.clicked.connect(self.clear_current_game)
        actions.addWidget(self.clear_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.status_label)
        self.warning_label = QLabel("")
        self.warning_label.setWordWrap(True)
        self.warning_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.warning_label)
        layout.addStretch(1)

    def _path_row(self, edit: QLineEdit) -> QWidget:
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
        return row

    @property
    def selected_game_id(self) -> str:
        value = self.game_combo.currentData()
        return str(value)

    def _load_game_fields(self, _index: int = -1) -> None:
        game_id = self.selected_game_id
        game_root = self.settings.game_root(game_id)
        save_root = self.settings.save_root(game_id)
        self.steam_root_edit.setText(
            str(self.settings.steam_root) if self.settings.steam_root is not None else ""
        )
        self.game_root_edit.setText(str(game_root) if game_root is not None else "")
        self.save_root_edit.setText(str(save_root) if save_root is not None else "")

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
        game_id = self.selected_game_id
        settings = self.settings.with_steam_root(
            self._path_from_text(self.steam_root_edit.text(), "Корень Steam")
        )
        settings = settings.with_game_root(
            game_id,
            self._path_from_text(self.game_root_edit.text(), "Папка игры"),
        )
        return settings.with_save_root(
            game_id,
            self._path_from_text(self.save_root_edit.text(), "Папка сохранений"),
        )

    def clear_current_game(self) -> None:
        self.game_root_edit.clear()
        self.save_root_edit.clear()

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
