from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

from tinymacro.core.theme_pack import Theme

# Accent hues for the optional presets. "monochrome" intentionally has no hue:
# it keeps the original black/white identity and stays the default.
PRESET_ACCENTS = {
    "monochrome": "",
    "slate": "#5b7089",
    "amber": "#d98a20",
    "emerald": "#2f9e6f",
    "violet": "#7c5cd6",
}

# A refined, cross-platform UI font stack (Qt picks the first family installed).
#
# Order matters: the OS defaults (Segoe UI / SF / Ubuntu) sit *after* the crafted
# faces, so the app doesn't just inherit the stock system look. Drop an Inter (or
# any other) font file into ``gui/fonts`` and :func:`load_bundled_fonts` registers
# it at startup, making the whole UI use it on every machine.
UI_FONT_STACK = (
    '"Inter", "Inter Display", "InterVariable", "SF Pro Text", '
    '"Segoe UI Variable Text", "Segoe UI", "Ubuntu", "Cantarell", '
    '"Noto Sans", "DejaVu Sans", "Helvetica Neue", Arial, sans-serif'
)

# Directory scanned for bundled font files (packaged alongside the icons).
FONT_DIR = Path(__file__).resolve().parent / "fonts"


def load_bundled_fonts() -> list[str]:
    """Register any bundled .ttf/.otf with Qt; returns the families added.

    Lets Tiny Macro ship its own typeface so the UI looks identical everywhere
    instead of falling back to whatever the OS provides. Missing directory or
    unreadable files are ignored — the stack above then degrades to system faces.
    """
    from PyQt6.QtGui import QFontDatabase

    families: list[str] = []
    if not FONT_DIR.is_dir():
        return families
    for path in sorted(FONT_DIR.iterdir()):
        if path.suffix.lower() not in (".ttf", ".otf"):
            continue
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id != -1:
            families.extend(QFontDatabase.applicationFontFamilies(font_id))
    return families


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
    # Opacity of surfaces (panels/toolbars/lists). < 1 when a custom image/GIF
    # background should show through them.
    surface_alpha: float = 1.0
    # True when the window itself should be transparent so a ThemedBackground
    # widget shows behind the content (image/animated custom themes).
    image_background: bool = False
    # Optional UI font family override (falls back to the default stack).
    font_family: str = ""
    # Explicit per-kind palette (custom themes); None → computed from the accent.
    kind_colors_map: dict[str, str] | None = None

    # Fixed, kind-coded colors for the timeline/editor. In monochrome mode these
    # are shown as gray tints so the mono identity holds; presets tint them.
    @property
    def kind_colors(self) -> dict[str, str]:
        if self.kind_colors_map:
            return dict(self.kind_colors_map)
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
_current_theme: Theme | None = None


def current_colors() -> ThemeColors | None:
    """The colors from the most recent :func:`apply_theme`, or None if unset."""
    return _current_colors


def current_theme() -> Theme | None:
    """The active custom :class:`Theme`, or None when a built-in preset is in use."""
    return _current_theme


def _rgba(hex_color: str, alpha: float) -> str:
    c = QColor(hex_color)
    return f"rgba({c.red()},{c.green()},{c.blue()},{max(0.0, min(1.0, alpha)):.3f})"


def _colors_from_theme(theme: Theme) -> ThemeColors:
    image_bg = theme.background.kind in ("image", "animated")
    bg = theme.background.color if theme.background.kind == "solid" else theme.panel
    return ThemeColors(
        dark=theme.dark,
        bg=bg,
        panel=theme.panel,
        elevated=theme.elevated,
        text=theme.text,
        muted=theme.muted,
        border=theme.border,
        accent=theme.accent,
        accent_text=theme.accent_text,
        surface_alpha=theme.panel_opacity if image_bg else 1.0,
        image_background=image_bg,
        font_family=theme.font_family,
        kind_colors_map=dict(theme.kind_colors),
    )


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


def _resolve_active_theme(settings_or_theme) -> Theme | None:
    """Load the settings' active custom theme, or None to use a built-in preset."""
    path = getattr(settings_or_theme, "active_theme", "")
    if not path:
        return None
    try:
        return Theme.load(path)
    except Exception:  # noqa: BLE001 - a broken theme falls back to the preset
        return None


