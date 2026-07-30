<div align="center">

# Tiny Macro

**A deterministic, keep-it-on-top macro recorder for Windows, macOS, and Linux.**

TinyTask-style simplicity that scales up into a real automation studio — precise
replay, a live editor, playlists, image-aware steps, custom themes, and portable
encrypted bundles.

[![CI](https://github.com/medriid/tinymacro/actions/workflows/ci.yml/badge.svg)](https://github.com/medriid/tinymacro/actions/workflows/ci.yml)
[![Release](https://github.com/medriid/tinymacro/actions/workflows/release.yml/badge.svg)](https://github.com/medriid/tinymacro/actions/workflows/release.yml)
[![Latest release](https://img.shields.io/github/v/release/medriid/tinymacro?sort=semver)](https://github.com/medriid/tinymacro/releases/latest)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/)
![Platforms](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-informational)

</div>

---

## Contents

- [Why Tiny Macro](#why-tiny-macro)
- [Platform support](#platform-support)
- [Download](#download)
- [Install from source](#install-from-source)
- [Permissions](#permissions)
- [Features](#features)
- [Macro formats](#macro-formats)
- [Building your own binaries](#building-your-own-binaries)
- [Automated releases (CI)](#automated-releases-ci)
- [Bundle encryption](#bundle-encryption)
- [Development](#development)
- [Scope & safety](#scope--safety)
- [License](#license)

## Why Tiny Macro

Tiny Macro records mouse and keyboard input and replays it **exactly** — timing
is reconstructed from monotonic nanosecond timestamps, not guessed. It starts as
a tiny always-on-top toolbar and expands, only when you want it, into a full
editor with a timeline, breakpoints, conditionals, image matching, scheduling,
and notifications.

Two interchangeable interfaces ship in one app:

- **Classic** — the compact toolbar for everyday absolute-coordinate macros.
- **Studio** — a wide frame that **docks a target window** in the centre and
  records everything *relative* to it, so the macro replays at any resolution or
  window size and is shareable.

Switch between them any time from the View menu (Classic) or the side panel
(Studio).

## Platform support

| Capability | Windows | macOS | Linux (X11) | Linux (Wayland) |
|---|:---:|:---:|:---:|:---:|
| Record & replay | ✅ | ✅ | ✅ | ✅ |
| Global hotkeys | ✅ | ✅ | ✅ | ✅ |
| Text-type step | ✅ | ✅ | ✅ | ✅ |
| Window docking (Studio) | ✅ | 🧪 | 🧪 | ✕ |
| Image steps / triggers (`vision`) | ✅ | ✅ | ✅ | ⚠️ degrades |
| Backend | native hooks + `SendInput` | Quartz via `pynput` | `pynput` | `evdev` / `uinput` |
| Extra setup | run as admin for elevated apps | grant Accessibility + Input Monitoring | — | `input` group + udev rule |

✅ supported · 🧪 experimental · ⚠️ partial · — not available · ✕ impossible.
See [Permissions](#permissions) for the macOS and Linux one-time setup.

> **On window docking:** full and battle-tested on Windows. macOS (via the
> Accessibility API) and Linux/X11 (via EWMH) are **experimental** — they move
> the whole window frame and depend on a cooperative window manager. Wayland
> deliberately forbids apps from positioning other windows, so docking cannot be
> supported there by design (input capture still works via the evdev backend).

## Download

Grab a prebuilt zip from the [**latest release**](https://github.com/medriid/tinymacro/releases/latest), extract it once, then run the app from the extracted folder:

| OS | File | Run it |
|---|---|---|
| Windows | `tiny-macro-windows.zip` | open `tiny-macro-windows/tiny-macro-windows.exe` |
| macOS | `tiny-macro-macos.zip` | `cd tiny-macro-macos && ./tiny-macro-macos` |
| Linux | `tiny-macro-linux.zip` | `cd tiny-macro-linux && ./tiny-macro-linux` |

> **macOS Gatekeeper:** the binary is unsigned, so the first launch needs
> right-click → **Open** (or *System Settings → Privacy & Security → Open
> Anyway*). Then grant the permissions below.

The packaged app uses PyInstaller's onedir layout so it does not unpack a large
bundle to temp every time it starts. The zips also carry the optional
image-matching stack, so no extra install is needed for the vision features.

## Install from source

Requires **Python 3.12+**.

```bash
git clone https://github.com/medriid/tinymacro.git
cd tinymacro
python -m pip install -e .
tiny-macro
```

Add the on-screen image-matching features with the `vision` extra:

```bash
python -m pip install -e ".[vision]"
```

**Platform notes**

- **Windows** — no extra packages; native input is driven through `ctypes`.
- **macOS** — `pip` pulls in `pynput` and the `pyobjc` Quartz bridge automatically.
- **Linux (Arch)** — `sudo pacman -S python python-pyqt6 python-pynput python-evdev`.

Pick a backend explicitly with `tiny-macro --backend {auto,windows,macos,x11,wayland,fake}`
if auto-detection guesses wrong.

## Permissions

### macOS

macOS gates global input behind its privacy system (TCC). Open **System Settings
→ Privacy & Security** and enable Tiny Macro under:

- **Accessibility** — required to replay input.
- **Input Monitoring** — required to record input.
- **Screen Recording** — only if you use the image steps/triggers.

When running from source the grant attaches to your terminal (or Python), not to
Tiny Macro itself. Quit and reopen after granting. If capture is silent, this is
almost always the cause — Tiny Macro will tell you so on startup.

### Linux (Wayland)

Wayland blocks apps from globally recording/replaying input, so the backend talks
to the kernel input devices directly and needs access to `/dev/input/event*` and
`/dev/uinput`:

```bash
sudo groupadd -f input
sudo usermod -aG input "$USER"
printf 'KERNEL=="uinput", GROUP="input", MODE="0660", OPTIONS+="static_node=uinput"\n' \
  | sudo tee /etc/udev/rules.d/99-tiny-macro-uinput.rules
sudo udevadm control --reload-rules
sudo modprobe uinput
```

Log out and back in, then verify with `groups`, `ls -l /dev/uinput`, and
`ls -l /dev/input/event*`. Prefer this group/udev setup over running the GUI as
root. X11 needs no special permissions.

## Features

**Recording & playback**
- Deterministic replay from monotonic nanosecond timestamps.
- Pause/resume recording, adjustable mouse-move sampling, undo-last-segment.
- Pause/resume playback, single-step, and a dry-run validator that checks a
  macro for structural problems without sending real input.
- Optional timing jitter for realistic QA runs; cursor start-position capture.

**Editing & composition**
- Timeline editor with colour-coded events, search/filter, inline notes, insert
  wait steps (fixed or random-range), bulk delete, keep-range, timing scale, and
  undo/redo.
- Insert any key/mouse/wheel event by hand; duplicate, copy/paste, reorder,
  right-click menu, and **Run from here**.
- A zoomable graphical timeline track synced to the selection; consecutive mouse
  moves collapse into expandable movement groups.
- **Playlists / flow builder** — chain macros, repeat ×N, and gate steps on an
  image appearing on screen.

**Control flow & steps**
- `if (image on screen) … else …` and `loop ×N` blocks with proper nesting.
- Wait-for-pixel and wait-for-window steps; a **text-type** step for arbitrary
  unicode.
- **Run step** (shell/Python) — off by default behind a clearly-warned preference.

**Visual automation** (optional `vision` extra)
- **Click-Image step**: find an uploaded image on screen and click it, with
  adjustable confidence, timeout, button/offset, and on-missing policy. The
  target image is embedded in the macro, so it stays self-contained.
- **Image-trigger scheduler**: run a macro whenever a target image appears.

**Automation & integrations**
- Macro library with favorites, tags, search, recents, and run counts.
- Scheduler (interval / once / daily / on-image).
- Settings profiles with JSON import/export.
- Notifications: Discord webhook (templated embeds + optional screenshot),
  generic HTTP webhook, and native tray/toast on completion.
- Autosave & crash recovery, plus rotating structured logs with an in-app viewer.

**Interface**
- Two frameless UIs (custom title bar, window controls, animations).
- Monochrome by default, with colour presets, fully custom themes (image/animated
  backgrounds), per-button accents, and a themed colour picker.
- Subtle hover/press animations and optional UI sounds (toggle in Preferences).
- Optional system-tray icon; guided first-run onboarding.
- **Portable bundles** — export a playlist and its macros/assets as a single
  `.tmbundle`, optionally password-encrypted (Argon2id + AES-256-GCM).

## Macro formats

- Classic macros are `.tmacro` JSON (currently **format version 4**). Older files
  load unchanged and upgrade on load.
- Studio macros are `.tmacd` and store input relative to the docked window.
- The two formats are intentionally **not** interchangeable.
- Macros are not binary-compatible with TinyTask `.rec` files. Standalone runner
  scripts can be exported.

## Building your own binaries

Each platform builds a self-contained onedir app folder with
[PyInstaller](https://pyinstaller.org/). Release builds zip that folder into one
downloadable asset:

```bash
python -m pip install -e ".[build,vision]"
```

| OS | Command | Output |
|---|---|---|
| Windows | `pyinstaller --clean --noconfirm packaging/tiny-macro-windows.spec` | `dist/tiny-macro-windows/` |
| macOS | `pyinstaller --clean --noconfirm packaging/tiny-macro-macos.spec` | `dist/tiny-macro-macos` |
| Linux | `pyinstaller --clean --noconfirm packaging/tiny-macro-wayland.spec` | `dist/tiny-macro-wayland` |

On Windows you can also run `scripts\build_windows.ps1`, and on Arch there's a
turnkey `scripts/build_arch_wayland.sh` that installs prerequisites, builds, and
writes runtime setup notes.

## Automated releases (CI)

Two GitHub Actions workflows live in [`.github/workflows`](.github/workflows):

- **`ci.yml`** — runs the full test suite on Windows, macOS, and Linux for every
  push and pull request.
- **`release.yml`** — on any pushed tag matching `v*`, builds all three app
  folders in parallel, zips them, and attaches the zip assets to a GitHub Release
  with auto-generated notes.

Cutting a release is just:

```bash
git tag v0.1.7
git push origin v0.1.7
```

No secrets are required — the workflow uses the built-in `GITHUB_TOKEN`. You can
also run it manually from the **Actions** tab to produce downloadable artifacts
without publishing.

## Bundle encryption

Portable `.tmbundle` files can be encrypted, and the encryption
([`securepack.py`](src/tinymacro/core/securepack.py)) is fully open source — its
security follows [Kerckhoffs's principle](https://en.wikipedia.org/wiki/Kerckhoffs%27s_principle):
everything is public except your password.

- **Password-protected bundles** — real confidentiality. The key is stretched
  from your password with **Argon2id** (memory-hard) and the payload sealed with
  **AES-256-GCM**. A shared bundle is safe even against someone holding this
  entire repository: the only way in is to guess the password, which Argon2id
  makes very expensive. Use a strong password and share it out-of-band.
- **"Open" (no-password) bundles** — **obfuscation and tamper-evidence only, not
  confidentiality.** The key comes from a public constant, so anyone with the app
  can open them. If a shared bundle must stay private, give it a password.

Publishing the algorithm does not weaken the strong mode — that is the whole
point of well-designed cryptography.

## Development

```bash
python -m pip install -e ".[dev]"
python -m pytest           # full suite, incl. PyQt6 GUI smoke tests
```

No `pytest`? `python scripts/selfcheck.py` runs the non-GUI subset with only the
standard library. On headless Linux, set `QT_QPA_PLATFORM=offscreen` for the GUI
tests (CI does this automatically).

## Scope & safety

Tiny Macro is a desktop automation and QA/testing tool. Timing jitter exists to
make test playback realistic — **not** to defeat anti-cheat, anti-bot, or DRM
systems. Some games and protected/raw-input windows will block synthetic input
by design.

Always test a macro once at normal speed before looping it. `Pause`, `Break`, and
`ScrollLock` are reserved as emergency-stop keys by default. Enable debug mode in
Preferences for detailed error dialogs when diagnosing recording/playback.

## License

Released under the [MIT License](LICENSE).
