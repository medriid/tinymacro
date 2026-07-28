# Tiny Macro — Roadmap & Working Notes

Living plan for picking the project back up on a fresh machine: what exists, what
to build next, what to improve, and how to develop/build/release.

---

## Current state (shipped in v0.1.3)

- **Two UI variants** (both frameless, custom title bar/icons, animations):
  - **Classic** — compact toolbar UI, absolute-coordinate macros (`.tmacc`).
  - **Studio** — 16:9 frame that position-attaches a selected window into a
    **see-through dock aperture**; records **window-relative** coordinates so
    macros are resolution-independent and shareable (`.tmacd`). Single
    **Dock/Undock** button, overview + logs (left), options (right),
    Preferences, and the same global hotkeys as Classic.
- **Playback engine**: deterministic, absolute-time-anchored scheduling;
  captures leading/trailing idle as wait steps so loop time includes idle and
  loops don't speed up. **Sub-millisecond precise timing** — each event's
  deadline is anchored to a per-loop start and the final slice is busy-spun on a
  high-res clock (with the Windows 1ms timer via `timeBeginPeriod`), so every
  loop replays identically (measured stdev ~0.005 ms across loops) and small
  inter-event pauses are honored. The control-flow interpreter advances a running
  target clock so `if/else/endif` + `loop` timing doesn't drift either.
  **Fresh loops**: an optional (default-on) settling gap between iterations and a
  release of any keys/buttons left held, so each loop starts clean.
- **Playlists**: chain several macros to play back-to-back (`core/playlist.py` +
  `PlaylistDialog`, `.tmplist` files) with per-item repeat and an inter-macro gap;
  variant-scoped (classic/Studio). Surfaced in both UIs; the stitched macro runs
  through the normal player, so loop/speed/notifications apply to the whole set.
- **Live debugging editor**: the Macro Editor is non-modal and can stay open while
  a macro plays. It highlights the executing step in the event tree and the
  timeline (a green playhead), and supports **breakpoints** (right-click → Toggle
  Breakpoint) that auto-pause playback at a step (amber highlight) with Resume.
  Edits apply to the host live; the timeline gained a `set_playing` marker.
- **DPI-correct docking**: the Studio aperture is reported in physical pixels
  (`dock.scale_to_physical`), so on a scaled display (e.g. 125%) the docked window
  fills and centres correctly and recorded clicks land right — Studio macros are
  truly resolution-independent. Studio now opens **maximized**; undock restores the
  target window to where it was (Preferences toggle).
- **Window chrome**: the title-bar maximize button swaps between a full-window and
  a restore (two-window) glyph to mirror the window state, in both UIs.
- **Cinematic onboarding**: a first-run guided tour (`gui/onboarding.py`) blurs the
  window and spotlights each feature one at a time with a **crisp white, pixel-style
  card** (monospace, square reticle with corner brackets), Back / Next / Skip (arrow
  keys / Esc). It tracks the window wherever it is/resizes, runs once
  (`onboarding_seen`) in whichever UI launches first, and is replayable from
  **Preferences → Show Introduction** in both UIs.
- **Studio dock aperture**: aspect lock (Free / 16:9 / Match-window) that
  letterboxes the aperture; the choice persists.
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
1. ~~**Studio parity with Classic tools**~~ — **done**: Library, Scheduler, Log
   Viewer, Validate, Export (and now Playlist) are in the Studio side panel.
2. ~~**Region-capture tool**~~ — **done**: `gui/region_capture.py` drag-to-snip
   feeds click-image and wait-pixel steps.
3. ~~**Live current-step highlight** during playback + non-modal editor~~ —
   **done**: the editor is non-modal (live two-way sync, `show()` not `exec()`),
   the executing step is highlighted in the tree and timeline (green playhead), and
   **breakpoints** (right-click → Toggle Breakpoint) auto-pause playback (amber
   highlight) with Resume in both UIs. Player hooks: `on_step` / `on_breakpoint` /
   `breakpoints`.
4. ~~**Undock leaves the target where it is**~~ — **done**: the target window's
   client rect is captured at dock time and restored on undock (toggle in
   Preferences, default on).
