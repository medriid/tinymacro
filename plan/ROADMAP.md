# Tiny Macro — Roadmap & Working Notes

Living plan for picking the project back up on a fresh machine: what exists, what
to build next, what to improve, and how to develop/build/release.

---

## Current state (shipped in v0.1.1.1)

- **Two UI variants** (both frameless, custom title bar/icons, animations):
  - **Classic** — compact toolbar UI, absolute-coordinate macros (`.tmacc`).
  - **Studio** — 16:9 frame that position-attaches a selected window into a
    **see-through dock aperture**; records **window-relative** coordinates so
    macros are resolution-independent and shareable (`.tmacd`). Single
    **Dock/Undock** button, overview + logs (left), options (right),
    Preferences, and the same global hotkeys as Classic.
- **Playback engine**: deterministic, absolute-time-anchored scheduling;
  captures leading/trailing idle as wait steps so loop time includes idle and
  loops don't speed up. Control-flow interpreter for `if/else/endif` + `loop`.
- **Step types**: key/mouse/wheel, wait (fixed/jitter), **click-image**,
  **wait-pixel**, **wait-window**, **run shell/Python** (opt-in, off by default).
- **Windows backend**: low-level hooks; **scan-code injection** (works in games
  like Roblox); focus-restore before keyboard playback; window enumerate/move for
  docking. Wayland (evdev/uinput) + X11 (pynput) backends also present.
- **Vision** (optional `[vision]` extra: OpenCV + mss): template match + pixel read.
- **Extras**: macro library, scheduler (interval/daily/once/**image-trigger**),
  notifications (Discord + generic webhook + tray), settings profiles, autosave/
  crash recovery, logging + log viewer, graphical timeline, editor power-ups.
- **Formats**: `.tmacc` (classic), `.tmacd` (Studio/docked). Legacy `.tmacro`
  still loads. On-disk `format` field is the source of truth, not the extension.

---

## Features to add next

1. **Studio parity with Classic tools** — expose Library, Scheduler, Log Viewer,
   Validate (dry-run), and Export from the Studio side panel (currently
   Classic-only via its menus).
2. **Region-capture tool** for click-image / wait-pixel — drag a rectangle on
   screen to grab the target image/color instead of picking a file.
3. **Live current-step highlight** during playback in the editor + a non-modal
   editor so it can stay open while a macro runs (enables breakpoints).
4. **Undock leaves the target where it is** — optionally restore the target
   window's original size/position on undock (remember it at dock time).
5. **Studio: aspect-ratio lock options** (16:9 / match-target / free) for the
   dock aperture.
6. **Macro chaining / playlists in the UI** (core `Macro.then/chain/repeated`
   already exist — surface them).
7. **GIF/preview export** of a macro (was deferred; needs Pillow/imageio).
8. **First-run onboarding** + a few bundled sample macros.

## Improvements / tech debt

- **Shared controller refactor**: Classic and Studio each drive their own
  Recorder/Player glue. Extract a `MacroController` so both are thin views (was
  deferred to limit risk). Would de-duplicate record/play/save wiring.
- **Timeline in Studio**: reuse `gui/timeline.py` in the Studio overview.
- **Dock tracker**: currently a 150 ms `QTimer`; consider WinEvent hooks for
  smoother/instant tracking and less idle CPU.
- **Wayland docking**: enumerate/move windows isn't supported on Wayland; Studio
  degrades to a message. Investigate portal-based approaches if needed.
- **Test the frameless chrome interactions** (drag/resize/min/max) — currently
  only construction is smoke-tested.
- **Packaging size**: binaries are ~90–130 MB (PyQt6 + OpenCV). Consider trimming
  unused Qt plugins / opencv modules if size matters.

## Known limitations

- Window docking + enumeration is **Windows-only**.
- Kernel-level anti-cheat games can block all synthetic input (by design; not a bug).
- Elevated target apps require running Tiny Macro **as administrator**.

---

## Dev setup (fresh machine)

```bash
# Windows (PowerShell), from the repo root:
py -3.14 -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"     # dev = pytest + vision extras
.venv\Scripts\python -m pytest -q                    # run the suite
.venv\Scripts\python -m tinymacro                    # launch the app
```

- Python **3.12+** (3.14 used here). GUI is PyQt6.
- Optional image features need the `vision` extra (OpenCV-headless + mss + numpy),
  already included in the `dev` extra.

## Building binaries

- **Windows**: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_windows.ps1`
  → `dist/tiny-macro-windows.exe` (rebuilds `.venv-windows-build`, regenerates the
  multi-res app `.ico`, bundles icons + vision).
- **Arch/Wayland** (run on Arch, or Arch WSL): `bash scripts/build_arch_wayland.sh`
  → `dist/tiny-macro-wayland`. On WSL, build from the Linux filesystem (e.g.
  `~/tiny-macro-build`), not `/mnt/c`, or PyInstaller/venv perms fail.

## Release flow

1. Bump `version` in `pyproject.toml`.
2. `pytest -q` green; rebuild both binaries.
3. Commit (no AI co-author trailer — user preference), push.
4. `git tag vX` ; `gh release create vX dist/tiny-macro-windows.exe dist/tiny-macro-wayland --title ... --notes ...`.

## Architecture map

- `core/` — `events.py` (MacroEvent), `macro.py` (Macro + formats), `recorder.py`,
  `player.py` (scheduled + control-flow execution), `dock.py` (relative coords),
  `vision.py`, `scheduler.py` + `image_watcher.py`, `settings.py`, `hotkeys.py`.
- `backends/` — `base.py`, `windows.py`, `evdev_wayland.py`, `x11.py`, `fake.py`.
- `gui/` — `app.py` (bootstrap + variant switch), `main_window.py` (Classic),
  `studio_window.py` (Studio), `framed_window.py` (frameless chrome), `anim.py`,
  `icons.py`, `timeline.py`, `editor.py`, dialogs.
- `tests/` — pytest + pytest-qt.
