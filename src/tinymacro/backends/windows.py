from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import threading

from tinymacro.backends.base import BackendCapabilities, EventCallback, HotkeyCallback, InputBackend
from tinymacro.core.events import MacroEvent


WH_KEYBOARD_LL = 13
WH_MOUSE_LL = 14
WM_QUIT = 0x0012
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_MBUTTONDOWN = 0x0207
WM_MBUTTONUP = 0x0208
WM_MOUSEWHEEL = 0x020A
WM_MOUSEHWHEEL = 0x020E
LLKHF_INJECTED = 0x10
LLMHF_INJECTED = 0x01
WHEEL_DELTA = 120

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
KEYEVENTF_EXTENDEDKEY = 0x0001
MAPVK_VK_TO_VSC = 0

# Virtual keys that live on the "extended" part of the keyboard and need the
# extended-key flag so scan-code injection maps them correctly.
EXTENDED_VKS = {
    0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28,  # pgup/pgdn/end/home/arrows
    0x2D, 0x2E,  # insert / delete
    0x5B, 0x5C,  # left/right win
    0x90,        # numlock
    0xA3, 0xA5,  # right ctrl / right alt
    0x6F,        # numpad divide
}
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x01000
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

VK_ALIASES = {
    "backspace": 0x08,
    "tab": 0x09,
    "enter": 0x0D,
    "return": 0x0D,
    "shift": 0x10,
    "ctrl": 0x11,
    "control": 0x11,
    "alt": 0x12,
    "pause": 0x13,
    "break": 0x13,
    "capslock": 0x14,
    "esc": 0x1B,
    "escape": 0x1B,
    "space": 0x20,
    "pageup": 0x21,
    "pagedown": 0x22,
    "end": 0x23,
    "home": 0x24,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "insert": 0x2D,
    "delete": 0x2E,
    "super": 0x5B,
    "meta": 0x5B,
    "win": 0x5B,
    "leftctrl": 0xA2,
    "rightctrl": 0xA3,
    "leftshift": 0xA0,
    "rightshift": 0xA1,
    "leftalt": 0xA4,
    "rightalt": 0xA5,
    "scrolllock": 0x91,
}

VK_NAMES = {
    0x08: "backspace",
    0x09: "tab",
    0x0D: "enter",
    0x10: "shift",
    0x11: "ctrl",
    0x12: "alt",
    0x13: "pause",
    0x14: "capslock",
    0x1B: "esc",
    0x20: "space",
    0x21: "pageup",
    0x22: "pagedown",
    0x23: "end",
    0x24: "home",
    0x25: "left",
    0x26: "up",
    0x27: "right",
    0x28: "down",
    0x2D: "insert",
    0x2E: "delete",
    0x5B: "super",
    0x5C: "super",
    0x91: "scrolllock",
    0xA0: "shift",
    0xA1: "shift",
    0xA2: "ctrl",
    0xA3: "ctrl",
    0xA4: "alt",
    0xA5: "alt",
}

BUTTON_FLAGS = {
    "left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
    "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
    "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
}


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


WNDENUMPROC = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)(
    wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
)

GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
SW_RESTORE = 9


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", POINT),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", INPUT_UNION)]


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", POINT),
    ]


HOOKPROC = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)(
    ctypes.c_ssize_t,
    ctypes.c_int,
    wintypes.WPARAM,
    wintypes.LPARAM,
)


def _signed_high_word(value: int) -> int:
    word = (value >> 16) & 0xFFFF
    return word - 0x10000 if word & 0x8000 else word


def _key_name(vk_code: int) -> str:
    if 0x30 <= vk_code <= 0x39:
        return chr(vk_code).lower()
    if 0x41 <= vk_code <= 0x5A:
        return chr(vk_code).lower()
    if 0x70 <= vk_code <= 0x87:
        return f"f{vk_code - 0x6F}"
    return VK_NAMES.get(vk_code, f"vk{vk_code}")


def _vk_code(key: str) -> int:
    normalized = key.strip().lower().replace(" ", "")
    if len(normalized) == 1 and normalized.isalnum():
        return ord(normalized.upper())
    if normalized.startswith("f") and normalized[1:].isdigit():
        number = int(normalized[1:])
        if 1 <= number <= 24:
            return 0x6F + number
    if normalized.startswith("vk") and normalized[2:].isdigit():
        return int(normalized[2:])
    try:
        return VK_ALIASES[normalized]
    except KeyError as exc:
        raise ValueError(f"Unsupported Windows key: {key}") from exc


