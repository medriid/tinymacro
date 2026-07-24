from __future__ import annotations

from PyQt6.QtCore import (
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QSequentialAnimationGroup,
    Qt,
    QTimer,
)
from PyQt6.QtWidgets import QGraphicsOpacityEffect, QLabel, QWidget


class Toast(QLabel):
    """A transient, self-dismissing message that floats over its parent."""

    def __init__(self, parent: QWidget, text: str, level: str = "info", animated: bool = True) -> None:
        super().__init__(text, parent)
        self._animated = animated
        self.setWordWrap(True)
        self.setMargin(10)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        palette = {
            "info": ("#2a2a2a", "#f0f0f0"),
            "success": ("#1f6f4a", "#ffffff"),
            "warning": ("#8a5a1a", "#ffffff"),
            "error": ("#8a2f2f", "#ffffff"),
        }
        bg, fg = palette.get(level, palette["info"])
        self.setStyleSheet(
            f"background: {bg}; color: {fg}; border-radius: 8px; font-weight: 600;"
        )
        self._effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._effect)
        self._effect.setOpacity(0.0)
        self.adjustSize()
        self.setMaximumWidth(max(240, parent.width() - 40))

    def show_for(self, milliseconds: int = 2600) -> None:
        self._reposition()
        self.show()
        self.raise_()
        if not self._animated:
            self._effect.setOpacity(0.96)
            QTimer.singleShot(milliseconds, self.close)
            return
        fade_in = QPropertyAnimation(self._effect, b"opacity", self)
        fade_in.setDuration(180)
        fade_in.setStartValue(0.0)
        fade_in.setEndValue(0.96)
        fade_in.setEasingCurve(QEasingCurve.Type.OutCubic)
        hold = QPropertyAnimation(self._effect, b"opacity", self)
        hold.setDuration(max(0, milliseconds))
        hold.setStartValue(0.96)
        hold.setEndValue(0.96)
        fade_out = QPropertyAnimation(self._effect, b"opacity", self)
        fade_out.setDuration(320)
        fade_out.setStartValue(0.96)
        fade_out.setEndValue(0.0)
        fade_out.setEasingCurve(QEasingCurve.Type.InCubic)
        group = QSequentialAnimationGroup(self)
        group.addAnimation(fade_in)
        group.addAnimation(hold)
        group.addAnimation(fade_out)
        group.finished.connect(self.close)
        group.start()
        self._group = group  # keep a reference alive

    def _reposition(self) -> None:
        parent = self.parentWidget()
        if not parent:
            return
        self.adjustSize()
        x = (parent.width() - self.width()) // 2
        y = parent.height() - self.height() - 16
        self.move(QPoint(max(8, x), max(8, y)))


class ToastManager:
    """Convenience for showing toasts over a host widget."""

    def __init__(self, host: QWidget, animated: bool = True) -> None:
        self.host = host
        self.animated = animated
        self._current: Toast | None = None

    def set_animated(self, animated: bool) -> None:
        self.animated = animated

    def show(self, text: str, level: str = "info", milliseconds: int = 2600) -> None:
        if self._current is not None:
            self._current.close()
        toast = Toast(self.host, text, level=level, animated=self.animated)
        toast.show_for(milliseconds)
        self._current = toast
