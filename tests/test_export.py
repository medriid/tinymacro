from __future__ import annotations

import os

from tinymacro.core.events import MacroEvent
from tinymacro.core.macro import Macro
from tinymacro.export import export_runner


def test_export_runner_writes_executable_pair(tmp_path):
    macro = Macro(events=[MacroEvent(0, "key", "press", key="a")])

    runner, macro_path = export_runner(macro, tmp_path / "demo", loop_count=2, speed=3.0)

    assert runner.exists()
    assert macro_path.exists()
    assert os.access(runner, os.X_OK)
    assert "loop_count=2" in runner.read_text(encoding="utf-8")
