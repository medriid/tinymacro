from __future__ import annotations

from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTimeEdit,
    QVBoxLayout,
)
from PyQt6.QtCore import QTime

from tinymacro.core.scheduler import Schedule, ScheduleStore


class SchedulerDialog(QDialog):
    """Create and manage schedules that run macros automatically."""

    def __init__(self, store: ScheduleStore, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Scheduler")
        self.resize(560, 460)
        self.store = store

        self.list = QListWidget()

        self.macro_path = QLineEdit()
        self.macro_path.setPlaceholderText("Path to .tmacro file…")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        path_row = QHBoxLayout()
        path_row.addWidget(self.macro_path, 1)
        path_row.addWidget(browse)

        self.kind = QComboBox()
        self.kind.addItems(["interval", "daily", "once"])
        self.kind.currentTextChanged.connect(self._update_fields)
        self.interval = QSpinBox()
        self.interval.setRange(1, 86_400)
        self.interval.setSuffix(" s")
        self.interval.setValue(3600)
        self.time_edit = QTimeEdit(QTime(9, 0))
        self.loop_count = QSpinBox()
        self.loop_count.setRange(0, 999_999)
        self.loop_count.setValue(1)
        self.speed = QDoubleSpinBox()
        self.speed.setRange(0.01, 100.0)
        self.speed.setValue(1.0)

        form_row = QHBoxLayout()
        form_row.addWidget(QLabel("When"))
        form_row.addWidget(self.kind)
        form_row.addWidget(self.interval)
        form_row.addWidget(self.time_edit)
        form_row.addWidget(QLabel("Loops"))
        form_row.addWidget(self.loop_count)
        form_row.addWidget(QLabel("Speed"))
        form_row.addWidget(self.speed)

        add = QPushButton("Add Schedule")
        add.setObjectName("primary")
        remove = QPushButton("Remove Selected")
        close = QPushButton("Close")
        add.clicked.connect(self._add)
        remove.clicked.connect(self._remove)
        close.clicked.connect(self.accept)
        buttons = QHBoxLayout()
        buttons.addWidget(add)
        buttons.addWidget(remove)
        buttons.addStretch(1)
        buttons.addWidget(close)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Existing schedules"))
        layout.addWidget(self.list, 1)
        layout.addLayout(path_row)
        layout.addLayout(form_row)
        layout.addLayout(buttons)

        self._update_fields(self.kind.currentText())
        self._refresh()

    def _update_fields(self, kind: str) -> None:
        self.interval.setVisible(kind == "interval")
        self.time_edit.setVisible(kind in ("daily", "once"))

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose Macro", "", "Tiny Macro (*.tmacro)")
        if path:
            self.macro_path.setText(path)

    def _refresh(self) -> None:
        self.list.clear()
        for schedule in self.store.schedules:
            state = "on" if schedule.enabled else "off"
            if schedule.kind == "interval":
                when = f"every {schedule.interval_seconds}s"
            elif schedule.kind == "daily":
                when = f"daily {schedule.at_hour:02d}:{schedule.at_minute:02d}"
            else:
                when = f"once {schedule.run_at}"
            self.list.addItem(f"[{state}] {schedule.display_name} — {when} ×{schedule.loop_count}")

    def _add(self) -> None:
        path = self.macro_path.text().strip()
        if not path:
            QMessageBox.warning(self, "Missing macro", "Choose a .tmacro file first.")
            return
        kind = self.kind.currentText()
        schedule = Schedule(
            macro_path=path,
            kind=kind,  # type: ignore[arg-type]
            interval_seconds=self.interval.value(),
            at_hour=self.time_edit.time().hour(),
            at_minute=self.time_edit.time().minute(),
            loop_count=self.loop_count.value(),
            speed=self.speed.value(),
        )
        if kind == "once":
            from datetime import datetime, timedelta

            target = datetime.now().replace(
                hour=self.time_edit.time().hour(),
                minute=self.time_edit.time().minute(),
                second=0,
                microsecond=0,
            )
            if target <= datetime.now():
                target += timedelta(days=1)
            schedule.run_at = target.isoformat()
        try:
            self.store.add(schedule)
            self.store.save()
        except Exception as exc:
            QMessageBox.warning(self, "Invalid schedule", str(exc))
            return
        self._refresh()

    def _remove(self) -> None:
        row = self.list.currentRow()
        if row >= 0:
            self.store.remove(row)
            self.store.save()
            self._refresh()
