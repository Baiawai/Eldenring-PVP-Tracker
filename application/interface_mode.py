"""Persistent interface mode and launching a local Chromium app window."""
import os
import sqlite3
import subprocess
import threading
import time
import webbrowser
from contextlib import closing
from pathlib import Path
import win32api
import win32con
import win32gui
import win32process
from application.init import database_setting


def get_mode():
    with closing(sqlite3.connect(database_setting, timeout=10)) as con:
        con.execute('CREATE TABLE IF NOT EXISTS interface_mode (id INTEGER PRIMARY KEY CHECK(id=1), mode TEXT NOT NULL)')
        row = con.execute('SELECT mode FROM interface_mode WHERE id=1').fetchone()
    return row[0] if row and row[0] in ('browser', 'window') else 'browser'


def set_mode(mode):
    if mode not in ('browser', 'window'):
        raise ValueError('Invalid interface mode')
    with closing(sqlite3.connect(database_setting, timeout=10)) as con, con:
        con.execute('CREATE TABLE IF NOT EXISTS interface_mode (id INTEGER PRIMARY KEY CHECK(id=1), mode TEXT NOT NULL)')
        con.execute('INSERT INTO interface_mode(id,mode) VALUES(1,?) ON CONFLICT(id) DO UPDATE SET mode=excluded.mode', (mode,))


def browser_executable():
    """Prefer the user's Chromium default, otherwise use an installed Chromium browser."""
    default = ''
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice') as key:
            default = winreg.QueryValueEx(key, 'ProgId')[0].lower()
    except OSError:
        pass
    names = ['msedge.exe', 'chrome.exe'] if 'edge' in default else ['chrome.exe', 'msedge.exe']
    roots = [os.environ.get('PROGRAMFILES', ''), os.environ.get('PROGRAMFILES(X86)', ''), os.environ.get('LOCALAPPDATA', '')]
    for name in names:
        subdir = ('Microsoft/Edge/Application/' if name == 'msedge.exe' else 'Google/Chrome/Application/') + name
        for root in roots:
            if root:
                path = Path(root) / subdir
                if path.is_file():
                    return str(path)
    return None


def _app_windows(executable):
    """Find visible tracker app windows belonging to the selected browser."""
    windows = set()
    expected = os.path.normcase(os.path.abspath(executable))

    def inspect(hwnd, _):
        try:
            if (not win32gui.IsWindowVisible(hwnd) or
                    win32gui.GetClassName(hwnd) != 'Chrome_WidgetWin_1' or
                    win32gui.GetWindowText(hwnd) != 'Elden PVP Tracker'):
                return
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            handle = win32api.OpenProcess(win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_VM_READ, False, pid)
            try:
                actual = os.path.normcase(os.path.abspath(win32process.GetModuleFileNameEx(handle, 0)))
            finally:
                handle.Close()
            if actual == expected:
                windows.add(hwnd)
        except (OSError, win32api.error):
            pass
    win32gui.EnumWindows(inspect, None)
    return windows


def _maximize_new_window(executable, previous):
    # Chromium ignores --start-maximized when it delegates to an existing process.
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        for hwnd in _app_windows(executable) - previous:
            try:
                win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
                return
            except win32api.error:
                pass
        time.sleep(.2)


def open_interface(url, mode=None):
    mode = mode or get_mode()
    if mode == 'window':
        executable = browser_executable()
        if not executable:
            raise RuntimeError('Chromium browser unavailable')
        previous = _app_windows(executable)
        subprocess.Popen([executable, '--start-maximized', '--app=' + url], close_fds=True)
        threading.Thread(target=_maximize_new_window, args=(executable, previous),
                         name='maximize-tracker-window', daemon=True).start()
    elif mode == 'browser':
        if not webbrowser.open_new(url):
            raise RuntimeError('Browser unavailable')
    else:
        raise ValueError('Invalid interface mode')
