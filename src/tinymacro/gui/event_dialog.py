"""Dialog to build or edit a plain input event (key / mouse / wheel).

Complements the wait and click-image inserters so the editor can add or tweak
any ordinary step by hand.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
)

from tinymacro.core.events import MacroEvent

_ACTIONS = {
    "key": ["press", "release"],
    "mouse": ["press", "release", "move"],
    "wheel": ["scroll"],
}


class EventDialog(QDialog):
    """Configure one key/mouse/wheel event; :meth:`build_event` returns it."""

    def __init__(self, event: MacroEvent | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit Event" if event else "Insert Event")
        self.setMinimumWidth(320)

        self.kind = QComboBox()
        self.kind.addItems(["key", "mouse", "wheel"])
        self.action = QComboBox()
        self.key = QLineEdit()
        self.key.setPlaceholderText("e.g. a, enter, ctrl")
        self.button = QComboBox()
        self.button.addItems(["left", "right", "middle"])
        self.x = QSpinBox()
        self.x.setRange(0, 100_000)
        self.y = QSpinBox()
        self.y.setRange(0, 100_000)
        self.dx = QSpinBox()
        self.dx.setRange(-10_000, 10_000)
        self.dy = QSpinBox()
        self.dy.setRange(-10_000, 10_000)
        self.note = QLineEdit()

        xy_row = QHBoxLayout()
        xy_row.addWidget(QLabel("x"))
        xy_row.addWidget(self.x)
        xy_row.addWidget(QLabel("y"))
        xy_row.addWidget(self.y)
        self._xy_widget = QLabel  # placeholder; real rows added below

        d_row = QHBoxLayout()
        d_row.addWidget(QLabel("dx"))
        d_row.addWidget(self.dx)
        d_row.addWidget(QLabel("dy"))
        d_row.addWidget(self.dy)

        form = QFormLayout()
        form.addRow("Kind", self.kind)
        form.addRow("Action", self.action)
        self._key_label = QLabel("Key")
        form.addRow(self._key_label, self.key)
        self._button_label = QLabel("Button")
        form.addRow(self._button_label, self.button)
        self._xy_label = QLabel("Position")
        form.addRow(self._xy_label, self._wrap(xy_row))
        self._d_label = QLabel("Delta")
        form.addRow(self._d_label, self._wrap(d_row))
        form.addRow("Note", self.note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        outer = QFormLayout(self)
        outer.addRow(form)
        outer.addRow(buttons)

        self.kind.currentTextChanged.connect(self._sync_actions)
        self.action.currentTextChanged.connect(self._sync_visibility)

        if event is not None:
            self._load(event)
        else:
            self._sync_actions(self.kind.currentText())

    @staticmethod
    def _wrap(layout) -> "QWidget":  # noqa: F821 - forward ref for a local import
        from PyQt6.QtWidgets import QWidget

        widget = QWidget()
        widget.setLayout(layout)
        return widget

    def _load(self, event: MacroEvent) -> None:
        self.kind.setCurrentText(event.kind if event.kind in _ACTIONS else "key")
        self._sync_actions(self.kind.currentText())
        if event.action in _ACTIONS.get(event.kind, []):
            self.action.setCurrentText(event.action)
        self.key.setText(event.key or "")
        if event.button:
            self.button.setCurrentText(event.button)
        self.x.setValue(event.x or 0)
        self.y.setValue(event.y or 0)
        self.dx.setValue(event.dx)
        self.dy.setValue(event.dy)
        self.note.setText(event.note)
        self._sync_visibility(self.action.currentText())

    def _sync_actions(self, kind: str) -> None:
        self.action.blockSignals(True)
        self.action.clear()
        self.action.addItems(_ACTIONS.get(kind, ["press"]))
        self.action.blockSignals(False)
        self._sync_visibility(self.action.currentText())

    def _sync_visibility(self, action: str) -> None:
        kind = self.kind.currentText()
        is_key = kind == "key"
        is_mouse_click = kind == "mouse" and action in ("press", "release")
        is_mouse_move = kind == "mouse" and action == "move"
        is_wheel = kind == "wheel"
        self._key_label.setVisible(is_key)
        self.key.setVisible(is_key)
        self._button_label.setVisible(is_mouse_click)
        self.button.setVisible(is_mouse_click)
        show_xy = is_mouse_click or is_mouse_move
        self._xy_label.setVisible(show_xy)
        self._xy_label.parentWidget()  # keep ref
        for w in (self.x, self.y):
            w.setVisible(show_xy)
        for w in (self.dx, self.dy):
            w.setVisible(is_wheel or is_mouse_move)
        self._d_label.setVisible(is_wheel or is_mouse_move)

    def build_event(self, timestamp_ns: int = 0) -> MacroEvent:
        kind = self.kind.currentText()
        action = self.action.currentText()
        return MacroEvent(
            timestamp_ns=timestamp_ns,
            kind=kind,  # type: ignore[arg-type]
            action=action,  # type: ignore[arg-type]
            key=self.key.text().strip() or None if kind == "key" else None,
            button=self.button.currentText() if kind == "mouse" and action in ("press", "release") else None,
            x=self.x.value() if kind == "mouse" and action in ("press", "release", "move") else None,
            y=self.y.value() if kind == "mouse" and action in ("press", "release", "move") else None,
            dx=self.dx.value() if kind in ("wheel", "mouse") else 0,
            dy=self.dy.value() if kind in ("wheel", "mouse") else 0,
            note=self.note.text().strip(),
        )