5. ~~**Studio: aspect-ratio lock options**~~ — **done**: a Studio selector locks
   the dock aperture to Free / 16:9 / Match-window (the docked target's ratio);
   `DockArea` letterboxes its inner frame and the choice persists.
6. ~~**Macro chaining / playlists in the UI**~~ — **done**: `core/playlist.py` +
   `PlaylistDialog` (`.tmplist`), surfaced in both UIs.
7. **GIF/preview export** of a macro (was deferred; needs Pillow/imageio).
8. **First-run onboarding** — **done** (the guided tour); bundled sample macros
   still TODO. `gui/onboarding.py` is a cinematic blurred-spotlight walk-through
   (animated spotlight + card, Back/Next/Skip, arrow keys/Esc) that runs once on
   first launch (`onboarding_seen`) and can be replayed from Guided Tour in both
   UIs.

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

## Custom themes (`.tmactheme`) — shipped (phases 1–4)

**Implemented**: full reskinning — a **solid colour, a PNG/JPG, or an animated
GIF** background (fit modes + adjustable scrim), a chosen **accent/highlight**,
translucent panel/text colours (surface opacity so the background shows through
toolbars/lists/cards), and an optional UI font. Themes export as a single portable,
gzip-compressed **`.tmactheme`** with base64-embedded assets — no external paths,
cross-platform, safe to share.

- `core/theme_pack.py` — pure `Theme`/`Background` model, base64 assets, strict
  validation (hex colours, opacity ranges, fit/kind, image magic-byte sniffing,
  per-asset + total size caps, WCAG contrast warnings), gzip save/`.tmactheme`
  load (also reads plain JSON). Fully unit-tested.
- `gui/themed_background.py` — a click-through, lowered `ThemedBackground` that
  paints the still image or GIF (`QMovie`) per fit mode with a scrim; **paused
  during playback and when animations are off** (perf/reduce-motion guard).
- `gui/theme.py` — `apply_theme(Theme)` / `apply_theme_object` build the palette +
  rgba-surface stylesheet and font override; built-in presets still work.
- `gui/theme_editor.py` — live editor (colours, background, scrim/opacity sliders,
  font), **Save & Use**, **Use Default**, and **Import/Export `.tmactheme`**,
  reached from **Preferences → Appearance → Custom Themes…**. `Settings.active_theme`
  persists the choice; themes live in `~/.config/tiny-macro/themes/`.

**Still TODO** (phase 5): a theme gallery + workshop/site integration and cloud
sync (below). Original design notes retained for reference:

Goal: let users fully reskin Tiny Macro — a **solid colour, a PNG, or an animated
GIF** as the window background, a chosen **accent/highlight**, and panel/text
colours — then **export the whole look as a single portable `.tmactheme` file**
that imports on any other machine (Windows or Linux) and looks identical. Themes
are **pure data + bundled assets** (no code, no external file paths), so they are
safe to share and inherently cross-platform.

### A. What a theme controls

Extend today's `ThemeColors` (in `gui/theme.py`) into a richer, serialisable
`Theme`:

- **Background layer** — one of:
  - `solid`: a hex colour;
  - `image`: a still PNG/JPG (tiled / centred / stretched / `cover` / `fit`);
  - `animated`: a GIF/APNG played via `QMovie` (with a `fit` mode + optional
    frame-rate cap and a "freeze on first frame" fallback).
  Plus a **scrim**: an adjustable dark/light overlay alpha drawn *over* the
  background so foreground text stays legible on busy images.
- **Surfaces** — panel / elevated / border colours, each with an **opacity** so
  the background shows through cards, toolbars and list rows (the key to making an
  image background actually read as a theme rather than being hidden).
- **Accent / highlight** — the existing accent + `accent_text`; drives buttons,
  selections, the timeline playhead, progress chunks, checkboxes.
- **Text** — text + muted colours (auto-contrast helper: warn/adjust when the
  chosen text colour fails a WCAG-ish contrast ratio against the background).
- **Kind colours** — the editor/timeline per-kind palette (`key/mouse/wheel/wait`).
- **Font** — optional UI font family override (falls back to `UI_FONT_STACK`).
- **Metadata** — `name`, `author`, `version`, `created_at`, and a small preview
  thumbnail (base64 PNG) for a theme gallery.

Rendering approach: a `ThemedBackground` widget painted behind the central widget
(a custom `paintEvent` for solid/still images, a `QMovie`-driven `QLabel`/paint
for GIFs), with the existing stylesheet regenerated so panels use `rgba(...)` from
the surface opacities. Both `FramelessWindow` subclasses host it beneath their
content; the onboarding overlay already blurs whatever is behind it, so it "just
works" over a themed background.

### B. The `.tmactheme` file format

A single JSON document with **assets embedded as base64** so the file is
self-contained and portable (no broken image paths across PCs/OSes):

```jsonc
{
  "format": "tiny-macro-theme",
  "version": 1,
  "name": "Synthwave",
  "author": "…",
  "background": { "kind": "animated", "fit": "cover", "scrim": 0.35,
                  "asset": "grid.gif", "fps_cap": 24 },
  "surfaces": { "panel": "#181826", "panel_opacity": 0.82, "border": "#33334d", … },
  "accent": "#ff5cae", "accent_text": "#0c0c12",
  "text": "#f0f0ff", "muted": "#9aa0c0",
  "kind_colors": { "key": "#…", "mouse": "#…", "wheel": "#…", "wait": "#…" },
  "font_family": "",
  "assets": { "grid.gif": "<base64>", "thumbnail": "<base64-png>" }
}
```

Design decisions:
- **Embedded, not referenced** assets → true portability and one-file sharing.
- **Size discipline**: hard cap the packed file (e.g. ≤ 8–12 MB); warn on large
  GIFs; downscale/re-encode oversized images on export; store a separate small
  thumbnail so galleries don't decode full GIFs. Consider zlib-compressing the
  JSON (`.tmactheme` = gzipped JSON) to shrink base64 overhead.
- **Cross-platform correctness**: only hex colours + PNG/GIF bytes + family
  *names*; never absolute paths, never platform fonts assumed present (missing
  family → documented fallback). Pillow/Qt decode identically on Win/Linux.
- **Versioned + forward-compatible** like the macro format: unknown keys ignored,
  new optional keys only written when set.

### C. Core + GUI work

- `core/theme_pack.py` — pure, testable `Theme` dataclass with
  `to_dict`/`from_dict`/`save`/`load`, asset (de)serialisation, validation
  (colour syntax, opacity range, asset size/type sniffing, contrast check). No Qt,
  so it unit-tests cleanly like `dock.py`/`playlist.py`.
- `gui/theme.py` — `apply_theme` learns to take a `Theme` (built-in presets become
  thin `Theme` instances), regenerating palette + stylesheet with rgba surfaces
  and installing/removing the `ThemedBackground`.
- `gui/theme_store.py` + a small on-disk themes dir (`~/.config/tiny-macro/themes`)
  with an index, mirroring `MacroLibrary`.
- **Theme editor dialog** — pick background (colour / "Choose image…" / "Choose
  GIF…"), sliders for scrim + surface opacity, accent/text pickers, font, **live
  preview** on a mini mock, and **Export…/Import…** (`.tmactheme`). A gallery of
  saved themes with the thumbnails.
- `Settings` gains `active_theme` (name or path) resolved on launch; built-in
  presets stay the default so nothing changes unless a user opts in.

### D. Safety, performance, reliability

- **Untrusted input**: a `.tmactheme` is *data only*. Decode images through
  Pillow/Qt with strict type/size caps; reject anything that isn't a valid
  PNG/JPG/GIF; never execute anything; treat `name/author` as plain text in the
  UI (no rich markup). This dovetails with the workshop's moderation story — a
  future theme gallery on the site reuses the same validation.
- **Animated backgrounds**: cap FPS + resolution; pause the `QMovie` when the
  window is minimised/inactive or the macro is *playing* (so capture/replay timing
  and CPU aren't disturbed); a global "reduce motion / disable animated
  backgrounds" toggle (also honour the OS reduce-motion hint). Freeze to the first
  frame as a low-power fallback.
- **Legibility**: enforce a minimum scrim/contrast so text never becomes
  unreadable on a wild background; offer an auto-scrim that samples the image.

### E. Distribution tie-in

Themes ride the same rails as macros: shareable single files now, and later
first-class objects in the **workshop website** (browse/preview/download themes
per game or vibe, `tinymacro://install?theme=…` deep links, cloud sync of a user's
themes). The embedded-asset format means a theme downloaded on the site drops
straight into the desktop app unchanged.

### Suggested phase order

1. `core/theme_pack.py` (`Theme` + `.tmactheme` load/save/validate) with tests.
2. `apply_theme(Theme)` + `ThemedBackground` for **solid** and **still image**
   backgrounds + surface opacity; wire built-in presets through it.
3. Theme editor dialog with live preview + Import/Export.
4. **Animated (GIF)** backgrounds via `QMovie` with the motion/perf guards.
5. Theme gallery + workshop/site integration and cloud sync.

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
  `player.py` (scheduled + control-flow execution, precise timing), `playlist.py`
  (chain macros into one run), `dock.py` (relative coords), `vision.py`,
  `scheduler.py` + `image_watcher.py`, `settings.py`, `hotkeys.py`.
- `backends/` — `base.py`, `windows.py`, `evdev_wayland.py`, `x11.py`, `fake.py`.
- `gui/` — `app.py` (bootstrap + variant switch), `main_window.py` (Classic),
  `studio_window.py` (Studio), `framed_window.py` (frameless chrome), `anim.py`,
  `icons.py`, `timeline.py`, `editor.py`, dialogs.
- `tests/` — pytest + pytest-qt.
