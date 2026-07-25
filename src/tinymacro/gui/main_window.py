from __future__ import annotations

import copy
from datetime import datetime
import time
from pathlib import Path
import subprocess
import threading
import traceback

from PyQt6.QtCore import QByteArray, QBuffer, QIODevice, QObject, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QDoubleSpinBox,
    QStatusBar,
    QSystemTrayIcon,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from tinymacro.backends.base import InputBackend
from tinymacro.backends.factory import create_backend
from tinymacro.core.library import MacroLibrary
from tinymacro.core.logging_setup import get_logger
from tinymacro.core.macro import Macro
from tinymacro.core.player import Player, simulate
from tinymacro.core.recorder import Recorder
from tinymacro.core.image_watcher import ImageWatcher
from tinymacro.core.scheduler import Schedule, ScheduleStore
from tinymacro.core.settings import Settings
from tinymacro.core.vision import CAPTURE_AVAILABLE, Locator
from tinymacro.desktop import install_file_association
from tinymacro.export import export_runner
from tinymacro.gui.editor import EditorDialog
from tinymacro.gui.icons import app_icon, get_icon
from tinymacro.gui.library_dialog import LibraryDialog
from tinymacro.gui.log_dialog import LogDialog
from tinymacro.gui.preferences import PreferencesDialog
from tinymacro.gui.scheduler_dialog import SchedulerDialog
from tinymacro.gui.theme import apply_theme, theme_manager
from tinymacro.gui.toast import ToastManager
from tinymacro.gui.widgets import RecordingIndicator
from tinymacro.notifications.base import LoopEvent, NotificationDispatcher
from tinymacro.notifications.discord_notifier import DiscordNotifier
from tinymacro.notifications.generic import GenericWebhookNotifier

AUTOSAVE_NAME = "autosave-recovery.tmacro"


class PlaybackSignalBridge(QObject):
    loop_completed = pyqtSignal(int, int, float, object)
    notify_error = pyqtSignal(str)
    hotkeys_pressed = pyqtSignal(object)
    debug_error = pyqtSignal(str, str)
    progress = pyqtSignal(int, int)
    image_trigger = pyqtSignal(object)  # fired by the ImageWatcher thread


