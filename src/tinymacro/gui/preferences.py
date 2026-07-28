from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QDoubleSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from tinymacro.core.hotkeys import Hotkey, HotkeySet
from tinymacro.core.settings import THEME_PRESETS, Settings


class PreferencesDialog(QDialog):
    """Tabbed preferences covering every configurable area of Tiny Macro."""

    replay_tour = pyqtSignal()  # user asked to (re)watch the introduction
    open_theme_editor = pyqtSignal()  # user asked to open the custom-theme editor

    def __init__(self, settings: Settings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.settings = settings
        self.resize(640, 560)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_general_tab(), "General")
        self.tabs.addTab(self._build_appearance_tab(), "Appearance")
        self.tabs.addTab(self._build_capture_tab(), "Capture")
        self.tabs.addTab(self._build_hotkeys_tab(), "Hotkeys")
        self.tabs.addTab(self._build_notifications_tab(), "Notifications")
        self.tabs.addTab(self._build_advanced_tab(), "Advanced")

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs)
        layout.addWidget(buttons)

    # -- tab builders ---------------------------------------------------------
    def _build_general_tab(self) -> QWidget:
        s = self.settings
        self.backend = QComboBox()
        self.backend.addItems(["auto", "x11", "wayland", "windows", "fake"])
        self.backend.setCurrentText(s.backend)
        self.always_on_top = QCheckBox()
        self.always_on_top.setChecked(s.always_on_top)
        self.loop_count = QSpinBox()
        self.loop_count.setRange(0, 999_999)
        self.loop_count.setValue(s.loop_count)
        self.speed = QDoubleSpinBox()
        self.speed.setRange(0.01, 100.0)
        self.speed.setSingleStep(0.25)
        self.speed.setValue(s.speed)
        self.tray_enabled = QCheckBox()
        self.tray_enabled.setChecked(s.tray_enabled)
        self.show_intro_btn = QPushButton("Show Introduction")
        self.show_intro_btn.setToolTip("Replay the guided tour of Tiny Macro.")
        self.show_intro_btn.clicked.connect(self._request_tour)
        self.docs_btn = QPushButton("Docs")
        self.docs_btn.setToolTip("Open the in-app documentation.")
        self.docs_btn.clicked.connect(self._open_docs)

        form = QFormLayout()
        form.addRow("Backend", self.backend)
        form.addRow("Always on top", self.always_on_top)
        form.addRow("Default loops (0 = infinite)", self.loop_count)
        form.addRow("Default speed", self.speed)
        form.addRow("Show system tray icon", self.tray_enabled)
        form.addRow("Help", self._row(self.show_intro_btn, self.docs_btn))
        return _wrap(form)

    def _open_docs(self) -> None:
        from tinymacro.gui.docs_dialog import DocsDialog

        DocsDialog(self).exec()

    def _request_tour(self) -> None:
        # Close Preferences, then let the host start the tour over the main window.
        self.replay_tour.emit()
        self.reject()

    def _request_theme_editor(self) -> None:
        self.open_theme_editor.emit()
        self.reject()

    def _pick_accent(self) -> None:
        from tinymacro.gui.color_picker import ColorPickerDialog

        chosen = ColorPickerDialog.get_color(self.accent_color.text().strip() or "#3b82f6", self)
        if chosen:
            self.accent_color.setText(chosen)

    @staticmethod
    def _row(*widgets) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        for widget in widgets:
            lay.addWidget(widget)
        lay.addStretch(1)
        return w

    def _build_appearance_tab(self) -> QWidget:
        s = self.settings
        self.theme = QComboBox()
        self.theme.addItems(["system", "light", "dark"])
        self.theme.setCurrentText(s.theme)
        self.theme_preset = QComboBox()
        self.theme_preset.addItems(list(THEME_PRESETS))
        self.theme_preset.setCurrentText(s.theme_preset)
        self.accent_color = QLineEdit(s.accent_color)
        self.accent_color.setPlaceholderText("#3b82f6 (blank = monochrome)")
        self.accent_pick = QPushButton("Pick…")
        self.accent_pick.clicked.connect(self._pick_accent)
        self.compact_mode = QCheckBox()
        self.compact_mode.setChecked(s.compact_mode)
        self.animations = QCheckBox()
        self.animations.setChecked(s.animations)
        self.ui_scale = QDoubleSpinBox()
        self.ui_scale.setRange(0.8, 1.8)
        self.ui_scale.setSingleStep(0.1)
        self.ui_scale.setValue(s.ui_scale)
        self.density = QComboBox()
        self.density.addItems(["comfortable", "compact"])
        self.density.setCurrentText(s.density)
        self.theme_editor_btn = QPushButton("Custom Themes…")
        self.theme_editor_btn.setToolTip(
            "Design a theme: image/GIF background, colours, opacity — and export/import "
            "portable .tmactheme files."
        )
        self.theme_editor_btn.clicked.connect(self._request_theme_editor)
        active = "  (a custom theme is active)" if s.active_theme else ""
        self._active_theme_label = QLabel(active)
        self._active_theme_label.setStyleSheet("color: palette(mid);")

        form = QFormLayout()
        form.addRow("Theme", self.theme)
        form.addRow("Color preset", self.theme_preset)
        form.addRow("Custom accent", self._row(self.accent_color, self.accent_pick))
        form.addRow("UI scale", self.ui_scale)
        form.addRow("Density", self.density)
        form.addRow("Custom themes", self._row(self.theme_editor_btn, self._active_theme_label))
        form.addRow("Start in compact mode", self.compact_mode)
        form.addRow("Enable animations", self.animations)
        return _wrap(form)

    def _build_capture_tab(self) -> QWidget:
        s = self.settings
        self.skip_final_click = QCheckBox()
        self.skip_final_click.setChecked(s.skip_final_click)
        self.move_min_interval = QSpinBox()
        self.move_min_interval.setRange(0, 1000)
        self.move_min_interval.setSuffix(" ms")
        self.move_min_interval.setValue(s.move_min_interval_ms)
        self.humanize_jitter = QSpinBox()
        self.humanize_jitter.setRange(0, 5000)
        self.humanize_jitter.setSuffix(" ms")
        self.humanize_jitter.setValue(s.humanize_jitter_ms)
        self.loop_gap_enabled = QCheckBox()
        self.loop_gap_enabled.setChecked(s.loop_gap_enabled)
        self.loop_gap_enabled.setToolTip(
            f"Insert a short {s.loop_gap_ms} ms settling pause between loop "
            "iterations so each loop starts fresh instead of blurring into the "
            "next. Off = loops run back-to-back."
        )
        self.record_countdown = QSpinBox()
        self.record_countdown.setRange(0, 30)
        self.record_countdown.setSuffix(" s")
        self.record_countdown.setValue(s.record_countdown)
        self.auto_trim_leading = QCheckBox()
        self.auto_trim_leading.setChecked(s.auto_trim_leading)
        self.restore_window_on_undock = QCheckBox()
        self.restore_window_on_undock.setChecked(s.restore_window_on_undock)
        self.restore_window_on_undock.setToolTip(
            "Studio: put the docked window back to its original size and position "
            "when you undock it."
        )

        form = QFormLayout()
        form.addRow("Skip final click on stop", self.skip_final_click)
        form.addRow("Mouse-move sampling interval", self.move_min_interval)
        form.addRow("Playback timing jitter (QA realism)", self.humanize_jitter)
        form.addRow("Fresh restart gap between loops", self.loop_gap_enabled)
        form.addRow("Countdown before recording (0 = off)", self.record_countdown)
        form.addRow("Auto-trim idle before first action", self.auto_trim_leading)
        form.addRow("Studio: restore window on undock", self.restore_window_on_undock)
        return _wrap(form)

    def _build_hotkeys_tab(self) -> QWidget:
        h = self.settings.hotkeys
        self.record_hotkey = QLineEdit(str(h.record))
        self.play_hotkey = QLineEdit(str(h.play))
        self.stop_hotkey = QLineEdit(str(h.stop))
        self.marker_hotkey = QLineEdit(str(h.marker))
        self.screenshot_hotkey = QLineEdit(str(h.screenshot))
        self.emergency_hotkeys = QLineEdit(", ".join(str(key) for key in h.emergency))

        form = QFormLayout()
        form.addRow("Record", self.record_hotkey)
        form.addRow("Play", self.play_hotkey)
        form.addRow("Stop", self.stop_hotkey)
        form.addRow("Marker (while recording)", self.marker_hotkey)
        form.addRow("Screenshot point (while recording)", self.screenshot_hotkey)
        form.addRow("Emergency stop keys", self.emergency_hotkeys)
        return _wrap(form)

    def _build_notifications_tab(self) -> QWidget:
        n = self.settings.notifications
        # Discord
        self.webhook_enabled = QCheckBox()
        self.webhook_enabled.setChecked(n.discord.enabled)
        self.webhook_url = QLineEdit(n.discord.url)
        self.webhook_url.setEchoMode(QLineEdit.EchoMode.Password)
        self.webhook_every = QSpinBox()
        self.webhook_every.setRange(1, 999_999)
        self.webhook_every.setValue(n.discord.every_loops)
        self.webhook_screenshot = QCheckBox()
        self.webhook_screenshot.setChecked(n.discord.include_screenshot)
        self.webhook_title = QLineEdit(n.discord.embed.title)
        self.webhook_description = QTextEdit(n.discord.embed.description)
        self.webhook_description.setFixedHeight(60)
        self.webhook_color = QLineEdit(n.discord.embed.color)
        # Generic webhook
        self.generic_enabled = QCheckBox()
        self.generic_enabled.setChecked(n.generic.enabled)
        self.generic_url = QLineEdit(n.generic.url)
        self.generic_every = QSpinBox()
        self.generic_every.setRange(1, 999_999)
        self.generic_every.setValue(n.generic.every_loops)
        self.generic_template = QLineEdit(n.generic.template)
        # Tray
        self.tray_notify = QCheckBox()
        self.tray_notify.setChecked(n.tray.notify_on_finish)

        form = QFormLayout()
        form.addRow("— Discord webhook —", QWidget())
        form.addRow("Enabled", self.webhook_enabled)
        form.addRow("URL", self.webhook_url)
        form.addRow("Send every N loops", self.webhook_every)
        form.addRow("Attach screenshot", self.webhook_screenshot)
        form.addRow("Embed title", self.webhook_title)
        form.addRow("Embed description", self.webhook_description)
        form.addRow("Embed color", self.webhook_color)
        form.addRow("— Generic webhook —", QWidget())
        form.addRow("Enabled", self.generic_enabled)
        form.addRow("URL", self.generic_url)
        form.addRow("Send every N loops", self.generic_every)
        form.addRow("Message template", self.generic_template)
        form.addRow("— Tray / toast —", QWidget())
        form.addRow("Notify when playback finishes", self.tray_notify)
        return _wrap(form)

    def _build_advanced_tab(self) -> QWidget:
        s = self.settings
        self.debug_mode = QCheckBox()
        self.debug_mode.setChecked(s.debug_mode)
        self.log_to_file = QCheckBox()
        self.log_to_file.setChecked(s.log_to_file)
        self.autosave_seconds = QSpinBox()
        self.autosave_seconds.setRange(0, 3600)
        self.autosave_seconds.setSuffix(" s")
        self.autosave_seconds.setValue(s.autosave_seconds)
        self.allow_code_execution = QCheckBox()
        self.allow_code_execution.setChecked(s.allow_code_execution)
        self.allow_code_execution.setToolTip(
            "Danger: lets 'run command / Python' macro steps execute code on this "
            "machine. Only enable for macros you fully trust."
        )

        form = QFormLayout()
        form.addRow("Debug mode (detailed errors)", self.debug_mode)
        form.addRow("Write log file", self.log_to_file)
        form.addRow("Autosave interval (0 = off)", self.autosave_seconds)
        form.addRow("⚠ Allow code-execution steps", self.allow_code_execution)
        return _wrap(form)

    # -- commit ---------------------------------------------------------------
    def _accept(self) -> None:
        try:
            emergency = tuple(
                Hotkey.parse(part)
                for part in self.emergency_hotkeys.text().split(",")
                if part.strip()
            )
            hotkeys = HotkeySet(
                record=Hotkey.parse(self.record_hotkey.text()),
                play=Hotkey.parse(self.play_hotkey.text()),
                stop=Hotkey.parse(self.stop_hotkey.text()),
                marker=Hotkey.parse(self.marker_hotkey.text()),
                screenshot=Hotkey.parse(self.screenshot_hotkey.text()),
                emergency=emergency,
            )
            hotkeys.validate()

            s = self.settings
            s.theme = self.theme.currentText()  # type: ignore[assignment]
            s.theme_preset = self.theme_preset.currentText()
            s.accent_color = self.accent_color.text().strip()
            s.compact_mode = self.compact_mode.isChecked()
            s.animations = self.animations.isChecked()
            s.ui_scale = self.ui_scale.value()
            s.density = self.density.currentText()
            s.backend = self.backend.currentText()
            s.always_on_top = self.always_on_top.isChecked()
            s.tray_enabled = self.tray_enabled.isChecked()
            s.debug_mode = self.debug_mode.isChecked()
            s.skip_final_click = self.skip_final_click.isChecked()
            s.move_min_interval_ms = self.move_min_interval.value()
            s.humanize_jitter_ms = self.humanize_jitter.value()
            s.loop_gap_enabled = self.loop_gap_enabled.isChecked()
            s.record_countdown = self.record_countdown.value()
            s.auto_trim_leading = self.auto_trim_leading.isChecked()
            s.restore_window_on_undock = self.restore_window_on_undock.isChecked()
            s.loop_count = self.loop_count.value()
            s.speed = self.speed.value()
            s.log_to_file = self.log_to_file.isChecked()
            s.autosave_seconds = self.autosave_seconds.value()
            s.allow_code_execution = self.allow_code_execution.isChecked()
            s.hotkeys = hotkeys

            n = s.notifications
            n.discord.enabled = self.webhook_enabled.isChecked()
            n.discord.url = self.webhook_url.text().strip()
            n.discord.every_loops = self.webhook_every.value()
            n.discord.include_screenshot = self.webhook_screenshot.isChecked()
            n.discord.embed.title = self.webhook_title.text()
            n.discord.embed.description = self.webhook_description.toPlainText()
            n.discord.embed.color = self.webhook_color.text()
            n.generic.enabled = self.generic_enabled.isChecked()
            n.generic.url = self.generic_url.text().strip()
            n.generic.every_loops = self.generic_every.value()
            n.generic.template = self.generic_template.text()
            n.tray.notify_on_finish = self.tray_notify.isChecked()

            s.validate()
        except Exception as exc:
            QMessageBox.warning(self, "Invalid preferences", str(exc))
            return
        self.accept()


def _wrap(form: QFormLayout) -> QWidget:
    widget = QWidget()
    widget.setLayout(form)
    return widget
