from __future__ import annotations

import base64

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QImage, QPixmap
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
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from tinymacro.core.events import MacroEvent
from tinymacro.core.macro import Macro
from tinymacro.gui.icons import get_icon
from tinymacro.gui.image_step_dialog import ImageStepDialog
from tinymacro.gui.theme import icon_color


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

        self._columns = ["#", "Time (s)", "Kind", "Action", "Key", "Button", "X/Y", "Delta", "Note"]
        self.tree = QTreeWidget()
        self.tree.setColumnCount(len(self._columns))
        self.tree.setHeaderLabels(self._columns)
        self.tree.setAlternatingRowColors(True)
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.tree.setUniformRowHeights(True)
        self.tree.setExpandsOnDoubleClick(False)
        self.tree.itemDoubleClicked.connect(self._on_double_click)
        self.tree.setIconSize(QSize(40, 26))

        # Row 1 of tools: structural edits.
        color = icon_color()
        self.undo_button = QPushButton(get_icon("undo", color), "Undo")
        self.redo_button = QPushButton(get_icon("redo", color), "Redo")
        self.delete_button = QPushButton(get_icon("trash", color), "Delete")
        self.trim_idle_button = QPushButton(get_icon("trim", color), "Trim Idle")
        self.keep_selected_button = QPushButton(get_icon("scale", color), "Keep Range")
        self.note_button = QPushButton(get_icon("note", color), "Edit Note…")

        # Row 2 of tools: timing + inserts.
        self.scale = QDoubleSpinBox()
        self.scale.setRange(0.01, 100.0)
        self.scale.setValue(1.0)
        self.scale.setSingleStep(0.1)
        self.scale_button = QPushButton(get_icon("scale", color), "Scale Timing")
        self.wait_ms = QSpinBox()
        self.wait_ms.setRange(1, 3_600_000)
        self.wait_ms.setValue(500)
        self.wait_ms.setSuffix(" ms")
        self.wait_jitter = QSpinBox()
        self.wait_jitter.setRange(0, 3_600_000)
        self.wait_jitter.setValue(0)
        self.wait_jitter.setPrefix("± ")
        self.wait_jitter.setSuffix(" ms")
        self.insert_wait_button = QPushButton(get_icon("wait", color), "Insert Wait")
        self.insert_image_button = QPushButton(get_icon("image", color), "Click-Image")
        self.insert_image_button.setToolTip("Insert a step that finds an image on screen and clicks it")

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
        tools2.addWidget(self.insert_image_button)
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
        layout.addWidget(self.tree, 1)
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
        self.insert_image_button.clicked.connect(self.insert_image_step)
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
        indices: set[int] = set()
        for item in self.tree.selectedItems():
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(data, list):
                indices.update(data)  # a movement group carries all its children
            elif data is not None:
                indices.add(data)
        return sorted(indices)

    @staticmethod
    def _is_move(event: MacroEvent) -> bool:
        return event.kind == "mouse" and event.action == "move"

    def _row_values(self, source_index: int, event: MacroEvent) -> list[str]:
        xy = "" if event.x is None or event.y is None else f"{event.x},{event.y}"
        delta = "" if not event.dx and not event.dy else f"{event.dx},{event.dy}"
        if event.kind == "image":
            # Surface the image step's key settings in the existing columns.
            offset = "" if not event.offset_x and not event.offset_y else f"+{event.offset_x},{event.offset_y}"
            note = event.note or f"conf {event.confidence:.2f} · {event.on_missing}"
            return [
                str(source_index),
                f"{event.timestamp_ns / 1_000_000_000:.6f}",
                "image",
                event.click_button if event.click_button == "none" else f"click {event.click_button}",
                "",
                "",
                "",
                offset,
                note,
            ]
        return [
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

    def _make_item(self, values: list[str], tint: str | None = None) -> QTreeWidgetItem:
        item = QTreeWidgetItem(values)
        for col in range(len(values)):
            item.setTextAlignment(col, Qt.AlignmentFlag.AlignCenter)
        if tint:
            color = QColor(tint)
            color.setAlpha(60)
            item.setBackground(2, color)
        return item

    def _populate(self) -> None:
        events = self.macro.sorted_events()
        image_count = self.macro.image_event_count()
        image_note = f", {image_count} image" if image_count else ""
        self.info.setText(
            f"{self.macro.name} | {len(events)} events "
            f"({self.macro.input_event_count()} input, {self.macro.wait_event_count()} wait{image_note}) | "
            f"{self.macro.duration_s:.3f}s | {self.macro.backend}"
        )
        self.tree.clear()
        move_tint = self._kind_colors.get("mouse")
        # While a filter is active, grouping is suppressed so matches stay flat
        # and predictable; otherwise consecutive moves collapse into one node.
        filtering = bool(self._filter)
        group_no = 0
        i = 0
        n = len(events)
        while i < n:
            source_index = i
            event = events[i]
            if not filtering and self._is_move(event):
                # Gather the maximal run of consecutive movements.
                run = []
                j = i
                while j < n and self._is_move(events[j]):
                    run.append(j)
                    j += 1
                if len(run) >= 2:
                    group_no += 1
                    start = events[run[0]].timestamp_ns / 1_000_000_000
                    end = events[run[-1]].timestamp_ns / 1_000_000_000
                    parent = self._make_item(
                        [
                            f"{run[0]}–{run[-1]}",
                            f"{start:.3f}",
                            "mouse",
                            f"move ×{len(run)}",
                            "",
                            "",
                            "",
                            "",
                            f"Mouse group {group_no} · {end - start:.3f}s",
                        ],
                        tint=move_tint,
                    )
                    parent.setData(0, Qt.ItemDataRole.UserRole, list(run))
                    for src in run:
                        child = self._make_item(self._row_values(src, events[src]), tint=move_tint)
                        child.setData(0, Qt.ItemDataRole.UserRole, src)
                        parent.addChild(child)
                    parent.setExpanded(False)
                    self.tree.addTopLevelItem(parent)
                    i = j
                    continue
                # A lone move falls through to a normal top-level row.
            if not self._row_matches(event):
                i += 1
                continue
            tint = self._kind_colors.get(event.kind)
            item = self._make_item(self._row_values(source_index, event), tint=tint)
            item.setData(0, Qt.ItemDataRole.UserRole, source_index)
            if event.kind == "image":
                thumb = _image_thumbnail(event.image_b64)
                if thumb is not None:
                    item.setIcon(0, thumb)
            self.tree.addTopLevelItem(item)
            i += 1
        for col in range(len(self._columns)):
            self.tree.resizeColumnToContents(col)
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

    def insert_image_step(self) -> None:
        dialog = ImageStepDialog(parent=self)
        if not dialog.exec():
            return
        indices = self._selected_source_indices()
        at = indices[0] if indices else len(self.macro.sorted_events())
        self._apply(self.macro.insert_image(at, dialog.build_event()))

    def edit_image_step(self, index: int) -> None:
        event = self.macro.sorted_events()[index]
        dialog = ImageStepDialog(event=event, parent=self)
        if not dialog.exec():
            return
        self._apply(self.macro.replace_event(index, dialog.build_event(event.timestamp_ns)))

    def _on_double_click(self, item, _column: int = 0) -> None:
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(data, int):
            event = self.macro.sorted_events()[data]
            if event.kind == "image":
                self.edit_image_step(data)
                return
        self.edit_note()

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


def _image_thumbnail(image_b64: str) -> QIcon | None:
    """Decode an embedded base64 PNG into a small icon for the editor tree."""
    if not image_b64:
        return None
    try:
        raw = base64.b64decode(image_b64)
    except Exception:  # noqa: BLE001
        return None
    image = QImage()
    if not image.loadFromData(raw, "PNG"):
        return None
    return QIcon(QPixmap.fromImage(image))
