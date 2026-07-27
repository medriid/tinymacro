"""Assemble several macros into a playlist and play them back-to-back.

The dialog edits a :class:`~tinymacro.core.playlist.Playlist` (macro paths +
per-item repeat + an inter-macro gap), can save/load it as a ``.tmplist`` file,
and emits the stitched :class:`~tinymacro.core.macro.Macro` via ``play_requested``
so the host runs it through the normal player (looping/speed/notifications all
apply to the whole playlist).
"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from tinymacro.core.library import MacroLibrary
from tinymacro.core.macro import CLASSIC_EXTENSION, DOCK_EXTENSION, LEGACY_CLASSIC_EXTENSION, Macro
from tinymacro.core.playlist import PLAYLIST_EXTENSION, Playlist
from tinymacro.gui.icons import get_icon
from tinymacro.gui.library_dialog import LibraryDialog
from tinymacro.gui.theme import icon_color


class PlaylistDialog(QDialog):
    """Build, save/load and play an ordered list of macros."""

    play_requested = pyqtSignal(object)  # the stitched Macro

    def __init__(self, library: MacroLibrary, docked: bool, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Macro Playlist")
        self.resize(560, 480)
        self.library = library
        self.playlist = Playlist(docked=docked)
        self.path: Path | None = None
        self._loading = False  # guard for programmatic widget updates

        color = icon_color()
        variant = "Studio (.tmacd)" if docked else "classic (.tmacc)"

        self.name_edit = QLineEdit(self.playlist.name)
        self.name_edit.setPlaceholderText("Playlist name")
        self.name_edit.textChanged.connect(self._on_name_changed)

        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._on_row_changed)

        self.repeat_spin = QSpinBox()
        self.repeat_spin.setRange(1, 9999)
        self.repeat_spin.setPrefix("Repeat ×")
        self.repeat_spin.setEnabled(False)
        self.repeat_spin.valueChanged.connect(self._on_repeat_changed)

        self.gap_spin = QSpinBox()
        self.gap_spin.setRange(0, 600_000)
        self.gap_spin.setSuffix(" ms gap")
        self.gap_spin.setValue(self.playlist.gap_ms)
        self.gap_spin.valueChanged.connect(self._on_gap_changed)

        self.add_button = QPushButton(get_icon("add_file", color), "Add File…")
        self.library_button = QPushButton(get_icon("library", color), "Add from Library…")
        self.remove_button = QPushButton(get_icon("remove", color), "Remove")
        self.up_button = QPushButton(get_icon("chevron_up", color), "Up")
        self.down_button = QPushButton(get_icon("chevron_down", color), "Down")
        self.save_button = QPushButton(get_icon("save", color), "Save…")
        self.load_button = QPushButton(get_icon("open", color), "Load…")
        self.play_button = QPushButton(get_icon("play", color), "Play")
        self.play_button.setObjectName("primary")
        close_button = QPushButton(get_icon("close", color), "Close")

        self.add_button.clicked.connect(self._add_file)
        self.library_button.clicked.connect(self._add_from_library)
        self.remove_button.clicked.connect(self._remove)
        self.up_button.clicked.connect(lambda: self._move(-1))
        self.down_button.clicked.connect(lambda: self._move(1))
        self.save_button.clicked.connect(self._save)
        self.load_button.clicked.connect(self._load)
        self.play_button.clicked.connect(self._play)
        close_button.clicked.connect(self.accept)

        row1 = QHBoxLayout()
        for widget in (self.add_button, self.library_button, self.remove_button, self.up_button, self.down_button):
            row1.addWidget(widget)
        row2 = QHBoxLayout()
        row2.addWidget(self.repeat_spin)
        row2.addWidget(self.gap_spin)
        row2.addStretch(1)
        actions = QHBoxLayout()
        actions.addWidget(self.save_button)
        actions.addWidget(self.load_button)
        actions.addStretch(1)
        actions.addWidget(self.play_button)
        actions.addWidget(close_button)

        self.info = QLabel()

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Playlist of {variant} macros — they play in order, one after another."))
        layout.addWidget(self.name_edit)
        layout.addWidget(self.list, 1)
        layout.addLayout(row1)
        layout.addLayout(row2)
        layout.addWidget(self.info)
        layout.addLayout(actions)

        self._refresh()

    # -- variant-aware macro loader ------------------------------------------
    def _loader(self, path: str) -> Macro:
        return Macro.load_for_variant(path, docked=self.playlist.docked)

    def _file_filter(self) -> str:
        if self.playlist.docked:
            return f"Studio Macro (*{DOCK_EXTENSION})"
        return f"Tiny Macro (*{CLASSIC_EXTENSION} *{LEGACY_CLASSIC_EXTENSION})"

    # -- list rendering -------------------------------------------------------
    def _refresh(self) -> None:
        self._loading = True
        row = self.list.currentRow()
        self.list.clear()
        for index, item in enumerate(self.playlist.items):
            missing = "" if Path(item.path).exists() else "  (missing)"
            suffix = f"  ×{item.repeat}" if item.repeat > 1 else ""
            entry = QListWidgetItem(f"{index + 1}. {item.display_name}{suffix}{missing}")
            entry.setData(Qt.ItemDataRole.UserRole, item.path)
            self.list.addItem(entry)
        if 0 <= row < self.list.count():
            self.list.setCurrentRow(row)
        elif self.list.count():
            self.list.setCurrentRow(min(row, self.list.count() - 1) if row >= 0 else 0)
        self._loading = False
        self._sync_selection_widgets()
        total_plays = sum(item.repeat for item in self.playlist.items)
        self.info.setText(f"{len(self.playlist.items)} macros · {total_plays} plays total")

    def _sync_selection_widgets(self) -> None:
        index = self.list.currentRow()
        has = 0 <= index < len(self.playlist.items)
        self.repeat_spin.setEnabled(has)
        self.remove_button.setEnabled(has)
        self.up_button.setEnabled(has and index > 0)
        self.down_button.setEnabled(has and index < len(self.playlist.items) - 1)
        if has:
            self._loading = True
            self.repeat_spin.setValue(self.playlist.items[index].repeat)
            self._loading = False

    # -- signal handlers ------------------------------------------------------
    def _on_name_changed(self, text: str) -> None:
        self.playlist.name = text.strip() or "Playlist"

    def _on_gap_changed(self, value: int) -> None:
        self.playlist.gap_ms = value

    def _on_row_changed(self, _row: int) -> None:
        if not self._loading:
            self._sync_selection_widgets()

    def _on_repeat_changed(self, value: int) -> None:
        if self._loading:
            return
        index = self.list.currentRow()
        if 0 <= index < len(self.playlist.items):
            self.playlist.set_repeat(index, value)
            self._refresh()

    # -- editing --------------------------------------------------------------
    def _add_path(self, path: str) -> None:
        try:
            self._loader(path)  # validate variant + readability before adding
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Cannot add", str(exc))
            return
        self.playlist.add(path)
        self._refresh()
        self.list.setCurrentRow(len(self.playlist.items) - 1)

    def _add_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Add Macro", "", self._file_filter())
        if path:
            self._add_path(path)

    def _add_from_library(self) -> None:
        dialog = LibraryDialog(self.library, self)
        dialog.open_requested.connect(self._add_path)  # reuse its picker; "Open" == add here
        dialog.play_requested.connect(self._add_path)
        dialog.exec()

    def _remove(self) -> None:
        index = self.list.currentRow()
        self.playlist.remove(index)
        self._refresh()

    def _move(self, direction: int) -> None:
        index = self.list.currentRow()
        new_index = self.playlist.move(index, direction)
        self._refresh()
        self.list.setCurrentRow(new_index)

    # -- files ----------------------------------------------------------------
    def _save(self) -> None:
        if not self.playlist.items:
            QMessageBox.information(self, "Empty playlist", "Add at least one macro first.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Playlist", "", f"Tiny Macro Playlist (*{PLAYLIST_EXTENSION})"
        )
        if not path:
            return
        if not path.endswith(PLAYLIST_EXTENSION):
            path += PLAYLIST_EXTENSION
        try:
            self.playlist.save(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Cannot save", str(exc))
            return
        self.path = Path(path)

    def _load(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Playlist", "", f"Tiny Macro Playlist (*{PLAYLIST_EXTENSION})"
        )
        if not path:
            return
        try:
            loaded = Playlist.load(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Cannot open", str(exc))
            return
        if loaded.docked != self.playlist.docked:
            wanted = "Studio" if self.playlist.docked else "classic"
            QMessageBox.warning(self, "Wrong variant", f"That playlist isn't for the {wanted} UI.")
            return
        self.playlist = loaded
        self.path = Path(path)
        self._loading = True
        self.name_edit.setText(self.playlist.name)
        self.gap_spin.setValue(self.playlist.gap_ms)
        self._loading = False
        self._refresh()

    # -- play -----------------------------------------------------------------
    def _play(self) -> None:
        if not self.playlist.items:
            QMessageBox.information(self, "Empty playlist", "Add at least one macro first.")
            return
        try:
            macro = self.playlist.build(self._loader)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Cannot play", str(exc))
            return
        self.play_requested.emit(macro)
