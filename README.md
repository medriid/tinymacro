# Tiny Macro

Tiny Macro is a small monochrome PyQt6 macro recorder for Linux, designed as a
TinyTask-style alternative for Arch Linux.

## Features

- Compact PyQt6 toolbar with open, save, record, play/stop, loop count, speed,
  editor, preferences, and always-on-top controls.
- Deterministic playback based on monotonic nanosecond timestamps.
- Native `.tmacro` JSON macro format.
- Customizable global hotkeys.
- X11 backend through `pynput`.
- Wayland-oriented backend through `evdev`/`uinput`, requiring input-device and
  uinput permissions.
- Timeline editor for deleting events, trimming idle time, trimming selected
  ranges, and scaling timing.
- Exportable macro runner scripts.

## Install On Arch Linux

```bash
sudo pacman -S python python-pyqt6 python-pynput python-evdev
python -m pip install -e .
tiny-macro
```

Wayland capture and playback require access to `/dev/input/event*` and
`/dev/uinput`. Prefer a dedicated input group or udev rule instead of running
the full GUI as root.

## File Format

Macros are saved as structured `.tmacro` JSON files. They are not binary
compatible with TinyTask `.rec` files.

## Safety

Always test a macro once at normal speed before looping it. `Pause`, `Break`,
and `ScrollLock` are reserved as emergency stop keys by default.
