"""
nexads/ui/config_theme.py
Dark mode stylesheet and QPalette for the config GUI.
"""

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPalette, QColor, QFont


_DARK_STYLESHEET = """
    QMainWindow {
        background-color: #1F232A;
        color: #E6EAF2;
    }

    QTabWidget::pane {
        border: 1px solid #343A46;
        background: #1F232A;
        border-radius: 8px;
        top: -1px;
    }

    QTabBar::tab {
        background: #2A2F3A;
        color: #D8DEEA;
        padding: 8px 12px;
        margin-right: 6px;
        border: 1px solid #343A46;
        border-bottom: none;
        border-top-left-radius: 8px;
        border-top-right-radius: 8px;
        min-width: 130px;
        font-size: 10.5pt;
        font-weight: 600;
    }

    QTabBar::tab:hover {
        background: #333A48;
    }

    QTabBar::tab:selected {
        background: #3C4558;
        color: #FFFFFF;
    }

    QGroupBox {
        border: 1px solid #343A46;
        border-radius: 10px;
        margin-top: 14px;
        padding: 12px 10px 10px 10px;
        color: #E2E7F1;
        font-size: 10.5pt;
        font-weight: 600;
    }

    QGroupBox::title {
        subcontrol-origin: margin;
        left: 12px;
        padding: 0 6px;
        color: #F3F6FC;
    }

    QLabel {
        color: #E6EAF2;
        font-size: 10pt;
    }

    QLineEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {
        background: #2A2F3A;
        color: #E8ECF5;
        border: 1px solid #3B4454;
        border-radius: 8px;
        padding: 6px 8px;
        selection-background-color: #3D73D8;
        selection-color: #FFFFFF;
        min-height: 18px;
        font-size: 10pt;
    }

    QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
        border: 1px solid #4C85F5;
    }

    QTextEdit {
        line-height: 1.35;
    }

    QPushButton {
        background: #3F69C9;
        color: #FFFFFF;
        border: 1px solid #4A78E0;
        border-radius: 8px;
        padding: 7px 12px;
        min-height: 20px;
        font-size: 10pt;
        font-weight: 600;
    }

    QPushButton:hover {
        background: #4E79DB;
    }

    QPushButton:pressed {
        background: #365AAF;
    }

    QTableWidget {
        background: #262C37;
        color: #E4E9F3;
        gridline-color: #3A4352;
        border: 1px solid #343A46;
        border-radius: 8px;
        font-size: 10.5pt;
    }

    QHeaderView::section {
        background: #313949;
        color: #F0F4FC;
        padding: 8px;
        border: 1px solid #3A4352;
        font-size: 10.5pt;
        font-weight: 600;
    }

    QTableWidget::item {
        padding: 6px;
    }

    QCheckBox {
        color: #E6EAF2;
        spacing: 8px;
        font-size: 10pt;
    }

    QRadioButton {
        color: #E6EAF2;
        spacing: 8px;
        font-size: 10pt;
    }

    QStatusBar {
        background: #1A1F27;
        color: #D6DEEC;
        border-top: 1px solid #343A46;
        font-size: 10.5pt;
    }

    QSlider::groove:horizontal {
        height: 9px;
        background: #313949;
        border-radius: 5px;
    }

    QSlider::handle:horizontal {
        width: 20px;
        height: 20px;
        background: #5D8FF0;
        border: 1px solid #7AA5F7;
        border-radius: 10px;
        margin: -6px 0;
    }

    QSlider::sub-page:horizontal {
        background: #4B7FE8;
        border-radius: 5px;
    }

    QListWidget {
        background: #2A2F3A;
        color: #E8ECF5;
        border: 1px solid #3B4454;
        border-radius: 8px;
        padding: 4px;
        font-size: 10pt;
    }

    QListWidget::item {
        padding: 6px 8px;
        border-radius: 4px;
    }

    QListWidget::item:selected {
        background: #3D73D8;
        color: #FFFFFF;
    }

    QListWidget::item:hover {
        background: #333A48;
    }
"""


def apply_dark_mode(window):
    """Apply dark mode stylesheet and QPalette to the given QMainWindow."""
    QApplication.setFont(QFont("Segoe UI", 10))
    window.setStyleSheet(_DARK_STYLESHEET)

    dark_palette = QPalette()
    dark_palette.setColor(QPalette.Window, QColor(31, 35, 42))
    dark_palette.setColor(QPalette.WindowText, Qt.white)
    dark_palette.setColor(QPalette.Base, QColor(38, 44, 55))
    dark_palette.setColor(QPalette.AlternateBase, QColor(42, 47, 58))
    dark_palette.setColor(QPalette.ToolTipBase, Qt.white)
    dark_palette.setColor(QPalette.ToolTipText, Qt.white)
    dark_palette.setColor(QPalette.Text, Qt.white)
    dark_palette.setColor(QPalette.Button, QColor(63, 105, 201))
    dark_palette.setColor(QPalette.ButtonText, Qt.white)
    dark_palette.setColor(QPalette.BrightText, Qt.red)
    dark_palette.setColor(QPalette.Link, QColor(93, 143, 240))
    dark_palette.setColor(QPalette.Highlight, QColor(93, 143, 240))
    dark_palette.setColor(QPalette.HighlightedText, Qt.white)
    QApplication.setPalette(dark_palette)
