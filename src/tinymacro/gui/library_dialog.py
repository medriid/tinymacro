from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from tinymacro.core.library import MacroLibrary


class LibraryDialog(QDialog):
    """Browse, search, favorite and launch macros from the local library."""

    open_requested = pyqtSignal(str)
    play_requested = pyqtSignal(str)

    def __init__(self, library: MacroLibrary, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Macro Library")
        self.resize(560, 460)
        self.library = library

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search by name, tag or path…")
        self.favorites_only = QCheckBox("Favorites only")
        self.search.textChanged.connect(self._refresh)
        self.favorites_only.toggled.connect(self._refresh)

        top = QHBoxLayout()
        top.addWidget(self.search, 1)
        top.addWidget(self.favorites_only)

        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda *_: self._open())
        self.info = QLabel()

        self.open_button = QPushButton("Open")
        self.play_button = QPushButton("Play")
        self.play_button.setObjectName("primary")
        self.favorite_button = QPushButton("Toggle Favorite")
        self.add_button = QPushButton("Add File…")
        self.remove_button = QPushButton("Remove")
        self.prune_button = QPushButton("Prune Missing")
        close_button = QPushButton("Close")

        buttons = QHBoxLayout()
        for widget in (
            self.open_button,
            self.play_button,
            self.favorite_button,
            self.add_button,
            self.remove_button,
            self.prune_button,
        ):
            buttons.addWidget(widget)
        buttons.addStretch(1)
        buttons.addWidget(close_button)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.list, 1)
        layout.addWidget(self.info)
        layout.addLayout(buttons)

        self.open_button.clicked.connect(self._open)
        self.play_button.clicked.connect(self._play)
        self.favorite_button.clicked.connect(self._toggle_favorite)
        self.add_button.clicked.connect(self._add_file)
        self.remove_button.clicked.connect(self._remove)
        self.prune_button.clicked.connect(self._prune)
        close_button.clicked.connect(self.accept)
        self._refresh()

    def _selected_path(self) -> str | None:
        item = self.list.currentItem()
        if not item:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def _refresh(self) -> None:
        self.list.clear()
        entries = self.library.search(self.search.text(), favorites_only=self.favorites_only.isChecked())
        for entry in entries:
            star = "★ " if entry.favorite else ""
            missing = "" if entry.exists else "  (missing)"
            tags = f"  [{', '.join(entry.tags)}]" if entry.tags else ""
            runs = f"  · {entry.run_count} runs" if entry.run_count else ""
            item = QListWidgetItem(f"{star}{entry.display_name}{tags}{runs}{missing}")
            item.setData(Qt.ItemDataRole.UserRole, entry.path)
            self.list.addItem(item)
        self.info.setText(f"{len(entries)} shown · {len(self.library.entries)} in library")

    def _open(self) -> None:
        path = self._selected_path()
        if path:
            self.open_requested.emit(path)
            self.accept()

    def _play(self) -> None:
        path = self._selected_path()
        if path:
            self.play_requested.emit(path)

    def _toggle_favorite(self) -> None:
        path = self._selected_path()
        if path:
            self.library.toggle_favorite(path)
            self.library.save()
            self._refresh()

    def _add_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Add Macro", "", "Tiny Macro (*.tmacro);;All Files (*)")
        if path:
            self.library.add(path, name=Path(path).stem)
            self.library.save()
            self._refresh()

    def _remove(self) -> None:
        path = self._selected_path()
        if path:
            self.library.remove(path)
            self.library.save()
            self._refresh()

    def _prune(self) -> None:
        self.library.prune_missing()
        self.library.save()
        self._refresh()
