"""Application theme: palette, fonts and Qt stylesheet."""

from __future__ import annotations

import sys

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

ACCENT = "#4F46E5"
ACCENT_HOVER = "#4338CA"
ACCENT_SOFT = "#EEF2FF"
SUCCESS = "#10B981"
WARNING = "#F59E0B"
DANGER = "#EF4444"
INK = "#0F172A"
MUTED = "#64748B"

STYLESHEET = """
QWidget {
    color: #0F172A;
    font-size: 13px;
}
QMainWindow, QWidget#appRoot, QWidget#contentArea, QScrollArea#pageScroll {
    background: #F1F4F9;
}
QScrollArea { border: none; background: transparent; }
QWidget#pageBody { background: transparent; }

/* Sidebar ------------------------------------------------------------ */
QFrame#sidebar {
    background: #0F172A;
    border: none;
}
QLabel#appTitle { color: #FFFFFF; font-size: 18px; font-weight: 700; }
QLabel#appSubtitle { color: #7C8AA5; font-size: 11px; letter-spacing: 1px; }
QLabel#navSection { color: #64748B; font-size: 10px; font-weight: 600; letter-spacing: 2px; }
QPushButton#navButton {
    background: transparent;
    color: #B7C2D6;
    text-align: left;
    padding: 10px 14px;
    border: none;
    border-radius: 10px;
    font-size: 14px;
}
QPushButton#navButton:hover { background: #1B2538; color: #FFFFFF; }
QPushButton#navButton:checked {
    background: #1E293B;
    color: #FFFFFF;
    font-weight: 600;
}
QLabel#sidebarHint { color: #64748B; font-size: 11px; }
QLabel#sidebarReady { color: #34D399; font-size: 11px; }
QLabel#sidebarLoading { color: #FBBF24; font-size: 11px; }
QLabel#sidebarError { color: #F87171; font-size: 11px; }
QFrame#sidebarDivider { background: #1E293B; max-height: 1px; border: none; }
QPushButton#sidebarLink {
    background: transparent;
    color: #94A3B8;
    border: none;
    text-align: left;
    padding: 4px 0;
    font-size: 11px;
}
QPushButton#sidebarLink:hover { color: #E2E8F0; }
QStackedWidget#contentArea { background: #F1F4F9; }

/* Cards -------------------------------------------------------------- */
QFrame#card {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 16px;
}
QFrame#innerPanel {
    background: #F8FAFC;
    border: 1px solid #E2E8F0;
    border-radius: 12px;
}
QLabel#pageTitle { font-size: 23px; font-weight: 700; color: #0F172A; }
QLabel#pageSubtitle { color: #64748B; font-size: 13px; }
QLabel#cardTitle { font-size: 15px; font-weight: 600; color: #0F172A; }
QLabel#cardSubtitle { color: #64748B; font-size: 12px; }
QLabel#hint { color: #64748B; font-size: 12px; }
QLabel#muted { color: #94A3B8; font-size: 12px; }
QLabel#fieldLabel { color: #475569; font-size: 12px; font-weight: 600; }
QLabel#bigStat { font-size: 30px; font-weight: 700; color: #4F46E5; }
QLabel#statCaption { color: #64748B; font-size: 11px; }
QLabel#scoreValue { font-size: 34px; font-weight: 700; }
QLabel#successText { color: #059669; font-size: 13px; font-weight: 600; }
QLabel#errorText { color: #DC2626; font-size: 13px; font-weight: 600; }
QLabel#windowBadge { background: #EEF2FF; color: #4338CA; border-radius: 9px; padding: 4px 10px; font-size: 11px; font-weight: 600; }

/* Badges ------------------------------------------------------------- */
QLabel#badgeSuccess { background: #ECFDF5; color: #047857; border: 1px solid #A7F3D0; border-radius: 10px; padding: 5px 14px; font-weight: 600; }
QLabel#badgeDanger { background: #FEF2F2; color: #B91C1C; border: 1px solid #FECACA; border-radius: 10px; padding: 5px 14px; font-weight: 600; }
QLabel#badgeNeutral { background: #F1F5F9; color: #475569; border: 1px solid #E2E8F0; border-radius: 10px; padding: 5px 14px; font-weight: 600; }

/* Buttons ------------------------------------------------------------ */
QPushButton {
    border-radius: 10px;
    padding: 8px 16px;
    font-size: 13px;
}
QPushButton#primary {
    background: #4F46E5;
    color: #FFFFFF;
    font-weight: 600;
    padding: 10px 22px;
}
QPushButton#primary:hover { background: #4338CA; }
QPushButton#primary:pressed { background: #3730A3; }
QPushButton#primary:disabled { background: #C7D2FE; color: #F5F3FF; }
QPushButton#secondary {
    background: #FFFFFF;
    border: 1px solid #CBD5E1;
    color: #334155;
    padding: 8px 14px;
}
QPushButton#secondary:hover { background: #F8FAFC; border-color: #94A3B8; }
QPushButton#secondary:disabled { color: #CBD5E1; border-color: #E2E8F0; }
QPushButton#ghost {
    background: transparent;
    color: #4F46E5;
    border: none;
    padding: 6px 8px;
    font-weight: 600;
}
QPushButton#ghost:hover { color: #3730A3; }
QPushButton#danger {
    background: #FEF2F2;
    border: 1px solid #FECACA;
    color: #B91C1C;
    padding: 8px 14px;
}
QPushButton#danger:hover { background: #FEE2E2; }

/* Inputs ------------------------------------------------------------- */
QLineEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    border: 1px solid #CBD5E1;
    border-radius: 10px;
    padding: 8px 12px;
    background: #FFFFFF;
    selection-background-color: #C7D2FE;
    selection-color: #1E1B4B;
}
QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border: 1px solid #6366F1;
}
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button { width: 0; border: none; }
QComboBox::drop-down { border: none; width: 24px; }

/* Tables ------------------------------------------------------------- */
QTableWidget, QTableView {
    background: #FFFFFF;
    border: none;
    gridline-color: #F1F5F9;
    selection-background-color: #EEF2FF;
    selection-color: #1E1B4B;
    alternate-background-color: #FAFBFF;
}
QHeaderView::section {
    background: #F8FAFC;
    border: none;
    border-bottom: 1px solid #E2E8F0;
    padding: 9px 8px;
    color: #64748B;
    font-size: 11px;
    font-weight: 600;
}
QTableWidget::item { padding: 6px; }

/* Misc --------------------------------------------------------------- */
QProgressBar {
    background: #EEF2FF;
    border: none;
    border-radius: 4px;
    max-height: 8px;
    min-height: 8px;
    text-align: center;
    color: transparent;
}
QProgressBar::chunk { background: #6366F1; border-radius: 4px; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #CBD5E1; border-radius: 5px; min-height: 32px; }
QScrollBar::handle:vertical:hover { background: #94A3B8; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: #CBD5E1; border-radius: 5px; min-width: 32px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QToolTip {
    background: #0F172A;
    color: #F8FAFC;
    border: none;
    border-radius: 6px;
    padding: 6px 8px;
}
QStatusBar { background: #FFFFFF; color: #64748B; border-top: 1px solid #E2E8F0; }
QMessageBox { background: #FFFFFF; }
"""


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    families = ["PingFang SC", "Microsoft YaHei UI", "Noto Sans CJK SC",
                "Source Han Sans SC", "Segoe UI", "Noto Sans"]
    available = set(QFontDatabase.families())
    chosen = [f for f in families if f in available]
    font = QFont()
    if chosen:
        font.setFamilies(chosen + ["sans-serif"])
    font.setPointSize(10)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    app.setFont(font)
    app.setStyleSheet(STYLESHEET)


def platform_name() -> str:
    if sys.platform == "darwin":
        return "macOS"
    if sys.platform.startswith("win"):
        return "Windows"
    return "Linux"