class WindowsBackend(InputBackend):
    name = "windows"
    capabilities = BackendCapabilities(capture=True, playback=True, global_hotkeys=True)

    def __init__(self) -> None:
        if os.name != "nt":
            raise RuntimeError("The Windows backend can only run on Windows")
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        try:
            self.winmm = ctypes.WinDLL("winmm")
        except Exception:  # noqa: BLE001
            self.winmm = None
        self._timer_period_active = False
        self._configure_api()
        self._capture_callback: EventCallback | None = None
        self._hotkey_callback: HotkeyCallback | None = None
        self._pressed: set[str] = set()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._thread_id = 0
        self._keyboard_hook = None
        self._mouse_hook = None
        self._keyboard_proc = HOOKPROC(self._keyboard_hook_proc)
        self._mouse_proc = HOOKPROC(self._mouse_hook_proc)
        self._ready = threading.Event()
        self._startup_error: Exception | None = None

    def start_capture(self, callback: EventCallback) -> None:
        with self._lock:
            self._capture_callback = callback
        self._ensure_hook_thread()

    def stop_capture(self) -> None:
        with self._lock:
            self._capture_callback = None
            should_stop = self._hotkey_callback is None
        if should_stop:
            self._stop_hook_thread()

    def emit(self, event: MacroEvent) -> None:
        if event.kind == "key" and event.key:
            self._send_keyboard(_vk_code(event.key), event.action == "release")
        elif event.kind == "mouse":
            if event.x is not None and event.y is not None:
                self._send_mouse_absolute(event.x, event.y)
            elif event.dx or event.dy:
                self._send_mouse(int(event.dx), int(event.dy), 0, MOUSEEVENTF_MOVE)
            if event.button and event.action in {"press", "release"}:
                down_flag, up_flag = BUTTON_FLAGS.get(event.button.lower(), BUTTON_FLAGS["left"])
                self._send_mouse(0, 0, 0, down_flag if event.action == "press" else up_flag)
        elif event.kind == "wheel":
            if event.dy:
                self._send_mouse(0, 0, int(event.dy) * WHEEL_DELTA, MOUSEEVENTF_WHEEL)
            if event.dx:
                self._send_mouse(0, 0, int(event.dx) * WHEEL_DELTA, MOUSEEVENTF_HWHEEL)

    def start_hotkeys(self, callback: HotkeyCallback) -> None:
        with self._lock:
            self._hotkey_callback = callback
        self._ensure_hook_thread()

    def stop_hotkeys(self) -> None:
        with self._lock:
            self._hotkey_callback = None
            self._pressed.clear()
            should_stop = self._capture_callback is None
        if should_stop:
            self._stop_hook_thread()

    def close(self) -> None:
        super().close()
        self._stop_hook_thread()

    def _configure_api(self) -> None:
        self.user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
        self.user32.SetWindowsHookExW.restype = wintypes.HHOOK
        self.user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
        self.user32.CallNextHookEx.restype = ctypes.c_ssize_t
        self.user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
        self.user32.UnhookWindowsHookEx.restype = wintypes.BOOL
        self.user32.GetMessageW.argtypes = [ctypes.POINTER(MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
        self.user32.GetMessageW.restype = wintypes.BOOL
        self.user32.TranslateMessage.argtypes = [ctypes.POINTER(MSG)]
        self.user32.DispatchMessageW.argtypes = [ctypes.POINTER(MSG)]
        self.user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        self.user32.PostThreadMessageW.restype = wintypes.BOOL
        self.user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
        self.user32.SendInput.restype = wintypes.UINT
        self.user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
        self.user32.GetCursorPos.restype = wintypes.BOOL
        self.user32.GetSystemMetrics.argtypes = [ctypes.c_int]
        self.user32.GetSystemMetrics.restype = ctypes.c_int
        self.user32.MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]
        self.user32.MapVirtualKeyW.restype = wintypes.UINT
        self.user32.GetForegroundWindow.restype = wintypes.HWND
        self.user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        self.user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        self.user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        self.user32.SetForegroundWindow.restype = wintypes.BOOL
        self.user32.BringWindowToTop.argtypes = [wintypes.HWND]
        self.user32.BringWindowToTop.restype = wintypes.BOOL
        self.user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
        self.user32.AttachThreadInput.restype = wintypes.BOOL
        self.user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        self.user32.ShowWindow.restype = wintypes.BOOL
        self.user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
        self.user32.EnumWindows.restype = wintypes.BOOL
        self.user32.IsWindowVisible.argtypes = [wintypes.HWND]
        self.user32.IsWindowVisible.restype = wintypes.BOOL
        self.user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        self.user32.GetWindowTextLengthW.restype = ctypes.c_int
        self.user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        self.user32.GetWindowTextW.restype = ctypes.c_int
        self.user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
        self.user32.GetWindowRect.restype = wintypes.BOOL
        self.user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
        self.user32.GetClientRect.restype = wintypes.BOOL
        self.user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(POINT)]
        self.user32.ClientToScreen.restype = wintypes.BOOL
        self.user32.SetWindowPos.argtypes = [
            wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
            ctypes.c_int, ctypes.c_int, wintypes.UINT,
        ]
        self.user32.SetWindowPos.restype = wintypes.BOOL
        self.user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        self.user32.GetWindowLongW.restype = wintypes.LONG
        self.kernel32.GetCurrentThreadId.restype = wintypes.DWORD
        self.kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        self.kernel32.GetModuleHandleW.restype = wintypes.HMODULE

    def _ensure_hook_thread(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._ready.clear()
            self._startup_error = None
            self._thread = threading.Thread(target=self._hook_loop, name="tiny-macro-windows-hooks", daemon=True)
            self._thread.start()
        if not self._ready.wait(timeout=3):
            raise RuntimeError("Timed out while starting Windows input hooks")
        if self._startup_error:
            raise RuntimeError(str(self._startup_error))

    def pointer_position(self) -> tuple[int, int] | None:
        point = POINT()
        if not self.user32.GetCursorPos(ctypes.byref(point)):
            return None
        return int(point.x), int(point.y)

    def begin_precise_timing(self) -> None:
        # Raise the system timer resolution to 1ms so the player's short sleeps
        # are accurate (default Windows granularity is ~15.6ms, which makes
        # densely-timed events drift). Paired with end_precise_timing().
        if self.winmm is not None and not self._timer_period_active:
            try:
                self.winmm.timeBeginPeriod(1)
                self._timer_period_active = True
            except Exception:  # noqa: BLE001
                pass

    def end_precise_timing(self) -> None:
        if self.winmm is not None and self._timer_period_active:
            try:
                self.winmm.timeEndPeriod(1)
            except Exception:  # noqa: BLE001
                pass
            self._timer_period_active = False

    def foreground_window_if_external(self) -> int:
        hwnd = self.user32.GetForegroundWindow()
        if not hwnd:
            return 0
        pid = wintypes.DWORD(0)
        self.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == os.getpid():
            return 0  # one of our own windows
        return int(hwnd)

    def focus_window(self, handle: int) -> bool:
        """Force keyboard focus to ``handle`` so key playback lands there.

        Uses the AttachThreadInput trick to get around SetForegroundWindow's
        focus-stealing restrictions.
        """
        if not handle:
            return False
        hwnd = wintypes.HWND(handle)
        target_thread = self.user32.GetWindowThreadProcessId(hwnd, None)
        current_thread = self.kernel32.GetCurrentThreadId()
        attached = False
        try:
            if target_thread and target_thread != current_thread:
                attached = bool(self.user32.AttachThreadInput(current_thread, target_thread, True))
            self.user32.ShowWindow(hwnd, 5)  # SW_SHOW (no-op if already visible)
            self.user32.BringWindowToTop(hwnd)
            return bool(self.user32.SetForegroundWindow(hwnd))
        finally:
            if attached:
                self.user32.AttachThreadInput(current_thread, target_thread, False)

    # -- window docking -------------------------------------------------------
    def supports_docking(self) -> bool:
        return True

    def list_windows(self) -> list[tuple[int, str]]:
        results: list[tuple[int, str]] = []
        own_pid = os.getpid()

        def callback(hwnd, _lparam):
            if not self.user32.IsWindowVisible(hwnd):
                return True
            ex_style = self.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            if ex_style & WS_EX_TOOLWINDOW:
                return True  # skip tool/utility windows
            length = self.user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True
            buffer = ctypes.create_unicode_buffer(length + 1)
            self.user32.GetWindowTextW(hwnd, buffer, length + 1)
            title = buffer.value
            if not title:
                return True
            pid = wintypes.DWORD(0)
            self.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == own_pid:
                return True  # never list our own windows
            results.append((int(hwnd), title))
            return True

        self.user32.EnumWindows(WNDENUMPROC(callback), 0)
        return results

    def window_client_rect(self, handle: int) -> tuple[int, int, int, int] | None:
        hwnd = wintypes.HWND(handle)
        client = RECT()
        if not self.user32.GetClientRect(hwnd, ctypes.byref(client)):
            return None
        origin = POINT(0, 0)
        if not self.user32.ClientToScreen(hwnd, ctypes.byref(origin)):
            return None
        width = client.right - client.left
        height = client.bottom - client.top
        return (int(origin.x), int(origin.y), int(width), int(height))

    def move_resize_window(self, handle: int, left: int, top: int, width: int, height: int) -> bool:
        """Size the window so its *client area* fills (left, top, width, height).

        SetWindowPos works on the whole window rect, so we add the non-client
        borders (title bar / frame) computed from the current window vs client
        rects. Without this compensation the title bar eats into the aperture and
        the client area falls short of filling the void.
        """
        if width <= 0 or height <= 0:
            return False
        hwnd = wintypes.HWND(handle)
        # Restore first so a maximized/minimized target has meaningful rects.
        self.user32.ShowWindow(hwnd, SW_RESTORE)
        window = RECT()
        client = RECT()
        if not self.user32.GetWindowRect(hwnd, ctypes.byref(window)):
            return False
        if not self.user32.GetClientRect(hwnd, ctypes.byref(client)):
            return False
        client_origin = POINT(0, 0)
        self.user32.ClientToScreen(hwnd, ctypes.byref(client_origin))
        border_left = client_origin.x - window.left
        border_top = client_origin.y - window.top
        extra_w = (window.right - window.left) - (client.right - client.left)
        extra_h = (window.bottom - window.top) - (client.bottom - client.top)
        return bool(
            self.user32.SetWindowPos(
                hwnd, None,
                int(left) - border_left, int(top) - border_top,
                int(width) + extra_w, int(height) + extra_h,
                SWP_NOZORDER | SWP_NOACTIVATE | SWP_SHOWWINDOW,
            )
        )

    def _stop_hook_thread(self) -> None:
        with self._lock:
            thread = self._thread
            thread_id = self._thread_id
        if thread and thread.is_alive() and thread_id:
            self.user32.PostThreadMessageW(thread_id, WM_QUIT, 0, 0)
            thread.join(timeout=2)
        with self._lock:
            if self._thread is thread:
                self._thread = None
                self._thread_id = 0
                self._keyboard_hook = None
                self._mouse_hook = None

    def _hook_loop(self) -> None:
        self._thread_id = int(self.kernel32.GetCurrentThreadId())
        module = self.kernel32.GetModuleHandleW(None)
        keyboard_hook = self.user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._keyboard_proc, module, 0)
        mouse_hook = self.user32.SetWindowsHookExW(WH_MOUSE_LL, self._mouse_proc, module, 0)
        if not keyboard_hook or not mouse_hook:
            self._startup_error = ctypes.WinError(ctypes.get_last_error())
            if keyboard_hook:
                self.user32.UnhookWindowsHookEx(keyboard_hook)
            if mouse_hook:
                self.user32.UnhookWindowsHookEx(mouse_hook)
            self._ready.set()
            return
        self._keyboard_hook = keyboard_hook
        self._mouse_hook = mouse_hook
        self._ready.set()
        msg = MSG()
        try:
            while self.user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                self.user32.TranslateMessage(ctypes.byref(msg))
                self.user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            self.user32.UnhookWindowsHookEx(keyboard_hook)
            self.user32.UnhookWindowsHookEx(mouse_hook)

    def _keyboard_hook_proc(self, code: int, w_param: int, l_param: int) -> int:
        if code < 0:
            return self.user32.CallNextHookEx(self._keyboard_hook, code, w_param, l_param)
        data = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
        if not data.flags & LLKHF_INJECTED:
            action = None
            if w_param in {WM_KEYDOWN, WM_SYSKEYDOWN}:
                action = "press"
            elif w_param in {WM_KEYUP, WM_SYSKEYUP}:
                action = "release"
            if action:
                self._dispatch_event(MacroEvent(0, "key", action, key=_key_name(int(data.vkCode))))
        return self.user32.CallNextHookEx(self._keyboard_hook, code, w_param, l_param)

    def _mouse_hook_proc(self, code: int, w_param: int, l_param: int) -> int:
        if code < 0:
            return self.user32.CallNextHookEx(self._mouse_hook, code, w_param, l_param)
        data = ctypes.cast(l_param, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
        if data.flags & LLMHF_INJECTED:
            return self.user32.CallNextHookEx(self._mouse_hook, code, w_param, l_param)
        event = self._mouse_event_from_message(int(w_param), data)
        if event:
            self._dispatch_event(event)
        return self.user32.CallNextHookEx(self._mouse_hook, code, w_param, l_param)

    def _mouse_event_from_message(self, message: int, data: MSLLHOOKSTRUCT) -> MacroEvent | None:
        x = int(data.pt.x)
        y = int(data.pt.y)
        if message == WM_MOUSEMOVE:
            return MacroEvent(0, "mouse", "move", x=x, y=y)
        button_messages = {
            WM_LBUTTONDOWN: ("press", "left"),
            WM_LBUTTONUP: ("release", "left"),
            WM_RBUTTONDOWN: ("press", "right"),
            WM_RBUTTONUP: ("release", "right"),
            WM_MBUTTONDOWN: ("press", "middle"),
            WM_MBUTTONUP: ("release", "middle"),
        }
        if message in button_messages:
            action, button = button_messages[message]
            return MacroEvent(0, "mouse", action, button=button, x=x, y=y)
        if message == WM_MOUSEWHEEL:
            return MacroEvent(0, "wheel", "scroll", x=x, y=y, dy=int(_signed_high_word(int(data.mouseData)) / WHEEL_DELTA))
        if message == WM_MOUSEHWHEEL:
            return MacroEvent(0, "wheel", "scroll", x=x, y=y, dx=int(_signed_high_word(int(data.mouseData)) / WHEEL_DELTA))
        return None

    def _dispatch_event(self, event: MacroEvent) -> None:
        if event.kind == "key" and event.key:
            self._update_hotkeys(event)
        with self._lock:
            callback = self._capture_callback
        if callback:
            callback(event)

    def _update_hotkeys(self, event: MacroEvent) -> None:
        key = event.key.lower() if event.key else ""
        with self._lock:
            callback = self._hotkey_callback
            if not callback:
                return
            if event.action == "press":
                if key in self._pressed:
                    return
                self._pressed.add(key)
                pressed = frozenset(self._pressed)
            elif event.action == "release":
                self._pressed.discard(key)
                return
            else:
                return
        callback(pressed)

    def _send_keyboard(self, vk_code: int, is_up: bool) -> None:
        """Inject a key using its hardware scan code.

        Games (Roblox, most DirectInput/Raw-Input titles) ignore virtual-key
        SendInput events and only react to scan codes, so we map the VK to a scan
        code and set KEYEVENTF_SCANCODE. Regular apps handle scan codes too. If a
        VK has no scan code we fall back to the virtual-key form.
        """
        scan = int(self.user32.MapVirtualKeyW(vk_code, MAPVK_VK_TO_VSC))
        if scan:
            flags = KEYEVENTF_SCANCODE
            if vk_code in EXTENDED_VKS:
                flags |= KEYEVENTF_EXTENDEDKEY
            if is_up:
                flags |= KEYEVENTF_KEYUP
            keybd = KEYBDINPUT(0, scan, flags, 0, 0)
        else:
            keybd = KEYBDINPUT(vk_code, 0, KEYEVENTF_KEYUP if is_up else 0, 0, 0)
        self._send_input(INPUT(type=INPUT_KEYBOARD, union=INPUT_UNION(ki=keybd)))

    def _send_mouse_absolute(self, x: int, y: int) -> None:
        left = self.user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
        top = self.user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
        width = max(1, self.user32.GetSystemMetrics(SM_CXVIRTUALSCREEN))
        height = max(1, self.user32.GetSystemMetrics(SM_CYVIRTUALSCREEN))
        absolute_x = int(round((x - left) * 65535 / max(1, width - 1)))
        absolute_y = int(round((y - top) * 65535 / max(1, height - 1)))
        self._send_mouse(absolute_x, absolute_y, 0, MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK)

    def _send_mouse(self, dx: int, dy: int, mouse_data: int, flags: int) -> None:
        item = INPUT(type=INPUT_MOUSE, union=INPUT_UNION(mi=MOUSEINPUT(dx, dy, mouse_data, flags, 0, 0)))
        self._send_input(item)

    def _send_input(self, item: INPUT) -> None:
        sent = self.user32.SendInput(1, ctypes.byref(item), ctypes.sizeof(INPUT))
        if sent != 1:
            raise ctypes.WinError(ctypes.get_last_error())
