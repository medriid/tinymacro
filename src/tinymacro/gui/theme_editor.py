"""Live theme editor: build, preview, save and import/export custom themes.

Users pick a background (solid colour / image / animated GIF), a scrim + surface
opacity, and accent/text/panel colours; the app re-skins **live** as they tweak.
"Save & Use" writes the theme into the local themes store and activates it;
Import/Export moves portable ``.tmactheme`` files between machines.
"""
from __future__ import annotations

from pathlib import Path
import re

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QFileDialog,
    QFontComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from tinymacro.core.settings import Settings
from tinymacro.core.theme_pack import (
    MAX_ASSET_BYTES,
    THEME_EXTENSION,
    Background,
    Theme,
    ThemeError,
    default_themes_dir,
)
from tinymacro.gui.theme import apply_theme, apply_theme_object, current_theme

_KINDS = ("solid", "image", "animated")
_FITS = ("cover", "contain", "stretch", "center", "tile")


def _mix(a: str, b: str, t: float) -> str:
    ca, cb = QColor(a), QColor(b)
    r = round(ca.red() + (cb.red() - ca.red()) * t)
    g = round(ca.green() + (cb.green() - ca.green()) * t)
    bl = round(ca.blue() + (cb.blue() - ca.blue()) * t)
    return QColor(r, g, bl).name()


def _auto_text(bg: str) -> str:
    return "#ffffff" if QColor(bg).lightness() < 150 else "#111111"


