"""On-screen image matching for the click-image step and image-trigger scheduler.

The heavy dependencies (OpenCV, NumPy, mss) are optional and only imported here,
behind :data:`VISION_AVAILABLE`. Everything that touches a real screen lives in
:class:`Locator`; the pure matching maths in :func:`match_template` takes plain
arrays/bytes so it can be unit-tested without a display.

Coordinates returned are absolute virtual-desktop pixels, ready to hand to a
backend's mouse events.
"""
from __future__ import annotations

from dataclasses import dataclass

try:  # pragma: no cover - trivial import guard
    import cv2
    import numpy as np

    _CV_AVAILABLE = True
except Exception:  # noqa: BLE001 - any import failure means the feature is off
    cv2 = None  # type: ignore[assignment]
    np = None  # type: ignore[assignment]
    _CV_AVAILABLE = False

try:  # pragma: no cover - trivial import guard
    import mss

    _MSS_AVAILABLE = True
except Exception:  # noqa: BLE001
    mss = None  # type: ignore[assignment]
    _MSS_AVAILABLE = False

# Matching (numpy/opencv) is enough for tests; capture additionally needs mss.
VISION_AVAILABLE = _CV_AVAILABLE
CAPTURE_AVAILABLE = _CV_AVAILABLE and _MSS_AVAILABLE

# Region is (left, top, width, height) in absolute desktop pixels.
Region = tuple[int, int, int, int]


@dataclass(frozen=True, slots=True)
class Match:
    """A located template: the click point plus the confidence score."""

    x: int
    y: int
    score: float


def _require_cv() -> None:
    if not _CV_AVAILABLE:
        raise RuntimeError(
            "Image matching needs the optional 'vision' extras. "
            "Install with: pip install \"tiny-macro[vision]\""
        )


def decode_png(png_bytes: bytes) -> "np.ndarray":
    """Decode PNG bytes into a BGR image array."""
    _require_cv()
    buffer = np.frombuffer(png_bytes, dtype=np.uint8)
    image = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Could not decode image bytes")
    return image


def encode_png(image: "np.ndarray") -> bytes:
    """Encode a BGR image array to PNG bytes (used by the region-capture tool)."""
    _require_cv()
    ok, buffer = cv2.imencode(".png", image)
    if not ok:
        raise ValueError("Could not encode image")
    return bytes(buffer.tobytes())


def match_in_image(
    haystack_bgr: "np.ndarray",
    needle_bgr: "np.ndarray",
    confidence: float = 0.85,
    grayscale: bool = True,
) -> Match | None:
    """Locate ``needle`` inside ``haystack``; return the center + score or None.

    Pure array-in/array-out so it is unit-testable without any screen. The
    returned point is the center of the match in ``haystack`` pixel coordinates
    (add the capture region's origin to make it absolute).
    """
    _require_cv()
    h_h, h_w = haystack_bgr.shape[:2]
    n_h, n_w = needle_bgr.shape[:2]
    if n_h > h_h or n_w > h_w:
        # A template larger than the search area can never match.
        return None

    if grayscale:
        haystack = cv2.cvtColor(haystack_bgr, cv2.COLOR_BGR2GRAY)
        needle = cv2.cvtColor(needle_bgr, cv2.COLOR_BGR2GRAY)
    else:
        haystack, needle = haystack_bgr, needle_bgr

    result = cv2.matchTemplate(haystack, needle, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)
    if max_val < confidence:
        return None
    center_x = int(max_loc[0] + n_w / 2)
    center_y = int(max_loc[1] + n_h / 2)
    return Match(center_x, center_y, float(max_val))


def match_template(
    haystack_png: bytes,
    needle_png: bytes,
    confidence: float = 0.85,
    grayscale: bool = True,
) -> Match | None:
    """PNG-bytes convenience wrapper over :func:`match_in_image`."""
    return match_in_image(
        decode_png(haystack_png), decode_png(needle_png), confidence, grayscale
    )


class Locator:
    """Captures the screen (via mss) and locates templates on it.

    One instance owns one ``mss`` handle. ``mss`` is not thread-safe, so create a
    Locator on the thread that will use it (the player worker or the image-watcher
    thread), not shared across threads.
    """

    def __init__(self) -> None:
        if not CAPTURE_AVAILABLE:
            raise RuntimeError(
                "Screen capture needs the optional 'vision' extras (opencv + mss). "
                "Install with: pip install \"tiny-macro[vision]\""
            )
        self._sct = mss.mss()

    def close(self) -> None:
        try:
            self._sct.close()
        except Exception:  # noqa: BLE001
            pass

    def __enter__(self) -> "Locator":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def _grab(self, region: Region | None) -> tuple["np.ndarray", int, int]:
        """Return (bgr_image, origin_x, origin_y) for the requested area."""
        if region:
            left, top, width, height = region
            monitor = {"left": left, "top": top, "width": width, "height": height}
            origin_x, origin_y = left, top
        else:
            # monitors[0] is the full virtual desktop across all screens.
            monitor = self._sct.monitors[0]
            origin_x, origin_y = monitor["left"], monitor["top"]
        shot = self._sct.grab(monitor)
        # mss returns BGRA; drop alpha to BGR for OpenCV.
        frame = np.asarray(shot)[:, :, :3]
        return frame, origin_x, origin_y

    def locate(
        self,
        needle_png: bytes,
        confidence: float = 0.85,
        region: Region | None = None,
        grayscale: bool = True,
    ) -> Match | None:
        """Capture the screen (or ``region``) and locate ``needle_png`` on it.

        The returned :class:`Match` is in **absolute** desktop coordinates.
        """
        needle = decode_png(needle_png)
        haystack, origin_x, origin_y = self._grab(region)
        found = match_in_image(haystack, needle, confidence, grayscale)
        if found is None:
            return None
        return Match(found.x + origin_x, found.y + origin_y, found.score)
