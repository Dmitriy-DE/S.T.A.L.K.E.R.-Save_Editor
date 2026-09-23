"""Tokenized, dependency-free Qt theme for the S.T.A.L.K.E.R. Save Editor.

The palette is kept in this module so the visual layer can evolve without
leaking presentation rules into the parser or editor service.  It uses only
Qt's built-in Fusion style and a stylesheet; no fonts, icons, or network
assets are required at runtime.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

PALETTE = {
    # Industrial S2-like grounds with an amber operational accent.
    "bg_base": "#0C0D0A",
    "bg_panel": "#101311",
    "bg_elevated": "#151814",
    "bg_hover": "#23261F",
    "border_subtle": "#242922",
    "border": "#33382F",
    "border_focus": "#D6A62D",
    # ``olive`` is the primary accent token; it now carries the brass/amber
    # highlight used on active nav, headings and focus.
    "olive": "#D6A62D",
    "olive_dim": "#8F6F22",
    "rust": "#A9532F",
    "warning": "#D6A62D",
    "error": "#D85A45",
    "success": "#7BCB62",
    "text": "#D8D2BE",
    "text_secondary": "#A29D90",
    "text_disabled": "#716F67",
    "text_read_only": "#C2BBA8",
    "warning_surface": "#322814",
    "error_surface": "#2A1B1A",
}

# Widget code consumes these semantic tokens instead of local visual constants.
COLORS = PALETTE
TYPOGRAPHY = {
    "body": '"Liberation Sans Narrow", "Ubuntu Sans", "Noto Sans", sans-serif',
    "heading": '"Liberation Sans Narrow", "Ubuntu Sans", "DejaVu Sans Condensed", sans-serif',
    "mono": '"Ubuntu Mono", "DejaVu Sans Mono", monospace',
}
SPACING = {"xs": 4, "sm": 8, "md": 12, "lg": 18}


def stylesheet() -> str:
    """Return the complete application stylesheet."""

    c = COLORS
    return _base_stylesheet(c) + _reference_stylesheet(c)


def _base_stylesheet(c: dict[str, str]) -> str:
    t = TYPOGRAPHY
    s = SPACING
    return f"""
    QWidget {{
        background: {c['bg_base']};
        color: {c['text']};
        font-family: {t['body']};
        font-size: 13px;
    }}
    QMainWindow, QWidget#appRoot {{ background: {c['bg_base']}; }}
    QWidget#launcher {{
        background: #090A08;
    }}
    QFrame#launcherHeader {{
        background: {c['bg_panel']};
        border: 1px solid {c['border']};
    }}
    QLabel#launcherBrand {{
        background: transparent;
        color: {c['olive']};
        font-family: "DejaVu Sans Condensed", "Arial Narrow", sans-serif;
        font-size: 22px;
        font-weight: 800;
        letter-spacing: 1px;
    }}
    QLabel#launcherTitle {{
        background: transparent;
        color: {c['text']};
        font-family: "DejaVu Sans Condensed", "Arial Narrow", sans-serif;
        font-size: 16px;
        font-weight: 700;
        letter-spacing: 1.4px;
    }}
    QLabel#launcherSubtitle, QLabel#launcherPanelHint {{
        background: transparent;
        color: {c['text_secondary']};
        font-size: 11px;
    }}
    QFrame#launcherGamesPanel, QFrame#launcherSavesPanel {{
        background: {c['bg_panel']};
        border: 1px solid {c['border']};
    }}
    QLabel#launcherPanelHeading {{
        background: transparent;
        color: {c['olive']};
        font-family: "JetBrains Mono", "Cascadia Mono", monospace;
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0.8px;
    }}
    QListWidget#launcherGameList {{
        background: {c['bg_base']};
        border: 1px solid {c['border_subtle']};
        outline: none;
    }}
    QListWidget#launcherGameList::item {{
        border-bottom: 1px solid {c['border_subtle']};
        color: {c['text_secondary']};
        padding: 13px 10px;
    }}
    QListWidget#launcherGameList::item:hover {{
        background: {c['bg_hover']};
        color: {c['text']};
    }}
    QListWidget#launcherGameList::item:selected {{
        background: {c['bg_elevated']};
        border-left: 3px solid {c['olive']};
        color: {c['olive']};
    }}
    QTableWidget#launcherSaveTable {{
        background: {c['bg_base']};
        border: 1px solid {c['border_subtle']};
        gridline-color: {c['border_subtle']};
        outline: none;
    }}
    QLabel#launcherStatus {{
        background: transparent;
        color: {c['text_secondary']};
        padding: 3px 0;
    }}
    QLabel#discoveryHint, QLabel#discoveryResults {{
        background: transparent;
        color: {c['text_secondary']};
    }}
    QLabel#launcherPathCount {{
        background: transparent;
        color: {c['olive_dim']};
        font-family: "JetBrains Mono", "Cascadia Mono", monospace;
        font-size: 10px;
    }}
    QPushButton#launcherPrimaryButton {{
        color: #1A180F;
        background: {c['olive']};
        border-color: {c['olive']};
        font-weight: 700;
    }}
    QPushButton#launcherPrimaryButton:hover {{
        background: #E0B457;
        border-color: #E0B457;
    }}
    QPushButton#launcherSecondaryButton, QPushButton#launcherCloudButton,
    QPushButton#launcherOpenButton, QPushButton#launcherBackButton {{
        color: {c['olive']};
        border-color: {c['olive_dim']};
    }}
    QPushButton#launcherBackButton {{ padding: 5px 10px; }}
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
        color: {c['text']};
        font-family: "JetBrains Mono", "Cascadia Mono", monospace;
        font-size: 11px;
        selection-background-color: {c['olive_dim']};
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
    QLabel#errorLabel, QLabel#cloudErrorLabel {{
        background: {c['error_surface']};
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
    QPushButton:focus {{ border: 2px solid {c['border_focus']}; }}
    QPushButton:pressed {{ background: {c['olive_dim']}; color: {c['bg_base']}; }}
    QPushButton:disabled {{ background: {c['bg_panel']}; color: {c['text_disabled']}; border-color: {c['border_subtle']}; }}
    QPushButton#primarySaveButton {{
        background: {c['olive']};
        border-color: {c['olive']};
        color: {c['bg_base']};
        font-weight: 700;
        padding: {s['sm']}px {s['lg']}px;
    }}
    QPushButton#primarySaveButton:disabled {{
        background: {c['bg_elevated']};
        color: {c['text_disabled']};
        border-color: {c['border_subtle']};
    }}
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
    QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{ border: 2px solid {c['border_focus']}; }}
    QLineEdit[readOnly="true"], QLabel[readOnly="true"] {{
        background: {c['bg_elevated']};
        border: 1px solid {c['border_subtle']};
        color: {c['text_read_only']};
        padding: {s['sm'] - 1}px {s['sm']}px;
    }}
    QLabel#warningLabel {{
        background: {c['warning_surface']};
        border: 1px solid {c['warning']};
        color: {c['text']};
        padding: {s['sm'] - 1}px {s['sm']}px;
    }}
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


