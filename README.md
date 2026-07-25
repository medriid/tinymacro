# Tiny Macro

Tiny Macro is a monochrome PyQt6 macro recorder for Linux and Windows, designed
as a TinyTask-style alternative that scales up into a fuller automation tool
without losing its lightweight, keep-it-on-top footprint.

## Features

### Two UI variants

Tiny Macro ships with two switchable, **frameless** interfaces (custom title bar,
window controls, and animations):

- **Classic** — the compact toolbar window for everyday absolute-coordinate
  macros (`.tmacro`).
- **Studio** — a wide recessed frame that **docks a selected window** in the center
  (logs + overview on the left, macro options on the right). Everything recorded
  is stored **relative to the docked window**, so a Studio macro (`.tmacd`)
  replays at any resolution/window size and is **shareable**. Switch between the
  two from the View menu (Classic) or the side panel (Studio). The two macro
  formats are intentionally not interchangeable. Docking is Windows-only.

### Interface

- Compact-by-default window (the classic toolbar footprint) that expands into a
  live view with a playback progress bar and a real-time event feed while
  recording. Toggle with the **Expand / Collapse** button or the View menu.
- Monochrome black/white/gray identity by default, with optional color presets
  (slate, amber, emerald, violet) and a custom accent color. Monochrome remains
  a fully supported first-class theme.
- Subtle animations: a pulsing record indicator, animated playback progress, and
  transient toast notifications (all disableable in Preferences → Appearance).
- Optional **system tray** icon with quick record/play/stop and show/hide.
- Tabbed Preferences (General, Appearance, Capture, Hotkeys, Notifications,
  Advanced).

### Recording & playback

- Deterministic playback based on monotonic nanosecond timestamps.
- **Pause/resume recording**, adjustable mouse-move sampling rate to thin dense
  motion, and undo-last-segment while still recording.
- **Pause/resume playback**, **step-through** one event at a time, and a
  **dry-run validation** that checks a macro for structural problems without
  sending real input.
- Optional playback timing jitter for realistic QA/testing runs.
- Cursor start-position recording with relative mouse motion accumulated into
  absolute positions for exact replay.

### Editing & composition

- Rebuilt timeline editor: color-coded events by kind, search/filter, inline
  note editing, insert **wait steps** (fixed or random-range delays), bulk
  delete, keep-range, timing scale, and in-session **undo/redo**.
- **Editor power-ups**: insert any key/mouse/wheel event by hand, duplicate,
  copy/paste, reorder, a right-click context menu, and **Run from here**.
- A zoomable **graphical timeline track** beside the table, synced to the
  selection.
- Macro composition helpers: chain/playlist multiple macros and repeat a macro
  N times (see `Macro.then`, `Macro.chain`, `Macro.repeated`).
- Consecutive mouse movements collapse into expandable **movement groups** in the
  editor timeline, so clicks and key events stay easy to find.

### Visual automation (optional `vision` extras)

- **Click-Image step**: insert a step that searches the screen for an uploaded
  image and clicks it once found, with adjustable **match confidence**, timeout,
  click button/offset, and an on-missing policy (fail / skip / continue). The
  target image is embedded in the `.tmacro`, so macros stay self-contained.
- **Image-trigger scheduler**: a second scheduler variant that runs a macro
  **whenever a target image appears on screen**. Its loop count caps how many
  sightings it acts on, and the trigger is suppressed while its macro plays so it
  never re-fires on the same still-visible image.
- Needs the `vision` extras (`pip install "tiny-macro[vision]"`: OpenCV + mss).
  These are bundled in the prebuilt binaries. Screen capture works on Windows and
  X11; on pure Wayland it degrades gracefully with a clear message.

### Control flow & automation steps

- **Conditionals and loops**: wrap steps in an `if (image on screen) … else …`
  block, or a `loop ×N` block, right from the editor. Playback interprets them
  with proper nesting.
- **Wait-for-pixel** (screen colour) and **wait-for-window** (active title) steps.
- **Run step**: execute a shell command or Python snippet — **off by default**
  behind a clearly-warned "Allow code-execution steps" preference.
