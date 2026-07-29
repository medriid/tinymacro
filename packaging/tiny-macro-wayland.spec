# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None
project_root = Path(SPECPATH).parent
gui_dir = project_root / "src" / "tinymacro" / "gui"
icons_dir = gui_dir / "icons"
sounds_dir = gui_dir / "sounds"
fonts_dir = gui_dir / "fonts"

hiddenimports = (
    collect_submodules("pynput")
    + collect_submodules("evdev")
    + [
        "PyQt6.QtCore",
        "PyQt6.QtGui",
        "PyQt6.QtWidgets",
        "PyQt6.QtSvg",
        "PyQt6.QtMultimedia",
        "numpy",
        "tinymacro.backends.evdev_wayland",
        "tinymacro.backends.x11",
        "tinymacro.backends._pynput",
        "tinymacro.gui.app",
    ]
)

datas = [(str(icons_dir), "tinymacro/gui/icons")]
# UI feedback sounds and any bundled typeface travel with the app.
for _src, _dest in ((sounds_dir, "tinymacro/gui/sounds"), (fonts_dir, "tinymacro/gui/fonts")):
    if _src.is_dir():
        datas.append((str(_src), _dest))
binaries = []

# Bundle the vision stack (click-image + image-trigger scheduler), python-xlib
# (X11 window docking talks EWMH through it), and the bundle-encryption crypto
# backend. Each is wrapped so a build env missing an optional one still succeeds.
hiddenimports.append("tinymacro.core.securepack")
for _pkg in ("cv2", "mss", "Xlib", "cryptography"):
    try:
        _d, _b, _h = collect_all(_pkg)
        datas += _d
        binaries += _b
        hiddenimports += _h
    except Exception:
        pass  # optional in some build envs; skip if absent

a = Analysis(
    [str(project_root / "src" / "tinymacro" / "cli.py")],
    pathex=[str(project_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "unittest"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="tiny-macro-wayland",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
