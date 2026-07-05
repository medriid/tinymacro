from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication


def system_prefers_dark(app: QApplication) -> bool:
    color = app.palette().color(QPalette.ColorRole.Window)
    return color.lightness() < 128


def apply_theme(app: QApplication, theme: str) -> None:
    dark = system_prefers_dark(app) if theme == "system" else theme == "dark"
    palette = QPalette()
    if dark:
        bg = QColor("#151515")
        panel = QColor("#202020")
        text = QColor("#f0f0f0")
        muted = QColor("#a8a8a8")
        border = QColor("#3a3a3a")
        accent = QColor("#ffffff")
    else:
        bg = QColor("#f7f7f7")
        panel = QColor("#ffffff")
        text = QColor("#111111")
        muted = QColor("#555555")
        border = QColor("#cfcfcf")
        accent = QColor("#000000")
    palette.setColor(QPalette.ColorRole.Window, bg)
    palette.setColor(QPalette.ColorRole.WindowText, text)
    palette.setColor(QPalette.ColorRole.Base, panel)
    palette.setColor(QPalette.ColorRole.AlternateBase, bg)
    palette.setColor(QPalette.ColorRole.Text, text)
    palette.setColor(QPalette.ColorRole.Button, panel)
    palette.setColor(QPalette.ColorRole.ButtonText, text)
    palette.setColor(QPalette.ColorRole.ToolTipBase, panel)
    palette.setColor(QPalette.ColorRole.ToolTipText, text)
    palette.setColor(QPalette.ColorRole.Highlight, accent)
    palette.setColor(QPalette.ColorRole.HighlightedText, bg)
    palette.setColor(QPalette.ColorRole.PlaceholderText, muted)
    app.setPalette(palette)
    app.setStyleSheet(
        f"""
        QWidget {{
            font-size: 12px;
            color: {text.name()};
        }}
        QMainWindow, QDialog {{
            background: {bg.name()};
        }}
        QToolBar {{
            spacing: 2px;
            padding: 2px;
            border: 1px solid {border.name()};
            background: {panel.name()};
        }}
        QToolButton, QPushButton {{
            min-width: 28px;
            min-height: 24px;
            border: 1px solid {border.name()};
            border-radius: 4px;
            background: {panel.name()};
            padding: 2px 6px;
        }}
        QToolButton:hover, QPushButton:hover {{
            border-color: {accent.name()};
        }}
        QToolButton:checked, QPushButton:checked {{
            background: {accent.name()};
            color: {bg.name()};
        }}
        QSpinBox, QDoubleSpinBox, QComboBox, QLineEdit {{
            min-height: 24px;
            border: 1px solid {border.name()};
            border-radius: 4px;
            background: {panel.name()};
            padding: 1px 4px;
        }}
        QTableWidget {{
            gridline-color: {border.name()};
            background: {panel.name()};
            alternate-background-color: {bg.name()};
        }}
        QHeaderView::section {{
            background: {bg.name()};
            border: 1px solid {border.name()};
            padding: 4px;
        }}
        QStatusBar {{
            border-top: 1px solid {border.name()};
        }}
        QCheckBox::indicator {{
            width: 14px;
            height: 14px;
        }}
        """
    )
    app.setAttribute(Qt.ApplicationAttribute.AA_DontShowIconsInMenus, False)
