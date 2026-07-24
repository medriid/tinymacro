from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from tinymacro.core.logging_setup import ring_buffer


class LogDialog(QDialog):
    """Read-only viewer over the in-memory log ring buffer."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Log Viewer")
        self.resize(680, 420)

        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

        refresh = QPushButton("Refresh")
        clear = QPushButton("Clear")
        close = QPushButton("Close")
        refresh.clicked.connect(self.refresh)
        clear.clicked.connect(self._clear)
        close.clicked.connect(self.accept)

        buttons = QHBoxLayout()
        buttons.addWidget(refresh)
        buttons.addWidget(clear)
        buttons.addStretch(1)
        buttons.addWidget(close)

        layout = QVBoxLayout(self)
        layout.addWidget(self.view, 1)
        layout.addLayout(buttons)
        self.refresh()

    def refresh(self) -> None:
        lines = [record.format() for record in ring_buffer().snapshot()]
        self.view.setPlainText("\n".join(lines))
        self.view.verticalScrollBar().setValue(self.view.verticalScrollBar().maximum())

    def _clear(self) -> None:
        ring_buffer().clear()
        self.refresh()
