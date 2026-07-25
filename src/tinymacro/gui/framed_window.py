"""Frameless window chrome shared by both UI variants.

Provides a custom title bar (app icon, optional menu bar, title, and
minimize/maximize/close buttons drawn from the custom icon set), drag-to-move,
edge/corner resizing, and open/close/minimize animations. Windows 11 rounds and
shadows frameless windows automatically, so we lean on the OS for corners.

Both ``MainWindow`` and ``StudioWindow`` subclass :class:`FramelessWindow`, which
stays a ``QMainWindow`` so the classic UI keeps its toolbar/central/status areas
unchanged beneath the title bar.
"""
from __future__ import annotations

from PyQt6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenuBar,
    QSizePolicy,
    QWidget,
)

from tinymacro.gui.anim import AnimatedToolButton
from tinymacro.gui.icons import app_icon, get_icon
from tinymacro.gui.theme import icon_color


def _opacity_anim(window, start, end, duration, easing, on_finished=None):
    window.setWindowOpacity(start)
    anim = QPropertyAnimation(window, b"windowOpacity", window)
    anim.setDuration(duration)
    anim.setStartValue(start)
    anim.setEndValue(end)
    anim.setEasingCurve(easing)
    if on_finished:
        anim.finished.connect(on_finished)
    anim.start()
    return anim

_RESIZE_MARGIN = 6
TITLE_BAR_HEIGHT = 40


class TitleBar(QWidget):
    """Custom draggable title bar with window controls."""

    def __init__(self, window: "FramelessWindow", title: str, with_menu: bool, animated: bool) -> None:
        super().__init__(window)
        self._window = window
        self._drag_offset: QPoint | None = None
        self.setFixedHeight(TITLE_BAR_HEIGHT)
        self.setObjectName("titleBar")

        color = icon_color()
        icon_label = QLabel()
        icon_label.setPixmap(app_icon().pixmap(20, 20))

        self.menu_bar = QMenuBar() if with_menu else None
        self.title_label = QLabel(title)
        self.title_label.setObjectName("titleLabel")
        self.title_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        self.btn_min = self._chrome_button("win_min", color, animated, window.showMinimized)
        self.btn_max = self._chrome_button("win_max", color, animated, window.toggle_max_restore)
        self.btn_close = self._chrome_button("win_close", color, animated, window.close)
        self.btn_close.setObjectName("closeButton")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 6, 4)
        layout.setSpacing(6)
        layout.addWidget(icon_label)
        if self.menu_bar is not None:
            layout.addWidget(self.menu_bar)
        layout.addWidget(self.title_label, 1)
        layout.addWidget(self.btn_min)
        layout.addWidget(self.btn_max)
        layout.addWidget(self.btn_close)

    def _chrome_button(self, icon: str, color: str, animated: bool, slot) -> AnimatedToolButton:
        button = AnimatedToolButton(self, animated=animated)
        button.setIcon(get_icon(icon, color, 18))
        button.setFixedSize(30, 26)
        button.clicked.connect(slot)
        return button

    def set_title(self, title: str) -> None:
        self.title_label.setText(title)

    # -- drag to move ---------------------------------------------------------
    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and not self._window.isMaximized():
            self._drag_offset = event.globalPosition().toPoint() - self._window.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):  # noqa: N802
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self._window.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event):  # noqa: N802
        self._drag_offset = None

    def mouseDoubleClickEvent(self, event):  # noqa: N802
        self._window.toggle_max_restore()


class FramelessWindow(QMainWindow):
    """A borderless QMainWindow with a custom title bar and open/close anims."""

    closing = pyqtSignal()

    def __init__(self, title: str = "Tiny Macro", *, with_menu: bool = True, animated: bool = True) -> None:
        super().__init__()
        self._animated = animated
        self._closing = False
        self._opened = False
        self.setWindowTitle(title)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setMouseTracking(True)
        self.title_bar = TitleBar(self, title, with_menu, animated)
        self.setMenuWidget(self.title_bar)
        self._resize_edge = Qt.Edge(0)

    def menu_bar(self) -> QMenuBar | None:
        return self.title_bar.menu_bar

    def set_window_title(self, title: str) -> None:
        self.setWindowTitle(title)
        self.title_bar.set_title(title)

    def toggle_max_restore(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    # -- open / close animations ----------------------------------------------
    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        if not self._opened:
            self._opened = True
            if self._animated:
                self._open_anim = _opacity_anim(self, 0.0, 1.0, 200, QEasingCurve.Type.OutCubic)

    def closeEvent(self, event):  # noqa: N802
        if self._closing or not self._animated:
            self.closing.emit()
            super().closeEvent(event)
            return
        event.ignore()
        self._closing = True
        self.closing.emit()
        self._close_anim = _opacity_anim(
            self, self.windowOpacity(), 0.0, 160, QEasingCurve.Type.InCubic, on_finished=self.close
        )

    # -- edge resize ----------------------------------------------------------
    def mouseMoveEvent(self, event):  # noqa: N802
        if not self.isMaximized():
            self._update_resize_cursor(event.position().toPoint())
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._resize_edge and not self.isMaximized():
            handle = self.windowHandle()
            if handle is not None:
                handle.startSystemResize(self._resize_edge)
                event.accept()
                return
        super().mousePressEvent(event)

    def _update_resize_cursor(self, pos) -> None:
        rect = self.rect()
        left = pos.x() <= _RESIZE_MARGIN
        right = pos.x() >= rect.width() - _RESIZE_MARGIN
        top = pos.y() <= _RESIZE_MARGIN
        bottom = pos.y() >= rect.height() - _RESIZE_MARGIN
        edge = Qt.Edge(0)
        cursor = Qt.CursorShape.ArrowCursor
        if left and top or (right and bottom):
            cursor = Qt.CursorShape.SizeFDiagCursor
        elif right and top or (left and bottom):
            cursor = Qt.CursorShape.SizeBDiagCursor
        elif left or right:
            cursor = Qt.CursorShape.SizeHorCursor
        elif top or bottom:
            cursor = Qt.CursorShape.SizeVerCursor
        if left:
            edge |= Qt.Edge.LeftEdge
        if right:
            edge |= Qt.Edge.RightEdge
        if top:
            edge |= Qt.Edge.TopEdge
        if bottom:
            edge |= Qt.Edge.BottomEdge
        self._resize_edge = edge
        self.setCursor(cursor)
