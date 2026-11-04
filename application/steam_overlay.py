"""Non-invasive heuristic for Steam's in-game overlay on Windows.

Steam and Elden Ring keep the same foreground HWND. On the observed setup the
Steam UI captures the game window, uses the Windows arrow, and releases cursor
clipping to the virtual desktop. None of these signals alone identifies Steam.
"""
import ctypes
import os
import time
import winreg
from ctypes import wintypes

import win32api
import win32con
import win32gui
import win32process


class _GuiThreadInfo(ctypes.Structure):
    _fields_ = [
        ('cbSize', wintypes.DWORD), ('flags', wintypes.DWORD),
        ('hwndActive', wintypes.HWND), ('hwndFocus', wintypes.HWND),
        ('hwndCapture', wintypes.HWND), ('hwndMenuOwner', wintypes.HWND),
        ('hwndMoveSize', wintypes.HWND), ('hwndCaret', wintypes.HWND),
        ('rcCaret', wintypes.RECT),
    ]


def overlay_indicators_match(game_hwnd, captured_hwnd, cursor_visible, cursor, arrow, clip, desktop):
    """Match all observed indicators; missing Windows data fails open."""
    return bool(game_hwnd and captured_hwnd == game_hwnd and cursor_visible and cursor and
                cursor == arrow and clip and desktop and
                clip[0] <= desktop[0] and clip[1] <= desktop[1] and
                clip[2] >= desktop[2] and clip[3] >= desktop[3])


def has_overlay_indicators(game_hwnd):
    if not game_hwnd:
        return False
    try:
        tid, _ = win32process.GetWindowThreadProcessId(game_hwnd)
        info = _GuiThreadInfo()
        info.cbSize = ctypes.sizeof(info)
        if not ctypes.windll.user32.GetGUIThreadInfo(tid, ctypes.byref(info)):
            return False
        flags, cursor, _ = win32gui.GetCursorInfo()
        arrow = win32gui.LoadCursor(0, win32con.IDC_ARROW)
        rect = wintypes.RECT()
        if not ctypes.windll.user32.GetClipCursor(ctypes.byref(rect)):
            return False
        x, y = win32api.GetSystemMetrics(76), win32api.GetSystemMetrics(77)
        desktop = (x, y, x + win32api.GetSystemMetrics(78), y + win32api.GetSystemMetrics(79))
        return overlay_indicators_match(game_hwnd, info.hwndCapture, bool(flags & 1), cursor, arrow,
                                        (rect.left, rect.top, rect.right, rect.bottom), desktop)
    except (OSError, ValueError, TypeError, win32gui.error):
        return False


def is_steam_overlay_window(foreground_hwnd, game_hwnd):
    """Recognize an overlay-owned foreground window associated with this game.

    Checking only the process name would confuse overlays from other games.
    Require both the actual Steam installation path and the game owner chain.
    Unknown or inaccessible windows are not considered evidence.
    """
    if not foreground_hwnd or not game_hwnd or foreground_hwnd == game_hwnd:
        return False
    try:
        owner = foreground_hwnd
        found_game = False
        for _ in range(16):
            owner = win32gui.GetWindow(owner, win32con.GW_OWNER)
            if not owner:
                break
            if owner == game_hwnd:
                found_game = True
                break
        if not found_game:
            return False
        _, pid = win32process.GetWindowThreadProcessId(foreground_hwnd)
        kernel = ctypes.windll.kernel32
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        kernel.QueryFullProcessImageNameW.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        try:
            buffer = ctypes.create_unicode_buffer(32768)
            length = wintypes.DWORD(len(buffer))
            if not kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(length)):
                return False
            executable = os.path.normcase(os.path.normpath(buffer.value))
        finally:
            kernel.CloseHandle(handle)
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam') as key:
            root = os.path.normcase(os.path.normpath(winreg.QueryValueEx(key, 'SteamPath')[0]))
        return executable in {os.path.join(root, 'gameoverlayui.exe'), os.path.join(root, 'gameoverlayui64.exe')}
    except (OSError, ValueError, TypeError, win32gui.error):
        return False


class OverlayDetector:
    def __init__(self, confirmation_seconds=0.4):
        self.confirmation_seconds = confirmation_seconds
        self._since = None

    def update(self, game_hwnd, now=None, overlay_window=False):
        now = time.monotonic() if now is None else now
        if not overlay_window and not has_overlay_indicators(game_hwnd):
            self._since = None
            return False
        if self._since is None:
            self._since = now
        return now - self._since >= self.confirmation_seconds