- Keyboard playback automatically returns focus to your target window, so
  recorded keystrokes land where you intend (not in Tiny Macro's own window).

### Automation & integrations

- **Macro library**: a local index of your macros with favorites, tags, search,
  recents, and run counts — independent of the OS file picker.
- **Scheduler**: run a macro on an interval, once at a time, daily, or when an
  image appears on screen (see above).
- **Settings profiles**: keep multiple named configurations and import/export
  them as JSON.
- **Pluggable notifications**: Discord webhook (with templated embeds and
  optional screenshot), a generic HTTP(S) webhook, and native tray/toast
  notifications on loop completion.
- **Autosave & crash recovery** of an in-progress macro, plus structured
  logging to a rotating file with an in-app log viewer.

### Platform & format

- X11 backend through `pynput`; Wayland backend through `evdev`/`uinput`;
  Windows backend through native hooks and `SendInput`.
- Native `.tmacro` JSON macro format, now at **format version 4** (adds wait
  steps, per-event notes, macro tags, click-image steps, and control-flow /
  automation steps). Older files load unchanged and are upgraded on load.
- Exportable standalone macro runner scripts.
- Customizable global hotkeys and an optional debug mode with detailed errors.

> **Scope note:** Tiny Macro is a desktop automation and QA/testing tool.
> Timing jitter exists to make test playback realistic, not to defeat
> anti-cheat, anti-bot, or DRM systems.

## Verifying without pytest

If you don't have `pytest` installed, `python scripts/selfcheck.py` runs the
non-GUI test suite using only the standard library. Install the `dev` extras and
run `pytest` for the full suite, including the PyQt6 GUI smoke tests.

## Install On Arch Linux

```bash
sudo pacman -S python python-pyqt6 python-pynput python-evdev
python -m pip install -e .
tiny-macro
```

Wayland capture and playback require access to `/dev/input/event*` and
`/dev/uinput`. Prefer a dedicated input group or udev rule instead of running
the full GUI as root.

## Build A Sendable Wayland Binary On Arch

If your friend has a fresh Arch install and may have nothing ready, send them
the project folder or `tiny-macro-arch-wayland-build-kit.zip`, then have them
run:

```bash
mkdir -p ~/tiny-macro-build-kit
unzip ~/Downloads/tiny-macro-arch-wayland-build-kit.zip -d ~/tiny-macro-build-kit
cd ~/tiny-macro-build-kit
bash scripts/build_arch_wayland.sh
```

Do not run the script from inside an archive preview window. Fully extract the
zip into a normal writable folder first. If they see `Permission denied` for a
path like `src/tinymacro/__pycache__`, run:

```bash
cd ~/tiny-macro-build-kit
sudo chown -R "$USER:$USER" .
chmod -R u+rwX .
bash scripts/build_arch_wayland.sh
```

The script checks every major prerequisite before building:

- Confirms it is running on Linux.
- Checks that the distro is Arch or Arch-like.
- Checks `pacman`, `sudo`, Python, pip, and venv support.
- Checks that the extracted project folder is writable.
- Removes stale Python `__pycache__` folders.
- Redirects Python cache files into `.pycache-build`.
- Installs missing pacman packages with `sudo pacman -S --needed`.
- Creates a clean `.venv-build`.
- Installs this project plus PyInstaller.
- Builds `dist/tiny-macro-wayland`.
- Writes `dist/README-WAYLAND.txt` with runtime permission steps.

After the build finishes, they can run:

```bash
./dist/tiny-macro-wayland --backend wayland
```

### Wayland Permission Setup

Wayland blocks normal apps from globally recording and replaying input. This
project's Wayland backend uses Linux input devices directly, so the user needs
permission for `/dev/input/event*` and `/dev/uinput`.

Recommended setup:

```bash
sudo groupadd -f input
sudo usermod -aG input "$USER"
printf 'KERNEL=="uinput", GROUP="input", MODE="0660", OPTIONS+="static_node=uinput"\n' | sudo tee /etc/udev/rules.d/99-tiny-macro-uinput.rules
sudo udevadm control --reload-rules
sudo modprobe uinput
```

Then log out and back in. Check permissions with:

```bash
groups
ls -l /dev/uinput
ls -l /dev/input/event* | head
```

Avoid running the full GUI as root except for a short temporary test.

## Build A Sendable Windows EXE

On Windows, run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_windows.ps1
```

The build writes:

```text
dist\tiny-macro-windows.exe
dist\README-WINDOWS.txt
```

The Windows build uses native low-level keyboard/mouse hooks for global capture
and hotkeys, and `SendInput` for playback. Normal desktop apps should work. To
control elevated/admin apps, run Tiny Macro as administrator too. Some games,
anti-cheat software, raw-input apps, or protected windows may block synthetic
input.

## File Format

Macros are saved as structured `.tmacro` JSON files. They are not binary
compatible with TinyTask `.rec` files.

## Safety

Always test a macro once at normal speed before looping it. `Pause`, `Break`,
and `ScrollLock` are reserved as emergency stop keys by default.

Enable debug mode in Preferences when diagnosing playback or recording issues.
In debug mode, Tiny Macro shows detailed error dialogs instead of only updating
the status bar.

On Wayland, exact cursor anchoring depends on what the compositor exposes.
Hyprland cursor position is detected through `hyprctl` when available. Other
Wayland compositors may still replay relative movement accurately but cannot
always reveal the initial global cursor position to normal apps.
