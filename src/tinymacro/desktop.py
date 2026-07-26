from __future__ import annotations

from pathlib import Path


DESKTOP_ENTRY = """\
[Desktop Entry]
Type=Application
Name=Tiny Macro
Comment=Replay Tiny Macro recordings
Exec=tiny-macro %f
MimeType=application/x-tiny-macro;
Icon=input-keyboard
Categories=Utility;
NoDisplay=false
"""

MIME_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<mime-info xmlns="http://www.freedesktop.org/standards/shared-mime-info">
  <mime-type type="application/x-tiny-macro">
    <comment>Tiny Macro recording</comment>
    <glob pattern="*.tmacc"/>
  </mime-type>
</mime-info>
"""


def install_file_association(prefix: Path | None = None) -> tuple[Path, Path]:
    base = prefix or (Path.home() / ".local" / "share")
    app_path = base / "applications" / "tiny-macro.desktop"
    mime_path = base / "mime" / "packages" / "tiny-macro.xml"
    app_path.parent.mkdir(parents=True, exist_ok=True)
    mime_path.parent.mkdir(parents=True, exist_ok=True)
    app_path.write_text(DESKTOP_ENTRY, encoding="utf-8")
    mime_path.write_text(MIME_XML, encoding="utf-8")
    return app_path, mime_path
