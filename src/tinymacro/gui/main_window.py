from __future__ import annotations

import copy
from datetime import datetime
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
    QStyle,
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
from tinymacro.core.scheduler import ScheduleStore
from tinymacro.core.settings import Settings
from tinymacro.desktop import install_file_association
from tinymacro.export import export_runner
from tinymacro.gui.editor import EditorDialog
from tinymacro.gui.library_dialog import LibraryDialog
from tinymacro.gui.log_dialog import LogDialog
from tinymacro.gui.preferences import PreferencesDialog
from tinymacro.gui.scheduler_dialog import SchedulerDialog
from tinymacro.gui.theme import apply_theme
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
        self.bridge = PlaybackSignalBridge(self)
        self.bridge.loop_completed.connect(self._handle_loop_completed)
        self.bridge.notify_error.connect(lambda message: self._toast(message, "error"))
        self.bridge.hotkeys_pressed.connect(self._activate_hotkeys)
        self.bridge.debug_error.connect(self._handle_debug_error)
        self.bridge.progress.connect(self._on_progress)
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

        self.setWindowTitle("Tiny Macro")
        self.setMinimumWidth(480)
        self.toasts = ToastManager(self, animated=settings.animations)

        self._build_central()
        self._build_toolbar()
        self._build_menu()
        self._build_tray()
        self._apply_window_flags()
        self._apply_mode()
        self._start_hotkeys()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(100)
        self._autosave_timer = QTimer(self)
        self._autosave_timer.timeout.connect(self._autosave)
        self._reschedule_autosave()
        self._schedule_timer = QTimer(self)
        self._schedule_timer.timeout.connect(self._check_schedules)
        self._schedule_timer.start(30_000)

        self._offer_recovery()
        if initial_macro:
            self.load_macro(initial_macro)
        self.log.info("Tiny Macro started (backend=%s)", self.backend.name)
        self._update_state()

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

        self.expand_button = QPushButton("Expand ▾")
        self.expand_button.clicked.connect(self.toggle_mode)
        layout.addWidget(self.expand_button)

        self._central = central
        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Controls")
        toolbar.setMovable(False)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)
        style = self.style()

        self.indicator = RecordingIndicator(animated=self.settings.animations)
        toolbar.addWidget(self.indicator)
        toolbar.addSeparator()

        self.open_action = _action(style, QStyle.StandardPixmap.SP_DialogOpenButton, "Open", self)
        self.save_action = _action(style, QStyle.StandardPixmap.SP_DialogSaveButton, "Save", self)
        self.record_action = _action(style, QStyle.StandardPixmap.SP_DialogApplyButton, "Record", self, checkable=True)
        self.play_action = _action(style, QStyle.StandardPixmap.SP_MediaPlay, "Play", self)
        self.pause_action = _action(style, QStyle.StandardPixmap.SP_MediaPause, "Pause/Resume", self)
        self.stop_action = _action(style, QStyle.StandardPixmap.SP_MediaStop, "Stop", self)
        self.step_action = _action(style, QStyle.StandardPixmap.SP_MediaSeekForward, "Step one event", self)
        self.editor_action = _action(style, QStyle.StandardPixmap.SP_FileDialogDetailedView, "Editor", self)
        self.library_action = _action(style, QStyle.StandardPixmap.SP_DirIcon, "Library", self)
        self.pref_action = _action(style, QStyle.StandardPixmap.SP_FileDialogInfoView, "Preferences", self)
        self.top_action = _action(style, QStyle.StandardPixmap.SP_TitleBarShadeButton, "Always on top", self, checkable=True)
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
        file_menu.addAction("Open", self.open_macro)
        file_menu.addAction("Save", self.save_macro)
        file_menu.addAction("Save As", self.save_macro_as)
        file_menu.addAction("Export Runner", self.export_macro_runner)
        file_menu.addAction("Install File Association", self.install_association)
        file_menu.addSeparator()
        file_menu.addAction("Quit", self.close)

        edit_menu = self.menuBar().addMenu("Edit")
        edit_menu.addAction("Macro Editor", self.open_editor)
        edit_menu.addAction("Preferences", self.open_preferences)

        tools_menu = self.menuBar().addMenu("Tools")
        tools_menu.addAction("Macro Library", self.open_library)
        tools_menu.addAction("Scheduler", self.open_scheduler)
        tools_menu.addAction("Validate (dry run)", self.validate_macro)
        tools_menu.addAction("Log Viewer", self.open_logs)

        view_menu = self.menuBar().addMenu("View")
        view_menu.addAction("Toggle compact / expanded", self.toggle_mode)

    def _build_tray(self) -> None:
        self.tray: QSystemTrayIcon | None = None
        if not self.settings.tray_enabled or not QSystemTrayIcon.isSystemTrayAvailable():
            return
        icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        self.tray = QSystemTrayIcon(icon, self)
        self.tray.setToolTip("Tiny Macro")
        menu = QMenu()
        menu.addAction("Show / Hide", self._toggle_visible)
        menu.addAction("Record", self.toggle_recording)
        menu.addAction("Play", self.toggle_playback)
        menu.addAction("Stop", self.stop_all)
        menu.addSeparator()
        menu.addAction("Quit", self.close)
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
        self.expand_button.setText("Collapse ▴" if expanded else "Expand ▾")
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
                self.dirty = True
                self._last_feed_count = 0
                self.log.info("Recording stopped: %d events", len(self.macro.events))
                self._toast("Recording stopped", "info")
            else:
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
        except Exception as exc:
            self._report_error("Recording failed", exc)
            self._update_state()

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
        self.library.add(path, name=path.stem)
        self.library.save()
        self.log.info("Loaded %s", path.name)
        self._toast(f"Loaded {path.name}", "info")
        self._update_state()

    def save_macro(self) -> None:
        if not self.path:
            self.save_macro_as()
            return
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
        dialog.exec()

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
        if hotkeys.record.is_subset_of(pressed):
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

    def _tick(self) -> None:
        self._update_state()
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


def _action(style, pixmap, tooltip, parent, checkable: bool = False) -> QAction:
    action = QAction(style.standardIcon(pixmap), "", parent)
    action.setToolTip(tooltip)
    action.setCheckable(checkable)
    return action
