from __future__ import annotations

from tinymacro.core.dock import DockRegion, to_absolute, to_relative


def test_round_trip_center():
    region = DockRegion(100, 50, 1920, 1080)
    fx, fy = to_relative(100 + 960, 50 + 540, region)
    assert abs(fx - 0.5) < 1e-9 and abs(fy - 0.5) < 1e-9
    x, y = to_absolute(fx, fy, region)
    assert (x, y) == (100 + 960, 50 + 540)


def test_resolution_independence():
    # Same fraction lands at the proportional spot in a differently sized region.
    small = DockRegion(0, 0, 1280, 720)
    big = DockRegion(200, 100, 2560, 1440)
    fx, fy = to_relative(640, 360, small)  # center of small
    assert abs(fx - 0.5) < 1e-9 and abs(fy - 0.5) < 1e-9
    x, y = to_absolute(fx, fy, big)
    assert (x, y) == (200 + 1280, 100 + 720)  # center of big


def test_corners():
    region = DockRegion(10, 20, 100, 200)
    assert to_relative(10, 20, region) == (0.0, 0.0)
    assert to_relative(110, 220, region) == (1.0, 1.0)


def test_clamped_outside():
    region = DockRegion(0, 0, 100, 100)
    assert to_relative(-50, 200, region) == (0.0, 1.0)


def test_invalid_region():
    region = DockRegion(0, 0, 0, 0)
    assert region.valid is False
    assert to_relative(5, 5, region) == (0.0, 0.0)


def test_aspect_ratio():
    assert abs(DockRegion(0, 0, 1920, 1080).aspect_ratio - 16 / 9) < 1e-6
