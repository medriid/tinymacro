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
    + [
        "PyQt6.QtCore",
        "PyQt6.QtGui",
        "PyQt6.QtWidgets",
        "PyQt6.QtSvg",
        "PyQt6.QtMultimedia",
        "numpy",
        "tinymacro.backends.macos",
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

# Bundle the optional vision stack (click-image + image-trigger scheduler).
for _pkg in ("cv2", "mss"):
    try:
        _d, _b, _h = collect_all(_pkg)
        datas += _d
        binaries += _b
        hiddenimports += _h
    except Exception:
        pass  # vision extras are optional; skip if not installed in the build env

# Bundle the optional (build-only, gitignored) encryption module and its crypto
# backend — only when present, so a fresh clone / CI checkout still builds.
if (project_root / "src" / "tinymacro" / "core" / "securepack.py").exists():
    hiddenimports.append("tinymacro.core.securepack")
    _d, _b, _h = collect_all("cryptography")
    datas += _d
    binaries += _b
    hiddenimports += _h

a = Analysis(
    [str(project_root / "src" / "tinymacro" / "cli.py")],
    pathex=[str(project_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "unittest", "evdev"],
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
    name="tiny-macro-macos",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX mangles macOS binaries; leave the Mach-O untouched
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=True,  # let macOS "open with" / file-drop args reach argv
    target_arch=None,     # build for the runner's arch (arm64 on macos-14)
    codesign_identity=None,
    entitlements_file=None,
)
