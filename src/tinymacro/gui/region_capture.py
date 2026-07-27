"""Full-screen "snip" overlay: drag a rectangle to grab an on-screen image or
colour.

The overlay freezes a screenshot of the whole virtual desktop first, then lets
the user rubber-band a rectangle over that frozen image (so the dimming overlay
itself is never captured). On release it can hand back either the cropped region
as a base64 PNG (for click-image steps) or a sampled pixel colour plus its screen
coordinates (for wait-pixel steps).

Everything is captured at each screen's native device resolution so the stored
template matches what playback grabs off the real screen.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QPoint, QRect, Qt
from PyQt6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QDialog, QWidget


@dataclass(frozen=True, slots=True)
class _ScreenGrab:
    """A single screen's frozen pixels plus where it lives in global space."""

    pixmap: QPixmap          # native-resolution grab
    geometry: QRect          # logical global geometry
    ratio: float             # device-pixel ratio (native px per logical px)


class RegionCaptureOverlay(QDialog):
    """Modal fullscreen rubber-band selector over a frozen desktop screenshot."""

    def __init__(self, parent: QWidget | None = None) -> None:
        # No parent so the overlay is a true top-level spanning every monitor.
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.selected_rect: QRect | None = None  # global logical coords

        self._grabs: list[_ScreenGrab] = []
        virtual = QRect()
        for screen in QGuiApplication.screens():
            geo = screen.geometry()
            pixmap = screen.grabWindow(0)  # 0 == entire screen
            self._grabs.append(_ScreenGrab(pixmap, geo, screen.devicePixelRatio()))
            virtual = virtual.united(geo)
        self._virtual = virtual

        # A logical-resolution composite used only for the dimmed backdrop.
        self._backdrop = QPixmap(virtual.size())
        self._backdrop.fill(Qt.GlobalColor.black)
        painter = QPainter(self._backdrop)
        for grab in self._grabs:
            target = grab.geometry.translated(-virtual.topLeft())
            painter.drawPixmap(target, grab.pixmap, grab.pixmap.rect())
        painter.end()

        self.setGeometry(virtual)
        self._origin: QPoint | None = None
        self._current: QPoint | None = None

    # -- painting -------------------------------------------------------------
    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._backdrop)
        # Dim everything, then punch the selection back to full brightness.
        painter.fillRect(self.rect(), QColor(0, 0, 0, 120))
        rect = self._selection_local()
        if rect is not None and rect.isValid():
            painter.drawPixmap(rect, self._backdrop, rect)
            pen = QPen(QColor(80, 170, 255), 2)
            painter.setPen(pen)
            painter.drawRect(rect)
        painter.end()

    # -- interaction ----------------------------------------------------------
    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._origin = event.pos()
            self._current = event.pos()
            self.update()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._origin is not None:
            self._current = event.pos()
            self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton or self._origin is None:
            return
        rect = self._selection_local()
        if rect is None or rect.width() < 2 or rect.height() < 2:
            # Treat a click / tiny drag as a 1x1 pick centred on the release point.
            rect = QRect(event.pos(), event.pos())
        self.selected_rect = rect.translated(self._virtual.topLeft())
        self.accept()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)

    def _selection_local(self) -> QRect | None:
        if self._origin is None or self._current is None:
            return None
        return QRect(self._origin, self._current).normalized()

    # -- results --------------------------------------------------------------
    def crop_native(self) -> QImage | None:
        """The selected region as a native-resolution image, or ``None``."""
        rect = self.selected_rect
        if rect is None:
            return None
        grab = self._grab_for(rect.center())
        if grab is None:
            return None
        # Map the global-logical selection into this screen's native pixels.
        local = rect.translated(-grab.geometry.topLeft())
        r = grab.ratio
        native = QRect(
            round(local.left() * r), round(local.top() * r),
            max(1, round(local.width() * r)), max(1, round(local.height() * r)),
        )
        native = native.intersected(grab.pixmap.rect())
        if native.isEmpty():
            return None
        return grab.pixmap.copy(native).toImage()

    def sample_color(self) -> tuple[int, int, int] | None:
        """Average RGB of the selected region (center pixel if 1x1)."""
        image = self.crop_native()
        if image is None:
            return None
        image = image.convertToFormat(QImage.Format.Format_RGB32)
        w, h = image.width(), image.height()
        if w * h <= 1:
            c = image.pixelColor(0, 0)
            return (c.red(), c.green(), c.blue())
        # Sample a small grid to keep it cheap on large selections.
        step_x = max(1, w // 8)
        step_y = max(1, h // 8)
        rs = gs = bs = n = 0
        for y in range(0, h, step_y):
            for x in range(0, w, step_x):
                c = image.pixelColor(x, y)
                rs += c.red(); gs += c.green(); bs += c.blue(); n += 1
        if n == 0:
            return None
        return (rs // n, gs // n, bs // n)

    def center_physical(self) -> tuple[int, int] | None:
        """Selection centre in physical/screen pixels (what mss samples at).

        Playback reads wait-pixel colours through mss, which addresses the desktop
        in device pixels, so a logical Qt coordinate would be off on a scaled
        display. Convert through the containing screen's device-pixel ratio.
        """
        rect = self.selected_rect
        if rect is None:
            return None
        grab = self._grab_for(rect.center())
        if grab is None:
            return None
        center = rect.center()
        local = center - grab.geometry.topLeft()
        r = grab.ratio
        origin_x = round(grab.geometry.left() * r)
        origin_y = round(grab.geometry.top() * r)
        return (origin_x + round(local.x() * r), origin_y + round(local.y() * r))

    def _grab_for(self, point: QPoint) -> _ScreenGrab | None:
        for grab in self._grabs:
            if grab.geometry.contains(point):
                return grab
        return self._grabs[0] if self._grabs else None


def _image_to_b64_png(image: QImage) -> str:
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    buffer.close()
    return base64.b64encode(bytes(data)).decode("ascii")


def capture_region_png(parent: QWidget | None = None) -> str | None:
    """Prompt the user to drag a rectangle; return its PNG as base64, or ``None``."""
    overlay = RegionCaptureOverlay(parent)
    if overlay.exec() != QDialog.DialogCode.Accepted:
        return None
    image = overlay.crop_native()
    if image is None or image.isNull():
        return None
    return _image_to_b64_png(image)


def capture_pixel(parent: QWidget | None = None) -> tuple[int, int, tuple[int, int, int]] | None:
    """Prompt the user to pick a point/region; return (x, y, (r, g, b)) or ``None``.

    ``x, y`` are the selection centre in global screen coordinates.
    """
    overlay = RegionCaptureOverlay(parent)
    if overlay.exec() != QDialog.DialogCode.Accepted or overlay.selected_rect is None:
        return None
    color = overlay.sample_color()
    center = overlay.center_physical()
    if color is None or center is None:
        return None
    return (center[0], center[1], color)
