"""Optionally ask the running Steam client to enable its IPC event log."""
import logging
import ctypes
import sqlite3
import subprocess
import threading
import time
import winreg
from contextlib import closing
from pathlib import Path

import win32api
import win32con
import win32event
import win32process
import pywintypes
from win32com.shell import shell, shellcon

from application.init import database_setting

COMMAND_FILTER = 'BeginAuthSession,EndAuthSession,LeaveLobby,SendClanChatMessage'
_wake = threading.Event()
_start_lock = threading.Lock()
_started = False


def get_enabled():
    with closing(sqlite3.connect(database_setting, timeout=10)) as db:
        db.execute('CREATE TABLE IF NOT EXISTS steam_log_auto (id INTEGER PRIMARY KEY CHECK(id=1), enabled INTEGER NOT NULL)')
        row = db.execute('SELECT enabled FROM steam_log_auto WHERE id=1').fetchone()
        db.commit()
    return bool(row[0]) if row else True


def set_enabled(value):
    with closing(sqlite3.connect(database_setting, timeout=10)) as db:
        db.execute('CREATE TABLE IF NOT EXISTS steam_log_auto (id INTEGER PRIMARY KEY CHECK(id=1), enabled INTEGER NOT NULL)')
        db.execute('INSERT OR REPLACE INTO steam_log_auto(id,enabled) VALUES(1,?)', (int(value),))
        db.commit()
    _wake.set()


def steam_session():
    """Identify the running Steam process; never start Steam when it is closed."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam') as key:
            executable = Path(winreg.QueryValueEx(key, 'SteamPath')[0]) / 'steam.exe'
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam\ActiveProcess') as key:
            pid = int(winreg.QueryValueEx(key, 'pid')[0])
        if pid <= 0 or not executable.is_file():
            return None
        handle = win32api.OpenProcess(win32con.PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        try:
            buffer = ctypes.create_unicode_buffer(32768)
            size = ctypes.c_ulong(len(buffer))
            query = ctypes.windll.kernel32.QueryFullProcessImageNameW
            query.argtypes = (ctypes.c_void_p, ctypes.c_ulong, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_ulong))
            query.restype = ctypes.c_int
            if not query(int(handle), 0, buffer, ctypes.byref(size)):
                return None
            actual = Path(buffer.value)
            started = win32process.GetProcessTimes(handle)['CreationTime']
        finally:
            handle.Close()
        if str(actual).casefold() != str(executable).casefold():
            return None
        return (pid, str(started), executable)
    except (OSError, ValueError, TypeError):
        return None


def activate(executable):
    """Request logging through Steam; None means Windows elevation was refused."""
    try:
        process = subprocess.Popen([str(executable), '-console', '+log_ipc', COMMAND_FILTER],
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        process.wait(timeout=15)
        return process.returncode == 0
    except OSError as error:
        if error.winerror == 740:
            return _activate_elevated(executable)
        logging.getLogger(__name__).exception('Unable to request Steam logging')
        return False
    except subprocess.TimeoutExpired:
        logging.getLogger(__name__).exception('Unable to request Steam logging')
        return False


def _activate_elevated(executable):
    """Use Windows consent if Steam itself is configured to require elevation."""
    handle = None
    try:
        launched = shell.ShellExecuteEx(
            fMask=shellcon.SEE_MASK_NOCLOSEPROCESS,
            lpVerb='runas', lpFile=str(executable),
            lpParameters=subprocess.list2cmdline(['-console', '+log_ipc', COMMAND_FILTER]),
            lpDirectory=str(executable.parent), nShow=win32con.SW_HIDE,
        )
        handle = launched.get('hProcess')
        if not handle or win32event.WaitForSingleObject(handle, 15000) != win32event.WAIT_OBJECT_0:
            return False
        return win32process.GetExitCodeProcess(handle) == 0
    except (OSError, pywintypes.error) as error:
        if getattr(error, 'winerror', None) == 1223:
            return None
        logging.getLogger(__name__).exception('Unable to request elevated Steam logging')
        return False
    finally:
        if handle:
            handle.Close()


def _worker(peer_enabled):
    last_session = None
    observed_session = None
    next_attempt = 0
    while True:
        try:
            if not get_enabled() or not peer_enabled():
                last_session = None
                observed_session = None
                next_attempt = 0
            else:
                session = steam_session()
                if session is None:
                    last_session = None
                    observed_session = None
                    next_attempt = 0
                else:
                    if session[:2] != observed_session:
                        observed_session = session[:2]
                        next_attempt = 0
                    if session[:2] != last_session and time.monotonic() >= next_attempt:
                        next_attempt = time.monotonic() + 60
                        outcome = activate(session[2])
                        if outcome is True or outcome is None:
                            # Do not repeatedly prompt after the user refuses elevation.
                            last_session = session[:2]
        except Exception:
            logging.getLogger(__name__).exception('Steam automatic logging failed')
        _wake.wait(5)
        _wake.clear()


def start_worker(peer_enabled):
    global _started
    with _start_lock:
        if not _started:
            _started = True
            threading.Thread(target=_worker, args=(peer_enabled,), name='steam-log-auto', daemon=True).start()
