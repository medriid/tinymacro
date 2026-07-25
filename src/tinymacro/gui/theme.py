from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

# Accent hues for the optional presets. "monochrome" intentionally has no hue:
# it keeps the original black/white identity and stays the default.
PRESET_ACCENTS = {
    "monochrome": "",
    "slate": "#5b7089",
    "amber": "#d98a20",
    "emerald": "#2f9e6f",
    "violet": "#7c5cd6",
}


@dataclass(frozen=True, slots=True)
class ThemeColors:
    dark: bool
    bg: str
    panel: str
    elevated: str
    text: str
    muted: str
    border: str
    accent: str
    accent_text: str

    # Fixed, kind-coded colors for the timeline/editor. In monochrome mode these
    # are shown as gray tints so the mono identity holds; presets tint them.
    @property
    def kind_colors(self) -> dict[str, str]:
        if self.accent:
            return {
                "key": "#4f9dde",
                "mouse": "#e0913a",
                "wheel": "#8a7de0",
                "wait": "#2f9e6f",
            }
        base = "#6a6a6a" if self.dark else "#8a8a8a"
        return {"key": base, "mouse": base, "wheel": base, "wait": base}


class _ThemeManager(QObject):
    """Broadcasts the resolved colors whenever the theme is (re)applied.

    Widgets that draw themselves (e.g. the recording indicator, toasts, tinted
    icons) can't rely on the app stylesheet alone, so they subscribe here and
    refresh their own colors on `changed`.
    """

    changed = pyqtSignal(object)


theme_manager = _ThemeManager()

_current_colors: ThemeColors | None = None


def current_colors() -> ThemeColors | None:
    """The colors from the most recent :func:`apply_theme`, or None if unset."""
    return _current_colors


def icon_color() -> str:
    """A sensible single-color tint for icons given the active theme."""
    return _current_colors.text if _current_colors else "#888888"


def system_prefers_dark(app: QApplication) -> bool:
    color = app.palette().color(QPalette.ColorRole.Window)
    return color.lightness() < 128


def resolve_colors(app: QApplication, theme: str, preset: str = "monochrome", accent_override: str = "") -> ThemeColors:
    dark = system_prefers_dark(app) if theme == "system" else theme == "dark"
    if dark:
        bg, panel, elevated = "#151515", "#202020", "#2a2a2a"
        text, muted, border = "#f0f0f0", "#a8a8a8", "#3a3a3a"
        mono_accent, mono_accent_text = "#ffffff", "#151515"
    else:
        bg, panel, elevated = "#f7f7f7", "#ffffff", "#eeeeee"
        text, muted, border = "#111111", "#555555", "#cfcfcf"
        mono_accent, mono_accent_text = "#000000", "#f7f7f7"
    accent = (accent_override or PRESET_ACCENTS.get(preset, "")).strip()
    if accent:
        if not accent.startswith("#"):
            accent = "#" + accent
        accent_text = "#ffffff" if QColor(accent).lightness() < 150 else "#111111"
    else:
        accent, accent_text = mono_accent, mono_accent_text
    return ThemeColors(dark, bg, panel, elevated, text, muted, border, accent, accent_text)


def _coerce(settings_or_theme) -> tuple[str, str, str]:
    """Accept either a Settings object or a bare theme string (back-compat)."""
    if isinstance(settings_or_theme, str):
        return settings_or_theme, "monochrome", ""
    theme = getattr(settings_or_theme, "theme", "system")
    preset = getattr(settings_or_theme, "theme_preset", "monochrome")
    accent = getattr(settings_or_theme, "accent_color", "")
    return theme, preset, accent


def apply_theme(app: QApplication, settings_or_theme) -> ThemeColors:
    global _current_colors
    theme, preset, accent = _coerce(settings_or_theme)
    c = resolve_colors(app, theme, preset, accent)
    _current_colors = c
    scale = float(getattr(settings_or_theme, "ui_scale", 1.0) or 1.0)
    density = getattr(settings_or_theme, "density", "comfortable")
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(c.bg))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(c.text))
    palette.setColor(QPalette.ColorRole.Base, QColor(c.panel))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(c.bg))
    palette.setColor(QPalette.ColorRole.Text, QColor(c.text))
    palette.setColor(QPalette.ColorRole.Button, QColor(c.panel))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(c.text))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(c.panel))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(c.text))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(c.accent))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(c.accent_text))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(c.muted))
    app.setPalette(palette)
    app.setStyleSheet(_stylesheet(c, scale, density))
    app.setAttribute(Qt.ApplicationAttribute.AA_DontShowIconsInMenus, False)
    theme_manager.changed.emit(c)
    return c


