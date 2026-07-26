from __future__ import annotations

import base64

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
    QWidget,
)
from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, Qt, QTime
from PyQt6.QtGui import QImage, QPixmap

from tinymacro.core.scheduler import Schedule, ScheduleStore
from tinymacro.gui.icons import get_icon
from tinymacro.gui.theme import icon_color


class SchedulerDialog(QDialog):
    """Create and manage schedules that run macros automatically."""

    def __init__(self, store: ScheduleStore, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Scheduler")
        self.resize(560, 460)
        self.store = store

        self.list = QListWidget()

        color = icon_color()
        self.macro_path = QLineEdit()
        self.macro_path.setPlaceholderText("Path to .tmacc file…")
        browse = QPushButton(get_icon("browse", color), "Browse…")
        browse.clicked.connect(self._browse)
        path_row = QHBoxLayout()
        path_row.addWidget(self.macro_path, 1)
        path_row.addWidget(browse)

        self.kind = QComboBox()
        self.kind.addItems(["interval", "daily", "once", "image"])
        self.kind.currentTextChanged.connect(self._update_fields)
        self.interval = QSpinBox()
        self.interval.setRange(1, 86_400)
        self.interval.setSuffix(" s")
        self.interval.setValue(3600)
        self.time_edit = QTimeEdit(QTime(9, 0))
        self.loop_count = QSpinBox()
        self.loop_count.setRange(0, 999_999)
        self.loop_count.setValue(1)
        self.loops_label = QLabel("Loops")
        self.speed = QDoubleSpinBox()
        self.speed.setRange(0.01, 100.0)
        self.speed.setValue(1.0)

        form_row = QHBoxLayout()
        form_row.addWidget(QLabel("When"))
        form_row.addWidget(self.kind)
        form_row.addWidget(self.interval)
        form_row.addWidget(self.time_edit)
        form_row.addWidget(self.loops_label)
        form_row.addWidget(self.loop_count)
        form_row.addWidget(QLabel("Speed"))
        form_row.addWidget(self.speed)

        # -- image-trigger controls (shown only for kind == "image") ----------
        self._image_b64 = ""
        self.image_button = QPushButton(get_icon("image", color), "Choose Image…")
        self.image_button.clicked.connect(self._choose_image)
        self.image_preview = QLabel()
        self.image_preview.setFixedSize(96, 60)
        self.image_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_preview.setStyleSheet("border: 1px solid palette(mid); border-radius: 4px;")
        self.confidence = QDoubleSpinBox()
        self.confidence.setRange(0.50, 1.00)
        self.confidence.setSingleStep(0.01)
        self.confidence.setDecimals(2)
        self.confidence.setValue(0.85)
        self.poll = QDoubleSpinBox()
        self.poll.setRange(0.2, 60.0)
        self.poll.setSingleStep(0.5)
        self.poll.setValue(2.0)
        self.poll.setSuffix(" s")

        image_row = QHBoxLayout()
        image_row.setContentsMargins(0, 0, 0, 0)
        image_row.addWidget(self.image_button)
        image_row.addWidget(self.image_preview)
        image_row.addWidget(QLabel("Confidence"))
        image_row.addWidget(self.confidence)
        image_row.addWidget(QLabel("Scan every"))
        image_row.addWidget(self.poll)
        image_row.addStretch(1)
        self.image_container = QWidget()
        self.image_container.setLayout(image_row)

        add = QPushButton(get_icon("add", color), "Add Schedule")
        add.setObjectName("primary")
        remove = QPushButton(get_icon("remove", color), "Remove Selected")
        close = QPushButton(get_icon("close", color), "Close")
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
        layout.addWidget(self.image_container)
        layout.addLayout(buttons)

        self._update_fields(self.kind.currentText())
        self._refresh()

    def _update_fields(self, kind: str) -> None:
        is_image = kind == "image"
        self.interval.setVisible(kind == "interval")
        self.time_edit.setVisible(kind in ("daily", "once"))
        self.image_container.setVisible(is_image)
        # For image triggers, "Loops" is instead the maximum number of fires.
        self.loops_label.setText("Max fires" if is_image else "Loops")
        self.loop_count.setToolTip(
            "0 = unlimited; otherwise stop after this many sightings" if is_image else ""
        )

    def _choose_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose target image", "", "Images (*.png *.jpg *.jpeg *.bmp);;All Files (*)"
        )
        if not path:
            return
        image = QImage(path)
        if image.isNull():
            QMessageBox.warning(self, "Invalid image", "That file could not be loaded as an image.")
            return
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, "PNG")
        buffer.close()
        self._image_b64 = base64.b64encode(bytes(data)).decode("ascii")
        pixmap = QPixmap.fromImage(image).scaled(
            92, 56, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        )
        self.image_preview.setPixmap(pixmap)

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose Macro", "", "Tiny Macro (*.tmacc *.tmacro)")
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
            elif schedule.kind == "image":
                fired = f" · {schedule.fire_count} fired" if schedule.fire_count else ""
                limit = "∞" if schedule.loop_count == 0 else schedule.loop_count
                self.list.addItem(
                    f"[{state}] {schedule.display_name} — on image "
                    f"(conf {schedule.confidence:.2f}, ≤{limit}){fired}"
                )
                continue
            else:
                when = f"once {schedule.run_at}"
            self.list.addItem(f"[{state}] {schedule.display_name} — {when} ×{schedule.loop_count}")

    def _add(self) -> None:
        path = self.macro_path.text().strip()
        if not path:
            QMessageBox.warning(self, "Missing macro", "Choose a macro file first.")
            return
        kind = self.kind.currentText()
        if kind == "image" and not self._image_b64:
            QMessageBox.warning(self, "Missing image", "Choose a target image for the trigger.")
            return
        schedule = Schedule(
            macro_path=path,
            kind=kind,  # type: ignore[arg-type]
            interval_seconds=self.interval.value(),
            at_hour=self.time_edit.time().hour(),
            at_minute=self.time_edit.time().minute(),
            loop_count=self.loop_count.value(),
            speed=self.speed.value(),
            image_b64=self._image_b64 if kind == "image" else "",
            confidence=self.confidence.value(),
            poll_seconds=self.poll.value(),
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
