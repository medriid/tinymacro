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
  loops don't speed up. Precise timing (fine sleeps + Windows 1ms timer via
  `timeBeginPeriod`), verified stable and leak-free across 100+ loops.
  Control-flow interpreter for `if/else/endif` + `loop`.
- **Recording fidelity**: only the *full* global-hotkey chord is swallowed, so
  plain letters used in a chord (c/r/s/p/m) and lone modifiers (Ctrl for
  Ctrl+C in the target app) record correctly.
- **Screenshot event**: a while-recording hotkey drops a "screenshot point"; at
  playback the screen is captured at that exact instant and that image is what
  the Discord webhook sends (works in both UIs).
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

0. **Install manager + auto-update** (big; see "Distribution" below) — ship an
   installer and a self-updater so users download once and always get the latest
   app, and their macros sync/update whenever they connect.
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

## Distribution: install manager + website (planned)

Goal: users download Tiny Macro once, it **installs cleanly**, **auto-updates**
itself, and **syncs macros** (and macro updates) from a website whenever they're
online. Plus a public site where people browse/share macros per game.

### A. Installer (Windows first)

- Build an **Inno Setup** (or NSIS) installer that wraps `tiny-macro-windows.exe`:
  installs to `%LOCALAPPDATA%\TinyMacro` (per-user → self-update needs no admin),
  Start-Menu + desktop shortcuts, registers the `.tmacc`/`.tmacd` file
  associations and the `tinymacro://` URL protocol (see C).
- Keep publishing the raw `.exe`/`wayland` binaries on GitHub Releases too.
- Script it in `scripts/build_installer.iss` invoked after `build_windows.ps1`.
- Later: **code-sign** the exe/installer (removes SmartScreen warnings). Needs a
  cert (~$100–300/yr) — note as a cost item.

### B. Auto-updater (self-update)

- **Update source = GitHub Releases** to start (no server needed). On launch (and
  hourly), the app calls the GitHub Releases API, compares the latest tag to its
  own `__version__`, and if newer:
  1. downloads the new binary to a temp file + verifies a SHA-256 from the
     release notes/asset;
  2. writes a tiny `updater` helper that waits for the app to exit, swaps the
     binary, and relaunches (Windows can't overwrite a running exe, hence the
     helper). On Linux, replace the AppImage/binary in place.
- New module `core/updater.py` + a "Check for updates" menu item and a settings
  toggle for auto-update channel (stable / none). Show a non-blocking toast when
  an update is ready.
- Evaluate off-the-shelf first: **PyUpdater**, **tufup** (TUF-based, secure), or
  **Velopack** (great Windows delta updates) — a mature framework beats rolling
  our own signature/rollback logic. Recommendation: prototype with GitHub-based
  self-update, migrate to **tufup** (signed, resumable, rollback) if it grows.

### C. `tinymacro://` deep links + "Install from web"

- Register a URL-protocol handler at install time so a website button
  `tinymacro://install?id=<macroId>` opens the app and imports that macro
  straight into the library. Handle the URI in `cli.py`/`app.py`.
- This is the glue between the website and the desktop app.

### D. Website + macro library (workshop)

- **Frontend**: Next.js or SvelteKit — browse/search macros, per-game categories,
  tags, ratings, screenshots (reuse the webhook screenshots!), a macro's version
  history, and an "Open in Tiny Macro" button (deep link in C). A download-count
  and "verified/creator" badges.
- **Backend API**: FastAPI (Python — shares the macro models) or Node. Endpoints:
  auth, macro CRUD, search, ratings, download, and a **version manifest** the
  updater can read (so the site can also drive updates). Store macro files +
  screenshots in S3-compatible object storage; metadata in Postgres.
- **Accounts + cloud library sync**: each user's macro library lives server-side;
  the desktop app pulls updates on connect (a "Sync" that merges the local
  `MacroLibrary` with the account's) so macros update across machines — this is
  the "get any update to their macro every time they connect" ask.
- **Safety/moderation**: macros containing `run` (shell/Python) steps are flagged
  in the UI and on the site; the code-exec gate stays **off by default**; add a
  report/removal flow. Never auto-enable code execution from a downloaded macro.
- **Hosting**: start cheap — Vercel/Netlify (frontend) + Fly.io/Railway/Render
  (API) + managed Postgres + Cloudflare R2/Backblaze B2 (files). A single small
  VPS also works. Note domain + hosting as recurring costs.

### Suggested phase order

1. Inno Setup installer + `core/updater.py` self-update against GitHub Releases.
2. `tinymacro://` protocol handler + "Install from web" on a static macro page.
3. Website + API + accounts (browse/upload/download macros).
4. Cloud macro-library sync (per-account) pulled on connect; optional code-signing.

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
