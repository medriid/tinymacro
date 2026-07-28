"""A cinematic first-run guided tour.

:class:`OnboardingOverlay` covers the host window with a *blurred snapshot* of it,
dims that, then punches a crisp, softly-glowing spotlight over one feature at a
time while a floating card explains it. The spotlight glides between steps, the
card cross-fades, and the whole thing fades in/out — so onboarding feels like a
guided walk-through rather than a stack of tooltips.

The host supplies an ordered list of :class:`OnboardingStep` (each pointing at a
widget to highlight); the overlay handles rendering, navigation (Back / Next /
Skip, plus arrow keys and Esc) and the fade animations. It emits :attr:`finished`
once the user completes or skips the tour, so the host can persist that it ran.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PyQt6.QtCore import (
    QEasingCurve,
    QEvent,
    QPoint,
    QPropertyAnimation,
    QRect,
    QRectF,
    Qt,
    QTimer,
    pyqtProperty,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import (
    QGraphicsBlurEffect,
    QGraphicsOpacityEffect,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


@dataclass
class OnboardingStep:
    """One stop on the tour: a title, a body, and the widget to spotlight.

    ``target`` is a callable resolved lazily at display time (widgets may not
    exist or be visible when the steps are declared). Returning ``None`` — or
    omitting it — makes the step a centred, spotlight-less card (intro/outro).
    """

    title: str
    body: str
    target: Callable[[], QWidget | None] | None = None


# Onboarding adopts the app's look: rounded surfaces, the UI font, theme colours.
_SPOT_PAD = 8       # padding around the highlighted widget
_SPOT_RADIUS = 8    # rounded corners to match the app's controls
_BLUR_RADIUS = 6    # a light blur — the UI stays recognisable behind the tour
_DIM_ALPHA = 150


def _colors():
    from tinymacro.gui.theme import current_colors

    return current_colors()


class _Dots(QWidget):
    """A row of rounded progress dots; the current step uses the accent colour."""

    def __init__(self, count: int, accent: str, muted: str, parent=None) -> None:
        super().__init__(parent)
        self._count = max(1, count)
        self._current = 0
        self._accent = QColor(accent)
        self._muted = QColor(muted)
        self.setFixedHeight(12)
        self.setMinimumWidth(self._count * 14)

    def set_current(self, index: int) -> None:
        self._current = index
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        cy = self.height() // 2
        for i in range(self._count):
            active = i == self._current
            painter.setBrush(self._accent if active else self._muted)
            r = 4 if active else 3
            cx = 5 + i * 14
            painter.drawEllipse(QPoint(cx, cy), r, r)


class OnboardingOverlay(QWidget):
    """A screen-filling blurred-spotlight tour over ``host``.

    Rendered as its own top-level window covering the whole screen the host is on,
    so the tour is fully visible even when the app window is small and tucked in a
    corner. The host window is drawn (blurred, then crisp inside the spotlight) at
    its real on-screen position; everything else is a dark scrim.
    """

    finished = pyqtSignal()

    def __init__(self, host: QWidget, steps: list[OnboardingStep], animated: bool = True) -> None:
        super().__init__(None)  # top-level, so it can span the whole screen
        self._host = host
        self._steps = steps
        self._index = 0
        self._animated = animated
        self._done = False
        self._blurred: QPixmap | None = None
        self._sharp: QPixmap | None = None
        self._host_rect = QRect()  # host window within this overlay (screen-local)
        self._spot_rect = QRect()
        self._pulse = 0.0
        # Adopt the active theme's colours so the tour feels part of the app.
        c = _colors()
        dark = c.dark if c else True
        self._panel = (c.elevated if c else ("#232326" if dark else "#ffffff"))
        self._border = (c.border if c else "#3a3a3a")
        self._text = (c.text if c else "#f0f0f0")
        self._muted = (c.muted if c else "#a0a0a0")
        self._accent = (c.accent if c else "#ffffff")
        self._accent_text = (c.accent_text if c else "#151515")

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        self._build_card()

        # A gentle pulse on the spotlight ring for a touch of life.
        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._tick_pulse)
        if animated:
            self._pulse_timer.start(33)

    # -- construction ---------------------------------------------------------
    def _build_card(self) -> None:
        self.card = QWidget(self)
        self.card.setObjectName("onbCard")
        self.card.setFixedWidth(390)
        self.card.setStyleSheet(
            f"""
            #onbCard {{
                background: {self._panel};
                border: 1px solid {self._border};
                border-radius: 10px;
            }}
            #onbTitle {{ color: {self._text}; font-size: 15px; font-weight: 700; }}
            #onbBody  {{ color: {self._text}; font-size: 12.5px; }}
            #onbStep  {{ color: {self._muted}; font-size: 11px; }}
            QPushButton {{
                color: {self._text}; background: {self._panel};
                border: 1px solid {self._border}; border-radius: 6px;
                padding: 6px 14px; font-size: 12px;
            }}
            QPushButton:hover {{ border-color: {self._accent}; }}
            QPushButton:disabled {{ color: {self._muted}; }}
            QPushButton#onbNext {{
                color: {self._accent_text}; background: {self._accent};
                border: 1px solid {self._accent}; font-weight: 600;
            }}
            QPushButton#onbSkip {{
                background: transparent; border: none; color: {self._muted};
            }}
            QPushButton#onbSkip:hover {{ color: {self._text}; }}
            """
        )
        lay = QVBoxLayout(self.card)
        lay.setContentsMargins(20, 18, 20, 16)
        lay.setSpacing(10)

        top = QHBoxLayout()
        self._step_label = QLabel(objectName="onbStep")
        self._skip_btn = QPushButton("Skip tour", objectName="onbSkip")
        self._skip_btn.clicked.connect(self._skip)
        top.addWidget(self._step_label)
        top.addStretch(1)
        top.addWidget(self._skip_btn)
        lay.addLayout(top)

        self._title = QLabel(objectName="onbTitle")
        self._title.setWordWrap(True)
        self._body = QLabel(objectName="onbBody")
        self._body.setWordWrap(True)
        lay.addWidget(self._title)
        lay.addWidget(self._body)

        controls = QHBoxLayout()
        self._dots = _Dots(len(self._steps), self._accent, self._muted)
        self._back_btn = QPushButton("Back")
        self._back_btn.clicked.connect(self._back)
        self._next_btn = QPushButton("Next", objectName="onbNext")
        self._next_btn.clicked.connect(self._next)
        controls.addWidget(self._dots)
        controls.addStretch(1)
        controls.addWidget(self._back_btn)
        controls.addWidget(self._next_btn)
        lay.addLayout(controls)

        # Fade the card in/out on each step via an opacity effect.
        self._card_fx = QGraphicsOpacityEffect(self.card)
        self.card.setGraphicsEffect(self._card_fx)
        self._card_fx.setOpacity(1.0)

    # -- lifecycle ------------------------------------------------------------
    def _fit_to_screen(self) -> None:
        """Cover the whole screen the host is on and locate the host within it."""
        screen = self._host.screen() or self._host.window().screen()
        geo = screen.geometry()
        self.setGeometry(geo)
        top_left = self._host.mapToGlobal(QPoint(0, 0)) - geo.topLeft()
        self._host_rect = QRect(top_left, self._host.size())

    def start(self) -> None:
        """Snapshot the host, show the full-screen overlay, present the first step."""
        self._fit_to_screen()
        self._capture()
        # Track the window: re-snapshot and re-fit if the host moves or resizes so
        # the tour stays glued to it wherever it is.
        self._host.installEventFilter(self)
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()
        if self._animated:
            fx = QGraphicsOpacityEffect(self)
            self.setGraphicsEffect(fx)
            self._fade = QPropertyAnimation(fx, b"opacity", self)
            self._fade.setDuration(260)
            self._fade.setStartValue(0.0)
            self._fade.setEndValue(1.0)
            self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._fade.finished.connect(lambda: self.setGraphicsEffect(None))
            self._fade.start()
        self._show_step(0, animate=False)

    def _capture(self) -> None:
        """Grab the host once, keep a sharp copy and a blurred copy."""
        sharp = self._host.grab()
        self._sharp = sharp
        self._blurred = self._blur(sharp, _BLUR_RADIUS)

    @staticmethod
    def _blur(pixmap: QPixmap, radius: float) -> QPixmap:
        scene = QGraphicsScene()
        item = QGraphicsPixmapItem(pixmap)
        effect = QGraphicsBlurEffect()
        effect.setBlurRadius(radius)
        item.setGraphicsEffect(effect)
        scene.addItem(item)
        out = QPixmap(pixmap.size())
        out.setDevicePixelRatio(pixmap.devicePixelRatio())
        out.fill(Qt.GlobalColor.transparent)
        painter = QPainter(out)
        scene.render(painter, QRectF(out.rect()), QRectF(pixmap.rect()))
        painter.end()
        return out

    # -- navigation -----------------------------------------------------------
    def _show_step(self, index: int, animate: bool = True) -> None:
        self._index = max(0, min(index, len(self._steps) - 1))
        step = self._steps[self._index]
        self._title.setText(step.title)
        self._body.setText(step.body)
        self._step_label.setText(f"Step {self._index + 1} of {len(self._steps)}")
        self._dots.set_current(self._index)
        self._back_btn.setEnabled(self._index > 0)
        self._next_btn.setText("Finish" if self._index == len(self._steps) - 1 else "Next")
        self.card.adjustSize()

        target_rect = self._target_rect(step)
        if animate and self._animated and not self._spot_rect.isNull():
            self._anim = QPropertyAnimation(self, b"spot", self)
            self._anim.setDuration(360)
            self._anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
            self._anim.setStartValue(self._spot_rect)
            self._anim.setEndValue(target_rect)
            self._anim.start()
        else:
            self.spot = target_rect  # type: ignore[assignment]
        self._flash_card()

    def _target_rect(self, step: OnboardingStep) -> QRect:
        widget = step.target() if step.target else None
        if widget is None or not widget.isVisible():
            return QRect()
        # Map the control's global position into this screen-filling overlay.
        top_left = widget.mapToGlobal(QPoint(0, 0)) - self.geometry().topLeft()
        rect = QRect(top_left, widget.size())
        return rect.adjusted(-_SPOT_PAD, -_SPOT_PAD, _SPOT_PAD, _SPOT_PAD)

    def _flash_card(self) -> None:
        if not self._animated:
            self._place_card(self._spot_rect)
            return
        self._card_anim = QPropertyAnimation(self._card_fx, b"opacity", self)
        self._card_anim.setDuration(220)
        self._card_anim.setStartValue(0.0)
        self._card_anim.setEndValue(1.0)
        self._card_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._card_anim.start()

    def _next(self) -> None:
        if self._index >= len(self._steps) - 1:
            self._finish()
        else:
            self._show_step(self._index + 1)

    def _back(self) -> None:
        if self._index > 0:
            self._show_step(self._index - 1)

    def _skip(self) -> None:
        self._finish()

    def eventFilter(self, obj, event):  # noqa: N802
        if obj is self._host and not self._done and event.type() in (
            QEvent.Type.Resize, QEvent.Type.Move
        ):
            self._fit_to_screen()
            self._capture()
            self._show_step(self._index, animate=False)
        return super().eventFilter(obj, event)

    def _finish(self) -> None:
        if self._done:
            return
        self._done = True
        self._host.removeEventFilter(self)
        self._pulse_timer.stop()
        self.finished.emit()
        if self._animated:
            fx = QGraphicsOpacityEffect(self)
            self.setGraphicsEffect(fx)
            self._out = QPropertyAnimation(fx, b"opacity", self)
            self._out.setDuration(200)
            self._out.setStartValue(1.0)
            self._out.setEndValue(0.0)
            self._out.setEasingCurve(QEasingCurve.Type.InCubic)
            self._out.finished.connect(self.close)
            self._out.start()
        else:
            self.close()

    # -- animated properties --------------------------------------------------
    def _get_spot(self) -> QRect:
        return self._spot_rect

    def _set_spot(self, rect: QRect) -> None:
        self._spot_rect = rect
        self._place_card(rect)
        self.update()

    spot = pyqtProperty(QRect, fget=_get_spot, fset=_set_spot)

    def _tick_pulse(self) -> None:
        self._pulse = (self._pulse + 0.04) % 1.0
        if not self._spot_rect.isNull():
            self.update()

    # -- placement ------------------------------------------------------------
    def _place_card(self, spot: QRect) -> None:
        cw, ch = self.card.width(), self.card.height()
        margin = 24
        if spot.isNull():
            x = (self.width() - cw) // 2
            y = (self.height() - ch) // 2
        else:
            if spot.bottom() + margin + ch <= self.height():
                y = spot.bottom() + margin
            elif spot.top() - margin - ch >= 0:
                y = spot.top() - margin - ch
            else:
                y = (self.height() - ch) // 2
            x = spot.center().x() - cw // 2
            x = max(margin, min(x, self.width() - cw - margin))
        self.card.move(int(x), int(y))

    # -- events ---------------------------------------------------------------
    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self._place_card(self._spot_rect)

    def keyPressEvent(self, event):  # noqa: N802
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self._skip()
        elif key in (Qt.Key.Key_Right, Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self._next()
        elif key == Qt.Key.Key_Left:
            self._back()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event):  # noqa: N802
        # A click on the highlighted feature advances; clicks elsewhere are
        # swallowed so the tour stays in control.
        if not self._spot_rect.isNull() and self._spot_rect.contains(event.pos()):
            self._next()
        event.accept()

    def paintEvent(self, _event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()

        # Dark fills the whole screen; the app window is drawn (blurred) in place.
        painter.fillRect(rect, QColor(6, 7, 10))
        if self._blurred is not None:
            painter.drawPixmap(self._host_rect, self._blurred)
        painter.fillRect(rect, QColor(8, 10, 14, _DIM_ALPHA))

        spot = self._spot_rect
        if not spot.isNull() and self._sharp is not None:
            path = QPainterPath()
            path.addRoundedRect(QRectF(spot), _SPOT_RADIUS, _SPOT_RADIUS)
            painter.save()
            painter.setClipPath(path)
            painter.drawPixmap(self._host_rect, self._sharp)  # crisp control inside the spotlight
            painter.restore()

            # A soft, gently pulsing rounded ring in the theme accent.
            glow = abs(0.5 - self._pulse) * 2  # 0..1 triangle
            ring = QColor(self._accent)
            ring.setAlpha(150 + int(80 * glow))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(ring, 2.5))
            painter.drawPath(path)
        painter.end()
