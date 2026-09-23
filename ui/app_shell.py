"""Reference shell shared by the desktop screens."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QPoint, QSize, Qt, Signal
from PySide6.QtGui import QFont, QIcon, QKeySequence, QMouseEvent, QShortcut
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .style_components import TextureFrame, action_button, key_hint


@dataclass(frozen=True)
class FooterAction:
    """One visible footer hint paired with the shortcut that executes it."""

    key: str
    label: str
    callback: Callable[[], None]
    shortcut: QShortcut


class _ChromeHeader(TextureFrame):
    """Frameless-window header with drag and double-click maximize behavior."""

    def __init__(self, parent: QWidget, *, asset: str) -> None:
        super().__init__(
            parent,
            asset=asset,
            overlay_alpha=0,
            draw_border=False,
        )
        self._drag_offset: QPoint | None = None
        self._controls_host: QWidget | None = None

    def set_controls_host(self, host: QWidget) -> None:
        self._controls_host = host
        self._position_controls()

    def _position_controls(self) -> None:
        if self._controls_host is not None:
            self._controls_host.move(self.width() - self._controls_host.width() - 10, 8)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        self._position_controls()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton and not self.window().isMaximized():
            self._drag_offset = event.globalPosition().toPoint() - self.window().frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt override
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.window().move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt override
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton:
            window = self.window()
            if window.isMaximized():
                window.showNormal()
            else:
                window.showMaximized()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class AppShell(QWidget):
    """A stable chrome frame with global navigation and a content slot.

    The shell deliberately knows nothing about saves or capabilities.  Views
    are injected into ``content_host`` by ``MainWindow`` and retain ownership
    of all domain state.
    """

    destination_requested = Signal(str)
    support_requested = Signal()
    close_requested = Signal()

    destination_names = (
        "ЛОКАЛЬНЫЕ СОХРАНЕНИЯ",
        "STEAM CLOUD",
        "ИСТОРИЯ",
        "НАСТРОЙКИ",
    )
    _destination_keys = ("library", "cloud", "history", "settings")
    _destination_icons = ("library", "cloud", "history", "settings")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("referenceShell")
        self._active_destination = "library"
        self.navigation_buttons: list[QPushButton] = []
        self.footer_actions: tuple[FooterAction, ...] = ()
        self._footer_shortcuts: list[QShortcut] = []
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = _ChromeHeader(self, asset="header_panorama.png")
        self.header = header
        header.setObjectName("referenceHeader")
        header.setFixedHeight(122)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(32, 6, 36, 0)
        header_layout.setSpacing(0)

        brand = QVBoxLayout()
        brand.setContentsMargins(19, 21, 14, 10)
        brand.setSpacing(2)
        title_row = QHBoxLayout()
        title_row.setSpacing(9)
        title = QLabel("S.T.A.L.K.E.R. — SAVE EDITOR", header)
        title.setObjectName("referenceBrand")
        title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)
        brand_font = QFont(title.font())
        brand_font.setPointSize(46)
        brand_font.setStretch(68)
        title.setFont(brand_font)
        title_row.addWidget(title)
        version = QLabel("v0.5.21", header)
        version.setObjectName("referenceVersion")
        title_row.addWidget(version, 0, Qt.AlignmentFlag.AlignBottom)
        title_row.addStretch(1)
        brand.addLayout(title_row)
        subtitle = QLabel("РЕДАКТОР СОХРАНЕНИЙ ДЛЯ ВСЕЙ СЕРИИ S.T.A.L.K.E.R.", header)
        subtitle.setObjectName("referenceSubtitle")
        brand.addWidget(subtitle)
        brand_host = QFrame(header)
        brand_host.setObjectName("referenceBrandPanel")
        brand_host.setFixedSize(498, 108)
        brand_host.setLayout(brand)
        header_layout.addWidget(brand_host)

        nav = QHBoxLayout()
        nav.setContentsMargins(0, 0, 0, 0)
        nav.setSpacing(19)
        nav_widths = (237, 158, 102, 162)
        nav_minimum_widths = (176, 116, 78, 122)
        for key, label, icon, width, minimum_width in zip(
            self._destination_keys,
            self.destination_names,
            self._destination_icons,
            nav_widths,
            nav_minimum_widths,
            strict=True,
        ):
            button = QPushButton(label, header)
            button.setObjectName("globalNav")
            button.setProperty("destination", key)
            button.setIcon(self._navigation_icon(icon))
            button.setIconSize(QSize(19, 19))
            button.setMinimumWidth(minimum_width)
            button.setMaximumWidth(width)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            button.setCheckable(True)
            button.clicked.connect(lambda _checked=False, dest=key: self.set_active_destination(dest))
            nav.addWidget(button)
            self.navigation_buttons.append(button)
        self.global_navigation = nav
        header_layout.addLayout(nav)
        header_layout.setAlignment(nav, Qt.AlignmentFlag.AlignBottom)
        header_layout.addStretch(1)

        support_host = QWidget(header)
        support_host.setFixedSize(180, 45)
        support = action_button(
            "♡  ПОДДЕРЖАТЬ ПРОЕКТ",
            support_host,
            kind="support",
            object_name="supportProject",
        )
        support.setGeometry(0, 0, 180, 32)
        self.support_button = support
        support.clicked.connect(self.support_requested)
        header_layout.addWidget(support_host, 0, Qt.AlignmentFlag.AlignBottom)

        controls_host = QWidget(header)
        controls_host.setObjectName("windowControlsHost")
        controls_host.setFixedSize(100, 26)
        window_controls = QHBoxLayout(controls_host)
        window_controls.setContentsMargins(0, 0, 0, 0)
        window_controls.setSpacing(3)
        controls = []
        for label in ("—", "□", "×"):
            control = QPushButton(label, controls_host)
            control.setObjectName("windowControl")
            control.setFixedSize(30, 26)
            controls.append(control)
            window_controls.addWidget(control)
        self.minimize_button, self.maximize_button, self.close_button = controls
        self.minimize_button.clicked.connect(self._minimize_window)
        self.maximize_button.clicked.connect(self.toggle_maximized)
        self.close_button.clicked.connect(self.close_requested)
        header.set_controls_host(controls_host)
        root.addWidget(header)

        self.content_host = TextureFrame(
            self,
            asset="surface_tile.png",
            tiled=True,
            overlay_alpha=28,
            draw_border=False,
        )
        self.content_host.setObjectName("referenceContent")
        self.content_host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._content_layout = QVBoxLayout(self.content_host)
        self._content_layout.setContentsMargins(24, 0, 32, 10)
        self._content_layout.setSpacing(0)
        root.addWidget(self.content_host, 1)
        footer = QFrame(self)
        footer.setObjectName("referenceFooter")
        footer.setFixedHeight(52)
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(32, 8, 32, 8)
        footer_layout.setSpacing(12)
        self.footer_action_host = QWidget(footer)
        self.footer_action_host.setObjectName("footerActions")
        self._footer_action_layout = QHBoxLayout(self.footer_action_host)
        self._footer_action_layout.setContentsMargins(0, 0, 0, 0)
        self._footer_action_layout.setSpacing(10)
        footer_layout.addWidget(self.footer_action_host)
        # Kept as a hidden compatibility handle for older callers. Visible
        # hints are the keycap widgets above, paired with live QShortcuts.
        self.footer_hints = QLabel("", footer)
        self.footer_hints.setObjectName("footerHints")
        self.footer_hints.hide()
        footer_layout.addStretch(1)
        self.footer_status = QLabel("CORE: READY  |  CRC / SHA / BACKUP ВКЛЮЧЕНЫ", footer)
        self.footer_status.setObjectName("footerStatus")
        footer_layout.addWidget(self.footer_status)
        root.addWidget(footer)

        self.set_active_destination("library")
        self._sync_maximize_button()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        compact = self.width() < 1490
        for button in self.navigation_buttons:
            if button.property("compactNav") == compact:
                continue
            button.setProperty("compactNav", compact)
            button.style().unpolish(button)
            button.style().polish(button)
            button.updateGeometry()

    def _minimize_window(self) -> None:
        self.window().showMinimized()

    def toggle_maximized(self) -> None:
        window = self.window()
        if window.isMaximized():
            window.showNormal()
        else:
            window.showMaximized()
        self._sync_maximize_button()

    def _sync_maximize_button(self) -> None:
        if hasattr(self, "maximize_button"):
            self.maximize_button.setText("❐" if self.window().isMaximized() else "□")

    @staticmethod
    def _navigation_icon(icon_name: str) -> QIcon:
        asset = Path(__file__).resolve().parents[1] / "assets" / "ui" / "shell_icons" / f"{icon_name}.svg"
        return QIcon(str(asset)) if asset.is_file() else QIcon()

    @property
    def active_destination(self) -> str:
        return self._active_destination

    def set_active_destination(self, destination: str, *, emit: bool = True) -> None:
        if destination not in self._destination_keys:
            return
        changed = destination != self._active_destination
        self._active_destination = destination
        for button in self.navigation_buttons:
            button.setChecked(button.property("destination") == destination)
        if changed and emit:
            self.destination_requested.emit(destination)

    def set_content(self, widget: QWidget) -> None:
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            old = item.widget() if item is not None else None
            if old is not None:
                old.setParent(None)
        self._content_layout.addWidget(widget)

    def set_footer_actions(
        self,
        actions: Sequence[tuple[str, str, Callable[[], None]]],
    ) -> None:
        """Render only shortcuts that are wired to a live callback."""

        old_shortcuts, self._footer_shortcuts = self._footer_shortcuts, []
        for shortcut in old_shortcuts:
            try:
                shortcut.setEnabled(False)
                shortcut.deleteLater()
            except RuntimeError:
                # Qt may already have destroyed a shortcut queued by a prior
                # screen transition; its visible hint is already gone.
                continue
        rendered: list[FooterAction] = []
        for key, label, callback in actions:
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
            shortcut.activated.connect(callback)
            self._footer_shortcuts.append(shortcut)
            rendered.append(FooterAction(key, label, callback, shortcut))
        self.footer_actions = tuple(rendered)
        while self._footer_action_layout.count():
            item = self._footer_action_layout.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.deleteLater()
        for index, action in enumerate(rendered):
            if index:
                separator = QFrame(self.footer_action_host)
                separator.setObjectName("footerActionSeparator")
                separator.setFrameShape(QFrame.Shape.VLine)
                self._footer_action_layout.addWidget(separator)
            self._footer_action_layout.addWidget(
                key_hint(action.key, action.label, self.footer_action_host)
            )


__all__ = ["AppShell"]
