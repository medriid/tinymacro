from __future__ import annotations

from PyQt6.QtCore import QAbstractAnimation, QSize, Qt, QVariantAnimation, pyqtProperty
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QWidget


class RecordingIndicator(QWidget):
    """A small dot that gently pulses while recording is active.

    When animations are disabled it degrades to a static filled/hollow dot, so
    the widget is always meaningful regardless of the animation setting.
    """

    def __init__(self, parent: QWidget | None = None, animated: bool = True) -> None:
        super().__init__(parent)
        self._active = False
        self._animated = animated
        self._phase = 1.0
        self._color = QColor("#d64545")
        self.setFixedSize(16, 16)
        self._anim = QVariantAnimation(self)
        self._anim.setStartValue(0.35)
        self._anim.setEndValue(1.0)
        self._anim.setDuration(750)
        self._anim.setLoopCount(-1)
        self._anim.valueChanged.connect(self._on_phase)
        self.setToolTip("Idle")

    def sizeHint(self) -> QSize:
        return QSize(16, 16)

    def set_animated(self, animated: bool) -> None:
        self._animated = animated
        if self._active:
            self.set_active(True)

    def set_color(self, color: str) -> None:
        self._color = QColor(color)
        self.update()

    def set_active(self, active: bool) -> None:
        running = self._anim.state() == QAbstractAnimation.State.Running
        if active == self._active and (running or not active):
            # Avoid restarting the pulse on every UI tick.
            return
        self._active = active
        self.setToolTip("Recording" if active else "Idle")
        self._anim.stop()
        if active and self._animated:
            self._anim.start()
        else:
            self._phase = 1.0 if active else 0.0
            self.update()

    def _on_phase(self, value: object) -> None:
        try:
            self._phase = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            self._phase = 1.0
        self.update()

    def get_phase(self) -> float:
        return self._phase

    def set_phase(self, value: float) -> None:
        self._phase = value
        self.update()

    phase = pyqtProperty(float, fget=get_phase, fset=set_phase)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(self._color)
        if not self._active:
            # Hollow gray dot when idle.
            color = QColor("#8a8a8a")
            color.setAlpha(120)
        else:
            color.setAlphaF(max(0.0, min(1.0, self._phase)))
        radius = 5 + (2 * self._phase if self._active else 0)
        center = self.rect().center()
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(center, int(radius), int(radius))
        painter.end()
