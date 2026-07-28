"""A polished, theme-matching colour picker used everywhere in Tiny Macro.

Replaces the OS-native ``QColorDialog`` (which ignores our theme) with a compact
dialog that inherits the app stylesheet: a saturation/value field, a hue bar,
live hex / RGB / HSV inputs, and a swatch strip of presets + recently used
colours. Call :meth:`ColorPickerDialog.get_color` for a hex string, or embed the
:class:`ColorPickerDialog` widget.
"""
from __future__ import annotations

from PyQt6.QtCore import QPoint, QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QLinearGradient, QPainter, QPen
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

# Persisted for the session so recently chosen colours are one click away.
_RECENT: list[str] = []
_PRESETS = [
    "#ffffff", "#c9ced6", "#8a8f99", "#3a3f47", "#111318", "#000000",
    "#e0554e", "#e0913a", "#e6c84f", "#2f9e6f", "#4f9dde", "#7c5cd6",
    "#ff5cae", "#d76d77", "#3a1c71", "#0f4c81", "#1f9e8f", "#b5179e",
]


class _SVField(QWidget):
    """Saturation (x) / value (y) picker for the current hue."""

    changed = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumSize(240, 180)
        self._h = 0.0
        self._s = 1.0
        self._v = 1.0

    def set_hue(self, h: float) -> None:
        self._h = h
        self.update()

    def set_sv(self, s: float, v: float) -> None:
        self._s, self._v = s, v
        self.update()

    def sv(self) -> tuple[float, float]:
        return self._s, self._v

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        base = QColor.fromHsvF(self._h, 1.0, 1.0)
        h_grad = QLinearGradient(r.left(), 0, r.right(), 0)
        h_grad.setColorAt(0.0, QColor("#ffffff"))
        h_grad.setColorAt(1.0, base)
        p.fillRect(r, h_grad)
        v_grad = QLinearGradient(0, r.top(), 0, r.bottom())
        v_grad.setColorAt(0.0, QColor(0, 0, 0, 0))
        v_grad.setColorAt(1.0, QColor(0, 0, 0, 255))
        p.fillRect(r, v_grad)
        # Marker.
        mx = r.left() + self._s * r.width()
        my = r.top() + (1 - self._v) * r.height()
        ring = QColor("#000000") if self._v > 0.5 else QColor("#ffffff")
        p.setPen(QPen(ring, 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(mx, my), 6, 6)

    def _apply(self, pos: QPoint) -> None:
        w, h = max(1, self.width()), max(1, self.height())
        self._s = min(1.0, max(0.0, pos.x() / w))
        self._v = 1.0 - min(1.0, max(0.0, pos.y() / h))
        self.update()
        self.changed.emit()

    def mousePressEvent(self, e) -> None:  # noqa: N802
        self._apply(e.position().toPoint())

    def mouseMoveEvent(self, e) -> None:  # noqa: N802
        if e.buttons() & Qt.MouseButton.LeftButton:
            self._apply(e.position().toPoint())


class _HueBar(QWidget):
    """Vertical hue selector."""

    changed = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.setFixedWidth(24)
        self.setMinimumHeight(180)
        self._h = 0.0

    def set_hue(self, h: float) -> None:
        self._h = h
        self.update()

    def hue(self) -> float:
        return self._h

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        r = QRectF(self.rect())
        grad = QLinearGradient(0, r.top(), 0, r.bottom())
        for i in range(7):
            grad.setColorAt(i / 6, QColor.fromHsvF(i / 6, 1.0, 1.0))
        p.fillRect(r, grad)
        y = r.top() + self._h * r.height()
        p.setPen(QPen(QColor("#ffffff"), 2))
        p.drawLine(int(r.left()), int(y), int(r.right()), int(y))
        p.setPen(QPen(QColor("#000000"), 1))
        p.drawLine(int(r.left()), int(y) + 2, int(r.right()), int(y) + 2)

    def _apply(self, y: int) -> None:
        self._h = min(1.0, max(0.0, y / max(1, self.height())))
        self.update()
        self.changed.emit()

    def mousePressEvent(self, e) -> None:  # noqa: N802
        self._apply(e.position().toPoint().y())

    def mouseMoveEvent(self, e) -> None:  # noqa: N802
        if e.buttons() & Qt.MouseButton.LeftButton:
            self._apply(e.position().toPoint().y())


class ColorPickerDialog(QDialog):
    """Themed colour picker returning a ``#rrggbb`` string."""

    def __init__(self, initial: str = "#ffffff", parent=None, title: str = "Pick a colour") -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self._updating = False
        self._color = QColor(initial if QColor.isValidColor(initial) else "#ffffff")

        self.sv = _SVField()
        self.hue = _HueBar()
        self.preview = QLabel()
        self.preview.setFixedHeight(28)
        self.hex = QLineEdit()
        self.hex.setMaxLength(7)
        self.hex.setFixedWidth(90)
        self.r = self._spin()
        self.g = self._spin()
        self.b = self._spin()

        top = QHBoxLayout()
        top.addWidget(self.sv, 1)
        top.addWidget(self.hue)

        rgb = QHBoxLayout()
        rgb.addWidget(QLabel("HEX"))
        rgb.addWidget(self.hex)
        rgb.addSpacing(8)
        for label, spin in (("R", self.r), ("G", self.g), ("B", self.b)):
            rgb.addWidget(QLabel(label))
            rgb.addWidget(spin)
        rgb.addStretch(1)

        self._swatches = QGridLayout()
        self._swatches.setSpacing(4)
        self._build_swatches()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.addLayout(top)
        root.addWidget(self.preview)
        root.addLayout(rgb)
        root.addWidget(QLabel("Presets & recent"))
        sw = QWidget()
        sw.setLayout(self._swatches)
        root.addWidget(sw)
        root.addWidget(buttons)

        self.sv.changed.connect(self._from_field)
        self.hue.changed.connect(self._from_field)
        self.hex.editingFinished.connect(self._from_hex)
        for spin in (self.r, self.g, self.b):
            spin.valueChanged.connect(self._from_rgb)

        self._set_color(self._color)

    # -- helpers --------------------------------------------------------------
    def _spin(self) -> QSpinBox:
        s = QSpinBox()
        s.setRange(0, 255)
        s.setFixedWidth(58)
        return s

    def _build_swatches(self) -> None:
        while self._swatches.count():
            item = self._swatches.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        colors = _PRESETS + [c for c in _RECENT if c not in _PRESETS]
        for i, hexv in enumerate(colors[:24]):
            btn = QPushButton()
            btn.setFixedSize(22, 22)
            btn.setToolTip(hexv)
            btn.setStyleSheet(f"background: {hexv}; border: 1px solid palette(mid); border-radius: 3px;")
            btn.clicked.connect(lambda _c, h=hexv: self._set_color(QColor(h)))
            self._swatches.addWidget(btn, i // 8, i % 8)

    def color_hex(self) -> str:
        return self._color.name()

    # -- synchronisation ------------------------------------------------------
    def _set_color(self, color: QColor) -> None:
        if not color.isValid():
            return
        self._color = color
        self._updating = True
        h, s, v, _ = color.getHsvF()
        h = max(0.0, h)  # achromatic colours report hue -1
        self.hue.set_hue(h)
        self.sv.set_hue(h)
        self.sv.set_sv(s, v)
        self.hex.setText(color.name())
        self.r.setValue(color.red())
        self.g.setValue(color.green())
        self.b.setValue(color.blue())
        self.preview.setStyleSheet(
            f"background: {color.name()}; border: 1px solid palette(mid); border-radius: 4px;"
        )
        self._updating = False

    def _from_field(self) -> None:
        if self._updating:
            return
        s, v = self.sv.sv()
        self._set_color(QColor.fromHsvF(self.hue.hue(), s, v))

    def _from_hex(self) -> None:
        if self._updating:
            return
        text = self.hex.text().strip()
        if not text.startswith("#"):
            text = "#" + text
        if QColor.isValidColor(text):
            self._set_color(QColor(text))

    def _from_rgb(self) -> None:
        if self._updating:
            return
        self._set_color(QColor(self.r.value(), self.g.value(), self.b.value()))

    def _accept(self) -> None:
        hexv = self._color.name()
        if hexv in _RECENT:
            _RECENT.remove(hexv)
        _RECENT.insert(0, hexv)
        del _RECENT[8:]
        self.accept()

    @staticmethod
    def get_color(initial: str = "#ffffff", parent=None, title: str = "Pick a colour") -> str | None:
        dlg = ColorPickerDialog(initial, parent, title)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            return dlg.color_hex()
        return None
