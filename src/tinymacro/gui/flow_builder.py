"""Visual flow builder — the playlist creator.

A node canvas where each macro is a draggable card wired into a sequence, and each
card can carry an **image gate** ("wait until this appears before playing"). It
edits a :class:`~tinymacro.core.playlist.Playlist`, plays the stitched result, and
exports a portable, optionally-encrypted **bundle** that runs on any machine.

v1 is a linear flow (Start → macro → macro → …) with per-node gates and repeats;
branching is future work. The nodes are freely draggable for layout, but the run
order is the playlist order (edit it with Move Up/Down).
"""
from __future__ import annotations

import base64
from pathlib import Path

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QImage, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QGraphicsItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from tinymacro.core import bundle
from tinymacro.core.library import MacroLibrary
from tinymacro.core.macro import CLASSIC_EXTENSION, DOCK_EXTENSION, LEGACY_CLASSIC_EXTENSION, Macro
from tinymacro.core.playlist import PLAYLIST_EXTENSION, Playlist, PlaylistItem
from tinymacro.gui.icons import get_icon
from tinymacro.gui.region_capture import capture_region_png
from tinymacro.gui.theme import current_colors, icon_color

_NODE_W = 220
_NODE_H = 70


class _FlowNode(QGraphicsItem):
    """A draggable card for one playlist item (or the Start marker)."""

    def __init__(self, index: int, on_moved) -> None:
        super().__init__()
        self.index = index          # -1 for the Start node
        self._on_moved = on_moved
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.title = "Start"
        self.subtitle = ""
        self.gate_pixmap: QPixmap | None = None

    def boundingRect(self) -> QRectF:  # noqa: N802
        return QRectF(0, 0, _NODE_W, _NODE_H)

    def center(self) -> QPointF:
        return self.pos() + QPointF(_NODE_W / 2, _NODE_H / 2)

    def itemChange(self, change, value):  # noqa: N802
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and self._on_moved:
            self._on_moved()
        return super().itemChange(change, value)

    def paint(self, painter: QPainter, _option, _widget=None) -> None:  # noqa: N802
        c = current_colors()
        panel = QColor(c.elevated if c else "#242424")
        border = QColor(c.accent if (c and self.isSelected()) else (c.border if c else "#3a3a3a"))
        text = QColor(c.text if c else "#f0f0f0")
        muted = QColor(c.muted if c else "#a0a0a0")
        start = self.index < 0
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(1, 1, _NODE_W - 2, _NODE_H - 2), 10, 10)
        painter.fillPath(path, QBrush(panel if not start else QColor(c.accent if c else "#ffffff")))
        painter.setPen(QPen(border, 2 if self.isSelected() else 1))
        painter.drawPath(path)
        if start:
            painter.setPen(QColor(c.accent_text if c else "#151515"))
            painter.drawText(QRectF(0, 0, _NODE_W, _NODE_H), Qt.AlignmentFlag.AlignCenter, "▶  Start")
            return
        # Gate thumbnail (left), title + subtitle (right).
        x = 12
        if self.gate_pixmap is not None:
            painter.drawPixmap(int(x), int(_NODE_H / 2 - 20), self.gate_pixmap.scaled(
                40, 40, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            painter.setPen(QColor("#28c76f"))
            painter.drawText(QRectF(x, _NODE_H - 20, 40, 16), Qt.AlignmentFlag.AlignHCenter, "gate")
            x += 48
        painter.setPen(text)
        f = painter.font()
        f.setBold(True)
        painter.setFont(f)
        painter.drawText(QRectF(x, 12, _NODE_W - x - 10, 20), Qt.AlignmentFlag.AlignLeft, self.title)
        f.setBold(False)
        painter.setFont(f)
        painter.setPen(muted)
        painter.drawText(QRectF(x, 36, _NODE_W - x - 10, 20), Qt.AlignmentFlag.AlignLeft, self.subtitle)


class FlowBuilderDialog(QDialog):
    """Assemble, play and export an image-gated playlist visually."""

    play_requested = pyqtSignal(object)  # the stitched Macro

    def __init__(self, library: MacroLibrary, docked: bool, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Flow Builder")
        self.resize(880, 560)
        self.library = library
        self.playlist = Playlist(docked=docked)
        self._nodes: list[_FlowNode] = []
        self._edges: list = []
        self._building = False

        color = icon_color()
        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.scene.selectionChanged.connect(self._on_selection)

        # Left toolbar.
        tools = QVBoxLayout()
        for text, icon, slot in (
            ("Add Macro…", "add_file", self._add_file),
            ("Add from Library…", "library", self._add_from_library),
            ("Move Up", "chevron_up", lambda: self._move(-1)),
            ("Move Down", "chevron_down", lambda: self._move(1)),
            ("Remove", "remove", self._remove),
        ):
            b = QPushButton(get_icon(icon, color), " " + text)
            b.clicked.connect(slot)
            tools.addWidget(b)
        tools.addSpacing(10)
        tools.addWidget(QLabel("Selected node"))
        self.repeat_spin = QSpinBox()
        self.repeat_spin.setRange(1, 9999)
        self.repeat_spin.setPrefix("Repeat ×")
        self.repeat_spin.setEnabled(False)
        self.repeat_spin.valueChanged.connect(self._on_repeat)
        tools.addWidget(self.repeat_spin)
        self.gate_btn = QPushButton(get_icon("crop", color), " Set Gate (snip)…")
        self.gate_btn.setToolTip("Wait for this image on screen before this macro plays")
        self.gate_btn.clicked.connect(self._set_gate)
        self.gate_btn.setEnabled(False)
        self.gate_clear_btn = QPushButton(get_icon("clear", color), " Clear Gate")
        self.gate_clear_btn.clicked.connect(self._clear_gate)
        self.gate_clear_btn.setEnabled(False)
        self.gate_timeout = QSpinBox()
        self.gate_timeout.setRange(0, 600_000)
        self.gate_timeout.setSuffix(" ms gate wait")
        self.gate_timeout.setEnabled(False)
        self.gate_timeout.valueChanged.connect(self._on_gate_timeout)
        tools.addWidget(self.gate_btn)
        tools.addWidget(self.gate_timeout)
        tools.addWidget(self.gate_clear_btn)
        tools.addStretch(1)
        self.gap_spin = QSpinBox()
        self.gap_spin.setRange(0, 600_000)
        self.gap_spin.setValue(self.playlist.gap_ms)
        self.gap_spin.setSuffix(" ms gap")
        self.gap_spin.valueChanged.connect(lambda v: setattr(self.playlist, "gap_ms", v))
        tools.addWidget(self.gap_spin)
        tools_wrap = QWidget()
        tools_wrap.setLayout(tools)
        tools_wrap.setFixedWidth(210)

        # Bottom actions.
        actions = QHBoxLayout()
        for text, icon, slot in (
            ("Import Bundle…", "open", self._import_bundle),
            ("Export Bundle…", "save", self._export_bundle),
            ("Load Playlist…", "open", self._load_playlist),
            ("Save Playlist…", "save", self._save_playlist),
        ):
            b = QPushButton(get_icon(icon, color), " " + text)
            b.clicked.connect(slot)
            actions.addWidget(b)
        actions.addStretch(1)
        self.play_btn = QPushButton(get_icon("play", color), " Play")
        self.play_btn.setObjectName("primary")
        self.play_btn.clicked.connect(self._play)
        close = QPushButton(get_icon("close", color), " Close")
        close.clicked.connect(self.accept)
        actions.addWidget(self.play_btn)
        actions.addWidget(close)

        top = QHBoxLayout()
        top.addWidget(tools_wrap)
        top.addWidget(self.view, 1)
        root = QVBoxLayout(self)
        variant = "Studio (.tmacd)" if docked else "classic (.tmacc)"
        root.addWidget(QLabel(f"Build a flow of {variant} macros. Add a gate to wait for an image before a macro plays."))
        root.addLayout(top, 1)
        root.addLayout(actions)

        self._rebuild_scene()

    # -- variant-aware loader -------------------------------------------------
    def _loader(self, path: str) -> Macro:
        return Macro.load_for_variant(path, docked=self.playlist.docked)

    def _file_filter(self) -> str:
        if self.playlist.docked:
            return f"Studio Macro (*{DOCK_EXTENSION})"
        return f"Tiny Macro (*{CLASSIC_EXTENSION} *{LEGACY_CLASSIC_EXTENSION})"

    # -- scene ----------------------------------------------------------------
    def _rebuild_scene(self) -> None:
        self._building = True  # suppress edge redraws while items are repositioned
        self.scene.clear()     # deletes all nodes + edge lines
        self._edges = []       # their C++ objects are gone; drop stale refs
        self._nodes = []
        start = _FlowNode(-1, self._redraw_edges)
        start.setPos(40, 30)
        self.scene.addItem(start)
        self._nodes.append(start)
        y = 30 + _NODE_H + 40
        for i, item in enumerate(self.playlist.items):
            node = _FlowNode(i, self._redraw_edges)
            node.title = item.display_name
            node.subtitle = f"×{item.repeat}" + ("   ·  gated" if item.has_gate else "")
            if item.has_gate:
                node.gate_pixmap = _pixmap_from_b64(item.gate_image)
            node.setPos(40, y)
            self.scene.addItem(node)
            self._nodes.append(node)
            y += _NODE_H + 40
        self._building = False
        self._redraw_edges()
        self.scene.setSceneRect(self.scene.itemsBoundingRect().adjusted(-40, -40, 40, 60))
        self._on_selection()

    def _redraw_edges(self) -> None:
        if self._building:
            return
        for line in self._edges:
            try:
                self.scene.removeItem(line)
            except RuntimeError:
                pass  # already removed by a scene.clear()
        self._edges = []
        c = current_colors()
        pen = QPen(QColor(c.muted if c else "#888"), 2)
        for a, b in zip(self._nodes, self._nodes[1:]):
            p1, p2 = a.center(), b.center()
            line = self.scene.addLine(p1.x(), p1.y(), p2.x(), p2.y(), pen)
            line.setZValue(-1)
            self._edges.append(line)

    def _selected_index(self) -> int:
        for node in self.scene.selectedItems():
            if isinstance(node, _FlowNode) and node.index >= 0:
                return node.index
        return -1

    def _on_selection(self) -> None:
        index = self._selected_index()
        has = 0 <= index < len(self.playlist.items)
        self.repeat_spin.setEnabled(has)
        self.gate_btn.setEnabled(has)
        self.gate_timeout.setEnabled(has)
        self.gate_clear_btn.setEnabled(has and self.playlist.items[index].has_gate)
        if has:
            item = self.playlist.items[index]
            self.repeat_spin.blockSignals(True)
            self.repeat_spin.setValue(item.repeat)
            self.repeat_spin.blockSignals(False)
            self.gate_timeout.blockSignals(True)
            self.gate_timeout.setValue(item.gate_timeout_ms)
            self.gate_timeout.blockSignals(False)

    # -- editing --------------------------------------------------------------
    def _add_path(self, path: str) -> None:
        try:
            self._loader(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Cannot add", str(exc))
            return
        self.playlist.add(path)
        self._rebuild_scene()

    def _add_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Add Macro", "", self._file_filter())
        if path:
            self._add_path(path)

    def _add_from_library(self) -> None:
        from tinymacro.gui.library_dialog import LibraryDialog

        dialog = LibraryDialog(self.library, self)
        dialog.open_requested.connect(self._add_path)
        dialog.play_requested.connect(self._add_path)
        dialog.exec()

    def _move(self, direction: int) -> None:
        index = self._selected_index()
        if index < 0:
            return
        new_index = self.playlist.move(index, direction)
        self._rebuild_scene()
        if 1 + new_index < len(self._nodes):
            self._nodes[1 + new_index].setSelected(True)

    def _remove(self) -> None:
        index = self._selected_index()
        if index >= 0:
            self.playlist.remove(index)
            self._rebuild_scene()

    def _on_repeat(self, value: int) -> None:
        index = self._selected_index()
        if index >= 0:
            self.playlist.set_repeat(index, value)
            self._rebuild_scene()

    def _on_gate_timeout(self, value: int) -> None:
        index = self._selected_index()
        if index >= 0 and self.playlist.items[index].has_gate:
            self.playlist.items[index].gate_timeout_ms = value

    def _set_gate(self) -> None:
        index = self._selected_index()
        if index < 0:
            return
        image = capture_region_png(self)
        if not image:
            return
        self.playlist.set_gate(index, image)
        self._rebuild_scene()
        self._nodes[1 + index].setSelected(True)

    def _clear_gate(self) -> None:
        index = self._selected_index()
        if index >= 0:
            self.playlist.clear_gate(index)
            self._rebuild_scene()

    # -- play / files ---------------------------------------------------------
    def _play(self) -> None:
        if not self.playlist.items:
            QMessageBox.information(self, "Empty", "Add at least one macro first.")
            return
        try:
            macro = self.playlist.build(self._loader)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Cannot play", str(exc))
            return
        self.play_requested.emit(macro)

    def _save_playlist(self) -> None:
        if not self.playlist.items:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save Playlist", "", f"Tiny Macro Playlist (*{PLAYLIST_EXTENSION})")
        if not path:
            return
        if not path.endswith(PLAYLIST_EXTENSION):
            path += PLAYLIST_EXTENSION
        try:
            self.playlist.save(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Cannot save", str(exc))

    def _load_playlist(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Load Playlist", "", f"Tiny Macro Playlist (*{PLAYLIST_EXTENSION})")
        if not path:
            return
        try:
            loaded = Playlist.load(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Cannot open", str(exc))
            return
        if loaded.docked != self.playlist.docked:
            QMessageBox.warning(self, "Wrong variant", "That playlist isn't for this UI.")
            return
        self.playlist = loaded
        self.gap_spin.setValue(self.playlist.gap_ms)
        self._rebuild_scene()

    def _export_bundle(self) -> None:
        if not self.playlist.items:
            QMessageBox.information(self, "Empty", "Add at least one macro first.")
            return
        # Choose protection.
        options = ["Open (encrypted, no password)", "Password protected"]
        if not bundle.encryption_available():
            options = ["Plain (this build can't encrypt)"]
        choice, ok = QInputDialog.getItem(self, "Export Bundle", "Protection:", options, 0, False)
        if not ok:
            return
        password = None
        encrypt = bundle.encryption_available()
        if encrypt and choice.startswith("Password"):
            password, ok = QInputDialog.getText(self, "Password", "Bundle password:", QLineEdit.EchoMode.Password)
            if not ok or not password:
                return
        path, _ = QFileDialog.getSaveFileName(self, "Export Bundle", "", f"Tiny Macro Bundle (*{bundle.BUNDLE_EXTENSION})")
        if not path:
            return
        if not path.endswith(bundle.BUNDLE_EXTENSION):
            path += bundle.BUNDLE_EXTENSION
        try:
            bundle.save(self.playlist, self._loader, path, encrypt=encrypt, password=password)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Export failed", str(exc))
            return
        QMessageBox.information(self, "Exported", f"Saved {Path(path).name}")

    def _import_bundle(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import Bundle", "", f"Tiny Macro Bundle (*{bundle.BUNDLE_EXTENSION})")
        if not path:
            return
        try:
            blob = Path(path).read_bytes()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Cannot open", str(exc))
            return
        password = None
        if bundle.needs_password(blob):
            password, ok = QInputDialog.getText(self, "Password", "Bundle password:", QLineEdit.EchoMode.Password)
            if not ok:
                return
        try:
            playlist, macros = bundle.unpack(blob, password)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Import failed", str(exc))
            return
        if playlist.docked != self.playlist.docked:
            QMessageBox.warning(self, "Wrong variant", "That bundle isn't for this UI.")
            return
        # Materialise the embedded macros to a temp folder so items reference real
        # files the rest of the app (play/save) can use.
        target = Path.home() / ".config" / "tiny-macro" / "bundles" / _safe(playlist.name)
        target.mkdir(parents=True, exist_ok=True)
        ext = DOCK_EXTENSION if playlist.docked else CLASSIC_EXTENSION
        for item in playlist.items:
            macro = macros.get(item.path)
            if macro is None:
                continue
            out = target / f"{item.path}{ext}"
            macro.save(out)
            item.path = str(out)
        self.playlist = playlist
        self.gap_spin.setValue(self.playlist.gap_ms)
        self._rebuild_scene()
        QMessageBox.information(self, "Imported", f"Loaded {len(playlist.items)} macros from the bundle.")


def _pixmap_from_b64(b64: str) -> QPixmap | None:
    try:
        raw = base64.b64decode(b64)
    except Exception:  # noqa: BLE001
        return None
    image = QImage()
    if not image.loadFromData(raw):
        return None
    return QPixmap.fromImage(image)


def _safe(name: str) -> str:
    import re

    return re.sub(r"[^a-zA-Z0-9._-]+", "-", name.strip()) or "bundle"