def _reference_stylesheet(c: dict[str, str]) -> str:
    """Styles for the canonical shell and its reusable visual primitives."""

    t = TYPOGRAPHY
    return f"""
    QWidget#referenceShell {{
        background: {c['bg_base']};
        color: {c['text']};
    }}
    QWidget#referenceContent {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 #0B0E0C, stop:0.48 #121510, stop:1 #080A09);
    }}
    QFrame#referenceHeader {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 #080A09, stop:0.62 #151A17, stop:1 #0A0C0B);
        border-bottom: 1px solid {c['border']};
    }}
    QLabel#referenceBrand {{
        background: transparent;
        color: {c['text']};
        font-family: {t['heading']};
        font-size: 31px;
        font-weight: 800;
        letter-spacing: 1px;
    }}
    QLabel#referenceVersion {{
        background: transparent;
        color: {c['olive']};
        border: 1px solid {c['olive']};
        padding: 3px 7px;
        font-family: {t['mono']};
        font-size: 11px;
    }}
    QLabel#referenceSubtitle {{
        background: transparent;
        color: {c['text_secondary']};
        font-family: {t['heading']};
        font-size: 13px;
        letter-spacing: 1.1px;
    }}
    QPushButton#globalNav {{
        background: rgba(16, 19, 17, 210);
        color: {c['text_secondary']};
        border: 1px solid {c['border']};
        border-bottom: 3px solid transparent;
        border-radius: 0;
        min-height: 45px;
        padding: 0 19px;
        font-family: {t['heading']};
        font-size: 12px;
        letter-spacing: 0.8px;
    }}
    QPushButton#globalNav:hover {{ color: {c['text']}; background: {c['bg_hover']}; }}
    QPushButton#globalNav[destination="library"] {{ min-width: 196px; }}
    QPushButton#globalNav[destination="cloud"] {{ min-width: 135px; }}
    QPushButton#globalNav[destination="history"] {{ min-width: 80px; }}
    QPushButton#globalNav[destination="settings"] {{ min-width: 135px; }}
    QPushButton#globalNav:checked {{
        color: {c['text']};
        border-bottom-color: {c['olive']};
        background: #171B17;
    }}
    QPushButton#supportProject {{
        background: rgba(11, 13, 12, 220);
        color: {c['olive']};
        border: 1px solid {c['border']};
        border-radius: 0;
        padding: 8px 14px;
        font-family: {t['heading']};
        font-size: 11px;
    }}
    QPushButton#windowControl {{
        background: transparent;
        color: {c['text_secondary']};
        border: 1px solid transparent;
        padding: 0;
        font-size: 16px;
    }}
    QPushButton#windowControl:hover {{ color: {c['text']}; border-color: {c['border']}; }}
    QFrame#referenceFooter {{
        background: #090B0A;
        border-top: 1px solid {c['border']};
    }}
    QLabel#footerHints, QLabel#footerStatus {{
        background: transparent;
        color: {c['text_secondary']};
        font-family: {t['mono']};
        font-size: 10px;
    }}
    QLabel#footerStatus {{ color: {c['text_secondary']}; letter-spacing: 0.5px; }}
    QFrame#referencePanel, QFrame#sectionHeader {{
        background: rgba(16, 19, 17, 225);
        border: 1px solid {c['border']};
        border-radius: 0;
    }}
    QFrame#sectionHeader {{
        background: #151914;
        border-bottom-color: {c['border_subtle']};
    }}
    QLabel#sectionHeading {{
        background: transparent;
        color: {c['text']};
        font-family: {t['heading']};
        font-size: 14px;
        font-weight: 700;
        letter-spacing: 0.8px;
    }}
    QLabel#sectionNote {{
        background: transparent;
        color: {c['text_secondary']};
        font-family: {t['mono']};
        font-size: 9px;
        letter-spacing: 0.7px;
    }}
    QLabel#statusChip {{
        background: transparent;
        border: 1px solid {c['border']};
        color: {c['text_secondary']};
        padding: 4px 8px;
        font-family: {t['heading']};
        font-size: 10px;
        letter-spacing: 0.5px;
    }}
    QLabel#statusChip[tone="success"] {{ color: {c['success']}; border-color: {c['success']}; }}
    QLabel#statusChip[tone="warning"] {{ color: {c['warning']}; border-color: {c['warning']}; }}
    QLabel#statusChip[tone="danger"] {{ color: {c['error']}; border-color: {c['error']}; }}
    QLabel#statusChip[tone="info"] {{ color: #8BB8D6; border-color: #4A6877; }}
    QPushButton#primaryButton, QPushButton#primaryActionButton {{
        background: {c['olive']};
        color: #17130A;
        border: 1px solid {c['olive']};
        border-radius: 0;
        padding: 10px 17px;
        font-family: {t['heading']};
        font-weight: 800;
        letter-spacing: 0.7px;
    }}
    QPushButton#primaryButton:hover, QPushButton#primaryActionButton:hover {{ background: #E5BA45; }}
    QPushButton#neutralButton, QPushButton#dangerButton, QPushButton#supportButton {{
        border-radius: 0;
        padding: 8px 13px;
        font-family: {t['heading']};
        letter-spacing: 0.5px;
    }}
    QPushButton#dangerButton {{ color: {c['error']}; border-color: {c['error']}; }}
    QLineEdit#referenceSearch, QComboBox#referenceSort, QLineEdit#referenceField {{
        background: #0B0E0C;
        color: {c['text']};
        border: 1px solid {c['border']};
        border-radius: 0;
        padding: 8px 10px;
    }}
    QLineEdit#referenceSearch:focus, QComboBox#referenceSort:focus, QLineEdit#referenceField:focus {{
        border-color: {c['olive']};
    }}
    QPushButton#keyHintKey {{
        background: #252821;
        color: {c['text']};
        border: 1px solid {c['border']};
        padding: 2px 5px;
    }}
    QLabel#keyHintText {{ background: transparent; color: {c['text_secondary']}; }}
    QTableView#referenceTable, QTableWidget#referenceTable {{
        background: #0B0E0C;
        alternate-background-color: #101411;
        border: 1px solid {c['border']};
        gridline-color: {c['border_subtle']};
        selection-background-color: #D8D1BE;
        selection-color: #151713;
        outline: none;
    }}
    QTableView#referenceTable::item, QTableWidget#referenceTable::item {{ padding: 6px 7px; }}
    QTableView#referenceTable::item:selected, QTableWidget#referenceTable::item:selected {{
        background: #D8D1BE;
        color: #151713;
    }}
    QHeaderView::section {{
        background: #171B17;
        color: {c['text_secondary']};
        border: none;
        border-bottom: 1px solid {c['border']};
        padding: 8px 7px;
        font-family: {t['heading']};
        font-size: 10px;
        letter-spacing: 0.7px;
    }}
    QScrollBar:vertical {{ background: #0B0E0C; width: 9px; border: none; }}
    QScrollBar::handle:vertical {{ background: {c['border']}; min-height: 22px; }}
    QScrollBar::handle:vertical:hover {{ background: {c['olive_dim']}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}

    /* Canonical screen geometry */
    QWidget#libraryView, QWidget#editorView, QWidget#cloudLibraryView,
    QWidget#historyView, QWidget#characterView, QWidget#saveReviewView,
    QWidget#saveResultView, QWidget#unsupportedView, QWidget#settingsView {{
        background: transparent;
        color: {c['text']};
    }}
    QLabel#screenTitle, QWidget#libraryView > QLabel, QWidget#cloudLibraryView > QLabel,
    QWidget#historyView > QLabel, QWidget#characterView > QLabel,
    QWidget#saveReviewView > QLabel, QWidget#saveResultView > QLabel,
    QWidget#unsupportedView > QLabel, QWidget#settingsView > QLabel {{
        background: transparent;
        color: {c['text']};
        font-family: {t['heading']};
        font-size: 16px;
        font-weight: 800;
        letter-spacing: 1px;
    }}
    QLabel#screenSubtitle {{
        background: transparent;
        color: {c['text_secondary']};
        font-size: 11px;
    }}
    QFrame#libraryGameRail, QFrame#libraryCentre, QFrame#libraryPreviewPanel,
    QFrame#libraryRecentActivity, QFrame#cloudControlsPanel, QFrame#cloudTablePanel,
    QFrame#cloudDetailPanel, QFrame#cloudSafetyPanel, QFrame#historyTablePanel,
    QFrame#historyDetailPanel, QFrame#characterProfilePanel, QFrame#characterRelationsPanel,
    QFrame#reviewChangesPanel, QFrame#reviewPipelinePanel, QFrame#resultReceiptPanel,
    QFrame#unsupportedDetailPanel, QFrame#settingsCategoryRail,
    QFrame#generalSettingsPanel, QFrame#pathsSettingsPanel, QFrame#backupsSettingsPanel,
    QFrame#cloudSettingsPanel, QFrame#diagnosticsSettingsPanel,
    QFrame#interfaceSettingsPanel, QFrame#supportSettingsPanel {{
        background: rgba(16, 19, 17, 235);
        border: 1px solid {c['border']};
        border-radius: 0;
    }}
    QFrame#libraryRecentActivity {{ background: #0C100D; }}
    QFrame#libraryQuickSummary {{ background: #0B0E0C; border: 1px solid {c['border_subtle']}; }}
    QLabel#librarySummaryValue {{ background: transparent; color: {c['text_secondary']}; font-family: {t['mono']}; font-size: 9px; }}
    QFrame#zoneDecoration {{ background: transparent; border: 1px solid {c['border_subtle']}; }}
    QLabel#zoneDecorationText {{
        background: transparent;
        color: {c['text_secondary']};
        font-family: {t['heading']};
        font-size: 12px;
        letter-spacing: 1.2px;
    }}
    QListWidget#libraryGameList, QListWidget#reviewPipelineSteps {{
        background: #0B0E0C;
        border: 1px solid {c['border_subtle']};
        outline: none;
    }}
    QListWidget#libraryGameList::item {{
        color: {c['text_secondary']};
        border-bottom: 1px solid {c['border_subtle']};
        padding: 11px 8px;
    }}
    QListWidget#libraryGameList::item:selected {{
        background: #D8D1BE;
        color: #151713;
        border-left: 3px solid {c['olive']};
    }}
    QTableWidget#librarySaveTable, QTableWidget#cloudSaveTable,
    QTableWidget#historyTable, QTableWidget#characterFactionTable,
    QTableWidget#reviewChangesTable, QTableWidget#resultReceiptTable {{
        background: #0B0E0C;
        alternate-background-color: #101411;
        border: 1px solid {c['border']};
        gridline-color: {c['border_subtle']};
        selection-background-color: #D8D1BE;
        selection-color: #151713;
        outline: none;
    }}
    QTableWidget#librarySaveTable::item:selected, QTableWidget#cloudSaveTable::item:selected,
    QTableWidget#historyTable::item:selected {{ background: #D8D1BE; color: #151713; }}
    QLabel#libraryPreviewImage {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #273029, stop:1 #0A0D0B);
        border: 1px solid {c['border']};
        color: {c['text_secondary']};
        font-family: {t['heading']};
        font-size: 17px;
        letter-spacing: 1px;
    }}
    QLabel#libraryPreviewName, QLabel#cloudDetailName, QLabel#historyDetailName,
    QLabel#characterProfileLabel {{
        background: transparent;
        color: {c['text']};
        font-family: {t['heading']};
        font-size: 15px;
        font-weight: 700;
    }}
    QLabel#libraryPreviewMeta, QLabel#cloudDetailMeta, QLabel#historyDetailStatus,
    QLabel#resultSubtitle, QLabel#reviewSourceLabel, QLabel#unsupportedWriterLabel,
    QLabel#unsupportedFileLabel {{ background: transparent; color: {c['text_secondary']}; line-height: 1.4; }}
    QLabel#cloudReadOnlyBanner, QLabel#reviewWarningLabel, QLabel#characterWarning {{
        background: {c['warning_surface']};
        border: 1px solid {c['warning']};
        color: {c['text']};
        padding: 8px;
    }}
    QPushButton#categoryButton, QPushButton#settingsCategoryButton {{
        background: transparent;
        color: {c['text_secondary']};
        border: 1px solid transparent;
        border-radius: 0;
        padding: 9px 10px;
        text-align: left;
        font-family: {t['heading']};
        letter-spacing: .7px;
    }}
    QPushButton#categoryButton:hover, QPushButton#settingsCategoryButton:hover {{ background: {c['bg_hover']}; color: {c['text']}; }}
    QPushButton#categoryButton:checked, QPushButton#settingsCategoryButton:checked {{
        background: #D8D1BE;
        color: #151713;
        border-left: 3px solid {c['olive']};
        font-weight: 700;
    }}
    QWidget#editorView QLabel#editorBreadcrumb {{
        background: transparent;
        color: {c['text_secondary']};
        font-family: {t['mono']};
        font-size: 11px;
    }}
    QWidget#editorView QLabel#editorMetric {{
        background: transparent;
        color: {c['text']};
        font-family: {t['mono']};
        font-size: 16px;
    }}
    QWidget#editorView QLabel#editorInfo {{
        background: transparent;
        color: {c['text_secondary']};
        padding: 7px 0;
        border-bottom: 1px solid {c['border_subtle']};
    }}
    QFrame#editorStatusColumn, QFrame#editorInventoryColumn, QFrame#editorDetailColumn {{
        background: rgba(16, 19, 17, 235);
        border: 1px solid {c['border']};
    }}
    QPushButton#equipmentSlot {{
        background: #0B0E0C;
        border: 1px solid {c['border_subtle']};
        color: {c['text_secondary']};
        padding: 12px 8px;
        text-align: left;
    }}
    QPushButton#equipmentSlot:hover {{ border-color: {c['olive']}; color: {c['text']}; }}
    QLabel#detailItemName {{ background: transparent; color: {c['text']}; font-family: {t['heading']}; font-size: 22px; font-weight: 800; }}
    QLabel#detailItemType, QLabel#detailDescription, QLabel#detailModuleStatus {{ background: transparent; color: {c['text_secondary']}; }}
    QLabel#detailItemImage {{ background: #0B0E0C; border: 1px solid {c['border']}; color: {c['olive']}; font-size: 48px; min-height: 112px; }}
    QLabel#settingsSafetyRow {{ background: #0B0E0C; border-bottom: 1px solid {c['border_subtle']}; color: {c['success']}; padding: 3px 8px; font-size: 11px; }}
    QFrame#pathsSettingsPanel QLineEdit, QFrame#pathsSettingsPanel QPushButton {{ padding-top: 4px; padding-bottom: 4px; }}
    QFrame#pathsSettingsPanel QLabel#discoveryHint {{ font-size: 9px; }}
    QScrollArea#settingsScroll {{ background: transparent; border: none; }}
    QWidget#settingsContent {{ background: transparent; }}
    QPushButton#primaryButton:disabled, QPushButton#primaryActionButton:disabled {{ background: {c['bg_elevated']}; color: {c['text_disabled']}; border-color: {c['border_subtle']}; }}
    """


def apply_theme(app: QApplication | None) -> None:
    """Apply the S2-like industrial palette to an existing QApplication."""

    if app is None:
        return
    if bool(app.property("_save_editor_theme_applied")):
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
    app.setProperty("_save_editor_theme_applied", True)


__all__ = ["COLORS", "PALETTE", "SPACING", "TYPOGRAPHY", "apply_theme", "stylesheet"]
