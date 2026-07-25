"""Shared animation helpers and animated widgets.

Built on the same QPropertyAnimation / QGraphicsOpacityEffect primitives already
used by ``toast.py`` and ``widgets.py``. Every animation respects an ``animated``
flag so the whole app degrades to instant, static behaviour when the user turns
animations off in Preferences.
"""
from __future__ import annotations

from PyQt6.QtCore import (
    QAbstractAnimation,
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QRect,
    Qt,
    pyqtProperty,
)
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QGraphicsOpacityEffect, QToolButton, QWidget


def fade_widget(widget: QWidget, start: float, end: float, duration: int = 180,
                on_finished=None, animated: bool = True) -> None:
    """Fade ``widget`` between two opacities via a graphics effect."""
    if not animated:
        if on_finished:
            on_finished()
        return
    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    effect.setOpacity(start)
    anim = QPropertyAnimation(effect, b"opacity", widget)
    anim.setDuration(duration)
    anim.setStartValue(start)
    anim.setEndValue(end)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    if on_finished:
        anim.finished.connect(on_finished)
    anim.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)
    widget._anim_ref = anim  # keep alive


def animate_geometry(widget: QWidget, start: QRect, end: QRect, duration: int = 200,
                     on_finished=None, animated: bool = True) -> None:
    if not animated:
        widget.setGeometry(end)
        if on_finished:
            on_finished()
        return
    anim = QPropertyAnimation(widget, b"geometry", widget)
    anim.setDuration(duration)
    anim.setStartValue(start)
    anim.setEndValue(end)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    if on_finished:
        anim.finished.connect(on_finished)
    anim.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)
    widget._geo_anim_ref = anim


class AnimatedToolButton(QToolButton):
    """A tool button with a smooth hover/press glow that QSS can't animate.

    A ``glow`` property (0..1) is driven by a QPropertyAnimation on hover/press
    and painted as a soft rounded background behind the normal button content.
    """

    def __init__(self, parent: QWidget | None = None, accent: str = "#3b82f6", animated: bool = True) -> None:
        super().__init__(parent)
        self._glow = 0.0
        self._accent = QColor(accent)
        self._animated = animated
        self.setAutoRaise(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._anim = QPropertyAnimation(self, b"glow", self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def set_accent(self, color: str) -> None:
        self._accent = QColor(color)
        self.update()

    def set_animated(self, animated: bool) -> None:
        self._animated = animated

    def get_glow(self) -> float:
        return self._glow

    def set_glow(self, value: float) -> None:
        self._glow = value
        self.update()

    glow = pyqtProperty(float, fget=get_glow, fset=set_glow)

    def _to(self, value: float) -> None:
        if not self._animated:
            self.set_glow(value)
            return
        self._anim.stop()
        self._anim.setStartValue(self._glow)
        self._anim.setEndValue(value)
        self._anim.start()

    def enterEvent(self, event):  # noqa: N802
        self._to(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event):  # noqa: N802
        self._to(0.0)
        super().leaveEvent(event)

    def paintEvent(self, event):  # noqa: N802
        if self._glow > 0.01:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            color = QColor(self._accent)
            color.setAlphaF(0.16 * self._glow)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 6, 6)
            painter.end()
        super().paintEvent(event)
