"""Relative-coordinate engine for the Studio UI's docked-window mode.

A :class:`DockRegion` is the on-screen rectangle of the Studio docking aperture.
Recording converts absolute pointer coordinates into fractions of that rectangle
(0..1); playback converts them back using the region as it is at replay time.
Because the coordinates are normalised, a macro recorded in one window size
replays correctly at any other size or screen resolution, which is what makes
Studio macros distributable.

Everything here is pure (no Qt / no OS calls) so it is trivially unit-testable.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DockRegion:
    """The Studio docking aperture, in absolute screen pixels."""

    left: int
    top: int
    width: int
    height: int

    @property
    def valid(self) -> bool:
        return self.width > 0 and self.height > 0

    @property
    def aspect_ratio(self) -> float:
        return self.width / self.height if self.height else 0.0


def scale_to_physical(
    left: float, top: float, width: float, height: float, device_pixel_ratio: float
) -> DockRegion:
    """Convert a logical (Qt device-independent) rectangle to physical pixels.

    Qt reports widget geometry in logical points, but the Windows APIs we drive
    the docked window with — ``SetWindowPos`` — and the low-level mouse hook that
    records pointer positions both work in physical device pixels. On a scaled
    display (e.g. 125%) those differ, which is what made the docked window land
    small and off-centre. Multiplying by the screen's device-pixel ratio brings
    the region into the same physical space as everything else.

    Assumes a single scale factor across the layout (true for one monitor, and for
    multi-monitor setups where every screen shares the same scale).
    """
    ratio = device_pixel_ratio or 1.0
    return DockRegion(
        round(left * ratio),
        round(top * ratio),
        round(width * ratio),
        round(height * ratio),
    )


def to_relative(x: int, y: int, region: DockRegion) -> tuple[float, float]:
    """Absolute screen point → (fx, fy) as fractions of ``region`` (clamped 0..1)."""
    if not region.valid:
        return 0.0, 0.0
    fx = (x - region.left) / region.width
    fy = (y - region.top) / region.height
    return _clamp01(fx), _clamp01(fy)


def to_absolute(fx: float, fy: float, region: DockRegion) -> tuple[int, int]:
    """(fx, fy) fractions → absolute screen point inside ``region``."""
    x = region.left + fx * region.width
    y = region.top + fy * region.height
    return int(round(x)), int(round(y))


def _clamp01(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value
