"""Dialog to create or edit a click-image step.

Collects a target image plus its match/click options and hands back a fully
formed ``image`` :class:`MacroEvent`. The image is stored embedded (base64 PNG)
so the macro stays self-contained.
"""
from __future__ import annotations

import base64

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from tinymacro.core.events import DEFAULT_CONFIDENCE, DEFAULT_TIMEOUT_MS, MacroEvent
from tinymacro.gui.icons import get_icon
from tinymacro.gui.region_capture import capture_region_png
from tinymacro.gui.theme import icon_color

_THUMB_W, _THUMB_H = 220, 150


class ImageStepDialog(QDialog):
    """Configure a click-image step; :meth:`build_event` returns the result."""

    def __init__(self, event: MacroEvent | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Click-Image Step")
        self.setMinimumWidth(360)
        self._image_b64 = event.image_b64 if event and event.kind == "image" else ""
        color = icon_color()

        self.preview = QLabel("No image chosen")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setFixedSize(_THUMB_W, _THUMB_H)
        self.preview.setStyleSheet("border: 1px solid palette(mid); border-radius: 6px;")

        choose = QPushButton(get_icon("image", color), "Choose Image…")
        choose.clicked.connect(self._choose_image)
        grab = QPushButton(get_icon("crop", color), "Grab from Screen…")
        grab.setToolTip("Drag a rectangle on screen to capture the target image")
        grab.clicked.connect(self._grab_region)
        source_row = QHBoxLayout()
        source_row.addStretch(1)
        source_row.addWidget(choose)
        source_row.addWidget(grab)
        source_row.addStretch(1)

        self.confidence = QDoubleSpinBox()
        self.confidence.setRange(0.50, 1.00)
        self.confidence.setSingleStep(0.01)
        self.confidence.setDecimals(2)
        self.confidence.setValue(event.confidence if event and event.confidence else DEFAULT_CONFIDENCE)
        self.confidence.setToolTip("Higher = stricter match (fewer false hits, more misses)")

        self.timeout = QSpinBox()
        self.timeout.setRange(0, 3_600_000)
        self.timeout.setSingleStep(500)
        self.timeout.setSuffix(" ms")
        self.timeout.setValue(event.timeout_ms if event and event.timeout_ms else DEFAULT_TIMEOUT_MS)
        self.timeout.setToolTip("How long to keep searching before giving up")

        self.on_missing = QComboBox()
        self.on_missing.addItems(["fail", "skip", "continue"])
        if event:
            self.on_missing.setCurrentText(event.on_missing)
        self.on_missing.setToolTip(
            "If not found: fail (stop with error), skip (this step), continue (keep playing)"
        )

        self.click_button = QComboBox()
        self.click_button.addItems(["left", "right", "middle", "none"])
        if event and event.click_button:
            self.click_button.setCurrentText(event.click_button)
        self.click_button.setToolTip("Which button to click; 'none' waits for the image without clicking")

        self.offset_x = QSpinBox()
        self.offset_x.setRange(-9999, 9999)
        self.offset_x.setValue(event.offset_x if event else 0)
        self.offset_y = QSpinBox()
        self.offset_y.setRange(-9999, 9999)
        self.offset_y.setValue(event.offset_y if event else 0)
        offset_row = QHBoxLayout()
        offset_row.addWidget(QLabel("x"))
        offset_row.addWidget(self.offset_x)
        offset_row.addWidget(QLabel("y"))
        offset_row.addWidget(self.offset_y)
        offset_row.addStretch(1)

        self.grayscale = QCheckBox("Match in grayscale (faster, more tolerant)")
        self.grayscale.setChecked(event.grayscale if event else True)

        form = QFormLayout()
        form.addRow("Confidence", self.confidence)
        form.addRow("Timeout", self.timeout)
        form.addRow("If missing", self.on_missing)
        form.addRow("Click", self.click_button)
        form.addRow("Offset", offset_row)
        form.addRow("", self.grayscale)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.preview, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addLayout(source_row)
        layout.addLayout(form)
        layout.addWidget(self.buttons)

        self._refresh_preview()

    # -- image handling -------------------------------------------------------
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
        self._refresh_preview()

    def _grab_region(self) -> None:
        # Hide our own window so it isn't in the frozen screenshot.
        self.hide()
        try:
            b64 = capture_region_png(self)
        finally:
            self.show()
        if b64:
            self._image_b64 = b64
            self._refresh_preview()

    def _refresh_preview(self) -> None:
        has_image = bool(self._image_b64)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(has_image)
        if not has_image:
            self.preview.setText("No image chosen")
            self.preview.setPixmap(QPixmap())
            return
        image = QImage()
        image.loadFromData(base64.b64decode(self._image_b64), "PNG")
        pixmap = QPixmap.fromImage(image).scaled(
            _THUMB_W - 8,
            _THUMB_H - 8,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.preview.setPixmap(pixmap)

    # -- result ---------------------------------------------------------------
    def build_event(self, timestamp_ns: int = 0) -> MacroEvent:
        return MacroEvent.image_click(
            timestamp_ns,
            self._image_b64,
            confidence=self.confidence.value(),
            timeout_ms=self.timeout.value(),
            on_missing=self.on_missing.currentText(),  # type: ignore[arg-type]
            click_button=self.click_button.currentText(),
            offset_x=self.offset_x.value(),
            offset_y=self.offset_y.value(),
            grayscale=self.grayscale.isChecked(),
        )
