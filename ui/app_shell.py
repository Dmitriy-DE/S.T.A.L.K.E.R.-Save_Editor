"""Reference shell shared by the desktop screens."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .style_components import TextureFrame, action_button


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
    _destination_icons = ("▣", "☁", "◷", "⚙")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("referenceShell")
        self._active_destination = "library"
        self.navigation_buttons: list[QPushButton] = []
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = TextureFrame(self, asset="header_panorama.png")
        header.setObjectName("referenceHeader")
        header.setFixedHeight(122)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(46, 14, 30, 0)
        header_layout.setSpacing(10)

        brand = QVBoxLayout()
        brand.setContentsMargins(0, 0, 20, 10)
        brand.setSpacing(2)
        title_row = QHBoxLayout()
        title_row.setSpacing(12)
        title = QLabel("S.T.A.L.K.E.R. — SAVE EDITOR", header)
        title.setObjectName("referenceBrand")
        title_row.addWidget(title)
        version = QLabel("v0.5.21", header)
        version.setObjectName("referenceVersion")
        title_row.addWidget(version, 0, Qt.AlignmentFlag.AlignVCenter)
        title_row.addStretch(1)
        brand.addLayout(title_row)
        subtitle = QLabel("РЕДАКТОР СОХРАНЕНИЙ ДЛЯ ВСЕЙ СЕРИИ S.T.A.L.K.E.R.", header)
        subtitle.setObjectName("referenceSubtitle")
        brand.addWidget(subtitle)
        brand_host = QWidget(header)
        brand_host.setFixedWidth(500)
        brand_host.setLayout(brand)
        header_layout.addWidget(brand_host)

        nav = QHBoxLayout()
        nav.setContentsMargins(0, 0, 0, 0)
        nav.setSpacing(4)
        for key, label, icon in zip(
            self._destination_keys,
            self.destination_names,
            self._destination_icons,
            strict=True,
        ):
            button = QPushButton(label, header)
            button.setObjectName("globalNav")
            button.setProperty("destination", key)
            button.setIcon(self._navigation_icon(icon))
            button.setIconSize(QSize(19, 19))
            button.setCheckable(True)
            button.clicked.connect(lambda _checked=False, dest=key: self.set_active_destination(dest))
            nav.addWidget(button)
            self.navigation_buttons.append(button)
        self.global_navigation = nav
        header_layout.addLayout(nav)
        header_layout.setAlignment(nav, Qt.AlignmentFlag.AlignBottom)

        support = action_button("♡  ПОДДЕРЖАТЬ ПРОЕКТ", header, kind="support", object_name="supportProject")
        self.support_button = support
        support.setFixedHeight(45)
        support.setFixedWidth(180)
        support.clicked.connect(self.support_requested)
        header_layout.addWidget(support, 0, Qt.AlignmentFlag.AlignBottom)

        window_controls = QHBoxLayout()
        window_controls.setContentsMargins(2, 0, 0, 0)
        window_controls.setSpacing(3)
        for label in ("—", "□", "×"):
            control = QPushButton(label, header)
            control.setObjectName("windowControl")
            control.setFixedSize(28, 26)
            if label == "×":
                control.clicked.connect(self.close_requested)
            window_controls.addWidget(control)
        header_layout.addLayout(window_controls)
        header_layout.setAlignment(window_controls, Qt.AlignmentFlag.AlignTop)
        header_layout.addStretch(1)
        root.addWidget(header)

        self.content_host = TextureFrame(
            self,
            asset="surface_tile.png",
            tiled=True,
            overlay_alpha=74,
            draw_border=False,
        )
        self.content_host.setObjectName("referenceContent")
        self.content_host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._content_layout = QVBoxLayout(self.content_host)
        self._content_layout.setContentsMargins(32, 0, 32, 20)
        self._content_layout.setSpacing(0)
        root.addWidget(self.content_host, 1)

        footer = QFrame(self)
        footer.setObjectName("referenceFooter")
        footer.setFixedHeight(43)
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(32, 8, 32, 8)
        footer_layout.setSpacing(16)
        self.footer_hints = QLabel(
            "Enter  Открыть    I  Импорт    R  Обновить    F  Фильтр    Esc  Назад",
            footer,
        )
        self.footer_hints.setObjectName("footerHints")
        footer_layout.addWidget(self.footer_hints)
        footer_layout.addStretch(1)
        self.footer_status = QLabel("CORE: READY  |  CRC / SHA / BACKUP ВКЛЮЧЕНЫ", footer)
        self.footer_status.setObjectName("footerStatus")
        footer_layout.addWidget(self.footer_status)
        root.addWidget(footer)

        self.set_active_destination("library")

    @staticmethod
    def _navigation_icon(glyph: str) -> QIcon:
        """Keep the glyph visual while preserving the public button label."""

        pixmap = QPixmap(24, 24)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setPen(Qt.GlobalColor.white)
        font = painter.font()
        font.setPixelSize(17)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, glyph)
        painter.end()
        return QIcon(pixmap)

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


__all__ = ["AppShell"]