def apply_theme(app: QApplication, settings_or_theme) -> ThemeColors:
    global _current_colors, _current_theme
    custom = _resolve_active_theme(settings_or_theme)
    _current_theme = custom
    if custom is not None:
        c = _colors_from_theme(custom)
    else:
        theme, preset, accent = _coerce(settings_or_theme)
        c = resolve_colors(app, theme, preset, accent)
    scale = float(getattr(settings_or_theme, "ui_scale", 1.0) or 1.0)
    density = getattr(settings_or_theme, "density", "comfortable")
    return _apply_colors(app, c, scale, density)


def apply_theme_object(app: QApplication, theme: Theme, scale: float = 1.0, density: str = "comfortable") -> ThemeColors:
    """Apply a :class:`Theme` object directly (used for live editor preview)."""
    global _current_theme
    _current_theme = theme
    return _apply_colors(app, _colors_from_theme(theme), scale, density)


def _apply_colors(app: QApplication, c: ThemeColors, scale: float, density: str) -> ThemeColors:
    global _current_colors
    _current_colors = c
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


def _surface(c: ThemeColors, hex_color: str) -> str:
    """A surface fill — translucent when a background should show through."""
    return _rgba(hex_color, c.surface_alpha) if c.surface_alpha < 1.0 else hex_color


def _stylesheet(c: ThemeColors, scale: float = 1.0, density: str = "comfortable") -> str:
    font_px = max(9, round(12 * scale))
    pad_v = 2 if density == "compact" else 3
    pad_h = 6 if density == "compact" else 8
    ctrl_h = 22 if density == "compact" else 24
    font_family = f'"{c.font_family}", {UI_FONT_STACK}' if c.font_family else UI_FONT_STACK
    panel = _surface(c, c.panel)
    elevated = _surface(c, c.elevated)
    window_bg = "transparent" if c.image_background else c.bg
    alt_bg = _surface(c, c.bg)
    return f"""
        QWidget {{
            font-family: {font_family};
            font-size: {font_px}px;
            color: {c.text};
        }}
        /* Typography: slightly tighter, heavier control text reads as designed
           rather than stock. Studio's section headings set their own style. */
        QPushButton, QToolButton, QComboBox, QSpinBox, QDoubleSpinBox,
        QLineEdit, QCheckBox, QTabBar::tab, QHeaderView::section {{
            letter-spacing: 0.2px;
        }}
        QLabel {{
            letter-spacing: 0.1px;
        }}
        QMainWindow, QDialog {{
            background: {window_bg};
        }}
        QToolBar {{
            spacing: 3px;
            padding: 3px;
            border: 1px solid {c.border};
            background: {panel};
        }}
        QToolButton, QPushButton {{
            min-width: 28px;
            min-height: {ctrl_h}px;
            border: 1px solid {c.border};
            border-radius: 5px;
            background: {panel};
            padding: {pad_v}px {pad_h}px;
            font-weight: 500;
        }}
        QToolButton:hover, QPushButton:hover {{
            border-color: {c.accent};
            background: {elevated};
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
            background: {panel};
            padding: {pad_v}px {pad_h}px;
            selection-background-color: {c.accent};
            selection-color: {c.accent_text};
        }}
        QComboBox:hover, QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover {{
            border-color: {c.accent};
        }}
        QTableWidget, QListWidget, QTreeWidget {{
            gridline-color: {c.border};
            background: {panel};
            alternate-background-color: {alt_bg};
            border: 1px solid {c.border};
            border-radius: 5px;
        }}
        QTableWidget::item:selected, QListWidget::item:selected {{
            background: {c.accent};
            color: {c.accent_text};
        }}
        QHeaderView::section {{
            background: {alt_bg};
            border: 1px solid {c.border};
            padding: 4px;
        }}
        QTabWidget::pane {{
            border: 1px solid {c.border};
            border-radius: 5px;
            top: -1px;
        }}
        QTabBar::tab {{
            background: {panel};
            border: 1px solid {c.border};
            padding: 6px 12px;
            margin-right: 2px;
            border-top-left-radius: 5px;
            border-top-right-radius: 5px;
        }}
        QTabBar::tab:selected {{
            background: {elevated};
            border-bottom-color: {elevated};
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
            background: {panel};
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
            background: {panel};
        }}
        QCheckBox::indicator:checked {{
            background: {c.accent};
            border-color: {c.accent};
        }}
        QScrollBar:vertical {{
            background: {alt_bg};
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
