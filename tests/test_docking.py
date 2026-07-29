"""Window-docking behaviour for the X11 and macOS backends.

The real move/resize paths need a live X server or Quartz + Accessibility, so
here we cover the parts that are testable off-platform: enumeration filtering
(via a fake Quartz) and graceful degradation when the platform libraries or
permissions are absent.
"""
from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

from tests.test_pynput_backend import _install_fake_pynput


# -- graceful degradation (no X / no Quartz — the default on this test host) ---

def test_x11_docking_unavailable_without_xlib(monkeypatch):
    _install_fake_pynput(monkeypatch)
    monkeypatch.setitem(sys.modules, "Xlib", None)  # force the import to fail
    from tinymacro.backends.x11 import X11Backend

    backend = X11Backend()
    assert backend.supports_docking() is False
    assert backend.list_windows() == []
    assert backend.window_client_rect(123) is None
    assert backend.move_resize_window(123, 0, 0, 100, 100) is False


def test_macos_docking_unavailable_without_quartz(monkeypatch):
    _install_fake_pynput(monkeypatch)
    monkeypatch.setitem(sys.modules, "Quartz", None)
    from tinymacro.backends.macos import MacBackend

    backend = MacBackend()
    assert backend.supports_docking() is False
    assert backend.list_windows() == []


# -- macOS enumeration filtering (fake Quartz) --------------------------------

def _fake_quartz(windows):
    q = ModuleType("Quartz")
    q.kCGWindowListOptionOnScreenOnly = 1
    q.kCGWindowListExcludeDesktopElements = 16
    q.kCGNullWindowID = 0
    q.CGWindowListCopyWindowInfo = lambda opts, wid: windows
    return q


def test_macos_list_windows_filters(monkeypatch):
    _install_fake_pynput(monkeypatch)
    import os

    own = os.getpid()
    windows = [
        {"kCGWindowLayer": 0, "kCGWindowOwnerPID": 4242, "kCGWindowNumber": 11,
         "kCGWindowOwnerName": "Safari", "kCGWindowName": "Home"},
        {"kCGWindowLayer": 0, "kCGWindowOwnerPID": own, "kCGWindowNumber": 12,
         "kCGWindowOwnerName": "TinyMacro", "kCGWindowName": "Studio"},   # our own -> skip
        {"kCGWindowLayer": 25, "kCGWindowOwnerPID": 99, "kCGWindowNumber": 13,
         "kCGWindowOwnerName": "MenuBar", "kCGWindowName": "x"},          # non-zero layer -> skip
        {"kCGWindowLayer": 0, "kCGWindowOwnerPID": 77, "kCGWindowNumber": 14,
         "kCGWindowOwnerName": "", "kCGWindowName": ""},                  # empty title -> skip
        {"kCGWindowLayer": 0, "kCGWindowOwnerPID": 55, "kCGWindowNumber": 15,
         "kCGWindowOwnerName": "Notes", "kCGWindowName": ""},             # owner only, kept
    ]
    monkeypatch.setitem(sys.modules, "Quartz", _fake_quartz(windows))
    from tinymacro.backends.macos import MacBackend

    backend = MacBackend()
    listed = backend.list_windows()

    handles = {h for h, _ in listed}
    assert handles == {11, 15}
    titles = dict(listed)
    assert titles[11] == "Safari — Home"
    assert titles[15] == "Notes"
    # The index is populated so a later move/resize can find the AX window.
    assert backend._window_index[11] == (4242, "Home")


# -- both backends expose the full docking contract ---------------------------

def test_backends_expose_docking_methods(monkeypatch):
    _install_fake_pynput(monkeypatch)
    from tinymacro.backends.macos import MacBackend
    from tinymacro.backends.x11 import X11Backend

    for backend in (X11Backend(), MacBackend()):
        for method in ("supports_docking", "list_windows", "window_client_rect", "move_resize_window"):
            assert callable(getattr(backend, method))
