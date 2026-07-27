"""A zoomable graphical timeline track that visualises a macro's events.

Point events (key/mouse/wheel/image/run/pixel/control) render as coloured ticks;
wait steps render as spans proportional to their duration. Clicking a mark emits
the event's index so the editor can select the matching table row.
"""
from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QWidget

from tinymacro.core.macro import Macro

_NS = 1_000_000_000
_LEFT = 8
_TOP = 10
_TRACK_H = 34

# Fallback colours for kinds the theme's kind_colors doesn't cover.
_EXTRA_COLORS = {
    "image": "#4f9dde",
    "run": "#c2596b",
    "pixel": "#2f9e6f",
    "window": "#8a7de0",
    "if": "#d98a20",
    "else": "#d98a20",
    "endif": "#d98a20",
    "loop": "#7c5cd6",
    "endloop": "#7c5cd6",
}


class TimelineWidget(QWidget):
    event_clicked = pyqtSignal(int)

    def __init__(self, parent=None, kind_colors: dict | None = None) -> None:
        super().__init__(parent)
        self._macro = Macro()
        self._kind_colors = dict(kind_colors or {})
        self._pps = 120.0  # pixels per second (zoom)
        self._selected = -1
        self._playing = -1  # source index currently executing during playback
        self.setMinimumHeight(_TOP + _TRACK_H + 18)
        self.setMouseTracking(True)

    # -- data / zoom ----------------------------------------------------------
    def set_macro(self, macro: Macro) -> None:
        self._macro = macro
        self._resize_to_content()
        self.update()

    def set_kind_colors(self, kind_colors: dict) -> None:
        self._kind_colors = dict(kind_colors or {})
        self.update()

    def set_selected(self, index: int) -> None:
        self._selected = index
        self.update()

    def set_playing(self, index: int) -> None:
        """Mark the step currently executing during playback (-1 to clear)."""
        if index == self._playing:
            return
        self._playing = index
        self.update()

    def set_zoom(self, pixels_per_second: float) -> None:
        self._pps = max(4.0, float(pixels_per_second))
        self._resize_to_content()
        self.update()

    def _duration_s(self) -> float:
        return max(self._macro.duration_ns / _NS, 0.001)

    def _resize_to_content(self) -> None:
        width = int(_LEFT * 2 + self._duration_s() * self._pps) + 40
        self.setMinimumWidth(max(width, 200))
        self.resize(max(width, self.width()), self.height())

    # -- interaction ----------------------------------------------------------
    def mousePressEvent(self, event) -> None:  # noqa: N802
        events = self._macro.sorted_events()
        if not events:
            return
        click_x = event.position().x()
        best, best_dist = -1, 1e9
        for i, ev in enumerate(events):
            x = _LEFT + (ev.timestamp_ns / _NS) * self._pps
            dist = abs(x - click_x)
            if dist < best_dist:
                best, best_dist = i, dist
        if best >= 0 and best_dist <= 12:
            self._selected = best
            self.event_clicked.emit(best)
            self.update()

    # -- painting -------------------------------------------------------------
    def _color_for(self, kind: str) -> QColor:
        hexval = self._kind_colors.get(kind) or _EXTRA_COLORS.get(kind, "#8a8a8a")
        return QColor(hexval)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = self.palette()
        painter.fillRect(self.rect(), palette.base())

        baseline = _TOP + _TRACK_H
        border = palette.mid().color()
        painter.setPen(border)
        painter.drawLine(0, baseline, self.width(), baseline)

        # Second ticks, spaced so labels never crowd.
        step = 1
        for candidate in (1, 2, 5, 10, 30, 60, 120, 300):
            if candidate * self._pps >= 48:
                step = candidate
                break
        painter.setPen(palette.mid().color())
        second = 0
        while _LEFT + second * self._pps <= self.width():
            x = int(_LEFT + second * self._pps)
            painter.drawLine(x, baseline, x, baseline + 4)
            painter.drawText(x + 2, baseline + 15, f"{second}s")
            second += step

        events = self._macro.sorted_events()
        for i, ev in enumerate(events):
            x = _LEFT + (ev.timestamp_ns / _NS) * self._pps
            color = self._color_for(ev.kind)
            if ev.kind == "wait":
                span = max(2.0, (ev.duration_ns / _NS) * self._pps)
                rect = QRectF(x, _TOP + 6, span, _TRACK_H - 12)
                color.setAlpha(150)
                painter.fillRect(rect, color)
            else:
                rect = QRectF(x - 1.5, _TOP, 3.0, _TRACK_H)
                painter.fillRect(rect, color)
            if i == self._selected:
                painter.setPen(palette.highlight().color())
                painter.drawRect(QRectF(x - 3, _TOP - 3, 6, _TRACK_H + 6))
                painter.setPen(Qt.PenStyle.NoPen)

        # Playhead: a bright vertical line + top caret at the executing step, drawn
        # last so it sits above every tick.
        if 0 <= self._playing < len(events):
            px = _LEFT + (events[self._playing].timestamp_ns / _NS) * self._pps
            play_color = QColor("#28c76f")
            painter.setPen(play_color)
            painter.drawLine(int(px), _TOP - 4, int(px), baseline)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(play_color)
            caret = [QPointF(px + dx, _TOP - 6 + dy) for dx, dy in ((-4, -2), (4, -2), (0, 4))]
            painter.drawPolygon(*caret)
            painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.end()
