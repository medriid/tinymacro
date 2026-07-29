"""The "Studio" UI variant: a wide frameless frame that docks a target window.

Left column = overview + logs, center = a recessed dock area that a selected
window is position-attached into, right column = macro options. Everything
recorded here is stored relative to the dock area (see
:mod:`tinymacro.core.dock`) so the macro replays at any resolution and can be
distributed as a ``.tmacd`` file.
"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QObject, QPoint, QRect, QSize, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QRegion
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
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
from tinymacro.core.dock import DockRegion, scale_to_physical
from tinymacro.core.library import MacroLibrary
from tinymacro.core.logging_setup import get_logger
from tinymacro.core.macro import DOCK_EXTENSION, Macro
from tinymacro.core.theme_pack import resolve_button_color
from tinymacro.core.player import Player, simulate
from tinymacro.core.recorder import Recorder
from tinymacro.core.scheduler import ScheduleStore
from tinymacro.core.settings import Settings
from tinymacro.core.vision import capture_fullscreen_png
from tinymacro.export import export_runner
from tinymacro.notifications.base import LoopEvent, NotificationDispatcher
from tinymacro.notifications.discord_notifier import DiscordNotifier
from tinymacro.notifications.generic import GenericWebhookNotifier
from tinymacro.gui.anim import AnimatedToolButton, InteractionFx
from tinymacro.gui.editor import EditorDialog
from tinymacro.gui.framed_window import FramelessWindow
from tinymacro.gui.icons import get_icon
from tinymacro.gui.library_dialog import LibraryDialog
from tinymacro.gui.playlist_dialog import PlaylistDialog
from tinymacro.gui.log_dialog import LogDialog
from tinymacro.gui.onboarding import OnboardingOverlay, OnboardingStep
from tinymacro.gui.scheduler_dialog import SchedulerDialog
from tinymacro.gui.sounds import ui_sounds
from tinymacro.gui.theme import apply_theme, current_theme, icon_color, theme_manager
from tinymacro.gui.themed_background import ThemedBackground
from tinymacro.gui.toast import ToastManager
from tinymacro.gui.window_picker import WindowPicker

_DOCK_FILTER = f"Studio Macro (*{DOCK_EXTENSION})"


class _Bridge(QObject):
    loop_completed = pyqtSignal(int, int, object)
    progress = pyqtSignal(int, int)
    error = pyqtSignal(str)
    hotkeys_pressed = pyqtSignal(object)  # global hotkeys, marshalled to the GUI thread
    step_reached = pyqtSignal(int)  # live playhead: source index now executing
    breakpoint_hit = pyqtSignal(int)  # playback paused at a breakpoint


class DockArea(QWidget):
    """Holds the recessed docking aperture."""

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumSize(560, 420)
        self._ratio: float | None = None  # None = free (fill); else width/height lock
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
        self._apply_layout()

    def set_aspect_ratio(self, ratio: float | None) -> None:
        """Lock the aperture to ``ratio`` (width/height), or None to fill freely."""
        self._ratio = ratio if (ratio and ratio > 0) else None
        self._apply_layout()

    def _apply_layout(self) -> None:
        """Place ``inner`` — full-bleed when free, else the largest centred rect of
        the locked aspect ratio (letterboxed within the available area)."""
        avail_w, avail_h = self.width(), self.height()
        if self._ratio is None:
            x, y, w, h = 0, 0, avail_w, avail_h
        elif avail_h and avail_w / avail_h > self._ratio:
            h = avail_h
            w = round(h * self._ratio)
            x, y = (avail_w - w) // 2, 0
        else:
            w = avail_w
            h = round(w / self._ratio) if self._ratio else avail_h
            x, y = 0, (avail_h - h) // 2
        self.inner.setGeometry(x, y, w, h)

    def region(self) -> DockRegion:
        # Report the aperture in *physical* pixels: SetWindowPos (docking) and the
        # low-level mouse hook (recording) both work in device pixels, so on a
        # scaled display the logical Qt geometry must be converted or the docked
        # window lands small and off-centre.
        top_left = self.inner.mapToGlobal(QPoint(0, 0))
        return scale_to_physical(
            top_left.x(), top_left.y(),
            self.inner.width(), self.inner.height(),
            self.inner.devicePixelRatioF(),
        )

    def set_docked(self, docked: bool) -> None:
        # When docked the interior becomes a see-through hole, so hide the hint.
        self.placeholder.setVisible(not docked)


class StudioWindow(FramelessWindow):
    switch_variant_requested = pyqtSignal(str)
    _ASPECT_MODES = ("free", "16:9", "match")

    def __init__(
        self,
        settings: Settings,
        backend: InputBackend,
        persist_settings: bool = True,
        library: MacroLibrary | None = None,
        schedules: ScheduleStore | None = None,
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
        self.schedules = schedules if schedules is not None else ScheduleStore()
        self.macro = Macro(docked=True)
        self.path: Path | None = None
        self._target_hwnd: int | None = None
        self._target_title = ""
        # The target window's client rect (physical px) captured at dock time, so
        # undock can put it back where it was.
        self._pre_dock_rect: tuple[int, int, int, int] | None = None
        self._cleaned = False
        self._keep_backend = False  # set true on a variant switch to share the backend
        self._mask_hole: QRect | None = None
        # Hover tint + hover/click sounds for the plain side-panel push buttons.
        self._fx = InteractionFx(self)
        self.toasts = ToastManager(self, animated=settings.animations)

        self.recorder = Recorder(
            backend, settings.hotkeys,
            skip_final_click=settings.skip_final_click,
            dock_region_provider=self._dock_region,
        )
        self.player = Player(backend, dock_region_provider=self._dock_region)
        self.player.allow_code_execution = settings.allow_code_execution
        self.player.screenshot_capturer = capture_fullscreen_png
        # A small settling gap between loops + release of any leftover held input,
        # so every iteration replays as a clean, fresh run.
        self.player.loop_gap_ns = settings.effective_loop_gap_ns
        self.player.reset_between_loops = True
        self.dispatcher = NotificationDispatcher(on_error=lambda name, exc: None)
        self._rebuild_dispatcher()
        self.bridge = _Bridge(self)
        self.bridge.loop_completed.connect(self._on_loop_completed)
        self.bridge.progress.connect(self._on_progress)
        self.bridge.error.connect(lambda m: self._toast(m, "error"))
        self.bridge.hotkeys_pressed.connect(self._activate_hotkeys)
        self.bridge.step_reached.connect(self._on_step_reached)
        self.bridge.breakpoint_hit.connect(self._on_breakpoint_hit)
        self.player.on_loop_complete = (
            lambda done, total, spd, macro, shot: self.bridge.loop_completed.emit(done, total, shot)
        )
        self.player.on_progress = lambda i, t: self.bridge.progress.emit(i, t)
        self.player.on_error = lambda exc: self.bridge.error.emit(str(exc))
        self.player.on_step = lambda i: self.bridge.step_reached.emit(i)
        self.player.on_breakpoint = lambda i: self.bridge.breakpoint_hit.emit(i)
        # Non-modal editor + whether the live playhead applies to the current run.
        self._editor: EditorDialog | None = None
        self._playhead_active = False
        self._onboarding: OnboardingOverlay | None = None
        self._onboarding_pending = not settings.onboarding_seen

        self.setMinimumSize(1100, 620)
        self.resize(1320, 760)
        self._build_ui()
        self._apply_aspect()  # honour the persisted aspect lock

        self._tracker = QTimer(self)
        self._tracker.timeout.connect(self._track_dock)
        self._tracker.start(150)
        self._state_timer = QTimer(self)
        self._state_timer.timeout.connect(self._update_state)
        self._state_timer.start(120)
        theme_manager.changed.connect(lambda c: self._retint(c))
        self._themed_bg: ThemedBackground | None = None
        theme_manager.changed.connect(lambda _c: self._refresh_themed_background())
        self._refresh_themed_background()
        self._start_hotkeys()
        self._update_overview()
        self._update_state()

    def _refresh_themed_background(self) -> None:
        """Install/replace/remove the image-or-GIF backdrop for the active theme."""
        if self._themed_bg is not None:
            self._themed_bg.dispose()
            self._themed_bg.deleteLater()
            self._themed_bg = None
        theme = current_theme()
        if theme is not None and theme.background.kind in ("image", "animated"):
            self._themed_bg = ThemedBackground(self, theme)
            self._themed_bg.set_paused(self.player.state.playing or not self.settings.animations)

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
        self.aspect_combo = QComboBox()
        self.aspect_combo.addItems(["Aspect: Free", "Aspect: 16:9", "Aspect: Match window"])
        self.aspect_combo.setCurrentIndex(self._ASPECT_MODES.index(self.settings.studio_aspect))
        self.aspect_combo.setToolTip("Lock the docking aperture's shape.")
        self.aspect_combo.currentIndexChanged.connect(self._on_aspect_changed)
        right.addWidget(self.aspect_combo)

        right.addSpacing(6)
        right.addWidget(_heading("Record & Play"))
        # All three transport controls share one row as icon-only buttons, each
        # tinted with its own colour (record orange, play green, stop red…) so
        # they're identifiable without labels. Play is a combined Play/Stop
        # toggle; Pause/Resume is a separate button.
        self.record_btn = self._transport_button("record", "Record", self.toggle_recording)
        self.play_btn = self._transport_button("play", "Play", self.toggle_playback)
        self.pause_btn = self._transport_button("pause", "Pause", self.toggle_pause)
        transport = QHBoxLayout()
        transport.setSpacing(6)
        for button in (self.record_btn, self.play_btn, self.pause_btn):
            transport.addWidget(button, 1)
        right.addLayout(transport)

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
        self.editor_btn = self._row_button("editor", "Editor", color, self.open_editor)
        right.addWidget(self.editor_btn)

        right.addSpacing(6)
        right.addWidget(_heading("Tools"))
        self.library_btn = self._row_button("library", "Library", color, self.open_library)
        right.addWidget(self.library_btn)
        self.playlist_btn = self._row_button("play", "Playlist", color, self.open_playlist)
        right.addWidget(self.playlist_btn)
        right.addWidget(self._row_button("scheduler", "Flow Builder", color, self.open_flow_builder))
        right.addWidget(self._row_button("scheduler", "Scheduler", color, self.open_scheduler))
        right.addWidget(self._row_button("logs", "Log Viewer", color, self.open_logs))
        right.addWidget(self._row_button("validate", "Validate", color, self.validate_macro))
        right.addWidget(self._row_button("add_file", "Export…", color, self.export_macro_runner))
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

    def _transport_button(self, name: str, tooltip: str, slot) -> AnimatedToolButton:
        """A large icon-only transport button glowing in its own accent colour."""
        accent = self._button_color(name)
        button = AnimatedToolButton(accent=accent, animated=self.settings.animations)
        button.setIcon(get_icon(name, accent, 24))
        button.setIconSize(QSize(24, 24))
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        button.setToolTip(tooltip)
        button.setMinimumHeight(44)
        button.clicked.connect(slot)
        return button

    def _row_button(self, icon, text, color, slot) -> QPushButton:
        button = QPushButton(get_icon(icon, color), text)
        button.clicked.connect(slot)
        self._fx.attach(button, self.colors.accent if self.colors else None)
        return button

    # -- aspect lock ----------------------------------------------------------
    def _aspect_ratio_value(self) -> float | None:
        """Resolve the current aspect mode to a width/height ratio (None = free)."""
        mode = self.settings.studio_aspect
        if mode == "16:9":
            return 16 / 9
        if mode == "match" and self._pre_dock_rect:
            _, _, w, h = self._pre_dock_rect
            return (w / h) if h else None
        return None

    def _apply_aspect(self) -> None:
        """Push the resolved aspect ratio to the dock area and re-track the window."""
        self.dock.set_aspect_ratio(self._aspect_ratio_value())
        self._update_mask()
        if self._target_hwnd is not None:
            self._track_dock()

    def _on_aspect_changed(self, index: int) -> None:
        self.settings.studio_aspect = self._ASPECT_MODES[index]
        if self.persist_settings and self._on_persist:
            self._on_persist()
        self._apply_aspect()

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
                "Window docking isn't available on this backend.\n\n"
                "It works on Windows, macOS (grant Accessibility permission), and "
                "Linux/X11. Wayland forbids apps from moving other windows, so "
                "docking can't be supported there.",
            )
            return
        picker = WindowPicker(self.backend, self)
        if not picker.exec() or picker.selected is None:
            return
        self._target_hwnd = picker.selected
        self._target_title = picker.selected_title
        # Remember where the window was before we move it, to restore on undock.
        try:
            self._pre_dock_rect = self.backend.window_client_rect(self._target_hwnd)
        except Exception:  # noqa: BLE001
            self._pre_dock_rect = None
        self.macro = self.macro.copy_with(target_window=self._target_title)
        self.dock.set_docked(True)
        self.dock_btn.setText("Undock Window")
        self._apply_aspect()  # "match" needs the just-captured target ratio
        self._track_dock()
        self._toast(f"Docked: {self._target_title}", "success")
        self._update_overview()

    def _undock(self) -> None:
        title = self._target_title
        hwnd = self._target_hwnd
        # Put the window back where it was before docking (if enabled).
        if hwnd and self.settings.restore_window_on_undock and self._pre_dock_rect:
            try:
                self.backend.move_resize_window(hwnd, *self._pre_dock_rect)
            except Exception as exc:  # noqa: BLE001
                self.log.warning("Restoring window on undock failed: %s", exc)
        self._pre_dock_rect = None
        self._target_hwnd = None
        self.dock.set_docked(False)
        self.dock_btn.setText("Dock Window")
        self._apply_aspect()  # "match" reverts to free once the target is gone
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
            self.player.stop()  # Play/Stop toggle; Pause is a separate button
            self._update_state()
            return
        if not self.macro.events:
            QMessageBox.information(self, "No macro", "Record or open a macro first.")
            return
        if self._target_hwnd is not None:
            self.backend.focus_window(self._target_hwnd)
        self.settings.loop_count = self.loop_spin.value()
        self.settings.speed = self.speed_spin.value()
        self._prepare_playhead(True)  # a plain Play drives the editor playhead
        self.player.start(self.macro, loop_count=self.loop_spin.value(), speed=self.speed_spin.value())
        self.logs.addItem(f"▶ Playback started ×{self.loop_spin.value() or '∞'}")
        self._update_state()

    def toggle_pause(self) -> None:
        if not self.player.state.playing:
            return
        if self.player.state.paused:
            self.player.resume()
        else:
            self.player.pause()
        self._update_state()

    def stop_all(self) -> None:
        self.player.stop()
        if self.recorder.recording:
            self.macro = self.recorder.stop().copy_with(docked=True, target_window=self._target_title)
        self._update_state()
        self._update_overview()

    def open_editor(self) -> None:
        # A single, non-modal editor that stays open during playback: the current
        # step is highlighted live and breakpoints pause playback.
        if self._editor is not None:
            self._editor.raise_()
            self._editor.activateWindow()
            return
        editor = EditorDialog(self.macro, self, colors=self.colors, live=True)
        editor.macro_changed.connect(self._replace_macro)
        editor.breakpoints_changed.connect(self._on_breakpoints_changed)
        editor.finished.connect(self._on_editor_closed)
        self._editor = editor
        editor.show()

    def _on_editor_closed(self, _result: int = 0) -> None:
        self._playhead_active = False
        self.player.breakpoints = set()
        self._editor = None

    def _open_theme_editor(self) -> None:
        from tinymacro.gui.theme_editor import ThemeEditor

        persist = self._on_persist if (self.persist_settings and self._on_persist) else None
        ThemeEditor(self.settings, self, persist=persist).exec()

    def _on_breakpoints_changed(self, breakpoints: set) -> None:
        self.player.breakpoints = set(breakpoints)

    def _on_step_reached(self, index: int) -> None:
        if self._playhead_active and self._editor is not None:
            self._editor.set_playing_index(index)

    def _on_breakpoint_hit(self, index: int) -> None:
        if self._playhead_active and self._editor is not None:
            self._editor.set_paused_at(index)
        self.logs.addItem(f"⏸ Breakpoint at step {index} — press Resume")
        self._toast(f"Paused at step {index} (breakpoint) — press Resume", "info")
        self._update_state()

    def _prepare_playhead(self, active: bool) -> None:
        """Arm/disarm the live playhead + breakpoints for the next run."""
        self._playhead_active = active and self._editor is not None
        if active and self._editor is not None:
            self.player.breakpoints = set(self._editor.breakpoints)
        else:
            self.player.breakpoints = set()
            if self._editor is not None:
                self._editor.clear_playing()

    def _replace_macro(self, macro: Macro) -> None:
        self.macro = macro.copy_with(docked=True, target_window=self._target_title)
        self._update_overview()

    @staticmethod
    def _named_from_path(macro: Macro, path: Path) -> Macro:
        """Adopt the file's name so the overview shows it instead of "Untitled"."""
        if macro.name in ("", "Untitled"):
            return macro.copy_with(name=path.stem)
        return macro

    # -- tools (Classic parity) ----------------------------------------------
    def open_library(self) -> None:
        dialog = LibraryDialog(self.library, self)
        dialog.open_requested.connect(lambda p: self._load_macro_path(Path(p)))
        dialog.play_requested.connect(self._play_path)
        dialog.exec()

    def open_playlist(self) -> None:
        dialog = PlaylistDialog(self.library, docked=True, parent=self)
        dialog.play_requested.connect(self._play_built_macro)
        dialog.exec()

    def open_flow_builder(self) -> None:
        from tinymacro.gui.flow_builder import FlowBuilderDialog

        dialog = FlowBuilderDialog(self.library, docked=True, parent=self)
        dialog.play_requested.connect(self._play_built_macro)
        dialog.exec()

    def _play_built_macro(self, macro: Macro) -> None:
        """Run a macro assembled by a tool (e.g. a playlist) through the player."""
        if not macro.events:
            QMessageBox.information(self, "Empty", "That playlist produced no events.")
            return
        if self._target_hwnd is not None:
            self.backend.focus_window(self._target_hwnd)
        self._prepare_playhead(False)  # a stitched playlist isn't the editor's macro
        try:
            self.player.start(macro, loop_count=self.loop_spin.value(), speed=self.speed_spin.value())
        except Exception as exc:  # noqa: BLE001
            self._toast(str(exc), "error")
            return
        self.logs.addItem(f"▶ Playlist started ({len(macro.events)} events)")
        self._update_state()

    def open_scheduler(self) -> None:
        SchedulerDialog(self.schedules, self).exec()

    def open_logs(self) -> None:
        LogDialog(self).exec()

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
            QMessageBox.warning(
                self, "Validation warnings", summary + "\n\n" + "\n".join(report.warnings)
            )

    def export_macro_runner(self) -> None:
        if not self.macro.events:
            QMessageBox.information(self, "No macro", "Record or open a macro first.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export Runner", "", "Python Runner (*.py)")
        if not path:
            return
        macro = self.macro.copy_with(
            docked=True, target_window=self._target_title,
            speed=self.speed_spin.value(), loop_count=self.loop_spin.value(),
        )
        try:
            runner, _ = export_runner(
                macro, path, loop_count=self.loop_spin.value(), speed=self.speed_spin.value()
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Export failed", str(exc))
            return
        self._toast(f"Exported {runner.name}", "success")

    def _load_macro_path(self, path: Path) -> None:
        try:
            self.macro = Macro.load_for_variant(str(path), docked=True)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Cannot open", str(exc))
            return
        self.macro = self._named_from_path(self.macro, path)
        self.path = path
        self._target_title = self.macro.target_window
        self.loop_spin.setValue(self.macro.loop_count)
        self.speed_spin.setValue(self.macro.speed)
        self._toast(f"Loaded {path.name}", "info")
        self._update_overview()

    def _play_path(self, path: str) -> None:
        try:
            macro = Macro.load_for_variant(path, docked=True)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Play failed", str(exc))
            return
        if self._target_hwnd is not None:
            self.backend.focus_window(self._target_hwnd)
        self._prepare_playhead(False)
        try:
            self.player.start(
                macro, loop_count=self.loop_spin.value(), speed=self.speed_spin.value()
            )
        except Exception as exc:  # noqa: BLE001
            self._toast(str(exc), "error")
            return
        self.library.record_run(path)
        self.library.save()
        self._update_state()

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
        self.macro = self._named_from_path(self.macro, Path(path))
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
        name = self.macro.name if self.macro.name not in ("", "Untitled") else Path(path).stem
        self.macro = self.macro.copy_with(
            docked=True, target_window=self._target_title, name=name,
            speed=self.speed_spin.value(), loop_count=self.loop_spin.value(),
        )
        try:
            self.macro.save(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Cannot save", str(exc))
            return
        self.path = Path(path)
        self._update_overview()
        self._toast(f"Saved {Path(path).name}", "success")

    # -- state / overview -----------------------------------------------------
    def _update_state(self) -> None:
        recording = self.recorder.recording
        playing = self.player.state.playing
        if self._editor is not None and not playing:
            self._editor.clear_playing()  # playback ended → drop the live playhead
        if self._themed_bg is not None:
            self._themed_bg.set_paused(playing or not self.settings.animations)  # freeze GIF during playback
        self.dock_btn.setText("Undock Window" if self._target_hwnd is not None else "Dock Window")
        # Icon-only transport row: the tooltip carries the label, and each button
        # glows in its own accent so state reads from colour + glyph alone.
        self._set_transport(self.record_btn, "record", "Stop Recording" if recording else "Record")
        self.play_btn.setEnabled((bool(self.macro.events) or playing) and not recording)
        # Play is a combined Play/Stop toggle; Pause/Resume is its own button.
        if playing:
            self._set_transport(self.play_btn, "stop", "Stop")
        else:
            self._set_transport(self.play_btn, "play", "Play")
        paused = self.player.state.paused
        self.pause_btn.setEnabled(playing)
        self._set_transport(
            self.pause_btn, "play" if paused else "pause", "Resume" if paused else "Pause",
            accent_name="pause",
        )

    def _set_transport(self, button, icon: str, tooltip: str, accent_name: str | None = None) -> None:
        """Point a transport button at an icon/tooltip, re-tinting its accent."""
        accent = self._button_color(accent_name or icon)
        button.setIcon(get_icon(icon, accent, 24))
        button.setToolTip(tooltip)
        button.set_accent(accent)

    def _button_color(self, name: str) -> str:
        """A button's icon colour: theme override → transport default → icon tint."""
        return resolve_button_color(current_theme(), name, icon_color())

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

    def _dispatch_notifications(self, done: int, total: int, marked_shot: bytes | None) -> None:
        import threading

        notifications = self.settings.notifications
        if not (notifications.discord.enabled or notifications.generic.enabled):
            return
        screenshot = None
        if notifications.discord.include_screenshot:
            # ``marked_shot`` is the screenshot captured at the macro's screenshot
            # step this loop, delivered with the signal so it can't be overwritten
            # by the next loop; fall back to a fresh grab only if none was marked.
            screenshot = marked_shot or capture_fullscreen_png()
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

    def _on_loop_completed(self, done: int, total: int, screenshot: bytes | None) -> None:
        self.logs.addItem(f"✓ Loop {done}/{total or '∞'} complete")
        while self.logs.count() > 500:
            self.logs.takeItem(0)
        self._dispatch_notifications(done, total, screenshot)
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
        dialog.replay_tour.connect(lambda: QTimer.singleShot(250, lambda: self.start_onboarding(force=True)))
        dialog.open_theme_editor.connect(lambda: QTimer.singleShot(200, self._open_theme_editor))
        if not dialog.exec():
            return
        # Re-apply everything that can change from Preferences.
        self.colors = apply_theme(QApplication.instance(), self.settings)
        self.player.allow_code_execution = self.settings.allow_code_execution
        self.player.loop_gap_ns = self.settings.effective_loop_gap_ns
        ui_sounds().set_enabled(self.settings.ui_sounds)
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

    def show(self) -> None:  # noqa: D401
        # Studio always opens maximized: the docked window fills a large, stable
        # aperture, and the dock tracker keeps adapting if the user restores/resizes.
        self.showMaximized()
        if self._onboarding_pending:
            self._onboarding_pending = False
            QTimer.singleShot(600, self.start_onboarding)

    # -- onboarding -----------------------------------------------------------
    def _onboarding_steps(self) -> list[OnboardingStep]:
        return [
            OnboardingStep(
                "Welcome to Studio",
                "Studio docks a real window into a see-through aperture and records "
                "clicks relative to it, so your macro replays at any size or "
                "resolution. Here's a quick tour — Esc skips anytime.",
            ),
            OnboardingStep(
                "Dock a window",
                "Pick a window and Studio attaches it into the centre aperture. "
                "Everything you record is stored relative to it.",
                lambda: self.dock_btn,
            ),
            OnboardingStep(
                "Lock the shape",
                "Lock the aperture to Free, 16:9, or the docked window's own aspect "
                "ratio — handy for games and fixed-layout apps.",
                lambda: self.aspect_combo,
            ),
            OnboardingStep(
                "Record",
                "Record captures your input inside the docked window with faithful "
                "timing. Drop screenshot points with the hotkey to attach a webhook "
                "image from that exact instant.",
                lambda: self.record_btn,
            ),
            OnboardingStep(
                "Play it back",
                "Play replays with sub-millisecond timing — identical every loop. "
                "Set loops and speed just below.",
                lambda: self.play_btn,
            ),
            OnboardingStep(
                "Edit & debug",
                "The Editor stays open while a macro plays, highlighting the current "
                "step. Right-click a step to set a breakpoint that pauses playback.",
                lambda: self.editor_btn,
            ),
            OnboardingStep(
                "Library & playlists",
                "Save Studio macros to the Library and chain them into Playlists. "
                "You can replay this tour anytime with Guided Tour. Dock a window to "
                "get started!",
                lambda: self.library_btn,
            ),
        ]

    def start_onboarding(self, force: bool = False) -> None:
        if self._onboarding is not None:
            return
        if not force and self.settings.onboarding_seen:
            return
        overlay = OnboardingOverlay(self, self._onboarding_steps(), animated=self.settings.animations)
        self._onboarding = overlay
        overlay.finished.connect(self._on_onboarding_finished)
        overlay.start()

    def _on_onboarding_finished(self) -> None:
        self._onboarding = None
        if not self.settings.onboarding_seen:
            self.settings.onboarding_seen = True
            if self.persist_settings and self._on_persist:
                self._on_persist()

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
