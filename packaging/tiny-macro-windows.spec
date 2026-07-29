# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_all

block_cipher = None
project_root = Path(SPECPATH).parent
gui_dir = project_root / "src" / "tinymacro" / "gui"
icons_dir = gui_dir / "icons"
sounds_dir = gui_dir / "sounds"
fonts_dir = gui_dir / "fonts"
app_ico = icons_dir / "app" / "app.ico"

hiddenimports = [
    "PyQt6.QtCore",
    "PyQt6.QtGui",
    "PyQt6.QtWidgets",
    "PyQt6.QtSvg",
    "PyQt6.QtMultimedia",
    "numpy",
    "tinymacro.backends.windows",
    "tinymacro.gui.app",
]

datas = [(str(icons_dir), "tinymacro/gui/icons")]
# UI feedback sounds and any bundled typeface travel with the app.
for _src, _dest in ((sounds_dir, "tinymacro/gui/sounds"), (fonts_dir, "tinymacro/gui/fonts")):
    if _src.is_dir():
        datas.append((str(_src), _dest))
binaries = []

# Bundle the optional vision stack (click-image + image-trigger scheduler).
for _pkg in ("cv2", "mss"):
    _d, _b, _h = collect_all(_pkg)
    datas += _d
    binaries += _b
    hiddenimports += _h

# Bundle the (now open-source) encryption module and its crypto backend so
# .tmbundle password protection works in the packaged app.
hiddenimports.append("tinymacro.core.securepack")
for _pkg in ("cryptography",):
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

# onedir build: the exe launches from a folder (with _internal/ alongside) and
# does NOT re-extract a 110MB archive to temp on every start. This is the single
# biggest startup win — cold start drops from ~4.5s (onefile) to well under 1s.
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="tiny-macro-windows",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(app_ico) if app_ico.exists() else None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="tiny-macro-windows",
)
