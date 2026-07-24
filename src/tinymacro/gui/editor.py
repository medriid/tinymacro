from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from tinymacro.core.events import MacroEvent
from tinymacro.core.macro import Macro


class EditorDialog(QDialog):
    macro_changed = pyqtSignal(object)

    def __init__(self, macro: Macro, parent=None, colors=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Macro Editor")
        self.resize(880, 520)
        self._kind_colors = getattr(colors, "kind_colors", None) or {}
        self.macro = macro.normalized()
        self._history: list[Macro] = []
        self._redo: list[Macro] = []
        self._filter = ""

        self.info = QLabel()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter events (kind, key, button, note)…")
        self.search.textChanged.connect(self._on_filter)

        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(
            ["#", "Time (s)", "Kind", "Action", "Key", "Button", "X/Y", "Delta", "Note"]
        )
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(lambda *_: self.edit_note())

        # Row 1 of tools: structural edits.
        self.undo_button = QPushButton("Undo")
        self.redo_button = QPushButton("Redo")
        self.delete_button = QPushButton("Delete")
        self.trim_idle_button = QPushButton("Trim Idle")
        self.keep_selected_button = QPushButton("Keep Range")
        self.note_button = QPushButton("Edit Note…")

        # Row 2 of tools: timing + inserts.
        self.scale = QDoubleSpinBox()
        self.scale.setRange(0.01, 100.0)
        self.scale.setValue(1.0)
        self.scale.setSingleStep(0.1)
        self.scale_button = QPushButton("Scale Timing")
        self.wait_ms = QSpinBox()
        self.wait_ms.setRange(1, 3_600_000)
        self.wait_ms.setValue(500)
        self.wait_ms.setSuffix(" ms")
        self.wait_jitter = QSpinBox()
        self.wait_jitter.setRange(0, 3_600_000)
        self.wait_jitter.setValue(0)
        self.wait_jitter.setPrefix("± ")
        self.wait_jitter.setSuffix(" ms")
        self.insert_wait_button = QPushButton("Insert Wait")

        tools1 = QHBoxLayout()
        for widget in (
            self.undo_button,
            self.redo_button,
            self.delete_button,
            self.trim_idle_button,
            self.keep_selected_button,
            self.note_button,
        ):
            tools1.addWidget(widget)
        tools1.addStretch(1)

        tools2 = QHBoxLayout()
        tools2.addWidget(QLabel("Timing ×"))
        tools2.addWidget(self.scale)
        tools2.addWidget(self.scale_button)
        tools2.addSpacing(16)
        tools2.addWidget(QLabel("Wait"))
        tools2.addWidget(self.wait_ms)
        tools2.addWidget(self.wait_jitter)
        tools2.addWidget(self.insert_wait_button)
        tools2.addStretch(1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        tools_wrap = QWidget()
        tools_layout = QVBoxLayout(tools_wrap)
        tools_layout.setContentsMargins(0, 0, 0, 0)
        tools_layout.addLayout(tools1)
        tools_layout.addLayout(tools2)

        layout = QVBoxLayout(self)
        layout.addWidget(self.info)
        layout.addWidget(self.search)
        layout.addWidget(self.table, 1)
        layout.addWidget(tools_wrap)
        layout.addWidget(buttons)

        self.undo_button.clicked.connect(self.undo)
        self.redo_button.clicked.connect(self.redo)
        self.delete_button.clicked.connect(self.delete_selected)
        self.trim_idle_button.clicked.connect(self.trim_idle)
        self.keep_selected_button.clicked.connect(self.keep_selected_range)
        self.note_button.clicked.connect(self.edit_note)
        self.scale_button.clicked.connect(self.scale_timing)
        self.insert_wait_button.clicked.connect(self.insert_wait)
        self._populate()

    # -- history --------------------------------------------------------------
    def _apply(self, new_macro: Macro) -> None:
        self._history.append(self.macro)
        self._redo.clear()
        self.macro = new_macro
        self._populate()

    def undo(self) -> None:
        if not self._history:
            return
        self._redo.append(self.macro)
        self.macro = self._history.pop()
        self._populate()

    def redo(self) -> None:
        if not self._redo:
            return
        self._history.append(self.macro)
        self.macro = self._redo.pop()
        self._populate()

    # -- view -----------------------------------------------------------------
    def _on_filter(self, text: str) -> None:
        self._filter = text.strip().lower()
        self._populate()

    def _row_matches(self, event: MacroEvent) -> bool:
        if not self._filter:
            return True
        haystack = " ".join(
            str(part).lower()
            for part in (event.kind, event.action, event.key, event.button, event.note)
            if part
        )
        return self._filter in haystack

    def _selected_source_indices(self) -> list[int]:
        rows = sorted(index.row() for index in self.table.selectionModel().selectedRows())
        return [self.table.item(row, 0).data(Qt.ItemDataRole.UserRole) for row in rows]

    def _populate(self) -> None:
        events = self.macro.sorted_events()
        self.info.setText(
            f"{self.macro.name} | {len(events)} events "
            f"({self.macro.input_event_count()} input, {self.macro.wait_event_count()} wait) | "
            f"{self.macro.duration_s:.3f}s | {self.macro.backend}"
        )
        visible = [(idx, event) for idx, event in enumerate(events) if self._row_matches(event)]
        self.table.setRowCount(len(visible))
        for row, (source_index, event) in enumerate(visible):
            xy = "" if event.x is None or event.y is None else f"{event.x},{event.y}"
            delta = "" if not event.dx and not event.dy else f"{event.dx},{event.dy}"
            values = [
                str(source_index),
                f"{event.timestamp_ns / 1_000_000_000:.6f}",
                event.kind,
                event.action,
                event.key or "",
                event.button or "",
                xy,
                delta,
                event.note,
            ]
            tint = self._kind_colors.get(event.kind)
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, source_index)
                if tint and col == 2:
                    color = QColor(tint)
                    color.setAlpha(60)
                    item.setBackground(color)
                self.table.setItem(row, col, item)
        self.table.resizeColumnsToContents()
        self.undo_button.setEnabled(bool(self._history))
        self.redo_button.setEnabled(bool(self._redo))

    # -- operations -----------------------------------------------------------
    def delete_selected(self) -> None:
        indices = set(self._selected_source_indices())
        if not indices:
            return
        self._apply(self.macro.delete_indices(indices))

    def trim_idle(self) -> None:
        self._apply(self.macro.trim_trailing_idle())

    def keep_selected_range(self) -> None:
        indices = self._selected_source_indices()
        if not indices:
            return
        events = self.macro.sorted_events()
        self._apply(self.macro.trim_range(events[indices[0]].timestamp_ns, events[indices[-1]].timestamp_ns))

    def scale_timing(self) -> None:
        self._apply(self.macro.scale_timing(self.scale.value()))

    def insert_wait(self) -> None:
        indices = self._selected_source_indices()
        at = indices[0] if indices else len(self.macro.sorted_events())
        self._apply(
            self.macro.insert_wait(
                at,
                self.wait_ms.value() * 1_000_000,
                self.wait_jitter.value() * 1_000_000,
                note="wait",
            )
        )

    def edit_note(self) -> None:
        indices = self._selected_source_indices()
        if not indices:
            return
        index = indices[0]
        current = self.macro.sorted_events()[index].note
        text, ok = QInputDialog.getText(self, "Edit Note", "Note:", QLineEdit.EchoMode.Normal, current)
        if ok:
            self._apply(self.macro.set_note(index, text))

    def accept(self) -> None:
        self.macro_changed.emit(self.macro)
        super().accept()
