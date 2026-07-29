from __future__ import annotations

import argparse
from pathlib import Path
import sys

from tinymacro.backends.factory import create_backend
from tinymacro.core.macro import Macro
from tinymacro.core.player import Player
from tinymacro.desktop import install_file_association


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tiny-macro")
    parser.add_argument("macro", nargs="?", help="Optional .tmacc file to load or replay")
    parser.add_argument("--play", action="store_true", help="Replay the macro without opening the GUI")
    parser.add_argument("--backend", default="auto", help="auto, x11, wayland, macos, windows, or fake")
    parser.add_argument("--loop", type=int, default=1, help="Loop count; 0 means infinite")
    parser.add_argument("--speed", type=float, default=1.0, help="Playback speed multiplier")
    parser.add_argument("--install-file-association", action="store_true", help="Install user-local .tmacc association files")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.install_file_association:
        app_path, mime_path = install_file_association()
        print(f"Installed {app_path}")
        print(f"Installed {mime_path}")
        return 0
    if args.play:
        if not args.macro:
            raise SystemExit("--play requires a macro path")
        backend = create_backend(args.backend)
        try:
            Player(backend).start(Macro.load(args.macro), loop_count=args.loop, speed=args.speed, blocking=True)
        finally:
            backend.close()
        return 0
    from tinymacro.gui.app import run_app

    return run_app(Path(args.macro) if args.macro else None, backend_name=args.backend)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
