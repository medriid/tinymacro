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

## Build A Sendable Wayland Binary On Arch

If your friend has a fresh Arch install and may have nothing ready, send them
the project folder or `tiny-macro-arch-wayland-build-kit.zip`, then have them
run:

```bash
unzip tiny-macro-arch-wayland-build-kit.zip
cd tiny-macro-arch-wayland-build-kit
bash scripts/build_arch_wayland.sh
```

The script checks every major prerequisite before building:

- Confirms it is running on Linux.
- Checks that the distro is Arch or Arch-like.
- Checks `pacman`, `sudo`, Python, pip, and venv support.
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

## File Format

Macros are saved as structured `.tmacro` JSON files. They are not binary
compatible with TinyTask `.rec` files.

## Safety

Always test a macro once at normal speed before looping it. `Pause`, `Break`,
and `ScrollLock` are reserved as emergency stop keys by default.