def _stylesheet(c: ThemeColors, scale: float = 1.0, density: str = "comfortable") -> str:
    font_px = max(9, round(12 * scale))
    pad_v = 2 if density == "compact" else 3
    pad_h = 6 if density == "compact" else 8
    ctrl_h = 22 if density == "compact" else 24
    return f"""
        QWidget {{
            font-size: {font_px}px;
            color: {c.text};
        }}
        QMainWindow, QDialog {{
            background: {c.bg};
        }}
        QToolBar {{
            spacing: 3px;
            padding: 3px;
            border: 1px solid {c.border};
            background: {c.panel};
        }}
        QToolButton, QPushButton {{
            min-width: 28px;
            min-height: {ctrl_h}px;
            border: 1px solid {c.border};
            border-radius: 5px;
            background: {c.panel};
            padding: {pad_v}px {pad_h}px;
        }}
        QToolButton:hover, QPushButton:hover {{
            border-color: {c.accent};
            background: {c.elevated};
        }}
        QToolButton:pressed, QPushButton:pressed {{
            background: {c.accent};
            color: {c.accent_text};
        }}
        QToolButton:checked, QPushButton:checked {{
            background: {c.accent};
            color: {c.accent_text};
            border-color: {c.accent};
        }}
        QPushButton:disabled, QToolButton:disabled {{
            color: {c.muted};
            border-color: {c.border};
        }}
        QPushButton#primary {{
            background: {c.accent};
            color: {c.accent_text};
            border-color: {c.accent};
            font-weight: 600;
        }}
        QSpinBox, QDoubleSpinBox, QComboBox, QLineEdit, QTextEdit {{
            min-height: {ctrl_h}px;
            border: 1px solid {c.border};
            border-radius: 5px;
            background: {c.panel};
            padding: {pad_v}px {pad_h}px;
            selection-background-color: {c.accent};
            selection-color: {c.accent_text};
        }}
        QComboBox:hover, QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover {{
            border-color: {c.accent};
        }}
        QTableWidget, QListWidget, QTreeWidget {{
            gridline-color: {c.border};
            background: {c.panel};
            alternate-background-color: {c.bg};
            border: 1px solid {c.border};
            border-radius: 5px;
        }}
        QTableWidget::item:selected, QListWidget::item:selected {{
            background: {c.accent};
            color: {c.accent_text};
        }}
        QHeaderView::section {{
            background: {c.bg};
            border: 1px solid {c.border};
            padding: 4px;
        }}
        QTabWidget::pane {{
            border: 1px solid {c.border};
            border-radius: 5px;
            top: -1px;
        }}
        QTabBar::tab {{
            background: {c.panel};
            border: 1px solid {c.border};
            padding: 6px 12px;
            margin-right: 2px;
            border-top-left-radius: 5px;
            border-top-right-radius: 5px;
        }}
        QTabBar::tab:selected {{
            background: {c.elevated};
            border-bottom-color: {c.elevated};
            font-weight: 600;
        }}
        QTabBar::tab:hover {{
            border-color: {c.accent};
        }}
        QGroupBox {{
            border: 1px solid {c.border};
            border-radius: 5px;
            margin-top: 8px;
            padding-top: 8px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 8px;
            padding: 0 4px;
            color: {c.muted};
        }}
        QProgressBar {{
            border: 1px solid {c.border};
            border-radius: 5px;
            background: {c.panel};
            text-align: center;
            min-height: 14px;
        }}
        QProgressBar::chunk {{
            background: {c.accent};
            border-radius: 4px;
        }}
        QStatusBar {{
            border-top: 1px solid {c.border};
        }}
        QCheckBox::indicator {{
            width: 15px;
            height: 15px;
            border: 1px solid {c.border};
            border-radius: 3px;
            background: {c.panel};
        }}
        QCheckBox::indicator:checked {{
            background: {c.accent};
            border-color: {c.accent};
        }}
        QScrollBar:vertical {{
            background: {c.bg};
            width: 10px;
            margin: 0;
        }}
        QScrollBar::handle:vertical {{
            background: {c.border};
            border-radius: 5px;
            min-height: 24px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {c.muted};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0;
        }}
    """
