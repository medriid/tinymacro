from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from tinymacro.core.macro import Macro


class EditorDialog(QDialog):
    macro_changed = pyqtSignal(object)

    def __init__(self, macro: Macro, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Macro Editor")
        self.resize(760, 420)
        self.macro = macro.normalized()
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(["#", "Time", "Kind", "Action", "Key", "Button", "X/Y", "Delta"])
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        self.info = QLabel()
        self.delete_button = QPushButton("Delete")
        self.trim_idle_button = QPushButton("Trim Idle")
        self.keep_selected_button = QPushButton("Keep Range")
        self.scale = QDoubleSpinBox()
        self.scale.setRange(0.01, 100.0)
        self.scale.setValue(1.0)
        self.scale.setSingleStep(0.1)
        self.scale_button = QPushButton("Scale")

        tools = QHBoxLayout()
        tools.addWidget(self.delete_button)
        tools.addWidget(self.trim_idle_button)
        tools.addWidget(self.keep_selected_button)
        tools.addWidget(QLabel("Timing x"))
        tools.addWidget(self.scale)
        tools.addWidget(self.scale_button)
        tools.addStretch(1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.info)
        layout.addWidget(self.table)
        layout.addLayout(tools)
        layout.addWidget(buttons)

        self.delete_button.clicked.connect(self.delete_selected)
        self.trim_idle_button.clicked.connect(self.trim_idle)
        self.keep_selected_button.clicked.connect(self.keep_selected_range)
        self.scale_button.clicked.connect(self.scale_timing)
        self._populate()

    def _populate(self) -> None:
        events = self.macro.sorted_events()
        self.info.setText(
            f"{self.macro.name} | {len(events)} events | {self.macro.duration_s:.3f}s | "
            f"{self.macro.backend} | {self.macro.screen_geometry or 'geometry unknown'}"
        )
        self.table.setRowCount(len(events))
        for row, event in enumerate(events):
            values = [
                str(row),
                f"{event.timestamp_ns / 1_000_000_000:.6f}",
                event.kind,
                event.action,
                event.key or "",
                event.button or "",
                "" if event.x is None or event.y is None else f"{event.x},{event.y}",
                "" if not event.dx and not event.dy else f"{event.dx},{event.dy}",
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row, col, item)
        self.table.resizeColumnsToContents()

    def delete_selected(self) -> None:
        indices = {index.row() for index in self.table.selectionModel().selectedRows()}
        if not indices:
            return
        self.macro = self.macro.delete_indices(indices)
        self._populate()

    def trim_idle(self) -> None:
        self.macro = self.macro.trim_trailing_idle()
        self._populate()

    def keep_selected_range(self) -> None:
        rows = sorted(index.row() for index in self.table.selectionModel().selectedRows())
        if not rows:
            return
        events = self.macro.sorted_events()
        self.macro = self.macro.trim_range(events[rows[0]].timestamp_ns, events[rows[-1]].timestamp_ns)
        self._populate()

    def scale_timing(self) -> None:
        self.macro = self.macro.scale_timing(self.scale.value())
        self._populate()

    def accept(self) -> None:
        self.macro_changed.emit(self.macro)
        super().accept()
