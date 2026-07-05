from __future__ import annotations

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QSpinBox,
    QDoubleSpinBox,
    QVBoxLayout,
)

from tinymacro.core.hotkeys import Hotkey, HotkeySet
from tinymacro.core.settings import Settings


class PreferencesDialog(QDialog):
    def __init__(self, settings: Settings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.settings = settings
        self.theme = QComboBox()
        self.theme.addItems(["system", "light", "dark"])
        self.theme.setCurrentText(settings.theme)
        self.backend = QComboBox()
        self.backend.addItems(["auto", "x11", "wayland", "fake"])
        self.backend.setCurrentText(settings.backend)
        self.always_on_top = QCheckBox()
        self.always_on_top.setChecked(settings.always_on_top)
        self.skip_final_click = QCheckBox()
        self.skip_final_click.setChecked(settings.skip_final_click)
        self.loop_count = QSpinBox()
        self.loop_count.setRange(0, 999_999)
        self.loop_count.setValue(settings.loop_count)
        self.speed = QDoubleSpinBox()
        self.speed.setRange(0.01, 100.0)
        self.speed.setSingleStep(0.25)
        self.speed.setValue(settings.speed)
        self.record_hotkey = QLineEdit(str(settings.hotkeys.record))
        self.play_hotkey = QLineEdit(str(settings.hotkeys.play))
        self.stop_hotkey = QLineEdit(str(settings.hotkeys.stop))
        self.emergency_hotkeys = QLineEdit(", ".join(str(key) for key in settings.hotkeys.emergency))

        form = QFormLayout()
        form.addRow("Theme", self.theme)
        form.addRow("Backend", self.backend)
        form.addRow("Always on top", self.always_on_top)
        form.addRow("Skip final click", self.skip_final_click)
        form.addRow("Default loops", self.loop_count)
        form.addRow("Default speed", self.speed)
        form.addRow("Record hotkey", self.record_hotkey)
        form.addRow("Play hotkey", self.play_hotkey)
        form.addRow("Stop hotkey", self.stop_hotkey)
        form.addRow("Emergency keys", self.emergency_hotkeys)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

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
                emergency=emergency,
            )
            hotkeys.validate()
            self.settings.theme = self.theme.currentText()  # type: ignore[assignment]
            self.settings.backend = self.backend.currentText()
            self.settings.always_on_top = self.always_on_top.isChecked()
            self.settings.skip_final_click = self.skip_final_click.isChecked()
            self.settings.loop_count = self.loop_count.value()
            self.settings.speed = self.speed.value()
            self.settings.hotkeys = hotkeys
            self.settings.validate()
        except Exception as exc:
            QMessageBox.warning(self, "Invalid preferences", str(exc))
            return
        self.accept()
