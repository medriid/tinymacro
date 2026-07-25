# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_all

block_cipher = None
project_root = Path(SPECPATH).parent
icons_dir = project_root / "src" / "tinymacro" / "gui" / "icons"
app_ico = icons_dir / "app" / "app.ico"

hiddenimports = [
    "PyQt6.QtCore",
    "PyQt6.QtGui",
    "PyQt6.QtWidgets",
    "PyQt6.QtSvg",
    "numpy",
    "tinymacro.backends.windows",
    "tinymacro.gui.app",
]

datas = [(str(icons_dir), "tinymacro/gui/icons")]
binaries = []

# Bundle the optional vision stack (click-image + image-trigger scheduler).
for _pkg in ("cv2", "mss"):
    _d, _b, _h = collect_all(_pkg)
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
    name="tiny-macro-windows",
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
    icon=str(app_ico) if app_ico.exists() else None,
)
