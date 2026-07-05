from __future__ import annotations

import copy
from pathlib import Path
import subprocess
import threading

from PyQt6.QtCore import QByteArray, QBuffer, QIODevice, QObject, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QSpinBox,
    QDoubleSpinBox,
    QStatusBar,
    QToolBar,
    QStyle,
    QWidget,
)

from tinymacro.backends.base import InputBackend
from tinymacro.backends.factory import create_backend
from tinymacro.core.macro import Macro
from tinymacro.core.player import Player
from tinymacro.core.recorder import Recorder
from tinymacro.core.settings import Settings
from tinymacro.desktop import install_file_association
from tinymacro.export import export_runner
from tinymacro.gui.editor import EditorDialog
from tinymacro.gui.preferences import PreferencesDialog
from tinymacro.gui.theme import apply_theme
from tinymacro.notifications.discord import DiscordWebhookClient


class PlaybackSignalBridge(QObject):
    loop_completed = pyqtSignal(int, int, float, object)
    webhook_error = pyqtSignal(str)


class MainWindow(QMainWindow):
    def __init__(
        self,
        settings: Settings,
        backend: InputBackend,
        initial_macro: Path | None = None,
        persist_settings: bool = True,
    ) -> None:
        super().__init__()
        self.settings = settings
        self.backend = backend
        self.persist_settings = persist_settings
        self.recorder = Recorder(backend, settings.hotkeys, skip_final_click=settings.skip_final_click)
        self.player = Player(backend)
        self.notification_bridge = PlaybackSignalBridge(self)
        self.notification_bridge.loop_completed.connect(self._handle_loop_completed)
        self.notification_bridge.webhook_error.connect(lambda message: self.statusBar().showMessage(message, 6000))
        self.player.on_loop_complete = self._emit_loop_completed
        self.webhook_client = DiscordWebhookClient()
        self.macro = Macro()
        self.path: Path | None = None
        self.dirty = False
        self.setWindowTitle("Tiny Macro")
        self.setFixedHeight(86)
        self.setMinimumWidth(470)
        self.setCentralWidget(QWidget())
        self.setStatusBar(QStatusBar())
        self._build_toolbar()
        self._build_menu()
        self._apply_window_flags()
        self._start_hotkeys()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(100)
        if initial_macro:
            self.load_macro(initial_macro)
        self._update_state()

    def closeEvent(self, event) -> None:  # noqa: N802
        if not self._confirm_discard():
            event.ignore()
            return
        self.player.stop(wait=True)
        self.backend.close()
        if self.persist_settings:
            self.settings.save()
        event.accept()

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Controls")
        toolbar.setMovable(False)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)

        style = self.style()
        self.open_action = QAction(style.standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton), "", self)
        self.open_action.setToolTip("Open")
        self.save_action = QAction(style.standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton), "", self)
        self.save_action.setToolTip("Save")
        self.record_action = QAction(style.standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton), "", self)
        self.record_action.setToolTip("Record")
        self.record_action.setCheckable(True)
        self.play_action = QAction(style.standardIcon(QStyle.StandardPixmap.SP_MediaPlay), "", self)
        self.play_action.setToolTip("Play")
        self.stop_action = QAction(style.standardIcon(QStyle.StandardPixmap.SP_MediaStop), "", self)
        self.stop_action.setToolTip("Stop")
        self.editor_action = QAction(style.standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView), "", self)
        self.editor_action.setToolTip("Editor")
        self.pref_action = QAction(style.standardIcon(QStyle.StandardPixmap.SP_FileDialogInfoView), "", self)
        self.pref_action.setToolTip("Preferences")
        self.top_action = QAction(style.standardIcon(QStyle.StandardPixmap.SP_TitleBarShadeButton), "", self)
        self.top_action.setToolTip("Always on top")
        self.top_action.setCheckable(True)
        self.top_action.setChecked(self.settings.always_on_top)

        for action in [
            self.open_action,
            self.save_action,
            self.record_action,
            self.play_action,
            self.stop_action,
        ]:
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
        for action in [self.editor_action, self.pref_action, self.top_action]:
            toolbar.addAction(action)

        self.open_action.triggered.connect(self.open_macro)
        self.save_action.triggered.connect(self.save_macro)
        self.record_action.triggered.connect(self.toggle_recording)
        self.play_action.triggered.connect(self.toggle_playback)
        self.stop_action.triggered.connect(self.stop_all)
        self.editor_action.triggered.connect(self.open_editor)
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

    def _start_hotkeys(self) -> None:
        try:
            self.backend.start_hotkeys(self._handle_hotkeys)
        except Exception as exc:
            QMessageBox.warning(self, "Global hotkeys unavailable", str(exc))

    def _handle_hotkeys(self, pressed: frozenset[str]) -> None:
        hotkeys = self.settings.hotkeys
        if hotkeys.record.is_subset_of(pressed):
            QTimer.singleShot(0, self.toggle_recording)
        elif hotkeys.play.is_subset_of(pressed):
            QTimer.singleShot(0, self.toggle_playback)
        elif hotkeys.stop.is_subset_of(pressed) or any(key.is_subset_of(pressed) for key in hotkeys.emergency):
            QTimer.singleShot(0, self.stop_all)

    def toggle_recording(self) -> None:
        if self.recorder.recording:
            self.macro = self.recorder.stop()
            self.dirty = True
            self.statusBar().showMessage("Recording stopped")
        else:
            self.player.stop()
            self.recorder.skip_final_click = self.settings.skip_final_click
            self.recorder.hotkeys = self.settings.hotkeys
            self.recorder.start()
            self.statusBar().showMessage("Recording")
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
        self.player.on_loop_complete = self._emit_loop_completed
        self.player.start(self.macro, loop_count=self.settings.loop_count, speed=self.settings.speed)
        self._update_state()

    def stop_all(self) -> None:
        if self.recorder.recording:
            self.macro = self.recorder.stop()
            self.dirty = True
        self.player.stop()
        self.statusBar().showMessage("Stopped")
        self._update_state()

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
            QMessageBox.critical(self, "Open failed", str(exc))
            return
        self.path = path
        self.dirty = False
        self.statusBar().showMessage(f"Loaded {path.name}")
        self._update_state()

    def save_macro(self) -> None:
        if not self.path:
            self.save_macro_as()
            return
        try:
            self.macro.save(self.path)
        except Exception as exc:
            QMessageBox.critical(self, "Save failed", str(exc))
            return
        self.dirty = False
        self.statusBar().showMessage(f"Saved {self.path.name}")
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
        runner, macro = export_runner(self.macro, path, loop_count=self.loop_spin.value(), speed=self.speed_spin.value())
        self.statusBar().showMessage(f"Exported {runner.name} and {macro.name}")

    def install_association(self) -> None:
        app_path, mime_path = install_file_association()
        try:
            subprocess.run(["update-desktop-database", str(app_path.parent)], check=False)
            subprocess.run(["update-mime-database", str(mime_path.parent.parent)], check=False)
        except FileNotFoundError:
            pass
        self.statusBar().showMessage("Installed .tmacro association")

    def open_editor(self) -> None:
        dialog = EditorDialog(self.macro, self)
        dialog.macro_changed.connect(self._replace_macro)
        dialog.exec()

    def _replace_macro(self, macro: Macro) -> None:
        self.macro = macro
        self.dirty = True
        self._update_state()

    def open_preferences(self) -> None:
        old_backend = self.settings.backend
        dialog = PreferencesDialog(self.settings, self)
        if dialog.exec():
            self.settings.save()
            app = QApplication.instance()
            if app:
                apply_theme(app, self.settings.theme)
            self._apply_window_flags()
            if self.settings.backend != old_backend:
                self._switch_backend()

    def _switch_backend(self) -> None:
        self.backend.close()
        self.backend = create_backend(self.settings.backend)
        self.recorder.backend = self.backend
        self.player.backend = self.backend
        self.player.on_loop_complete = self._emit_loop_completed
        self._start_hotkeys()

    def _emit_loop_completed(self, loop_index: int, total_loops: int, speed: float, macro: Macro) -> None:
        self.notification_bridge.loop_completed.emit(loop_index, total_loops, speed, macro)

    def _handle_loop_completed(self, loop_index: int, total_loops: int, speed: float, macro: Macro) -> None:
        if not self.settings.webhook.should_send(loop_index):
            return
        screenshot = self._capture_screenshot_png() if self.settings.webhook.include_screenshot else None
        settings = copy.deepcopy(self.settings.webhook)

        def send() -> None:
            try:
                self.webhook_client.send_loop_update(settings, loop_index, total_loops, speed, macro, screenshot)
            except Exception as exc:
                self.notification_bridge.webhook_error.emit(str(exc))

        threading.Thread(target=send, name="tiny-macro-discord-webhook", daemon=True).start()

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

    def _confirm_discard(self) -> bool:
        if not self.dirty:
            return True
        answer = QMessageBox.question(self, "Unsaved macro", "Discard unsaved macro changes?")
        return answer == QMessageBox.StandardButton.Yes

    def _tick(self) -> None:
        self._update_state()

    def _update_state(self) -> None:
        self.record_action.setChecked(self.recorder.recording)
        self.play_action.setEnabled(bool(self.macro.events))
        self.editor_action.setEnabled(bool(self.macro.events))
        self.save_action.setEnabled(bool(self.macro.events))
        title = "Tiny Macro"
        if self.path:
            title += f" - {self.path.name}"
        if self.dirty:
            title += " *"
        self.setWindowTitle(title)
        if self.player.state.playing:
            loops = "inf" if self.loop_spin.value() == 0 else str(self.loop_spin.value())
            self.statusBar().showMessage(
                f"Playing loop {self.player.state.loop_index}/{loops} | "
                f"{self.player.state.remaining_ns / 1_000_000_000:.2f}s left"
            )
        elif self.recorder.recording:
            self.statusBar().showMessage("Recording")
        else:
            self.statusBar().showMessage(
                f"{len(self.macro.events)} events | {self.macro.duration_s:.3f}s | {self.backend.name}"
            )
