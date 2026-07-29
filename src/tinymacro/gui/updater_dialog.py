from __future__ import annotations

from pathlib import Path
import tempfile

from PyQt6.QtCore import QObject, QThread, QTimer, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from tinymacro import __version__
from tinymacro.core import updater
from tinymacro.core.updater import UpdateInfo


class _CheckWorker(QObject):
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)

    def run(self) -> None:
        try:
            self.finished.emit(updater.check_for_update())
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class _DownloadWorker(QObject):
    progress = pyqtSignal(int, int)
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, info: UpdateInfo) -> None:
        super().__init__()
        self.info = info
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        try:
            stage = Path(tempfile.mkdtemp(prefix="tinymacro-update-"))
            zip_path = stage / self.info.asset_name
            updater.download(
                self.info.url,
                zip_path,
                progress=lambda done, total: self.progress.emit(done, total),
                should_cancel=lambda: self._cancelled,
            )
            new_app = updater.extract_zip(zip_path, stage / "extracted")
            self.finished.emit(new_app)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class UpdateDialog(QDialog):
    """Check GitHub Releases, download an update, and restart into it."""

    _SPINNER = ("|", "/", "-", "\\")

    def __init__(self, parent=None, *, silent_no_update: bool = False) -> None:
        super().__init__(parent)
        self.setWindowTitle("Tiny Macro Updates")
        self.resize(520, 360)
        self._silent_no_update = silent_no_update
        self._info: UpdateInfo | None = None
        self._new_app_dir: Path | None = None
        self._check_worker: _CheckWorker | None = None
        self._check_thread: QThread | None = None
        self._download_thread: QThread | None = None
        self._download_worker: _DownloadWorker | None = None
        self._spin_index = 0

        self.spinner = QLabel("")
        self.spinner.setFixedWidth(20)
        self.spinner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status = QLabel(f"Current version: {__version__}")
        self.status.setWordWrap(True)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.notes = QTextEdit()
        self.notes.setReadOnly(True)
        self.notes.setPlaceholderText("Release notes appear here when an update is found.")

        top = QHBoxLayout()
        top.addWidget(self.spinner)
        top.addWidget(self.status, 1)

        self.check_btn = QPushButton("Check Again")
        self.download_btn = QPushButton("Download Update")
        self.restart_btn = QPushButton("Restart and Update")
        self.close_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_btn = self.close_box.button(QDialogButtonBox.StandardButton.Close)

        actions = QHBoxLayout()
        actions.addWidget(self.check_btn)
        actions.addWidget(self.download_btn)
        actions.addWidget(self.restart_btn)
        actions.addStretch(1)
        actions.addWidget(close_btn)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.progress)
        layout.addWidget(self.notes, 1)
        layout.addLayout(actions)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick_spinner)
        self.check_btn.clicked.connect(self.start_check)
        self.download_btn.clicked.connect(self.start_download)
        self.restart_btn.clicked.connect(self.apply_and_restart)
        self.close_box.rejected.connect(self.reject)

        self._set_idle()

    def start_check(self) -> None:
        if not updater.updates_supported():
            self.status.setText("Updates are available in packaged release builds.")
            self.notes.setPlainText(
                "This source/dev run cannot replace itself. Build or run the released "
                "Tiny Macro app to use automatic updates."
            )
            if self._silent_no_update:
                self.deleteLater()
            return
        self._set_busy("Checking GitHub for releases...")
        self._info = None
        worker = _CheckWorker()
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._check_finished)
        worker.failed.connect(self._check_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self._check_worker = worker
        self._check_thread = thread
        thread.start()

    def start_download(self) -> None:
        if self._info is None:
            return
        self._set_busy(f"Downloading {self._info.asset_name}...")
        self.progress.setValue(0)
        worker = _DownloadWorker(self._info)
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._download_progress)
        worker.finished.connect(self._download_finished)
        worker.failed.connect(self._download_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self._download_worker = worker
        self._download_thread = thread
        thread.start()

    def apply_and_restart(self) -> None:
        if self._new_app_dir is None:
            return
        answer = QMessageBox.question(
            self,
            "Restart Tiny Macro",
            "Tiny Macro will close, replace the app files, and open again.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        parent = self.parent()
        persist = getattr(parent, "_persist", None)
        if callable(persist):
            persist()
        updater.apply_update_and_relaunch(self._new_app_dir)

    def reject(self) -> None:
        if self._download_worker is not None:
            self._download_worker.cancel()
        super().reject()

    def _check_finished(self, info: UpdateInfo | None) -> None:
        self._set_idle()
        if info is None:
            self.status.setText(f"Tiny Macro {__version__} is up to date.")
            self.notes.clear()
            if self._silent_no_update:
                self.deleteLater()
            return
        self._info = info
        self._silent_no_update = False
        self.show()
        size = _format_bytes(info.size) if info.size else "unknown size"
        self.status.setText(f"Tiny Macro {info.version} is available ({size}).")
        self.notes.setPlainText(info.notes or "No release notes were provided.")
        self.download_btn.setEnabled(True)

    def _check_failed(self, message: str) -> None:
        self._set_idle()
        self.status.setText("Could not check for updates.")
        self.notes.setPlainText(message)
        if self._silent_no_update:
            self.deleteLater()

    def _download_progress(self, done: int, total: int) -> None:
        if total > 0:
            self.progress.setRange(0, 100)
            self.progress.setValue(min(100, round(done * 100 / total)))
            self.status.setText(f"Downloading update... {_format_bytes(done)} / {_format_bytes(total)}")
        else:
            self.progress.setRange(0, 0)
            self.status.setText(f"Downloading update... {_format_bytes(done)}")

    def _download_finished(self, new_app_dir: Path) -> None:
        self._set_idle()
        self._new_app_dir = Path(new_app_dir)
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.status.setText("Update downloaded. Restart to apply it.")
        self.download_btn.setEnabled(False)
        self.restart_btn.setEnabled(True)

    def _download_failed(self, message: str) -> None:
        self._set_idle()
        self.status.setText("Download failed.")
        self.notes.setPlainText(message)
        self.download_btn.setEnabled(self._info is not None)

    def _set_busy(self, text: str) -> None:
        self.status.setText(text)
        self.check_btn.setEnabled(False)
        self.download_btn.setEnabled(False)
        self.restart_btn.setEnabled(False)
        self.progress.setRange(0, 0)
        self._timer.start(120)

    def _set_idle(self) -> None:
        self._timer.stop()
        self.spinner.setText("")
        self.progress.setRange(0, 100)
        self.check_btn.setEnabled(True)
        self.download_btn.setEnabled(False)
        self.restart_btn.setEnabled(False)

    def _tick_spinner(self) -> None:
        self.spinner.setText(self._SPINNER[self._spin_index % len(self._SPINNER)])
        self._spin_index += 1


def show_update_dialog(parent, *, silent: bool = False) -> UpdateDialog:
    dialog = UpdateDialog(parent, silent_no_update=silent)
    setattr(parent, "_update_dialog", dialog)
    if not silent:
        dialog.show()
    QTimer.singleShot(0, dialog.start_check)
    return dialog


def _format_bytes(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size} B"
