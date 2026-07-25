"""Dialog for choosing which window to dock in the Studio UI."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)

from tinymacro.backends.base import InputBackend


class WindowPicker(QDialog):
    """Lists the backend's top-level windows; :attr:`selected` is the chosen handle."""

    def __init__(self, backend: InputBackend, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Select a window to dock")
        self.setMinimumSize(420, 360)
        self.selected: int | None = None
        self.selected_title: str = ""

        self.list = QListWidget()
        for handle, title in backend.list_windows():
            item = QListWidgetItem(title)
            item.setData(0x0100, handle)  # Qt.UserRole
            item.setData(0x0101, title)   # Qt.UserRole + 1 kept for convenience
            self.list.addItem(item)
        self.list.itemDoubleClicked.connect(lambda *_: self.accept())

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Pick the app window to dock into the Studio frame:"))
        layout.addWidget(self.list, 1)
        layout.addWidget(buttons)

    def accept(self) -> None:
        item = self.list.currentItem()
        if item is not None:
            self.selected = int(item.data(0x0100))
            self.selected_title = str(item.data(0x0101) or item.text())
        super().accept()
