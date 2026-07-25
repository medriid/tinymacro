"""Dialog to insert an automation step: run command/Python, or wait for a
screen pixel colour or an active-window title.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QSpinBox,
    QWidget,
)

from tinymacro.core.events import DEFAULT_TIMEOUT_MS, MacroEvent

_KINDS = ["run shell", "run python", "wait pixel", "wait window"]


class AutomationDialog(QDialog):
    """Build one automation step; :meth:`build_event` returns it."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Insert Automation Step")
        self.setMinimumWidth(420)

        self.kind = QComboBox()
        self.kind.addItems(_KINDS)
        self.kind.currentTextChanged.connect(self._sync)

        self.command = QPlainTextEdit()
        self.command.setPlaceholderText("Command / code / title substring / #hexcolor")
        self.command.setFixedHeight(70)
        self.x = QSpinBox()
        self.x.setRange(0, 100_000)
        self.y = QSpinBox()
        self.y.setRange(0, 100_000)
        self.tolerance = QDoubleSpinBox()
        self.tolerance.setRange(0.0, 1.0)
        self.tolerance.setSingleStep(0.02)
        self.tolerance.setValue(0.05)
        self.timeout = QSpinBox()
        self.timeout.setRange(0, 3_600_000)
        self.timeout.setSuffix(" ms")
        self.timeout.setValue(DEFAULT_TIMEOUT_MS)
        self.on_missing = QComboBox()
        self.on_missing.addItems(["fail", "skip", "continue"])

        xy_row = QHBoxLayout()
        xy_row.addWidget(QLabel("x"))
        xy_row.addWidget(self.x)
        xy_row.addWidget(QLabel("y"))
        xy_row.addWidget(self.y)
        xy_widget = QWidget()
        xy_widget.setLayout(xy_row)

        self._form = QFormLayout()
        self._form.addRow("Type", self.kind)
        self._form.addRow("Value", self.command)
        self._pixel_label = QLabel("Pixel")
        self._form.addRow(self._pixel_label, xy_widget)
        self._tol_label = QLabel("Tolerance")
        self._form.addRow(self._tol_label, self.tolerance)
        self._form.addRow("Timeout", self.timeout)
        self._form.addRow("If not met", self.on_missing)
        self._xy_widget = xy_widget

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        outer = QFormLayout(self)
        outer.addRow(self._form)
        outer.addRow(buttons)
        self._sync(self.kind.currentText())

    def _sync(self, kind: str) -> None:
        is_pixel = kind == "wait pixel"
        self._xy_widget.setVisible(is_pixel)
        self._pixel_label.setVisible(is_pixel)
        self.tolerance.setVisible(is_pixel)
        self._tol_label.setVisible(is_pixel)
        hints = {
            "run shell": "echo hello  (a shell command)",
            "run python": "print('hi')  (Python code)",
            "wait pixel": "#3b82f6  (target colour hex)",
            "wait window": "Notepad  (title substring)",
        }
        self.command.setPlaceholderText(hints.get(kind, ""))

    def build_event(self, timestamp_ns: int = 0) -> MacroEvent:
        kind = self.kind.currentText()
        text = self.command.toPlainText().strip()
        timeout = self.timeout.value()
        on_missing = self.on_missing.currentText()
        if kind == "run shell":
            return MacroEvent.run_step(timestamp_ns, text, mode="shell", timeout_ms=timeout, on_missing=on_missing)  # type: ignore[arg-type]
        if kind == "run python":
            return MacroEvent.run_step(timestamp_ns, text, mode="python", timeout_ms=timeout, on_missing=on_missing)  # type: ignore[arg-type]
        if kind == "wait pixel":
            return MacroEvent.wait_pixel(
                timestamp_ns, self.x.value(), self.y.value(), text,
                tolerance=self.tolerance.value(), timeout_ms=timeout, on_missing=on_missing,  # type: ignore[arg-type]
            )
        return MacroEvent.wait_window(timestamp_ns, text, timeout_ms=timeout, on_missing=on_missing)  # type: ignore[arg-type]