class MainWindow(QMainWindow):
    def __init__(
        self,
        settings: Settings,
        backend: InputBackend,
        initial_macro: Path | None = None,
        persist_settings: bool = True,
        library: MacroLibrary | None = None,
        schedules: ScheduleStore | None = None,
        colors=None,
        on_persist=None,
    ) -> None:
        super().__init__()
        self.settings = settings
        self.backend = backend
        self.persist_settings = persist_settings
        self.colors = colors
        self._on_persist = on_persist
        self.log = get_logger()
        self.library = library if library is not None else MacroLibrary()
        self.schedules = schedules if schedules is not None else ScheduleStore()

        self.recorder = Recorder(
            backend,
            settings.hotkeys,
            skip_final_click=settings.skip_final_click,
            move_min_interval_ns=settings.move_min_interval_ms * 1_000_000,
        )
        self.player = Player(backend)
        # Enables click-image steps during playback; the factory runs on the
        # player's own thread (mss is not thread-safe). Missing deps → None,
        # so image steps fall back to their on_missing rule.
        self.player.locator_factory = (lambda: Locator()) if CAPTURE_AVAILABLE else None
        self.player.on_image_missed = self._on_image_missed
        self.player.allow_code_execution = settings.allow_code_execution
        self.bridge = PlaybackSignalBridge(self)
        self.bridge.loop_completed.connect(self._handle_loop_completed)
        self.bridge.notify_error.connect(lambda message: self._toast(message, "error"))
        self.bridge.hotkeys_pressed.connect(self._activate_hotkeys)
        self.bridge.debug_error.connect(self._handle_debug_error)
        self.bridge.progress.connect(self._on_progress)
        self.bridge.image_trigger.connect(self._on_image_trigger)
        self.player.on_loop_complete = self._emit_loop_completed
        self.player.on_error = self._emit_playback_error
        self.player.on_progress = lambda i, t: self.bridge.progress.emit(i, t)

        self.dispatcher = NotificationDispatcher(
            on_error=lambda name, exc: self.bridge.notify_error.emit(f"{name}: {exc}")
        )
        self._rebuild_dispatcher()

        self.macro = Macro()
        self.path: Path | None = None
        self.dirty = False
        self._last_feed_count = 0
        self._step_index = 0
        # Icon-bearing widgets, so a theme change can re-tint them all at once.
        self._icon_actions: dict[QAction, str] = {}

        # Image-trigger scheduler: a background watcher fires macros when their
        # target image appears. The watcher runs only when there are usable
        # image triggers and the vision deps are present.
        self._image_watcher = ImageWatcher(
            provider=lambda: self.schedules.schedules,
            locator_factory=lambda: Locator(),
            on_match=lambda schedule: self.bridge.image_trigger.emit(schedule),
        )
        self._active_image_schedule: Schedule | None = None
        self._countdown_active = False
        self._countdown_left = 0
        # Last non-Tiny-Macro window to hold focus, so keyboard playback can be
        # directed back to the user's target window instead of at our own window.
        self._last_external_hwnd = 0

        self.setWindowTitle("Tiny Macro")
        self.setWindowIcon(app_icon())
        self.setMinimumWidth(480)
        self.toasts = ToastManager(self, animated=settings.animations)

        self._build_central()
        self._build_toolbar()
        self._build_menu()
        self._build_tray()
        self._apply_window_flags()
        self._apply_mode()
        self._start_hotkeys()
        theme_manager.changed.connect(self._on_theme_changed)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(100)
        self._autosave_timer = QTimer(self)
        self._autosave_timer.timeout.connect(self._autosave)
        self._reschedule_autosave()
        self._schedule_timer = QTimer(self)
        self._schedule_timer.timeout.connect(self._check_schedules)
        self._schedule_timer.start(30_000)
        self._countdown_timer = QTimer(self)
        self._countdown_timer.timeout.connect(self._tick_countdown)
        self._refresh_image_watcher()

        self._offer_recovery()
        if initial_macro:
            self.load_macro(initial_macro)
        self.log.info("Tiny Macro started (backend=%s)", self.backend.name)
        self._update_state()

    # -- icons ----------------------------------------------------------------
    def _icon_color(self) -> str:
        # Mid-gray reads acceptably on either theme when colors aren't set yet
        # (e.g. headless tests); the theme signal re-tints once real colors land.
        return getattr(self.colors, "text", None) or "#888888"

    def _action(self, icon_name: str, tooltip: str, checkable: bool = False) -> QAction:
        action = QAction(get_icon(icon_name, self._icon_color()), "", self)
        action.setToolTip(tooltip)
        action.setCheckable(checkable)
        self._icon_actions[action] = icon_name
        return action

    def _menu_action(self, menu, icon_name: str, text: str, slot) -> QAction:
        action = menu.addAction(get_icon(icon_name, self._icon_color()), text, slot)
        self._icon_actions[action] = icon_name
        return action

    def _on_theme_changed(self, colors) -> None:
        self.colors = colors
        color = self._icon_color()
        for action, icon_name in self._icon_actions.items():
            action.setIcon(get_icon(icon_name, color))
        expanded = not self.settings.compact_mode
        self.expand_button.setIcon(get_icon("chevron_up" if expanded else "chevron_down", color))

    # -- construction ---------------------------------------------------------
    def _build_central(self) -> None:
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(8, 4, 8, 8)

        progress_row = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        self.progress_label = QLabel("Ready")
        progress_row.addWidget(self.progress_label)
        progress_row.addWidget(self.progress, 1)
        layout.addLayout(progress_row)

        self.feed_label = QLabel("Live events")
        self.feed = QListWidget()
        self.feed.setMaximumHeight(160)
        layout.addWidget(self.feed_label)
        layout.addWidget(self.feed, 1)

        self.expand_button = QPushButton("Expand")
        self.expand_button.clicked.connect(self.toggle_mode)
        layout.addWidget(self.expand_button)

        self._central = central
        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Controls")
        toolbar.setMovable(False)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)

        self.indicator = RecordingIndicator(animated=self.settings.animations)
        toolbar.addWidget(self.indicator)
        toolbar.addSeparator()

        self.open_action = self._action("open", "Open")
        self.save_action = self._action("save", "Save")
        self.record_action = self._action("record", "Record", checkable=True)
        self.play_action = self._action("play", "Play")
        self.pause_action = self._action("pause", "Pause/Resume")
        self.stop_action = self._action("stop", "Stop")
        self.step_action = self._action("step", "Step one event")
        self.editor_action = self._action("editor", "Editor")
        self.library_action = self._action("library", "Library")
        self.pref_action = self._action("preferences", "Preferences")
        self.top_action = self._action("pin", "Always on top", checkable=True)
        self.top_action.setChecked(self.settings.always_on_top)

        for action in (self.open_action, self.save_action, self.record_action,
                       self.play_action, self.pause_action, self.stop_action, self.step_action):
            toolbar.addAction(action)
        toolbar.addSeparator()

        self.loop_spin = QSpinBox()
        self.loop_spin.setToolTip("Loop count; 0 means infinite")
        self.loop_spin.setRange(0, 999_999)
        self.loop_spin.setValue(self.settings.loop_count)
        self.loop_spin.setFixedWidth(78)
        self.speed_spin = QDoubleSpinBox()
        self.speed_spin.setToolTip("Playback speed")
        self.speed_spin.setRange(0.01, 100.0)
        self.speed_spin.setSingleStep(0.25)
        self.speed_spin.setValue(self.settings.speed)
        self.speed_spin.setSuffix("x")
        self.speed_spin.setFixedWidth(82)
        toolbar.addWidget(self.loop_spin)
        toolbar.addWidget(self.speed_spin)
        toolbar.addSeparator()
        for action in (self.editor_action, self.library_action, self.pref_action, self.top_action):
            toolbar.addAction(action)

        self.open_action.triggered.connect(self.open_macro)
        self.save_action.triggered.connect(self.save_macro)
        self.record_action.triggered.connect(self.toggle_recording)
        self.play_action.triggered.connect(self.toggle_playback)
        self.pause_action.triggered.connect(self.toggle_pause)
        self.stop_action.triggered.connect(self.stop_all)
        self.step_action.triggered.connect(self.step_once)
        self.editor_action.triggered.connect(self.open_editor)
        self.library_action.triggered.connect(self.open_library)
        self.pref_action.triggered.connect(self.open_preferences)
        self.top_action.triggered.connect(self.toggle_always_on_top)

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("File")
        self._menu_action(file_menu, "open", "Open", self.open_macro)
        self._menu_action(file_menu, "save", "Save", self.save_macro)
        self._menu_action(file_menu, "save", "Save As", self.save_macro_as)
        self._menu_action(file_menu, "add_file", "Export Runner", self.export_macro_runner)
        self._menu_action(file_menu, "pin", "Install File Association", self.install_association)
        file_menu.addSeparator()
        self._menu_action(file_menu, "close", "Quit", self.close)

        edit_menu = self.menuBar().addMenu("Edit")
        self._menu_action(edit_menu, "editor", "Macro Editor", self.open_editor)
        self._menu_action(edit_menu, "preferences", "Preferences", self.open_preferences)

        tools_menu = self.menuBar().addMenu("Tools")
        self._menu_action(tools_menu, "library", "Macro Library", self.open_library)
        self._menu_action(tools_menu, "scheduler", "Scheduler", self.open_scheduler)
        self._menu_action(tools_menu, "validate", "Validate (dry run)", self.validate_macro)
        self._menu_action(tools_menu, "note", "Drop Marker (while recording)", self.drop_marker)
        self._menu_action(tools_menu, "logs", "Log Viewer", self.open_logs)

        view_menu = self.menuBar().addMenu("View")
        self._menu_action(view_menu, "chevron_down", "Toggle compact / expanded", self.toggle_mode)

    def _build_tray(self) -> None:
        self.tray: QSystemTrayIcon | None = None
        if not self.settings.tray_enabled or not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.setToolTip("Tiny Macro")
        menu = QMenu()
        self._menu_action(menu, "pin", "Show / Hide", self._toggle_visible)
        self._menu_action(menu, "record", "Record", self.toggle_recording)
        self._menu_action(menu, "play", "Play", self.toggle_playback)
        self._menu_action(menu, "stop", "Stop", self.stop_all)
        menu.addSeparator()
        self._menu_action(menu, "close", "Quit", self.close)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    # -- mode / window --------------------------------------------------------
    def _apply_mode(self) -> None:
        expanded = not self.settings.compact_mode
        self.progress_label.setVisible(expanded)
        self.progress.setVisible(expanded)
        self.feed_label.setVisible(expanded)
        self.feed.setVisible(expanded)
        self.expand_button.setText("Collapse" if expanded else "Expand")
        self.expand_button.setIcon(get_icon("chevron_up" if expanded else "chevron_down", self._icon_color()))
        self.step_action.setVisible(expanded)
        if expanded:
            self.setMinimumHeight(0)
            self.setMaximumHeight(16_777_215)
            self.resize(self.width(), 340)
        else:
            self._central.adjustSize()
            self.setFixedHeight(self.sizeHint().height())

    def toggle_mode(self) -> None:
        self.settings.compact_mode = not self.settings.compact_mode
        # Leaving compact needs the height cap lifted before we grow.
        self.setMinimumHeight(0)
        self.setMaximumHeight(16_777_215)
        self._apply_mode()
        self._persist()

    # -- recording / playback -------------------------------------------------
    def toggle_recording(self) -> None:
        try:
            if self.recorder.recording:
                self.macro = self.recorder.stop()
                if self.settings.auto_trim_leading:
                    self.macro = self.macro.trim_leading_idle()
                self.dirty = True
                self._last_feed_count = 0
                self.log.info("Recording stopped: %d events", len(self.macro.events))
                self._toast("Recording stopped", "info")
                self._update_state()
            elif self._countdown_active:
                self._cancel_countdown()
            else:
                self._start_recording_with_countdown()
        except Exception as exc:
            self._report_error("Recording failed", exc)
            self._update_state()

    def _start_recording_with_countdown(self) -> None:
        seconds = max(0, self.settings.record_countdown)
        if seconds <= 0:
            self._begin_recording()
            return
        self._countdown_active = True
        self._countdown_left = seconds
        self._toast(f"Recording in {seconds}…", "info", 900)
        self.record_action.setChecked(True)
        self._countdown_timer.start(1000)

    def _tick_countdown(self) -> None:
        self._countdown_left -= 1
        if self._countdown_left <= 0:
            self._cancel_countdown(begin=True)
        else:
            self._toast(f"Recording in {self._countdown_left}…", "info", 900)

    def _cancel_countdown(self, begin: bool = False) -> None:
        self._countdown_timer.stop()
        self._countdown_active = False
        if begin:
            self._begin_recording()
        else:
            self.record_action.setChecked(False)
            self._toast("Recording cancelled", "info")
            self._update_state()

    def _begin_recording(self) -> None:
        self.player.stop()
        self.recorder.skip_final_click = self.settings.skip_final_click
        self.recorder.hotkeys = self.settings.hotkeys
        self.recorder.move_min_interval_ns = self.settings.move_min_interval_ms * 1_000_000
        self.feed.clear()
        self._last_feed_count = 0
        self.recorder.start()
        self.log.info("Recording started")
        self._toast("Recording…", "success")
        self._update_state()

    def drop_marker(self) -> None:
        if self.recorder.recording:
            self.recorder.add_marker("marker")
            self._toast("Marker dropped", "info", 1200)

    def toggle_playback(self) -> None:
        if self.player.state.playing:
            self.player.stop()
            self._update_state()
            return
        if not self.macro.events:
            QMessageBox.information(self, "No macro", "Record or open a macro first.")
            return
        self.settings.loop_count = self.loop_spin.value()
        self.settings.speed = self.speed_spin.value()
        macro = self.macro
        if self.settings.humanize_jitter_ms > 0:
            macro = macro.humanized(self.settings.humanize_jitter_ms * 1_000_000)
        self._restore_target_focus(macro)
        self.player.on_loop_complete = self._emit_loop_completed
        try:
            self.player.start(macro, loop_count=self.settings.loop_count, speed=self.settings.speed)
        except Exception as exc:
            self._report_error("Playback failed", exc)
            self._update_state()
            return
        if self.path:
            self.library.record_run(self.path)
            self.library.save()
        self.log.info("Playback started (loops=%s, speed=%s)", self.settings.loop_count, self.settings.speed)
        self._update_state()

    def toggle_pause(self) -> None:
        if not self.player.state.playing:
            return
        if self.player.state.paused:
            self.player.resume()
            self._toast("Resumed", "info")
        else:
            self.player.pause()
            self._toast("Paused", "info")
        self._update_state()

    def step_once(self) -> None:
        if self.player.state.playing or not self.macro.events:
            return
        events = self.macro.sorted_events()
        if self._step_index >= len(events):
            self._step_index = 0
        try:
            event = self.player.emit_index(self.macro, self._step_index)
        except Exception as exc:
            self._report_error("Step failed", exc)
            return
        self.progress_label.setText(f"Step {self._step_index + 1}/{len(events)}: {event.describe()}")
        self._step_index += 1

    def stop_all(self) -> None:
        try:
            if self.recorder.recording:
                self.macro = self.recorder.stop()
                self.dirty = True
            self.player.stop()
            self._step_index = 0
            self._toast("Stopped", "info")
            self._update_state()
        except Exception as exc:
            self._report_error("Stop failed", exc)

    def validate_macro(self) -> None:
        if not self.macro.events:
            QMessageBox.information(self, "No macro", "Record or open a macro first.")
            return
        report = simulate(self.macro)
        summary = (
            f"{report.event_count} events · {report.input_event_count} input · "
            f"{report.wait_event_count} wait · {report.duration_s:.3f}s"
        )
        if report.ok:
            QMessageBox.information(self, "Validation passed", f"No issues found.\n\n{summary}")
        else:
            QMessageBox.warning(self, "Validation warnings", summary + "\n\n" + "\n".join(report.warnings))

    # -- files ----------------------------------------------------------------
    def open_macro(self) -> None:
        if not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open Macro", "", "Tiny Macro (*.tmacro);;All Files (*)")
        if path:
            self.load_macro(Path(path))

    def load_macro(self, path: Path) -> None:
        try:
            self.macro = Macro.load(path)
        except Exception as exc:
            self._report_error("Open failed", exc, always_dialog=True)
            return
        self.path = path
        self.dirty = False
        self._step_index = 0
        # Restore the macro's own saved playback preferences.
        self.loop_spin.setValue(self.macro.loop_count)
        self.speed_spin.setValue(self.macro.speed)
        self.library.add(path, name=path.stem)
        self.library.save()
        self.log.info("Loaded %s", path.name)
        self._toast(f"Loaded {path.name}", "info")
        self._update_state()

    def save_macro(self) -> None:
        if not self.path:
            self.save_macro_as()
            return
        # Persist the current loop/speed choices with the macro.
        self.macro = self.macro.copy_with(
            speed=self.speed_spin.value(), loop_count=self.loop_spin.value()
        )
        try:
            self.macro.save(self.path)
        except Exception as exc:
            self._report_error("Save failed", exc, always_dialog=True)
            return
        self.dirty = False
        self.library.add(self.path, name=self.path.stem)
        self.library.save()
        self.log.info("Saved %s", self.path.name)
        self._toast(f"Saved {self.path.name}", "success")
        self._update_state()

    def save_macro_as(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save Macro", "", "Tiny Macro (*.tmacro)")
        if not path:
            return
        target = Path(path)
        if target.suffix != ".tmacro":
            target = target.with_suffix(".tmacro")
        self.path = target
        self.save_macro()

    def export_macro_runner(self) -> None:
        if not self.macro.events:
            QMessageBox.information(self, "No macro", "Record or open a macro first.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export Runner", "", "Python Runner (*.py)")
        if not path:
            return
        try:
            runner, macro = export_runner(self.macro, path, loop_count=self.loop_spin.value(), speed=self.speed_spin.value())
        except Exception as exc:
            self._report_error("Export failed", exc, always_dialog=True)
            return
        self._toast(f"Exported {runner.name}", "success")

    def install_association(self) -> None:
        app_path, mime_path = install_file_association()
        try:
            subprocess.run(["update-desktop-database", str(app_path.parent)], check=False)
            subprocess.run(["update-mime-database", str(mime_path.parent.parent)], check=False)
        except FileNotFoundError:
            pass
        self._toast("Installed .tmacro association", "info")

    # -- dialogs --------------------------------------------------------------
    def open_editor(self) -> None:
        dialog = EditorDialog(self.macro, self, colors=self.colors)
        dialog.macro_changed.connect(self._replace_macro)
        dialog.run_from_requested.connect(self._run_macro_from)
        dialog.exec()

    def _run_macro_from(self, index: int) -> None:
        """Play the current macro starting at ``index`` (editor 'Run from here')."""
        events = self.macro.sorted_events()
        if not (0 <= index < len(events)):
            return
        tail = self.macro.copy_with(events=events[index:]).normalized()
        self._restore_target_focus(tail)
        try:
            self.player.start(tail, loop_count=1, speed=self.speed_spin.value())
        except Exception as exc:  # noqa: BLE001
            self._report_error("Playback failed", exc)
        self._update_state()

    def _replace_macro(self, macro: Macro) -> None:
        self.macro = macro
        self.dirty = True
        self._update_state()

    def open_library(self) -> None:
        dialog = LibraryDialog(self.library, self)
        dialog.open_requested.connect(lambda p: self.load_macro(Path(p)))
        dialog.play_requested.connect(self._play_path)
        dialog.exec()

    def open_scheduler(self) -> None:
        SchedulerDialog(self.schedules, self).exec()
        # Triggers may have been added/removed/toggled.
        self._refresh_image_watcher()

    def open_logs(self) -> None:
        LogDialog(self).exec()

    def _play_path(self, path: str) -> None:
        try:
            macro = Macro.load(path)
        except Exception as exc:
            self._report_error("Play failed", exc, always_dialog=True)
            return
        self.player.start(macro, loop_count=self.loop_spin.value(), speed=self.speed_spin.value())
        self.library.record_run(path)
        self.library.save()
        self._update_state()

    def open_preferences(self) -> None:
        old_backend = self.settings.backend
        dialog = PreferencesDialog(self.settings, self)
        if dialog.exec():
            self._persist()
            self.player.allow_code_execution = self.settings.allow_code_execution
            self._sync_playback_controls_from_settings()
            app = QApplication.instance()
            if app:
                self.colors = apply_theme(app, self.settings)
                self.indicator.set_animated(self.settings.animations)
                self.toasts.set_animated(self.settings.animations)
            self._apply_window_flags()
            self._apply_mode()
            self._rebuild_dispatcher()
            self._reschedule_autosave()
            if self.settings.backend != old_backend:
                self._switch_backend()

    def _sync_playback_controls_from_settings(self) -> None:
        self.loop_spin.setValue(self.settings.loop_count)
        self.speed_spin.setValue(self.settings.speed)

    def _switch_backend(self) -> None:
        self.backend.close()
        self.backend = create_backend(self.settings.backend)
        self.recorder.backend = self.backend
        self.player.backend = self.backend
        self.player.on_loop_complete = self._emit_loop_completed
        self.player.on_error = self._emit_playback_error
        self.player.on_progress = lambda i, t: self.bridge.progress.emit(i, t)
        self._start_hotkeys()
        self.log.info("Switched backend to %s", self.backend.name)

    # -- notifications --------------------------------------------------------
    def _rebuild_dispatcher(self) -> None:
        self.dispatcher.clear()
        notifications = self.settings.notifications
        self.dispatcher.register(DiscordNotifier(notifications.discord))
        self.dispatcher.register(GenericWebhookNotifier(notifications.generic))

    def _handle_loop_completed(self, loop_index: int, total_loops: int, speed: float, macro: Macro) -> None:
        is_final = bool(total_loops) and loop_index >= total_loops
        tray = self.settings.notifications.tray
        if self.tray and tray.should_send(loop_index, is_final):
            self.tray.showMessage("Tiny Macro", f"Finished loop {loop_index}", QSystemTrayIcon.MessageIcon.Information, 3000)
        include_shot = self.settings.notifications.discord.include_screenshot
        screenshot = self._capture_screenshot_png() if include_shot else None
        event = LoopEvent(
            loop_index=loop_index,
            total_loops=total_loops,
            speed=speed,
            macro=copy.deepcopy(macro),
            is_final=is_final,
            screenshot_png=screenshot,
        )

        def send() -> None:
            fired = self.dispatcher.dispatch(event)
            if fired:
                self.log.info("Notified: %s", ", ".join(fired))

        threading.Thread(target=send, name="tiny-macro-notify", daemon=True).start()

    # -- hotkeys --------------------------------------------------------------
    def _start_hotkeys(self) -> None:
        try:
            self.backend.start_hotkeys(self._handle_hotkeys)
        except Exception as exc:
            QMessageBox.warning(self, "Global hotkeys unavailable", str(exc))

    def _handle_hotkeys(self, pressed: frozenset[str]) -> None:
        self.bridge.hotkeys_pressed.emit(pressed)

    def _activate_hotkeys(self, pressed: frozenset[str]) -> None:
        hotkeys = self.settings.hotkeys
        # Marker is checked first so it works while a recording is in progress.
        if self.recorder.recording and hotkeys.marker.is_subset_of(pressed):
            self.drop_marker()
        elif hotkeys.record.is_subset_of(pressed):
            self.toggle_recording()
        elif hotkeys.play.is_subset_of(pressed):
            self.toggle_playback()
        elif hotkeys.stop.is_subset_of(pressed) or any(key.is_subset_of(pressed) for key in hotkeys.emergency):
            self.stop_all()

    # -- signal plumbing ------------------------------------------------------
    def _emit_loop_completed(self, loop_index: int, total_loops: int, speed: float, macro: Macro) -> None:
        self.bridge.loop_completed.emit(loop_index, total_loops, speed, macro)

    def _emit_playback_error(self, exc: Exception) -> None:
        self.bridge.debug_error.emit("Playback failed", self._format_exception(exc))

    def _on_progress(self, index: int, total: int) -> None:
        if total > 0:
            self.progress.setValue(int(index * 100 / total))

    def _on_image_missed(self, event) -> None:
        """Runs on the playback thread when a click-image step can't find its target.

        Logs the miss and, when capture is available, saves a full-screen PNG next
        to the recovery file so the failure can be inspected afterwards.
        """
        self.log.warning("Click-image step missed (confidence %.2f)", event.confidence)
        if not CAPTURE_AVAILABLE:
            return
        try:
            with Locator() as locator:
                png = locator.capture_png(event.region)
            target = self._recovery_path().parent / f"image-miss-{datetime.now():%Y%m%d-%H%M%S}.png"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(png)
            self.log.info("Saved failure screenshot: %s", target)
        except Exception as exc:  # noqa: BLE001
            self.log.warning("Could not save failure screenshot: %s", exc)

    def _report_error(self, title: str, exc: Exception, *, always_dialog: bool = False) -> None:
        details = self._format_exception(exc)
        self.log.error("%s: %s", title, exc)
        if self.settings.debug_mode or always_dialog:
            QMessageBox.critical(self, title, details if self.settings.debug_mode else str(exc))
        self._toast(f"{title}: {exc}", "error", 5000)

    def _handle_debug_error(self, title: str, details: str) -> None:
        self.log.error("%s\n%s", title, details)
        if self.settings.debug_mode:
            QMessageBox.critical(self, title, details)
        first_line = details.splitlines()[-1] if details.splitlines() else details
        self._toast(f"{title}: {first_line}", "error", 5000)
        self._update_state()

    @staticmethod
    def _format_exception(exc: Exception) -> str:
        if exc.__traceback__:
            return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)).strip()
        return f"{type(exc).__name__}: {exc}"

    def _capture_screenshot_png(self) -> bytes | None:
        app = QApplication.instance()
        if not app:
            return None
        screen = app.primaryScreen()
        if not screen:
            return None
        pixmap = screen.grabWindow(0)
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        pixmap.save(buffer, "PNG")
        buffer.close()
        return bytes(data)

    # -- toasts / tray helpers ------------------------------------------------
    def _toast(self, message: str, level: str = "info", milliseconds: int = 2600) -> None:
        self.statusBar().showMessage(message, milliseconds)
        self.toasts.show(message, level=level, milliseconds=milliseconds)

    def _toggle_visible(self) -> None:
        self.hide() if self.isVisible() else self._toggle_visible_show()

    def _toggle_visible_show(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._toggle_visible()

    # -- window flags ---------------------------------------------------------
    def toggle_always_on_top(self) -> None:
        self.settings.always_on_top = self.top_action.isChecked()
        self._apply_window_flags()

    def _apply_window_flags(self) -> None:
        flags = self.windowFlags()
        if self.settings.always_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()

    # -- timers ---------------------------------------------------------------
    def _reschedule_autosave(self) -> None:
        seconds = self.settings.autosave_seconds
        if seconds > 0:
            self._autosave_timer.start(seconds * 1000)
        else:
            self._autosave_timer.stop()

    def _autosave(self) -> None:
        if not self.dirty or not self.macro.events:
            return
        try:
            self._recovery_path().parent.mkdir(parents=True, exist_ok=True)
            self.macro.save(self._recovery_path())
            self.log.info("Autosaved recovery snapshot")
        except OSError as exc:
            self.log.warning("Autosave failed: %s", exc)

    def _recovery_path(self) -> Path:
        return Path.home() / ".config" / "tiny-macro" / AUTOSAVE_NAME

    def _offer_recovery(self) -> None:
        # Skip when settings aren't persisted (e.g. automated tests) so start-up
        # never blocks on a modal dialog.
        if not self.persist_settings:
            return
        path = self._recovery_path()
        if not path.exists():
            return
        answer = QMessageBox.question(
            self,
            "Recover macro",
            "An unsaved macro from a previous session was found. Recover it?",
        )
        if answer == QMessageBox.StandardButton.Yes:
            try:
                self.macro = Macro.load(path)
                self.dirty = True
                self.log.info("Recovered autosaved macro")
            except Exception as exc:
                self.log.warning("Recovery failed: %s", exc)
        try:
            path.unlink()
        except OSError:
            pass

    def _check_schedules(self) -> None:
        if self.player.state.playing or self.recorder.recording:
            return
        now = datetime.now()
        for schedule in self.schedules.due(now):
            try:
                macro = Macro.load(schedule.macro_path)
            except Exception as exc:
                self.log.warning("Scheduled macro failed to load: %s", exc)
                continue
            schedule.mark_fired(now)
            self.schedules.save()
            self.player.start(macro, loop_count=schedule.loop_count, speed=schedule.speed)
            self.log.info("Ran scheduled macro %s", schedule.display_name)
            self._toast(f"Scheduled run: {schedule.display_name}", "info")
            break

    # -- image-trigger scheduling ---------------------------------------------
    def _refresh_image_watcher(self) -> None:
        """Start or stop the watcher based on whether it has work to do."""
        has_work = CAPTURE_AVAILABLE and any(
            s.is_image and s.can_fire() for s in self.schedules.schedules
        )
        if has_work and not self._image_watcher.is_running():
            self._image_watcher.start()
            self.log.info("Image-trigger watcher started")
        elif not has_work and self._image_watcher.is_running():
            self._image_watcher.stop()
            self.log.info("Image-trigger watcher stopped")

    def _on_image_trigger(self, schedule: Schedule) -> None:
        """A target image was seen (on the GUI thread via the bridge signal)."""
        # Something else is running: don't fire now; allow a fresh detection.
        if self.player.state.playing or self.recorder.recording:
            self._image_watcher.rearm(schedule, seen=False)
            return
        try:
            macro = Macro.load(schedule.macro_path)
        except Exception as exc:  # noqa: BLE001
            self.log.warning("Image-trigger macro failed to load: %s", exc)
            self._image_watcher.rearm(schedule, seen=False)
            return
        schedule.mark_image_fired()
        self.schedules.save()
        self._active_image_schedule = schedule
        self.player.start(macro, loop_count=1, speed=schedule.speed)
        self.log.info("Image trigger fired: %s", schedule.display_name)
        self._toast(f"Image trigger: {schedule.display_name}", "info")

    def _finish_image_trigger_if_done(self) -> None:
        """Re-arm the active image trigger once its macro stops playing."""
        schedule = self._active_image_schedule
        if schedule is None or self.player.state.playing:
            return
        self._active_image_schedule = None
        # seen=True: the image was present when it fired, so it must disappear and
        # reappear before firing again (counts distinct sightings, never loops).
        self._image_watcher.rearm(schedule, seen=True)
        if not schedule.can_fire():
            self.log.info("Image trigger %s reached its fire limit", schedule.display_name)
            self._refresh_image_watcher()

    def _restore_target_focus(self, macro: Macro) -> None:
        """Before keyboard playback, hand focus back to the user's target window.

        Keyboard events go to whatever window is focused; clicking Play focuses
        Tiny Macro, so a keyboard-only macro would otherwise type into us. Mouse
        events are coordinate-based and unaffected, so we only bother for macros
        that contain key events.
        """
        if not self._last_external_hwnd:
            return
        if not any(event.kind == "key" for event in macro.events):
            return
        try:
            if self.backend.focus_window(self._last_external_hwnd):
                time.sleep(0.06)  # let the target actually gain focus
        except Exception:  # noqa: BLE001
            pass

    def _tick(self) -> None:
        self._update_state()
        self._finish_image_trigger_if_done()
        # Continuously remember the user's target window (any focused window that
        # isn't ours), so keyboard playback can be directed back to it.
        try:
            hwnd = self.backend.foreground_window_if_external()
        except Exception:  # noqa: BLE001
            hwnd = 0
        if hwnd:
            self._last_external_hwnd = hwnd
        if self.recorder.recording and self.settings.compact_mode is False:
            self._update_feed()

    def _update_feed(self) -> None:
        events = self.recorder._events  # snapshot of in-progress capture
        if len(events) <= self._last_feed_count:
            return
        for event in events[self._last_feed_count:]:
            self.feed.addItem(event.describe())
        self._last_feed_count = len(events)
        self.feed.scrollToBottom()

    def _update_state(self) -> None:
        recording = self.recorder.recording
        playing = self.player.state.playing
        self.record_action.setChecked(recording)
        self.indicator.set_active(recording)
        self.play_action.setEnabled(bool(self.macro.events) and not recording)
        self.pause_action.setEnabled(playing)
        self.step_action.setEnabled(bool(self.macro.events) and not playing and not recording)
        self.editor_action.setEnabled(bool(self.macro.events))
        self.save_action.setEnabled(bool(self.macro.events))
        title = "Tiny Macro"
        if self.path:
            title += f" - {self.path.name}"
        if self.dirty:
            title += " *"
        self.setWindowTitle(title)
        if playing:
            loops = "inf" if self.loop_spin.value() == 0 else str(self.loop_spin.value())
            paused = " (paused)" if self.player.state.paused else ""
            self.progress_label.setText(
                f"Playing loop {self.player.state.loop_index}/{loops}{paused} · "
                f"{self.player.state.remaining_ns / 1_000_000_000:.2f}s left"
            )
            self.statusBar().showMessage(self.progress_label.text())
        elif recording:
            self.progress.setValue(0)
            self.progress_label.setText(f"Recording · {self.recorder.event_count} events")
            self.statusBar().showMessage(self.progress_label.text())
        else:
            self.progress.setValue(0)
            summary = (
                f"{len(self.macro.events)} events · {self.macro.duration_s:.3f}s · {self.backend.name}"
            )
            self.progress_label.setText(summary)
            self.statusBar().showMessage(summary)

    # -- persistence / close --------------------------------------------------
    def _persist(self) -> None:
        if not self.persist_settings:
            return
        try:
            if self._on_persist is not None:
                self._on_persist()
            else:
                self.settings.save()
        except Exception as exc:
            self.log.warning("Could not save settings: %s", exc)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self.toasts._current is not None:
            self.toasts._current._reposition()

    def closeEvent(self, event) -> None:  # noqa: N802
        if not self._confirm_discard():
            event.ignore()
            return
        self.player.stop(wait=True)
        self._image_watcher.stop()
        self.backend.close()
        if self.tray:
            self.tray.hide()
        self._persist()
        self.log.info("Tiny Macro closed")
        event.accept()

    def _confirm_discard(self) -> bool:
        if not self.dirty:
            return True
        answer = QMessageBox.question(self, "Unsaved macro", "Discard unsaved macro changes?")
        return answer == QMessageBox.StandardButton.Yes


