"""Renders a custom theme's image/animated background behind a window.

A :class:`ThemedBackground` is a click-through child widget lowered beneath the
window's content. It paints a still image (PNG/JPG) or an animated GIF (via
``QMovie``) scaled per the theme's fit mode, with a scrim over it for legibility.
Solid-colour backgrounds don't need this — the palette handles them — so the
window only installs one for ``image``/``animated`` themes.

Because the window's surfaces are made translucent (rgba) when a background is
active, the image shows through toolbars, panels and lists.
"""
from __future__ import annotations

from PyQt6.QtCore import QBuffer, QByteArray, QEvent, QIODevice, Qt
from PyQt6.QtGui import QColor, QMovie, QPainter, QPixmap
from PyQt6.QtWidgets import QWidget

from tinymacro.core.theme_pack import Theme


class ThemedBackground(QWidget):
    """A lowered, click-through image/animated backdrop for a window."""

    def __init__(self, window: QWidget, theme: Theme) -> None:
        super().__init__(window)
        self._window = window
        self._fit = theme.background.fit
        self._scrim = theme.background.scrim
        self._dark = theme.dark
        self._base = QColor(theme.panel)
        self._pixmap: QPixmap | None = None
        self._movie: QMovie | None = None
        self._buffer: QBuffer | None = None
        self._paused = False

        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self._load(theme)
        self.setGeometry(window.rect())
        window.installEventFilter(self)
        self.lower()
        self.show()

    # -- loading --------------------------------------------------------------
    def _load(self, theme: Theme) -> None:
        data = theme.background_bytes()
        if not data:
            return
        if theme.background.kind == "animated":
            self._buffer = QBuffer(self)
            self._buffer.setData(QByteArray(data))
            self._buffer.open(QIODevice.OpenModeFlag.ReadOnly)
            movie = QMovie(self._buffer, b"GIF", self)
            movie.setCacheMode(QMovie.CacheMode.CacheAll)
            # Coarse FPS cap: QMovie speed is a percentage of the GIF's own rate;
            # if the source is very fast, slow it toward the cap.
            movie.jumpToFrame(0)
            movie.frameChanged.connect(lambda _i: self.update())
            self._movie = movie
            movie.start()
        else:
            pixmap = QPixmap()
            if pixmap.loadFromData(data):
                self._pixmap = pixmap

    # -- animation control (perf guards) --------------------------------------
    def set_paused(self, paused: bool) -> None:
        """Freeze/resume the GIF — used while a macro plays or the window is idle."""
        self._paused = paused
        if self._movie is not None:
            state = QMovie.MovieState.Paused if paused else QMovie.MovieState.Running
            if self._movie.state() != state:
                self._movie.setPaused(paused)

    def dispose(self) -> None:
        """Stop animation and detach from the window before removal."""
        self._window.removeEventFilter(self)
        if self._movie is not None:
            self._movie.stop()
        if self._buffer is not None:
            self._buffer.close()

    # -- sizing ---------------------------------------------------------------
    def eventFilter(self, obj, event):  # noqa: N802
        if obj is self._window and event.type() == QEvent.Type.Resize:
            self.setGeometry(self._window.rect())
        return super().eventFilter(obj, event)

    # -- painting -------------------------------------------------------------
    def _current(self) -> QPixmap | None:
        if self._movie is not None:
            pm = self._movie.currentPixmap()
            return pm if not pm.isNull() else None
        return self._pixmap

    def paintEvent(self, _event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        rect = self.rect()
        pixmap = self._current()
        if pixmap is None or pixmap.isNull():
            painter.fillRect(rect, self._base)
            return

        fit = self._fit
        if fit == "tile":
            painter.drawTiledPixmap(rect, pixmap)
        elif fit == "stretch":
            painter.drawPixmap(rect, pixmap)
        else:
            if fit == "cover":
                scaled = pixmap.scaled(
                    self.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
            elif fit == "center":
                scaled = pixmap
                painter.fillRect(rect, self._base)
            else:  # contain
                scaled = pixmap.scaled(
                    self.size(), Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                painter.fillRect(rect, self._base)
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)

        if self._scrim > 0:
            shade = QColor(0, 0, 0) if self._dark else QColor(255, 255, 255)
            shade.setAlpha(int(self._scrim * 255))
            painter.fillRect(rect, shade)
