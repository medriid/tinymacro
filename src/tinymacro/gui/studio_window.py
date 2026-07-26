"""The "Studio" UI variant: a wide frameless frame that docks a target window.

Left column = overview + logs, center = a recessed dock area that a selected
window is position-attached into, right column = macro options. Everything
recorded here is stored relative to the dock area (see
:mod:`tinymacro.core.dock`) so the macro replays at any resolution and can be
distributed as a ``.tmacd`` file.
"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QObject, QPoint, QRect, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QRegion
from PyQt6.QtWidgets import (
    QApplication,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from tinymacro.backends.base import InputBackend
from tinymacro.core.dock import DockRegion
from tinymacro.core.library import MacroLibrary
from tinymacro.core.logging_setup import get_logger
from tinymacro.core.macro import DOCK_EXTENSION, Macro
from tinymacro.core.player import Player
from tinymacro.core.recorder import Recorder
from tinymacro.core.settings import Settings
from tinymacro.core.vision import capture_fullscreen_png
from tinymacro.notifications.base import LoopEvent, NotificationDispatcher
from tinymacro.notifications.discord_notifier import DiscordNotifier
from tinymacro.notifications.generic import GenericWebhookNotifier
from tinymacro.gui.anim import AnimatedToolButton
from tinymacro.gui.editor import EditorDialog
from tinymacro.gui.framed_window import FramelessWindow
from tinymacro.gui.icons import get_icon
from tinymacro.gui.theme import apply_theme, icon_color, theme_manager
from tinymacro.gui.toast import ToastManager
from tinymacro.gui.window_picker import WindowPicker

_DOCK_FILTER = f"Studio Macro (*{DOCK_EXTENSION})"


class _Bridge(QObject):
    loop_completed = pyqtSignal(int, int)
    progress = pyqtSignal(int, int)
    error = pyqtSignal(str)
    hotkeys_pressed = pyqtSignal(object)  # global hotkeys, marshalled to the GUI thread


class DockArea(QWidget):
    """Holds the recessed docking aperture."""

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumSize(560, 420)
        self.inner = QFrame(self)
        self.inner.setObjectName("dockWell")
        self.inner.setFrameShape(QFrame.Shape.StyledPanel)
        self.inner.setFrameShadow(QFrame.Shadow.Sunken)
        self.inner.setLineWidth(2)
        self.inner.setMidLineWidth(1)
        # Transparent interior: when a window is docked the interior is punched
        # out of the Studio window (see StudioWindow._update_mask) so the docked
        # window shows through and stays clickable. The border just frames it.
        self.inner.setStyleSheet(
            """
            #dockWell {
                background: transparent;
                border: 2px solid palette(mid);
                border-radius: 6px;
            }
            """
        )
        self.placeholder = QLabel("No window docked — use “Dock Window” →", self.inner)
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay = QVBoxLayout(self.inner)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.addWidget(self.placeholder, alignment=Qt.AlignmentFlag.AlignCenter)

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self.inner.setGeometry(0, 0, self.width(), self.height())

    def region(self) -> DockRegion:
        top_left = self.inner.mapToGlobal(QPoint(0, 0))
        return DockRegion(top_left.x(), top_left.y(), self.inner.width(), self.inner.height())

    def set_docked(self, docked: bool) -> None:
        # When docked the interior becomes a see-through hole, so hide the hint.
        self.placeholder.setVisible(not docked)


class StudioWindow(FramelessWindow):
    switch_variant_requested = pyqtSignal(str)

    def __init__(
        self,
        settings: Settings,
        backend: InputBackend,
        persist_settings: bool = True,
        library: MacroLibrary | None = None,
        colors=None,
        on_persist=None,
    ) -> None:
        super().__init__("Tiny Macro — Studio", with_menu=False, animated=settings.animations)
        self.settings = settings
        self.backend = backend
        self.persist_settings = persist_settings
        self._on_persist = on_persist
        self.colors = colors
        self.log = get_logger()
        self.library = library if library is not None else MacroLibrary()
        self.macro = Macro(docked=True)
        self.path: Path | None = None
        self._target_hwnd: int | None = None
        self._target_title = ""
        self._cleaned = False
        self._keep_backend = False  # set true on a variant switch to share the backend
        self._mask_hole: QRect | None = None
        self.toasts = ToastManager(self, animated=settings.animations)

        self.recorder = Recorder(
            backend, settings.hotkeys,
            skip_final_click=settings.skip_final_click,
            dock_region_provider=self._dock_region,
        )
        self.player = Player(backend, dock_region_provider=self._dock_region)
        self.player.allow_code_execution = settings.allow_code_execution
        self.player.screenshot_capturer = capture_fullscreen_png
        self.dispatcher = NotificationDispatcher(on_error=lambda name, exc: None)
        self._rebuild_dispatcher()
        self.bridge = _Bridge(self)
        self.bridge.loop_completed.connect(self._on_loop_completed)
        self.bridge.progress.connect(self._on_progress)
        self.bridge.error.connect(lambda m: self._toast(m, "error"))
        self.bridge.hotkeys_pressed.connect(self._activate_hotkeys)
        self.player.on_loop_complete = lambda done, total, spd, macro: self.bridge.loop_completed.emit(done, total)
        self.player.on_progress = lambda i, t: self.bridge.progress.emit(i, t)
        self.player.on_error = lambda exc: self.bridge.error.emit(str(exc))

        self.setMinimumSize(1100, 620)
        self.resize(1320, 760)
        self._build_ui()

        self._tracker = QTimer(self)
        self._tracker.timeout.connect(self._track_dock)
        self._tracker.start(150)
        self._state_timer = QTimer(self)
        self._state_timer.timeout.connect(self._update_state)
        self._state_timer.start(120)
        theme_manager.changed.connect(lambda c: self._retint(c))
        self._start_hotkeys()
        self._update_overview()
        self._update_state()

    # -- construction ---------------------------------------------------------
    def _build_ui(self) -> None:
        color = icon_color()
        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(10, 8, 10, 10)
        root.setSpacing(10)

        # LEFT — overview + logs
        left = QVBoxLayout()
        left.addWidget(_heading("Overview"))
        self.overview = QLabel()
        self.overview.setWordWrap(True)
        self.overview.setObjectName("overviewCard")
        self.overview.setStyleSheet("#overviewCard { border: 1px solid palette(mid); border-radius: 8px; padding: 8px; }")
        left.addWidget(self.overview)
        left.addWidget(_heading("Logs"))
        self.logs = QListWidget()
        left.addWidget(self.logs, 1)
        left_wrap = QWidget()
        left_wrap.setLayout(left)
        left_wrap.setFixedWidth(270)

        # CENTER — dock area
        self.dock = DockArea()

        # RIGHT — options
        right = QVBoxLayout()
        right.addWidget(_heading("Window"))
        self.dock_btn = self._row_button("dock", "Dock Window", color, self._toggle_dock)
        right.addWidget(self.dock_btn)

        right.addSpacing(6)
        right.addWidget(_heading("Record & Play"))
        self.record_btn = self._big_button("record", "Record", color, self.toggle_recording)
        self.play_btn = self._big_button("play", "Play", color, self.toggle_playback)
        self.stop_btn = self._big_button("stop", "Stop", color, self.stop_all)
        right.addWidget(self.record_btn)
        right.addWidget(self.play_btn)
        right.addWidget(self.stop_btn)

        right.addSpacing(6)
        right.addWidget(_heading("Settings"))
        self.loop_spin = QSpinBox()
        self.loop_spin.setRange(0, 999_999)
        self.loop_spin.setValue(self.settings.loop_count)
        self.loop_spin.setPrefix("Loops: ")
        self.speed_spin = QDoubleSpinBox()
        self.speed_spin.setRange(0.01, 100.0)
        self.speed_spin.setValue(self.settings.speed)
        self.speed_spin.setPrefix("Speed: ")
        self.speed_spin.setSuffix("x")
        right.addWidget(self.loop_spin)
        right.addWidget(self.speed_spin)
        right.addWidget(self._row_button("preferences", "Preferences…", color, self.open_preferences))

        right.addSpacing(6)
        right.addWidget(_heading("Macro"))
        right.addWidget(self._row_button("open", "Open", color, self.open_macro))
        right.addWidget(self._row_button("save", "Save", color, self.save_macro))
        right.addWidget(self._row_button("editor", "Editor", color, self.open_editor))
        right.addStretch(1)
        right.addWidget(self._row_button("switch", "Switch to Classic UI", color, self._go_classic))
        right_wrap = QWidget()
        right_wrap.setLayout(right)
        right_wrap.setFixedWidth(210)

        root.addWidget(left_wrap)
        root.addWidget(self.dock, 1)
        root.addWidget(right_wrap)
        self.setCentralWidget(central)

    def _big_button(self, icon, text, color, slot) -> AnimatedToolButton:
        button = AnimatedToolButton(animated=self.settings.animations)
        button.setIcon(get_icon(icon, color, 20))
        button.setText("  " + text)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        button.setMinimumHeight(38)
        button.clicked.connect(slot)
        return button

    def _row_button(self, icon, text, color, slot) -> QPushButton:
        button = QPushButton(get_icon(icon, color), text)
        button.clicked.connect(slot)
        return button

    # -- dock tracking --------------------------------------------------------
    def _dock_region(self) -> DockRegion | None:
        region = self.dock.region()
        return region if region.valid else None

    def _track_dock(self) -> None:
        self._update_mask()
        if self._target_hwnd is None:
            return
        region = self.dock.region()
        if region.valid:
            try:
                self.backend.move_resize_window(
                    self._target_hwnd, region.left, region.top, region.width, region.height
                )
            except Exception as exc:  # noqa: BLE001
                self.log.warning("Dock tracking failed: %s", exc)

    def _update_mask(self) -> None:
        """Punch a see-through, click-through hole where the docked window sits.

        The interior of the dock well is subtracted from the Studio window's
        shape, so the docked window (a separate top-level window filling that
        rectangle) is always visible through it and a click there lands on the
        docked window — even when the Studio window itself has focus. A few px are
        left so the well's border ring stays drawn.
        """
        if self._target_hwnd is None or not self.isVisible():
            if self._mask_hole is not None:
                self._mask_hole = None
                self.clearMask()
            return
        inner = self.dock.inner
        origin = inner.mapTo(self, QPoint(0, 0))
        hole = QRect(origin.x() + 3, origin.y() + 3, inner.width() - 6, inner.height() - 6)
        if hole.width() <= 0 or hole.height() <= 0:
            return
        if hole == self._mask_hole:
            return  # unchanged; avoid re-masking every tick (prevents flicker)
        self._mask_hole = hole
        self.setMask(QRegion(self.rect()).subtracted(QRegion(hole)))

    def _toggle_dock(self) -> None:
        if self._target_hwnd is not None:
            self._undock()
        else:
            self._select_window()

    def _select_window(self) -> None:
        if not self.backend.supports_docking():
            QMessageBox.information(
                self, "Not supported",
                "Window docking isn't available on this backend (Windows only).",
            )
            return
        picker = WindowPicker(self.backend, self)
        if not picker.exec() or picker.selected is None:
            return
        self._target_hwnd = picker.selected
        self._target_title = picker.selected_title
        self.macro = self.macro.copy_with(target_window=self._target_title)
        self.dock.set_docked(True)
        self.dock_btn.setText("Undock Window")
        self._track_dock()
        self._toast(f"Docked: {self._target_title}", "success")
        self._update_overview()

    def _undock(self) -> None:
        title = self._target_title
        self._target_hwnd = None
        self.dock.set_docked(False)
        self.dock_btn.setText("Dock Window")
        self._update_mask()  # remove the see-through hole
        self._toast(f"Undocked: {title}" if title else "Undocked", "info")
        self._update_overview()

    # -- record / play --------------------------------------------------------
    def toggle_recording(self) -> None:
        try:
            if self.recorder.recording:
                self.macro = self.recorder.stop().copy_with(
                    docked=True, target_window=self._target_title
                )
                self._toast("Recording stopped", "info")
            else:
                if self._target_hwnd is None:
                    QMessageBox.information(self, "No window", "Select a window to dock first.")
                    return
                self.player.stop()
                self.recorder.start()
                self._toast("Recording…", "success")
            self._update_state()
            self._update_overview()
        except Exception as exc:  # noqa: BLE001
            self._toast(f"Recording failed: {exc}", "error")

    def toggle_playback(self) -> None:
        if self.player.state.playing:
            self.player.stop()
            self._update_state()
            return
        if not self.macro.events:
            QMessageBox.information(self, "No macro", "Record or open a macro first.")
            return
        if self._target_hwnd is not None:
            self.backend.focus_window(self._target_hwnd)
        self.settings.loop_count = self.loop_spin.value()
        self.settings.speed = self.speed_spin.value()
        self.player.start(self.macro, loop_count=self.loop_spin.value(), speed=self.speed_spin.value())
        self.logs.addItem(f"▶ Playback started ×{self.loop_spin.value() or '∞'}")
        self._update_state()

    def stop_all(self) -> None:
        self.player.stop()
        if self.recorder.recording:
            self.macro = self.recorder.stop().copy_with(docked=True, target_window=self._target_title)
        self._update_state()
        self._update_overview()

    def open_editor(self) -> None:
        dialog = EditorDialog(self.macro, self, colors=self.colors)
        dialog.macro_changed.connect(self._replace_macro)
        dialog.exec()

    def _replace_macro(self, macro: Macro) -> None:
        self.macro = macro.copy_with(docked=True, target_window=self._target_title)
        self._update_overview()

    # -- files ----------------------------------------------------------------
    def open_macro(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open Studio Macro", "", _DOCK_FILTER)
        if not path:
            return
        try:
            self.macro = Macro.load_for_variant(path, docked=True)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Cannot open", str(exc))
            return
        self.path = Path(path)
        self._target_title = self.macro.target_window
        self.loop_spin.setValue(self.macro.loop_count)
        self.speed_spin.setValue(self.macro.speed)
        self._toast(f"Loaded {Path(path).name}", "info")
        self._update_overview()

    def save_macro(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save Studio Macro", "", _DOCK_FILTER)
        if not path:
            return
        if not path.endswith(DOCK_EXTENSION):
            path += DOCK_EXTENSION
        self.macro = self.macro.copy_with(
            docked=True, target_window=self._target_title,
            speed=self.speed_spin.value(), loop_count=self.loop_spin.value(),
        )
        try:
            self.macro.save(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Cannot save", str(exc))
            return
        self.path = Path(path)
        self._toast(f"Saved {Path(path).name}", "success")

    # -- state / overview -----------------------------------------------------
    def _update_state(self) -> None:
        recording = self.recorder.recording
        playing = self.player.state.playing
        self.dock_btn.setText("Undock Window" if self._target_hwnd is not None else "Dock Window")
        self.record_btn.setText("  Stop Rec" if recording else "  Record")
        self.play_btn.setEnabled(bool(self.macro.events) and not recording)
        self.play_btn.setText("  Stop" if playing else "  Play")

    def _update_overview(self) -> None:
        target = self._target_title or "— none —"
        self.overview.setText(
            f"<b>{self.macro.name}</b><br>"
            f"Target: {target}<br>"
            f"Events: {len(self.macro.events)}<br>"
            f"Duration: {self.macro.duration_s:.2f}s<br>"
            f"Format: Studio (.tmacd)"
        )
        self.dock.set_docked(self._target_hwnd is not None)

    def _rebuild_dispatcher(self) -> None:
        self.dispatcher.clear()
        notifications = self.settings.notifications
        self.dispatcher.register(DiscordNotifier(notifications.discord))
        self.dispatcher.register(GenericWebhookNotifier(notifications.generic))

    def _dispatch_notifications(self, done: int, total: int) -> None:
        import threading

        notifications = self.settings.notifications
        if not (notifications.discord.enabled or notifications.generic.enabled):
            return
        screenshot = None
        if notifications.discord.include_screenshot:
            screenshot = self.player.consume_marked_screenshot() or capture_fullscreen_png()
        event = LoopEvent(
            loop_index=done,
            total_loops=total,
            speed=self.speed_spin.value(),
            macro=self.macro,
            is_final=bool(total) and done >= total,
            screenshot_png=screenshot,
        )
        threading.Thread(
            target=lambda: self.dispatcher.dispatch(event),
            name="tiny-macro-notify",
            daemon=True,
        ).start()

    def _on_loop_completed(self, done: int, total: int) -> None:
        self.logs.addItem(f"✓ Loop {done}/{total or '∞'} complete")
        while self.logs.count() > 500:
            self.logs.takeItem(0)
        self._dispatch_notifications(done, total)
        self.logs.scrollToBottom()

    def _on_progress(self, index: int, total: int) -> None:
        pass  # reserved for a progress bar

    # -- misc -----------------------------------------------------------------
    def _toast(self, text: str, level: str = "info") -> None:
        self.toasts.show(text, level)

    def _start_hotkeys(self) -> None:
        try:
            self.backend.start_hotkeys(lambda pressed: self.bridge.hotkeys_pressed.emit(pressed))
        except Exception:  # noqa: BLE001
            pass

    def _activate_hotkeys(self, pressed) -> None:
        """Global record/play/stop/marker/screenshot hotkeys (same set as Classic)."""
        hotkeys = self.settings.hotkeys
        if self.recorder.recording and hotkeys.screenshot.is_subset_of(pressed):
            self.recorder.add_screenshot_point()
            self._toast("Screenshot point set", "success")
        elif self.recorder.recording and hotkeys.marker.is_subset_of(pressed):
            self.recorder.add_marker("marker")
            self._toast("Marker dropped", "info")
        elif hotkeys.record.is_subset_of(pressed):
            self.toggle_recording()
        elif hotkeys.play.is_subset_of(pressed):
            self.toggle_playback()
        elif hotkeys.stop.is_subset_of(pressed) or any(k.is_subset_of(pressed) for k in hotkeys.emergency):
            self.stop_all()

    def open_preferences(self) -> None:
        from tinymacro.gui.preferences import PreferencesDialog

        dialog = PreferencesDialog(self.settings, self)
        if not dialog.exec():
            return
        # Re-apply everything that can change from Preferences.
        self.colors = apply_theme(QApplication.instance(), self.settings)
        self.player.allow_code_execution = self.settings.allow_code_execution
        self.recorder.skip_final_click = self.settings.skip_final_click
        self.recorder.hotkeys = self.settings.hotkeys
        self.recorder.move_min_interval_ns = self.settings.move_min_interval_ms * 1_000_000
        self.toasts.set_animated(self.settings.animations)
        self.loop_spin.setValue(self.settings.loop_count)
        self.speed_spin.setValue(self.settings.speed)
        self._rebuild_dispatcher()  # webhook settings may have changed
        if self.persist_settings and self._on_persist:
            self._on_persist()

    def _retint(self, colors) -> None:
        self.colors = colors

    def _go_classic(self) -> None:
        self.settings.ui_variant = "classic"
        if self.persist_settings and self._on_persist:
            self._on_persist()
        self.switch_variant_requested.emit("classic")

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        if hasattr(self, "dock"):
            self._track_dock()

    def closeEvent(self, event):  # noqa: N802
        if not self._closing and not self._cleaned:
            self._cleaned = True
            self._tracker.stop()
            self.player.stop(wait=True)
            if self.recorder.recording:
                self.recorder.stop()
            if not self._keep_backend:
                self.backend.close()
        super().closeEvent(event)


def _heading(text: str) -> QLabel:
    label = QLabel(text.upper())
    label.setStyleSheet("color: palette(mid); font-weight: 600; font-size: 10px; letter-spacing: 1px;")
    return label
