from __future__ import annotations

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLineEdit,
    QMessageBox,
    QSpinBox,
    QDoubleSpinBox,
    QTextEdit,
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
        self.webhook_enabled = QCheckBox()
        self.webhook_enabled.setChecked(settings.webhook.enabled)
        self.webhook_url = QLineEdit(settings.webhook.url)
        self.webhook_url.setEchoMode(QLineEdit.EchoMode.Password)
        self.webhook_every = QSpinBox()
        self.webhook_every.setRange(1, 999_999)
        self.webhook_every.setValue(settings.webhook.every_loops)
        self.webhook_screenshot = QCheckBox()
        self.webhook_screenshot.setChecked(settings.webhook.include_screenshot)
        self.webhook_username = QLineEdit(settings.webhook.embed.username)
        self.webhook_title = QLineEdit(settings.webhook.embed.title)
        self.webhook_description = QTextEdit(settings.webhook.embed.description)
        self.webhook_description.setFixedHeight(72)
        self.webhook_footer = QLineEdit(settings.webhook.embed.footer)
        self.webhook_color = QLineEdit(settings.webhook.embed.color)
        self.webhook_image = QLineEdit(settings.webhook.embed.image)
        self.webhook_fields = QTextEdit(settings.webhook.embed.fields)
        self.webhook_fields.setFixedHeight(72)

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

        webhook_form = QFormLayout()
        webhook_form.addRow("Enabled", self.webhook_enabled)
        webhook_form.addRow("Webhook URL", self.webhook_url)
        webhook_form.addRow("Send every loops", self.webhook_every)
        webhook_form.addRow("Attach screenshot", self.webhook_screenshot)
        webhook_form.addRow("Username", self.webhook_username)
        webhook_form.addRow("Title", self.webhook_title)
        webhook_form.addRow("Description", self.webhook_description)
        webhook_form.addRow("Footer", self.webhook_footer)
        webhook_form.addRow("Color", self.webhook_color)
        webhook_form.addRow("Image", self.webhook_image)
        webhook_form.addRow("Fields", self.webhook_fields)
        webhook_group = QGroupBox("Discord Webhook")
        webhook_group.setLayout(webhook_form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(webhook_group)
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
            self.settings.webhook.enabled = self.webhook_enabled.isChecked()
            self.settings.webhook.url = self.webhook_url.text().strip()
            self.settings.webhook.every_loops = self.webhook_every.value()
            self.settings.webhook.include_screenshot = self.webhook_screenshot.isChecked()
            self.settings.webhook.embed.username = self.webhook_username.text().strip() or "Tiny Macro"
            self.settings.webhook.embed.title = self.webhook_title.text()
            self.settings.webhook.embed.description = self.webhook_description.toPlainText()
            self.settings.webhook.embed.footer = self.webhook_footer.text()
            self.settings.webhook.embed.color = self.webhook_color.text()
            self.settings.webhook.embed.image = self.webhook_image.text()
            self.settings.webhook.embed.fields = self.webhook_fields.toPlainText()
            self.settings.validate()
        except Exception as exc:
            QMessageBox.warning(self, "Invalid preferences", str(exc))
            return
        self.accept()
