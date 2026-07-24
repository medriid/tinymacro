from __future__ import annotations

import pytest

pytest.importorskip("PyQt6")

from tinymacro.core.events import MacroEvent
from tinymacro.core.library import MacroLibrary
from tinymacro.core.macro import Macro
from tinymacro.core.scheduler import ScheduleStore
from tinymacro.core.settings import Settings
from tinymacro.gui.editor import EditorDialog
from tinymacro.gui.library_dialog import LibraryDialog
from tinymacro.gui.log_dialog import LogDialog
from tinymacro.gui.preferences import PreferencesDialog
from tinymacro.gui.scheduler_dialog import SchedulerDialog
from tinymacro.gui.widgets import RecordingIndicator


def _macro():
    return Macro(events=[MacroEvent(0, "key", "press", key="a"), MacroEvent(10, "mouse", "press", button="left", x=1, y=2)])


def test_editor_insert_wait_and_undo(qtbot):
    dialog = EditorDialog(_macro())
    qtbot.addWidget(dialog)
    before = len(dialog.macro.events)
    dialog.insert_wait()
    assert dialog.macro.wait_event_count() == 1
    dialog.undo()
    assert len(dialog.macro.events) == before


def test_editor_filter_reduces_rows(qtbot):
    dialog = EditorDialog(_macro())
    qtbot.addWidget(dialog)
    dialog.search.setText("mouse")
    assert dialog.table.rowCount() == 1


def test_preferences_tabs_present(qtbot):
    dialog = PreferencesDialog(Settings())
    qtbot.addWidget(dialog)
    assert dialog.tabs.count() >= 5


def test_library_dialog_lists_entries(qtbot):
    lib = MacroLibrary()
    lib.add("/tmp/a.tmacro", name="Alpha")
    dialog = LibraryDialog(lib)
    qtbot.addWidget(dialog)
    assert dialog.list.count() == 1


def test_scheduler_dialog_opens(qtbot):
    dialog = SchedulerDialog(ScheduleStore())
    qtbot.addWidget(dialog)
    assert dialog.list.count() == 0


def test_log_dialog_opens(qtbot):
    dialog = LogDialog()
    qtbot.addWidget(dialog)
    dialog.refresh()


def test_recording_indicator_toggles(qtbot):
    indicator = RecordingIndicator()
    qtbot.addWidget(indicator)
    indicator.set_active(True)
    assert indicator._active
    indicator.set_active(False)
    assert not indicator._active
