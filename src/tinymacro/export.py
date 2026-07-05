from __future__ import annotations

from pathlib import Path
import stat
import textwrap

from tinymacro.core.macro import Macro


RUNNER_TEMPLATE = """\
#!/usr/bin/env python3
from pathlib import Path
import sys

from tinymacro.backends.factory import create_backend
from tinymacro.core.macro import Macro
from tinymacro.core.player import Player


def main() -> int:
    macro_path = Path(__file__).with_suffix(".tmacro")
    if not macro_path.exists():
        print(f"Missing macro file: {{macro_path}}", file=sys.stderr)
        return 2
    backend = create_backend("auto")
    macro = Macro.load(macro_path)
    try:
        Player(backend).start(macro, loop_count={loop_count}, speed={speed!r}, blocking=True)
    finally:
        backend.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
"""


def export_runner(macro: Macro, runner_path: str | Path, loop_count: int = 1, speed: float = 1.0) -> tuple[Path, Path]:
    runner = Path(runner_path)
    if runner.suffix != ".py":
        runner = runner.with_suffix(".py")
    macro_path = runner.with_suffix(".tmacro")
    macro.save(macro_path)
    runner.write_text(textwrap.dedent(RUNNER_TEMPLATE).format(loop_count=loop_count, speed=speed), encoding="utf-8")
    runner.chmod(runner.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return runner, macro_path
