"""In-app documentation browser.

A simple categorised help window: a list of topics on the left and a content
pane on the right. The category structure is in place; the per-topic write-ups
are filled in later (each currently shows a placeholder).
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

# Ordered categories. Content is intentionally empty for now — the sections are
# the scaffold that the docs will be written into.
CATEGORIES: list[tuple[str, str]] = [
    ("Getting Started", "A quick overview of Tiny Macro."),
    ("Recording", "Capturing keyboard and mouse input."),
    ("Playback & Loops", "Replaying macros, looping, and speed."),
    ("Editor & Breakpoints", "Editing steps and live debugging."),
    ("Playlists", "Chaining macros to run back-to-back."),
    ("Studio (Docking)", "Docking a window and resolution-independent macros."),
    ("Image & Automation Steps", "Click-image, wait-pixel, wait-window, run."),
    ("Custom Themes", "Backgrounds, colours, and .tmactheme files."),
    ("Hotkeys", "Global shortcuts for record/play/stop and more."),
    ("Notifications & Webhooks", "Discord and generic webhook alerts."),
    ("Scheduler", "Time- and image-triggered runs."),
]


class DocsDialog(QDialog):
    """Categorised documentation viewer (placeholder content for now)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Documentation")
        self.resize(640, 460)

        self.list = QListWidget()
        self.list.setFixedWidth(210)
        for title, _ in CATEGORIES:
            self.list.addItem(title)
        self.list.currentRowChanged.connect(self._show)

        self.heading = QLabel()
        self.heading.setStyleSheet("font-size: 16px; font-weight: 700;")
        self.subtitle = QLabel()
        self.subtitle.setStyleSheet("color: palette(mid);")
        self.subtitle.setWordWrap(True)
        self.body = QLabel("Documentation for this section is coming soon.")
        self.body.setWordWrap(True)
        self.body.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.body.setStyleSheet("color: palette(mid);")

        content = QVBoxLayout()
        content.addWidget(self.heading)
        content.addWidget(self.subtitle)
        content.addSpacing(12)
        content.addWidget(self.body, 1)
        content_wrap = QWidget()
        content_wrap.setLayout(content)

        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        close_row = QHBoxLayout()
        close_row.addStretch(1)
        close_row.addWidget(close)

        right = QVBoxLayout()
        right.addWidget(content_wrap, 1)
        right.addLayout(close_row)

        row = QHBoxLayout()
        row.addWidget(self.list)
        right_wrap = QWidget()
        right_wrap.setLayout(right)
        row.addWidget(right_wrap, 1)

        root = QVBoxLayout(self)
        root.addLayout(row)

        self.list.setCurrentRow(0)

    def _show(self, index: int) -> None:
        if not (0 <= index < len(CATEGORIES)):
            return
        title, subtitle = CATEGORIES[index]
        self.heading.setText(title)
        self.subtitle.setText(subtitle)
        self.body.setText("Documentation for this section is coming soon.")