def _safe_name(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", name.strip()) or "theme"
    return slug[:60]


class _Swatch(QPushButton):
    """A button that shows a colour and opens a picker when clicked."""

    def __init__(self, color: str, on_change) -> None:
        super().__init__()
        self._color = color
        self._on_change = on_change
        self.setFixedSize(64, 24)
        self.clicked.connect(self._pick)
        self._refresh()

    def color(self) -> str:
        return self._color

    def set_color(self, color: str) -> None:
        self._color = color
        self._refresh()

    def _refresh(self) -> None:
        self.setStyleSheet(f"background: {self._color}; border: 1px solid palette(mid); border-radius: 4px;")

    def _pick(self) -> None:
        chosen = QColorDialog.getColor(QColor(self._color), self, "Pick a colour")
        if chosen.isValid():
            self.set_color(chosen.name())
            self._on_change()


class ThemeEditor(QDialog):
    """Compose a :class:`Theme`, preview it live, and save/export it."""

    committed = pyqtSignal()  # active theme changed → host should persist settings

    def __init__(self, settings: Settings, parent=None, persist=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Custom Themes")
        self.resize(460, 560)
        self.settings = settings
        self._persist = persist
        self._committed = False
        self._original_active = settings.active_theme  # restore on cancel
        self._asset_bytes: bytes | None = None
        self._asset_name = ""

        base = current_theme()
        self.name = QLineEdit((base.name if base else "My Theme"))
        self.dark = QCheckBox("Dark base (affects scrim + icons)")
        self.dark.setChecked(base.dark if base else True)
        self.kind = QComboBox()
        self.kind.addItems(["Solid colour", "Image", "Animated GIF"])
        self.kind.setCurrentIndex(_KINDS.index(base.background.kind) if base else 0)
        self.kind.currentIndexChanged.connect(self._kind_changed)

        self.bg_color = _Swatch(base.background.color if base else "#151515", self._preview)
        self.choose_btn = QPushButton("Choose image / GIF…")
        self.choose_btn.clicked.connect(self._choose_asset)
        self.asset_label = QLabel("—")
        self.asset_label.setStyleSheet("color: palette(mid);")

        self.fit = QComboBox()
        self.fit.addItems([f.capitalize() for f in _FITS])
        self.fit.setCurrentIndex(_FITS.index(base.background.fit) if base else 0)
        self.fit.currentIndexChanged.connect(self._preview)

        self.scrim = self._slider(int((base.background.scrim if base else 0.0) * 100))
        self.opacity = self._slider(int((base.panel_opacity if base else 0.8) * 100))

        self.accent = _Swatch(base.accent if base else "#ffffff", self._preview)
        self.text = _Swatch(base.text if base else "#f0f0f0", self._preview)
        self.panel = _Swatch(base.panel if base else "#202020", self._preview)

        self.font_on = QCheckBox("Override UI font")
        self.font_on.setChecked(bool(base and base.font_family))
        self.font_on.toggled.connect(self._preview)
        self.font_combo = QFontComboBox()
        if base and base.font_family:
            self.font_combo.setCurrentFont(self.font_combo.currentFont().__class__(base.font_family))
        self.font_combo.currentFontChanged.connect(self._preview)

        if base and base.background.kind != "solid":
            data = base.background_bytes()
            if data:
                self._asset_bytes = data
                self._asset_name = base.background.asset or "embedded"
                self.asset_label.setText(f"embedded ({len(data)//1024} KB)")

        form = QFormLayout()
        form.addRow("Name", self.name)
        form.addRow("", self.dark)
        form.addRow("Background", self.kind)
        form.addRow("Solid colour", self.bg_color)
        form.addRow("Image / GIF", self._row(self.choose_btn, self.asset_label))
        form.addRow("Fit", self.fit)
        form.addRow("Scrim", self.scrim)
        form.addRow("Surface opacity", self.opacity)
        form.addRow("Accent", self.accent)
        form.addRow("Text", self.text)
        form.addRow("Panel", self.panel)
        form.addRow("", self.font_on)
        form.addRow("Font", self.font_combo)
        body = QWidget()
        body.setLayout(form)

        # Buttons.
        self.import_btn = QPushButton("Import…")
        self.export_btn = QPushButton("Export…")
        self.default_btn = QPushButton("Use Default")
        self.save_btn = QPushButton("Save & Use")
        self.save_btn.setObjectName("primary")
        self.close_btn = QPushButton("Close")
        self.import_btn.clicked.connect(self._import)
        self.export_btn.clicked.connect(self._export)
        self.default_btn.clicked.connect(self._use_default)
        self.save_btn.clicked.connect(self._save_and_use)
        self.close_btn.clicked.connect(self.reject)
        buttons = QHBoxLayout()
        buttons.addWidget(self.import_btn)
        buttons.addWidget(self.export_btn)
        buttons.addStretch(1)
        buttons.addWidget(self.default_btn)
        buttons.addWidget(self.save_btn)
        buttons.addWidget(self.close_btn)

        root = QVBoxLayout(self)
        root.addWidget(QLabel("Design a theme — the app updates live as you tweak."))
        root.addWidget(body, 1)
        root.addLayout(buttons)

        self._kind_changed()
        self._preview()

    # -- helpers --------------------------------------------------------------
    def _slider(self, value: int) -> QSlider:
        s = QSlider(Qt.Orientation.Horizontal)
        s.setRange(0, 100)
        s.setValue(value)
        s.valueChanged.connect(self._preview)
        return s

    @staticmethod
    def _row(*widgets) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        for widget in widgets:
            lay.addWidget(widget)
        lay.addStretch(1)
        return w

    def _kind_changed(self) -> None:
        kind = _KINDS[self.kind.currentIndex()]
        is_solid = kind == "solid"
        self.bg_color.setEnabled(is_solid)
        self.choose_btn.setEnabled(not is_solid)
        self.fit.setEnabled(not is_solid)
        self.scrim.setEnabled(not is_solid)
        self._preview()

    def _choose_asset(self) -> None:
        kind = _KINDS[self.kind.currentIndex()]
        flt = "GIF (*.gif)" if kind == "animated" else "Images (*.png *.jpg *.jpeg *.gif)"
        path, _ = QFileDialog.getOpenFileName(self, "Choose background", "", flt)
        if not path:
            return
        data = Path(path).read_bytes()
        if len(data) > MAX_ASSET_BYTES:
            QMessageBox.warning(self, "Too large", "That image is larger than the 24 MB limit.")
            return
        self._asset_bytes = data
        self._asset_name = Path(path).name
        self.asset_label.setText(f"{Path(path).name} ({len(data)//1024} KB)")
        self._preview()

    # -- theme building -------------------------------------------------------
    def _build_theme(self, warn: bool = True) -> Theme | None:
        kind = _KINDS[self.kind.currentIndex()]
        bg = Background(kind=kind, fit=_FITS[self.fit.currentIndex()], scrim=self.scrim.value() / 100)
        theme = Theme(name=self.name.text().strip() or "Custom", dark=self.dark.isChecked())
        if kind == "solid":
            bg.color = self.bg_color.color()
        else:
            if not self._asset_bytes:
                if warn:
                    QMessageBox.information(self, "No image", "Choose an image or GIF first.")
                return None
            theme.set_asset("bg", self._asset_bytes)
            bg.asset = "bg"
        theme.background = bg
        theme.accent = self.accent.color()
        theme.accent_text = _auto_text(self.accent.color())
        theme.text = self.text.color()
        theme.panel = self.panel.color()
        theme.elevated = _mix(self.panel.color(), self.text.color(), 0.12)
        theme.border = _mix(self.panel.color(), self.text.color(), 0.28)
        theme.muted = _mix(self.text.color(), self.panel.color(), 0.45)
        theme.panel_opacity = self.opacity.value() / 100
        theme.font_family = self.font_combo.currentFont().family() if self.font_on.isChecked() else ""
        try:
            theme.validate()
        except ThemeError as exc:
            if warn:
                QMessageBox.warning(self, "Invalid theme", str(exc))
            return None
        return theme

    def _preview(self) -> None:
        theme = self._build_theme(warn=False)
        app = QApplication.instance()
        if theme is not None and app is not None:
            apply_theme_object(app, theme, self.settings.ui_scale, self.settings.density)

    # -- actions --------------------------------------------------------------
    def _save_and_use(self) -> None:
        theme = self._build_theme()
        if theme is None:
            return
        themes_dir = default_themes_dir()
        themes_dir.mkdir(parents=True, exist_ok=True)
        path = themes_dir / f"{_safe_name(theme.name)}{THEME_EXTENSION}"
        try:
            theme.save(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Cannot save", str(exc))
            return
        self.settings.active_theme = str(path)
        self._commit()
        self.accept()

    def _use_default(self) -> None:
        self.settings.active_theme = ""
        app = QApplication.instance()
        if app is not None:
            apply_theme(app, self.settings)
        self._commit()
        self.accept()

    def _export(self) -> None:
        theme = self._build_theme()
        if theme is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export Theme", f"{_safe_name(theme.name)}{THEME_EXTENSION}",
                                              f"Tiny Macro Theme (*{THEME_EXTENSION})")
        if not path:
            return
        if not path.endswith(THEME_EXTENSION):
            path += THEME_EXTENSION
        try:
            theme.save(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Export failed", str(exc))
            return
        QMessageBox.information(self, "Exported", f"Saved {Path(path).name}")

    def _import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import Theme", "", f"Tiny Macro Theme (*{THEME_EXTENSION})")
        if not path:
            return
        try:
            theme = Theme.load(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Cannot import", str(exc))
            return
        self._load_into_controls(theme)
        self._preview()

    def _load_into_controls(self, theme: Theme) -> None:
        self.name.setText(theme.name)
        self.dark.setChecked(theme.dark)
        self.kind.setCurrentIndex(_KINDS.index(theme.background.kind))
        self.bg_color.set_color(theme.background.color)
        self.fit.setCurrentIndex(_FITS.index(theme.background.fit))
        self.scrim.setValue(int(theme.background.scrim * 100))
        self.opacity.setValue(int(theme.panel_opacity * 100))
        self.accent.set_color(theme.accent)
        self.text.set_color(theme.text)
        self.panel.set_color(theme.panel)
        self.font_on.setChecked(bool(theme.font_family))
        data = theme.background_bytes()
        if data:
            self._asset_bytes = data
            self._asset_name = theme.background.asset or "embedded"
            self.asset_label.setText(f"embedded ({len(data)//1024} KB)")
        self._kind_changed()

    # -- lifecycle ------------------------------------------------------------
    def _commit(self) -> None:
        self._committed = True
        if self._persist is not None:
            self._persist()
        self.committed.emit()

    def reject(self) -> None:
        # Restore the theme that was active before editing if nothing was saved.
        if not self._committed and self.settings.active_theme != self._original_active:
            self.settings.active_theme = self._original_active
        if not self._committed:
            app = QApplication.instance()
            if app is not None:
                apply_theme(app, self.settings)
        super().reject()
