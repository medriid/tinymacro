"""Custom filled icon set, rendered from inline SVG and tinted to the theme.

Every UI glyph in Tiny Macro comes from here so the toolbar, menus, and dialogs
share one cohesive, solid-filled look instead of the platform's default stock
icons. Icons are single-color: the ``{color}`` token in each SVG is substituted
at render time (QSvgRenderer does not resolve CSS ``currentColor``), so the same
source tints to whatever the active theme/accent needs.

The app/brand mark (:func:`app_icon`) is deliberately multi-color and fixed; it
identifies the app in the taskbar/tray and is not theme-tinted.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import struct

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt
from PyQt6.QtGui import QIcon, QImage, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

ICON_DIR = Path(__file__).resolve().parent / "icons"
APP_SVG = ICON_DIR / "app" / "app.svg"

# Each entry is a 24x24 solid-filled glyph. `{color}` is substituted per render.
_ICONS: dict[str, str] = {
    # -- window chrome (frameless title bar) ----------------------------------
    "win_min": '<rect x="5" y="11" width="14" height="2.2" rx="1" fill="{color}"/>',
    "win_max": '<rect x="5.5" y="5.5" width="13" height="13" rx="2" fill="none" '
               'stroke="{color}" stroke-width="2"/>',
    "win_restore": '<rect x="7.5" y="7.5" width="11" height="11" rx="2" fill="none" '
                   'stroke="{color}" stroke-width="2"/>'
                   '<path d="M7.5 7.5V6a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-1.5" '
                   'fill="none" stroke="{color}" stroke-width="2"/>',
    "win_close": '<path d="M6 6l12 12M18 6L6 18" stroke="{color}" stroke-width="2.2" '
                 'stroke-linecap="round"/>',
    # -- studio / docking -----------------------------------------------------
    "dock": '<rect x="3.5" y="5" width="17" height="14" rx="2.5" fill="none" '
            'stroke="{color}" stroke-width="1.8"/>'
            '<rect x="6.5" y="8" width="11" height="8" rx="1.5" fill="{color}" opacity="0.55"/>',
    "overview": '<rect x="4" y="4.5" width="7" height="7" rx="1.5" fill="{color}"/>'
                '<rect x="13" y="4.5" width="7" height="7" rx="1.5" fill="{color}" opacity="0.55"/>'
                '<rect x="4" y="13.5" width="7" height="6" rx="1.5" fill="{color}" opacity="0.55"/>'
                '<rect x="13" y="13.5" width="7" height="6" rx="1.5" fill="{color}"/>',
    "switch": '<path d="M7 8h9l-2.5-2.5M17 16H8l2.5 2.5" fill="none" stroke="{color}" '
              'stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/>',
    # -- transport / recording ------------------------------------------------
    "record": '<circle cx="12" cy="12" r="7" fill="{color}"/>',
    "play": '<path d="M8 5.5v13l11-6.5z" fill="{color}"/>',
    "pause": '<rect x="7" y="5.5" width="3.6" height="13" rx="1" fill="{color}"/>'
             '<rect x="13.4" y="5.5" width="3.6" height="13" rx="1" fill="{color}"/>',
    "stop": '<rect x="6.5" y="6.5" width="11" height="11" rx="2" fill="{color}"/>',
    "step": '<path d="M6 5.5v13l9-6.5z" fill="{color}"/>'
            '<rect x="16" y="5.5" width="3" height="13" rx="1" fill="{color}"/>',
    # -- files ----------------------------------------------------------------
    "open": '<path d="M3 6.5A1.5 1.5 0 0 1 4.5 5h4l2 2.2h7A1.5 1.5 0 0 1 19 8.7v.8H8.2'
            'a2 2 0 0 0-1.9 1.4L4 18V6.5z" fill="{color}"/>'
            '<path d="M6.4 11.2 4.2 18.6A1 1 0 0 0 5.2 20h12.1a1.5 1.5 0 0 0 1.44-1.06'
            'l1.9-6.3A1 1 0 0 0 20.7 11H7.36a1 1 0 0 0-.96.7z" fill="{color}" opacity="0.72"/>',
    "save": '<path d="M5 4h11l3 3v13H5z" fill="{color}"/>'
            '<rect x="8" y="4" width="6" height="5" rx="0.5" fill="#ffffff" opacity="0.85"/>'
            '<rect x="11.5" y="5" width="2" height="3" fill="{color}"/>'
            '<rect x="8" y="12" width="8" height="6" rx="0.5" fill="#ffffff" opacity="0.85"/>',
    "add_file": '<path d="M6 3h7l5 5v13H6z" fill="{color}"/>'
                '<path d="M13 3v5h5" fill="none" stroke="#ffffff" stroke-width="1.4" opacity="0.7"/>'
                '<path d="M12 11v6M9 14h6" stroke="#ffffff" stroke-width="1.8" '
                'stroke-linecap="round" opacity="0.95"/>',
    # -- library / tools ------------------------------------------------------
    "library": '<rect x="4" y="4" width="4" height="16" rx="1" fill="{color}"/>'
               '<rect x="9.5" y="4" width="4" height="16" rx="1" fill="{color}" opacity="0.72"/>'
               '<rect x="15.2" y="5.4" width="4" height="14.6" rx="1" fill="{color}" '
               'opacity="0.5" transform="rotate(9 17.2 12.7)"/>',
    "editor": '<rect x="4" y="5" width="16" height="14" rx="2" fill="{color}" opacity="0.16"/>'
              '<rect x="4" y="5" width="16" height="14" rx="2" fill="none" stroke="{color}" stroke-width="1.6"/>'
              '<path d="M7 9h10M7 12h10M7 15h6" stroke="{color}" stroke-width="1.6" stroke-linecap="round"/>',
    "preferences": '<path d="M12 8.2A3.8 3.8 0 1 0 12 15.8 3.8 3.8 0 0 0 12 8.2zm0 2.4'
                   'a1.4 1.4 0 1 1 0 2.8 1.4 1.4 0 0 1 0-2.8z" fill="{color}"/>'
                   '<path d="M12 2.5l1.5 2.2 2.6-.6.5 2.6 2.4 1.1-1 2.5 1 2.5-2.4 1.1-.5 2.6'
                   '-2.6-.6L12 21.5l-1.5-2.2-2.6.6-.5-2.6-2.4-1.1 1-2.5-1-2.5 2.4-1.1.5-2.6 2.6.6z" '
                   'fill="{color}" opacity="0.5"/>',
    "pin": '<path d="M14.5 3.2 20.8 9.5l-2.2 2.2-1-.4-3.3 3.3.5 2.4-1.6 1.6-3.4-3.4-3.6 3.6'
           '-1.1-1.1 3.6-3.6-3.4-3.4 1.6-1.6 2.4.5 3.3-3.3-.4-1z" fill="{color}"/>',
    "scheduler": '<circle cx="12" cy="13" r="8" fill="{color}" opacity="0.16"/>'
                 '<circle cx="12" cy="13" r="8" fill="none" stroke="{color}" stroke-width="1.6"/>'
                 '<path d="M12 8.5V13l3 2" stroke="{color}" stroke-width="1.7" '
                 'stroke-linecap="round" fill="none"/>'
                 '<path d="M9 2.5h6" stroke="{color}" stroke-width="1.8" stroke-linecap="round"/>',
    "validate": '<circle cx="12" cy="12" r="9" fill="{color}" opacity="0.16"/>'
                '<circle cx="12" cy="12" r="9" fill="none" stroke="{color}" stroke-width="1.6"/>'
                '<path d="M7.5 12.3l3 3 6-6.5" stroke="{color}" stroke-width="2" '
                'stroke-linecap="round" stroke-linejoin="round" fill="none"/>',
    "logs": '<rect x="4" y="4" width="16" height="16" rx="2" fill="none" stroke="{color}" stroke-width="1.6"/>'
            '<path d="M7.5 9h5M7.5 12h9M7.5 15h7" stroke="{color}" stroke-width="1.6" stroke-linecap="round"/>',
    # -- editing operations ---------------------------------------------------
    "undo": '<path d="M8.5 7 4 11.5 8.5 16v-3H13a4 4 0 0 1 0 8h-1v-2h1a2 2 0 0 0 0-4H8.5z" fill="{color}"/>',
    "redo": '<path d="M15.5 7 20 11.5 15.5 16v-3H11a4 4 0 0 0 0 8h1v-2h-1a2 2 0 0 1 0-4h4.5z" fill="{color}"/>',
    "trash": '<path d="M6 7h12l-1 13H7z" fill="{color}"/>'
             '<path d="M9 5.5h6l.6 1.5H8.4z" fill="{color}"/>'
             '<path d="M4.5 7h15" stroke="{color}" stroke-width="1.6" stroke-linecap="round"/>'
             '<path d="M10 10v7M14 10v7" stroke="#ffffff" stroke-width="1.3" '
             'stroke-linecap="round" opacity="0.7"/>',
    "trim": '<path d="M8 3v13.5a2.5 2.5 0 1 1-1.6.03V3zM7.2 20.5a1.2 1.2 0 1 0 0-2.4 1.2 1.2 0 0 0 0 2.4z" '
            'fill="{color}"/>'
            '<path d="M16 3v13.5a2.5 2.5 0 1 0 1.6.03V3zM16.8 20.5a1.2 1.2 0 1 1 0-2.4 1.2 1.2 0 0 1 0 2.4z" '
            'fill="{color}" opacity="0.72"/>'
            '<path d="M8 7l8 8M16 7l-8 8" stroke="{color}" stroke-width="1.3" opacity="0.55"/>',
    "note": '<path d="M15.5 4.5 19.5 8.5 9 19l-4.5 1L5.5 15.5z" fill="{color}"/>'
            '<path d="M14 6 18 10" stroke="#ffffff" stroke-width="1.2" opacity="0.6"/>',
    "scale": '<path d="M4 4h7l-2.4 2.4 2.6 2.6-1.6 1.6-2.6-2.6L4.6 10.4V4z" fill="{color}"/>'
             '<path d="M20 20h-7l2.4-2.4-2.6-2.6 1.6-1.6 2.6 2.6 2.4-2.4V20z" fill="{color}" opacity="0.72"/>',
    "wait": '<circle cx="12" cy="12" r="8.5" fill="{color}" opacity="0.16"/>'
            '<circle cx="12" cy="12" r="8.5" fill="none" stroke="{color}" stroke-width="1.6"/>'
            '<path d="M12 7v5l3.4 2" stroke="{color}" stroke-width="1.8" '
            'stroke-linecap="round" fill="none"/>',
    "image": '<rect x="3.5" y="5" width="17" height="14" rx="2.5" fill="none" '
             'stroke="{color}" stroke-width="1.6"/>'
             '<circle cx="8.5" cy="9.5" r="1.8" fill="{color}"/>'
             '<path d="M5 17.5 10 12l3.2 3 3-2.6 3 4" fill="none" stroke="{color}" '
             'stroke-width="1.6" stroke-linejoin="round"/>',
    # -- generic actions ------------------------------------------------------
    "star_filled": '<path d="M12 3.5 14.6 9l6 .7-4.5 4 1.3 5.9L12 16.7 6.6 19.6 7.9 13.7 3.4 9.7l6-.7z" '
                   'fill="{color}"/>',
    "star_outline": '<path d="M12 3.5 14.6 9l6 .7-4.5 4 1.3 5.9L12 16.7 6.6 19.6 7.9 13.7 3.4 9.7l6-.7z" '
                    'fill="none" stroke="{color}" stroke-width="1.6" stroke-linejoin="round"/>',
    "add": '<path d="M12 4v16M4 12h16" stroke="{color}" stroke-width="2.4" stroke-linecap="round"/>',
    "remove": '<path d="M5 12h14" stroke="{color}" stroke-width="2.4" stroke-linecap="round"/>',
    "prune": '<circle cx="7" cy="7" r="2.6" fill="none" stroke="{color}" stroke-width="1.6"/>'
             '<circle cx="7" cy="17" r="2.6" fill="none" stroke="{color}" stroke-width="1.6"/>'
             '<path d="M9 8.6 20 15M9 15.4 20 9" stroke="{color}" stroke-width="1.6" stroke-linecap="round"/>',
    "close": '<path d="M6 6l12 12M18 6 6 18" stroke="{color}" stroke-width="2.2" stroke-linecap="round"/>',
    "refresh": '<path d="M19 12a7 7 0 1 1-2.05-4.95" fill="none" stroke="{color}" '
               'stroke-width="2" stroke-linecap="round"/>'
               '<path d="M19 4.5V8.2h-3.7z" fill="{color}"/>',
    "clear": '<path d="M9.5 5.5h5l3 3-6.5 9.5H8L4.5 12z" fill="{color}"/>'
             '<path d="M14 20h5" stroke="{color}" stroke-width="2" stroke-linecap="round"/>',
    "browse": '<path d="M3 6.5A1.5 1.5 0 0 1 4.5 5h4l2 2.2h7A1.5 1.5 0 0 1 19 8.7V18a1.5 1.5 0 0 1-1.5 1.5'
              'H4.5A1.5 1.5 0 0 1 3 18z" fill="{color}"/>',
    "chevron_down": '<path d="M6 9.5 12 15.5 18 9.5" fill="none" stroke="{color}" '
                    'stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>',
    "chevron_up": '<path d="M6 14.5 12 8.5 18 14.5" fill="none" stroke="{color}" '
                  'stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>',
}

_SVG_TEMPLATE = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">{body}</svg>'


def icon_names() -> list[str]:
    """All available themed-icon names (used by tests to exercise every glyph)."""
    return sorted(_ICONS)


@lru_cache(maxsize=512)
def get_icon(name: str, color: str, size: int = 20) -> QIcon:
    """Return a themed :class:`QIcon` for ``name`` tinted with ``color``.

    Raises ``KeyError`` for an unknown name so a typo fails loudly in tests
    rather than silently rendering a blank button at runtime.
    """
    body = _ICONS[name].replace("{color}", color)
    svg = _SVG_TEMPLATE.format(body=body)
    renderer = QSvgRenderer(svg.encode("utf-8"))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return QIcon(pixmap)


@lru_cache(maxsize=1)
def app_icon() -> QIcon:
    """The multi-resolution app/brand mark for the window, taskbar, and tray."""
    icon = QIcon()
    if APP_SVG.exists():
        renderer = QSvgRenderer(str(APP_SVG))
        for dimension in (16, 24, 32, 48, 64, 128, 256):
            pixmap = QPixmap(dimension, dimension)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            renderer.render(painter, QRectF(0, 0, dimension, dimension))
            painter.end()
            icon.addPixmap(pixmap)
    return icon


def _render_png(renderer: QSvgRenderer, size: int) -> bytes:
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    buffer.close()
    return bytes(data)


def render_app_ico(destination: Path, sizes: tuple[int, ...] = (16, 24, 32, 48, 64, 128, 256)) -> Path:
    """Render the app SVG into a **multi-resolution** Windows ``.ico``.

    Qt's ``QImage.save(..., "ICO")`` writes only a single image, which leaves
    Explorer without the small sizes it needs for file thumbnails (so the shell
    falls back to the default exe icon). We assemble the ICO container by hand
    with PNG-compressed entries at every size — valid on Vista+ and what modern
    Windows expects. Used by the build tooling so the packaged ``.exe`` carries
    the brand icon at every shell size.
    """
    renderer = QSvgRenderer(str(APP_SVG))
    images = [(size, _render_png(renderer, size)) for size in sorted(set(sizes))]

    header = struct.pack("<HHH", 0, 1, len(images))  # reserved, type=icon, count
    offset = 6 + 16 * len(images)
    entries = b""
    payload = b""
    for size, png in images:
        dim = 0 if size >= 256 else size  # 0 encodes 256 in the ICO spec
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(png), offset)
        payload += png
        offset += len(png)

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(header + entries + payload)
    return destination
