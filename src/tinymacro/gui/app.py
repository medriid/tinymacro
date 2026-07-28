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
from tinymacro.gui.studio_window import StudioWindow
from tinymacro.gui.sounds import ui_sounds
from tinymacro.gui.theme import apply_theme, load_bundled_fonts


def run_app(initial_macro: Path | None = None, backend_name: str = "auto") -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Tiny Macro")
    app.setWindowIcon(app_icon())
    load_bundled_fonts()  # register any shipped typeface before the theme is built

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

    ui_sounds().set_enabled(settings.ui_sounds)
    colors = apply_theme(app, settings)
    try:
        backend = create_backend(settings.backend)
    except Exception as exc:
        QMessageBox.critical(None, "Backend unavailable", str(exc))
        return 2

    state: dict[str, object] = {"window": None}

    def persist_profiles() -> None:
        profiles.save()

    def build(variant: str, macro: Path | None):
        if variant == "studio":
            window = StudioWindow(
                settings, backend, persist_settings=True, library=library,
                schedules=schedules, colors=colors, on_persist=persist_profiles,
            )
        else:
            window = MainWindow(
                settings, backend, macro, persist_settings=True, library=library,
                schedules=schedules, colors=colors, on_persist=persist_profiles,
            )
        window.switch_variant_requested.connect(switch)
        return window

    def switch(variant: str) -> None:
        old = state["window"]
        new = build(variant, None)
        state["window"] = new
        new.show()
        if old is not None:
            # Keep the shared backend alive across the swap; the old window fades out.
            old._keep_backend = True  # type: ignore[attr-defined]
            old.close()

    state["window"] = build(settings.ui_variant, initial_macro)
    state["window"].show()  # type: ignore[union-attr]
    return app.exec()
