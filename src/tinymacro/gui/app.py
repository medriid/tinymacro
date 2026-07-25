from __future__ import annotations

import logging
from pathlib import Path
import sys

from PyQt6.QtWidgets import QApplication, QMessageBox

from tinymacro.backends.factory import create_backend
from tinymacro.core.library import MacroLibrary
from tinymacro.core.logging_setup import configure_logging
from tinymacro.core.profiles import ProfileStore
from tinymacro.core.scheduler import ScheduleStore
from tinymacro.gui.icons import app_icon
from tinymacro.gui.main_window import MainWindow
from tinymacro.gui.theme import apply_theme


def run_app(initial_macro: Path | None = None, backend_name: str = "auto") -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Tiny Macro")
    app.setWindowIcon(app_icon())

    profiles = ProfileStore.load()
    settings = profiles.current
    if backend_name != "auto":
        settings.backend = backend_name

    configure_logging(
        level=logging.DEBUG if settings.debug_mode else logging.INFO,
        to_file=settings.log_to_file,
    )
    library = MacroLibrary.load()
    schedules = ScheduleStore.load()

    colors = apply_theme(app, settings)
    try:
        backend = create_backend(settings.backend)
    except Exception as exc:
        QMessageBox.critical(None, "Backend unavailable", str(exc))
        return 2

    window = MainWindow(
        settings,
        backend,
        initial_macro,
        persist_settings=True,
        library=library,
        schedules=schedules,
        colors=colors,
        # The active profile is what gets written back on save/close.
        on_persist=profiles.save,
    )
    window.show()
    return app.exec()
