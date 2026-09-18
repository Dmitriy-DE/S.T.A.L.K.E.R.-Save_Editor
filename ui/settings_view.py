"""Manual save-location settings for the Qt shell."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from editor.platforms import installed_games, save_directories, steam_roots
from editor.releases import official_releases
from editor.settings import PathSettings, missing_manual_paths, save_settings


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
        self._load_fields()
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
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.steam_root_edit = QLineEdit()
        self.steam_root_edit.setPlaceholderText("Не задано — использовать автопоиск")
        self.steam_hint = self._hint_label()
        form.addRow("Корень Steam", self._path_row(self.steam_root_edit, self.steam_hint))
        layout.addLayout(form)

        actions = QHBoxLayout()
        self.save_button = QPushButton("Сохранить настройки")
        self.save_button.clicked.connect(self.save)
        actions.addWidget(self.save_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        found_caption = QLabel("Автопоиск нашёл (все игры сразу — выбирать не нужно):")
        found_caption.setWordWrap(True)
        layout.addWidget(found_caption)
        self.found_all_label = QLabel("Сканирую…")
        self.found_all_label.setWordWrap(True)
        self.found_all_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.found_all_label.setStyleSheet("color: palette(mid);")
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

    def _hint_label(self) -> QLabel:
        label = QLabel("")
        label.setWordWrap(True)
        label.setObjectName("discoveryHint")
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        font = label.font()
        font.setPointSizeF(max(7.0, font.pointSizeF() - 1.0))
        label.setFont(font)
        label.setStyleSheet("color: palette(mid);")
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

    def _set_hint(self, label: QLabel, discovered: Path | None) -> None:
        if discovered is not None:
            label.setText(f"Автопоиск: {discovered}")
        else:
            label.setText("Автопоиск: ничего не найдено — задай путь вручную")

    def _refresh_hints(self) -> None:
        try:
            self._set_hint(self.steam_hint, self._discover_steam_root())
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
            if game is None and save is None:
                continue
            parts = [release.title]
            if save is not None:
                parts.append(f"сейвы: {save}")
            elif game is not None:
                parts.append(f"игра: {game}")
            lines.append(" — ".join(parts))
        if len(lines) == 1:
            lines.append("Установленных игр не найдено.")
        self.found_all_label.setText("\n".join(lines))

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
        return self.settings.with_steam_root(
            self._path_from_text(self.steam_root_edit.text(), "Корень Steam")
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
