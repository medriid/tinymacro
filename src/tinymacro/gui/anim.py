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
    QEvent,
    QObject,
    QPoint,
    QPropertyAnimation,
    QRect,
    Qt,
    pyqtProperty,
)
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QGraphicsOpacityEffect, QToolButton, QWidget

from tinymacro.gui.sounds import ui_sounds


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


class InteractionFx(QObject):
    """Adds hover tint + hover/click sounds to buttons we don't subclass.

    Qt style sheets can colour a hover state but can't play audio or tint per
    button, so this event filter does both for the Classic toolbar's generated
    QToolButtons and the Studio side-panel QPushButtons. One instance can serve
    many buttons; ``attach`` remembers each button's accent.
    """

    # State lives on the widget as Qt properties rather than in a dict keyed by
    # id(): PyQt hands out a *new* Python wrapper for the same C++ widget on
    # every lookup (e.g. QToolBar.widgetForAction), and those short-lived
    # wrappers recycle their id(), which would collide and lose entries.
    _ACCENT = "tmAccent"
    _BASE = "tmBaseStyle"

    def attach(self, button: QWidget, accent: str | None = None) -> None:
        if button is None:
            return
        button.setProperty(self._BASE, button.styleSheet())
        if accent:
            button.setProperty(self._ACCENT, accent)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.installEventFilter(self)

    def set_accent(self, button: QWidget, accent: str) -> None:
        if button is not None:
            button.setProperty(self._ACCENT, accent)

    def eventFilter(self, obj, event):  # noqa: N802
        kind = event.type()
        if kind == QEvent.Type.Enter:
            if obj.isEnabled():
                ui_sounds().hover()
                self._tint(obj, hovered=True)
        elif kind == QEvent.Type.Leave:
            self._tint(obj, hovered=False)
        elif kind == QEvent.Type.MouseButtonPress:
            if obj.isEnabled():
                ui_sounds().click()
        return super().eventFilter(obj, event)

    def _tint(self, button: QWidget, hovered: bool) -> None:
        accent = button.property(self._ACCENT)
        base = button.property(self._BASE) or ""
        if not accent:
            return
        if hovered:
            colour = QColor(accent)
            soft = QColor(colour)
            soft.setAlpha(46)
            button.setStyleSheet(
                base
                + f"\nQToolButton, QPushButton {{ border: 1px solid {colour.name()};"
                f" background: rgba({soft.red()},{soft.green()},{soft.blue()},{soft.alpha()}); }}"
            )
        else:
            button.setStyleSheet(base)


class AnimatedToolButton(QToolButton):
    """A tool button with a smooth hover/press glow that QSS can't animate.

    A ``glow`` property (0..1) is driven by a QPropertyAnimation on hover/press
    and painted as a soft rounded background behind the normal button content.
    Pressing deepens the glow and draws an accent ring, so clicks feel physical;
    hover/click also drive the UI sound effects.
    """

    def __init__(self, parent: QWidget | None = None, accent: str = "#3b82f6", animated: bool = True) -> None:
        super().__init__(parent)
        self._glow = 0.0
        self._accent = QColor(accent)
        self._animated = animated
        self._pressed = False
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
        if self.isEnabled():
            ui_sounds().hover()
        super().enterEvent(event)

    def leaveEvent(self, event):  # noqa: N802
        self._pressed = False
        self._to(0.0)
        super().leaveEvent(event)

    def mousePressEvent(self, event):  # noqa: N802
        self._pressed = True
        if self.isEnabled():
            ui_sounds().click()
        self._to(1.0)
        self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802
        self._pressed = False
        self.update()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):  # noqa: N802
        if self._glow > 0.01 or self._pressed:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            # A pressed button sits noticeably brighter than a hovered one.
            fill = QColor(self._accent)
            fill.setAlphaF((0.30 if self._pressed else 0.18) * max(self._glow, 0.85 if self._pressed else 0.0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(fill)
            rect = self.rect().adjusted(1, 1, -1, -1)
            painter.drawRoundedRect(rect, 7, 7)
            # Accent ring grows in with the glow so hover reads as "targetable".
            ring = QColor(self._accent)
            ring.setAlphaF((0.85 if self._pressed else 0.45) * max(self._glow, 0.85 if self._pressed else 0.0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(ring, 1.4))
            painter.drawRoundedRect(rect, 7, 7)
            painter.end()
        super().paintEvent(event)
