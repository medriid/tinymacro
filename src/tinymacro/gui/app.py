from __future__ import annotations

from pathlib import Path
import sys

from PyQt6.QtWidgets import QApplication, QMessageBox

from tinymacro.backends.factory import create_backend
from tinymacro.core.settings import Settings
from tinymacro.gui.main_window import MainWindow
from tinymacro.gui.theme import apply_theme


def run_app(initial_macro: Path | None = None, backend_name: str = "auto") -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Tiny Macro")
    settings = Settings.load()
    if backend_name != "auto":
        settings.backend = backend_name
    apply_theme(app, settings.theme)
    try:
        backend = create_backend(settings.backend)
    except Exception as exc:
        QMessageBox.critical(None, "Backend unavailable", str(exc))
        return 2
    window = MainWindow(settings, backend, initial_macro)
    window.show()
    return app.exec()
