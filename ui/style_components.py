"""Small Qt primitives shared by the reference-style shell and screens."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QWidget

_SHELL_ASSETS = Path(__file__).resolve().parents[1] / "assets" / "ui" / "s2_shell"


class TextureFrame(QFrame):
    """Paint a restrained decorative texture beneath ordinary child widgets."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        asset: str,
        tiled: bool = False,
        overlay_alpha: int = 158,
        draw_border: bool = True,
    ) -> None:
        super().__init__(parent)
        self._texture = QPixmap(str(_SHELL_ASSETS / asset))
        self._tiled = tiled
        self._overlay_alpha = overlay_alpha
        self._draw_border = draw_border

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        super().paintEvent(event)
        if self._texture.isNull():
            return
        painter = QPainter(self)
        if self._tiled:
            for y in range(0, self.height(), self._texture.height()):
                for x in range(0, self.width(), self._texture.width()):
                    painter.drawPixmap(x, y, self._texture)
        else:
            painter.drawPixmap(self.rect(), self._texture)
        painter.fillRect(self.rect(), QColor(7, 9, 8, self._overlay_alpha))
        if self._draw_border:
            painter.setPen(QColor(51, 56, 47, 210))
            painter.drawRect(self.rect().adjusted(0, 0, -1, -1))


def panel(parent: QWidget | None = None, *, object_name: str = "referencePanel") -> QFrame:
    frame = QFrame(parent)
    frame.setObjectName(object_name)
    return frame


def section_header(
    title: str,
    subtitle: str = "",
    parent: QWidget | None = None,
) -> QWidget:
    frame = panel(parent, object_name="sectionHeader")
    layout = QHBoxLayout(frame)
    layout.setContentsMargins(12, 8, 12, 8)
    layout.setSpacing(12)
    heading = QLabel(title, frame)
    heading.setObjectName("sectionHeading")
    layout.addWidget(heading)
    if subtitle:
        note = QLabel(subtitle, frame)
        note.setObjectName("sectionNote")
        note.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(note, 1)
    else:
        layout.addStretch(1)
    return frame


def action_button(
    text: str,
    parent: QWidget | None = None,
    *,
    kind: str = "neutral",
    object_name: str | None = None,
) -> QPushButton:
    button = QPushButton(text, parent)
    button.setObjectName(object_name or f"{kind}Button")
    button.setProperty("buttonKind", kind)
    return button


def primary_button(text: str, parent: QWidget | None = None) -> QPushButton:
    """Create the amber action used for a committed user intent."""

    return action_button(text, parent, kind="primary", object_name="primaryButton")


def status_chip(
    text: str,
    parent: QWidget | None = None,
    *,
    tone: str = "neutral",
) -> QLabel:
    label = QLabel(text, parent)
    label.setObjectName("statusChip")
    label.setProperty("tone", tone)
    return label


def key_hint(key: str, text: str, parent: QWidget | None = None) -> QWidget:
    frame = QWidget(parent)
    layout = QHBoxLayout(frame)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(5)
    key_label = QLabel(key, frame)
    key_label.setObjectName("keyHintKey")
    label = QLabel(text, frame)
    label.setObjectName("keyHintText")
    layout.addWidget(key_label)
    layout.addWidget(label)
    return frame


__all__ = [
    "TextureFrame",
    "action_button",
    "key_hint",
    "panel",
    "primary_button",
    "section_header",
    "status_chip",
]
