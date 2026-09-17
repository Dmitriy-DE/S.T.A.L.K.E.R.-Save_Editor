"""Small, dependency-free Qt theme for the Zone inspired desktop shell.

The palette is kept in this module so the visual layer can evolve without
leaking presentation rules into the parser or editor service.  It uses only
Qt's built-in Fusion style and a stylesheet; no fonts, icons, or network
assets are required at runtime.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


def _chrome_dir() -> Path:
    """Locate the bundled X-Ray UI chrome pack (in-repo and PyInstaller)."""

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidate = Path(meipass) / "assets" / "chrome" / "xray"
        if candidate.is_dir():
            return candidate
    return Path(__file__).resolve().parent.parent / "assets" / "chrome" / "xray"


def _chrome_url(name: str) -> str | None:
    """Return a Qt ``url()`` path for a chrome texture, or ``None`` if absent."""

    path = _chrome_dir() / name
    return path.as_posix() if path.is_file() else None


COLORS = {
    # Deep "bunker" grounds with a warm brass accent and an olive PDA green,
    # matching the trilogy's menu palette rather than a cool grey-green shell.
    "bg_base": "#0C0D0A",
    "bg_panel": "#15170F",
    "bg_elevated": "#1E2016",
    "bg_hover": "#2A2C1D",
    "border_subtle": "#2A2E20",
    "border": "#3B3D30",
    "border_focus": "#C69A3E",
    # ``olive`` is the primary accent token; it now carries the brass/amber
    # highlight used on active nav, headings and focus.
    "olive": "#C69A3E",
    "olive_dim": "#7D6127",
    "rust": "#A9532F",
    "warning": "#C89A3E",
    "error": "#B8492B",
    "success": "#7E8F3E",
    "text": "#D8D2BE",
    "text_secondary": "#8E8974",
    "text_disabled": "#5C5A4C",
}


def stylesheet() -> str:
    """Return the complete application stylesheet."""

    c = COLORS
    return _base_stylesheet(c) + _chrome_stylesheet(c)


def _base_stylesheet(c: dict[str, str]) -> str:
    return f"""
    QWidget {{
        background: {c['bg_base']};
        color: {c['text']};
        font-family: "Segoe UI", "Noto Sans", sans-serif;
        font-size: 13px;
    }}
    QMainWindow, QWidget#appRoot {{ background: {c['bg_base']}; }}
    QFrame#titleBar {{
        background: {c['bg_panel']};
        border-bottom: 1px solid {c['border']};
    }}
    QLabel#appTitle {{
        background: transparent;
        color: {c['text']};
        font-size: 18px;
        font-weight: 700;
        letter-spacing: 0.4px;
    }}
    QLabel#versionBadge, QLabel#sourceBadge, QLabel#integrityBadge,
    QLabel#formatBadge {{
        background: {c['bg_elevated']};
        border: 1px solid {c['border']};
        border-radius: 4px;
        color: {c['text_secondary']};
        padding: 4px 8px;
        font-family: "JetBrains Mono", "Cascadia Mono", monospace;
        font-size: 11px;
        font-weight: 600;
    }}
    QLabel#versionBadge {{ color: {c['olive']}; border-color: {c['olive_dim']}; }}
    QLabel#sourceBadge {{ color: {c['olive']}; }}
    QLabel#integrityBadge {{ color: {c['success']}; }}
    QLabel#formatBadge {{ color: {c['text_secondary']}; }}
    QFrame#metaBar {{
        background: {c['bg_panel']};
        border-bottom: 1px solid {c['border_subtle']};
    }}
    QLabel#metaFilename {{
        background: transparent;
        color: {c['text']};
        font-size: 14px;
        font-weight: 600;
    }}
    QLabel#metaDetails, QLabel#sourceLabel {{
        background: transparent;
        color: {c['text_secondary']};
        font-family: "JetBrains Mono", "Cascadia Mono", monospace;
        font-size: 11px;
    }}
    QFrame#sidebar {{
        background: {c['bg_panel']};
        border: 1px solid {c['border_subtle']};
        border-radius: 6px;
    }}
    QLabel#sidebarHeading, QLabel#sidebarStatus {{
        background: transparent;
        color: {c['text_secondary']};
        font-family: "JetBrains Mono", "Cascadia Mono", monospace;
        font-size: 10px;
        letter-spacing: 0.5px;
    }}
    QLabel#sidebarHeading {{ color: {c['olive']}; font-weight: 700; }}
    QPushButton#navButton {{
        background: transparent;
        border: 1px solid transparent;
        border-radius: 4px;
        color: {c['text_secondary']};
        padding: 9px 10px;
        text-align: left;
    }}
    QPushButton#navButton:hover {{
        background: {c['bg_hover']};
        color: {c['text']};
        border-color: {c['border']};
    }}
    QPushButton#navButton:checked {{
        background: {c['bg_elevated']};
        border-color: {c['olive_dim']};
        color: {c['olive']};
        font-weight: 600;
    }}
    QFrame#contentPanel {{
        background: {c['bg_panel']};
        border: 1px solid {c['border_subtle']};
        border-radius: 6px;
    }}
    QTabWidget::pane {{
        background: {c['bg_panel']};
        border: none;
    }}
    QFrame#metricCard {{
        background: {c['bg_elevated']};
        border: 1px solid {c['border']};
        border-radius: 5px;
    }}
    QLabel#metricCaption {{
        background: transparent;
        color: {c['text_secondary']};
        font-size: 11px;
        text-transform: uppercase;
    }}
    QLabel#metricValue {{
        background: transparent;
        color: {c['text']};
        font-family: "JetBrains Mono", "Cascadia Mono", monospace;
        font-size: 19px;
        font-weight: 700;
    }}
    QGroupBox {{
        background: {c['bg_panel']};
        border: 1px solid {c['border_subtle']};
        border-radius: 5px;
        margin-top: 12px;
        padding: 12px 10px 8px 10px;
    }}
    QGroupBox::title {{
        background: {c['bg_panel']};
        color: {c['olive']};
        left: 10px;
        padding: 0 5px;
    }}
    QLabel#statusLabel {{
        background: {c['bg_elevated']};
        border: 1px solid {c['border_subtle']};
        border-radius: 4px;
        color: {c['text_secondary']};
        padding: 6px 9px;
    }}
    QLabel#errorLabel {{
        background: #2A1B1A;
        border: 1px solid {c['error']};
        border-radius: 4px;
        color: #F0B0A4;
        padding: 7px 9px;
    }}
    QPushButton {{
        background: {c['bg_elevated']};
        border: 1px solid {c['border']};
        border-radius: 4px;
        color: {c['text']};
        padding: 7px 12px;
    }}
    QPushButton:hover {{ background: {c['bg_hover']}; border-color: {c['border_focus']}; }}
    QPushButton:pressed {{ background: {c['olive_dim']}; color: {c['bg_base']}; }}
    QPushButton:disabled {{ background: {c['bg_panel']}; color: {c['text_disabled']}; border-color: {c['border_subtle']}; }}
    QPushButton#supportButton {{
        background: {c['bg_elevated']};
        border: 1px solid {c['rust']};
        color: #D8BA8C;
        font-family: "DejaVu Sans Condensed", "Arial Narrow", sans-serif;
        font-size: 12px;
        padding: 5px 10px;
    }}
    QPushButton#supportButton:hover {{
        background: {c['bg_hover']};
        border-color: #FFD23F;
        color: #FFD23F;
    }}
    QDialog#supportDialog {{
        background: {c['bg_panel']};
        border: 1px solid {c['rust']};
    }}
    QLabel#supportTitle {{
        background: transparent;
        color: #FFD23F;
        font-family: "DejaVu Sans Condensed", "Arial Narrow", sans-serif;
        font-size: 18px;
        font-weight: 700;
        letter-spacing: 0.5px;
    }}
    QLabel#supportIntro {{ color: {c['text_secondary']}; }}
    QLabel#supportMethod {{
        background: transparent;
        color: #D4A64B;
        font-family: "DejaVu Sans Condensed", "Arial Narrow", sans-serif;
        font-size: 14px;
        font-weight: 700;
    }}
    QLabel#supportDetail {{
        background: transparent;
        color: {c['text_secondary']};
        font-size: 12px;
    }}
    QLineEdit#supportValue {{
        background: {c['bg_base']};
        border: 1px solid {c['rust']};
        color: #D8BA8C;
        font-family: "JetBrains Mono", "Cascadia Mono", monospace;
        padding: 6px 8px;
    }}
    QPushButton#supportCopyButton, QPushButton#supportCloseButton {{
        border-color: {c['rust']};
        color: #E3C7B2;
        padding: 6px 10px;
    }}
    QPushButton#supportCopyButton:hover, QPushButton#supportCloseButton:hover {{
        border-color: #FFD23F;
        color: #FFD23F;
    }}
    QLineEdit, QSpinBox, QComboBox {{
        background: {c['bg_base']};
        border: 1px solid {c['border']};
        border-radius: 4px;
        color: {c['text']};
        padding: 6px 8px;
        selection-background-color: {c['olive_dim']};
    }}
    QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{ border-color: {c['border_focus']}; }}
    QTableView, QTableWidget, QListView {{
        background: {c['bg_base']};
        alternate-background-color: {c['bg_panel']};
        border: 1px solid {c['border_subtle']};
        gridline-color: {c['border_subtle']};
        selection-background-color: {c['olive_dim']};
        selection-color: {c['text']};
    }}
    QHeaderView::section {{
        background: {c['bg_elevated']};
        border: none;
        border-bottom: 1px solid {c['border']};
        color: {c['text_secondary']};
        font-size: 11px;
        font-weight: 600;
        padding: 7px 6px;
    }}
    QScrollBar:vertical {{ background: {c['bg_panel']}; width: 10px; margin: 0; }}
    QScrollBar::handle:vertical {{ background: {c['border']}; border-radius: 4px; min-height: 24px; }}
    QScrollBar::handle:vertical:hover {{ background: {c['olive_dim']}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QProgressBar {{
        background: {c['bg_base']};
        border: 1px solid {c['border']};
        border-radius: 4px;
        color: {c['text']};
        text-align: center;
    }}
    QProgressBar::chunk {{ background: {c['olive_dim']}; border-radius: 3px; }}
    QToolTip {{ background: {c['bg_elevated']}; border: 1px solid {c['border_focus']}; color: {c['text']}; }}
    """


def _chrome_stylesheet(c: dict[str, str]) -> str:
    """Overlay the real X-Ray UI textures (panels, buttons) when bundled.

    These crops come from the game's own ``ui_common`` atlas, so the panels
    and buttons are drawn from the same elements as the game.  When the pack
    is absent (e.g. a minimal checkout) the flat token styling above stands.
    """

    frame = _chrome_url("frame.png")
    field = _chrome_url("frame_thin.png")
    button = _chrome_url("button.png")
    button_hover = _chrome_url("button_hover.png")
    button_press = _chrome_url("button_press.png")
    button_disabled = _chrome_url("button_disabled.png")
    check_off = _chrome_url("check_off.png")
    check_on = _chrome_url("check_on.png")
    if not (frame and field and button and button_hover and button_press and button_disabled):
        return ""
    check_css = ""
    if check_off and check_on:
        check_css = f"""
    QCheckBox::indicator {{
        width: 18px; height: 18px;
        border-image: url("{check_off}") 6 6 6 6 stretch stretch;
        border-width: 6px;
    }}
    QCheckBox::indicator:checked {{
        border-image: url("{check_on}") 6 6 6 6 stretch stretch;
        border-width: 6px;
    }}
    """
    return f"""
    QFrame#sidebar, QFrame#contentPanel {{
        border-image: url("{frame}") 32 32 32 32 stretch stretch;
        border-width: 14px;
        border-radius: 0;
        background: {c['bg_panel']};
    }}
    QPushButton {{
        border-image: url("{button}") 0 8 0 8 stretch stretch;
        border-width: 0px 8px;
        border-radius: 0;
        background: transparent;
        color: #ECDFC2;
        padding: 7px 16px;
        min-height: 24px;
    }}
    QPushButton:hover {{
        border-image: url("{button_hover}") 0 8 0 8 stretch stretch;
        color: #FFE7A6;
    }}
    QPushButton:pressed {{
        border-image: url("{button_press}") 0 8 0 8 stretch stretch;
        color: #FFFFFF;
    }}
    QPushButton:disabled {{
        border-image: url("{button_disabled}") 0 8 0 8 stretch stretch;
        color: {c['text_disabled']};
    }}
    QPushButton#navButton {{
        border-image: none;
        border: 1px solid transparent;
        background: transparent;
        min-height: 0;
    }}
    QPushButton#navButton:checked {{
        border-image: none;
        border: 1px solid {c['olive_dim']};
        background: {c['bg_elevated']};
    }}
    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
        border-image: url("{field}") 10 10 10 10 stretch stretch;
        border-width: 8px;
        border-radius: 0;
        background: {c['bg_base']};
        color: {c['text']};
        padding: 3px 8px;
        selection-background-color: {c['olive_dim']};
    }}
    QComboBox QAbstractItemView {{
        background: {c['bg_elevated']};
        border: 1px solid {c['border']};
        selection-background-color: {c['olive_dim']};
        selection-color: {c['bg_base']};
    }}
    QScrollBar:vertical {{
        background: {c['bg_base']}; width: 14px; margin: 0; border: 1px solid {c['border_subtle']};
    }}
    QScrollBar::handle:vertical {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {c['border']}, stop:0.5 {c['olive_dim']}, stop:1 {c['border']});
        min-height: 24px; border: 1px solid {c['border']};
    }}
    QScrollBar::handle:vertical:hover {{ background: {c['olive_dim']}; }}
    QScrollBar:horizontal {{
        background: {c['bg_base']}; height: 14px; margin: 0; border: 1px solid {c['border_subtle']};
    }}
    QScrollBar::handle:horizontal {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {c['border']}, stop:0.5 {c['olive_dim']}, stop:1 {c['border']});
        min-width: 24px; border: 1px solid {c['border']};
    }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
    {check_css}
    """


def apply_theme(app: QApplication | None) -> None:
    """Apply the Zone palette to an existing QApplication instance."""

    if app is None:
        return
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(COLORS["bg_base"]))
    palette.setColor(QPalette.ColorRole.Base, QColor(COLORS["bg_base"]))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(COLORS["bg_panel"]))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(COLORS["text"]))
    palette.setColor(QPalette.ColorRole.Text, QColor(COLORS["text"]))
    palette.setColor(QPalette.ColorRole.Button, QColor(COLORS["bg_elevated"]))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(COLORS["text"]))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(COLORS["olive_dim"]))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(COLORS["text"]))
    app.setPalette(palette)
    app.setStyleSheet(stylesheet())


__all__ = ["COLORS", "apply_theme", "stylesheet"]
