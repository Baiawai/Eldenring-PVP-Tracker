"""Detect the game display and capture in virtual-desktop coordinates."""
import win32api
import win32con
import win32gui
from PIL import ImageGrab


def game_display():
    """Return the game window's monitor, or None while it cannot be located."""
    try:
        hwnd = win32gui.FindWindow(None, 'ELDEN RING™')
        if not hwnd or win32gui.IsIconic(hwnd):
            return None
        monitor = win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONULL)
        if not monitor:
            return None
        info = win32api.GetMonitorInfo(monitor)
        left, top, right, bottom = info['Monitor']
        if right <= left or bottom <= top:
            return None
        return {'name': info.get('Device', ''), 'x': left, 'y': top,
                'width': right - left, 'height': bottom - top}
    except (OSError, win32api.error, ValueError, KeyError):
        return None


def capture(display, filename=None, region=None):
    x, y, width, height = (display[key] for key in ('x', 'y', 'width', 'height'))
    if region is not None:
        left, top, w, h = (int(value) for value in region)
        if left < 0 or top < 0 or w <= 0 or h <= 0 or left + w > width or top + h > height:
            raise ValueError('Capture region outside display')
        x, y, width, height = x + left, y + top, w, h
    image = ImageGrab.grab(bbox=(x, y, x + width, y + height), all_screens=True)
    if filename:
        image.save(filename)
    return image
