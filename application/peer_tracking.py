"""Supervise the Steam session reader and report peer observations."""
import ctypes
import json
import logging
import os
import sqlite3
import subprocess
import threading
import time
import winreg
import uuid
import msvcrt
import win32api
import win32con
import win32event
import win32file
import win32pipe
import pywintypes
from win32com.shell import shell, shellcon
from contextlib import closing
from pathlib import Path
from application.init import database_setting
from application.geoip_country import country_code

HELPER = Path(__file__).with_name('steam_peers') / 'TrackerSteamPeersV4.exe'
_lock = threading.Lock()
_started = False
_process = None
_command_writer = None
_command_lock = threading.Lock()
_snapshot = {'status': 'starting', 'ping_mode': 'admin_required', 'peers': []}
_ask_elevation = False
_auto_ping_pending = False
_seed_ids = []
_observer = None

def enabled():
    with closing(sqlite3.connect(database_setting, timeout=10)) as db:
        db.execute('CREATE TABLE IF NOT EXISTS steam_peers_setting (id INTEGER PRIMARY KEY CHECK(id=1), enabled INTEGER NOT NULL)')
        row = db.execute('SELECT enabled FROM steam_peers_setting WHERE id=1').fetchone()
        db.commit()
    return bool(row[0]) if row else True

def set_enabled(value):
    global _ask_elevation, _auto_ping_pending
    with closing(sqlite3.connect(database_setting, timeout=10)) as db:
        db.execute('CREATE TABLE IF NOT EXISTS steam_peers_setting (id INTEGER PRIMARY KEY CHECK(id=1), enabled INTEGER NOT NULL)')
        db.execute('INSERT OR REPLACE INTO steam_peers_setting(id,enabled) VALUES(1,?)', (int(value),))
        db.commit()
    if not value:
        with _lock:
            _ask_elevation = False
            _auto_ping_pending = False

def _steam_path():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam') as key:
            return Path(winreg.QueryValueEx(key, 'SteamPath')[0])
    except OSError:
        return None

def set_observer(callback):
    global _observer
    _observer = callback


def _publish(status, peers=None, ping_mode='admin_required'):
    global _snapshot
    with _lock:
        _snapshot = {'status': status, 'ping_mode': ping_mode, 'peers': peers or []}
    if _observer:
        try:
            _observer(status, peers or [])
        except Exception:
            logging.getLogger(__name__).exception('Unable to record Steam observations')

def activate_ping():
    global _ask_elevation, _auto_ping_pending, _seed_ids
    if not enabled() or not ctypes.windll.user32.FindWindowW(None, 'ELDEN RING™'):
        return False
    with _lock:
        if _snapshot.get('ping_mode') in ('active', 'requesting') or _ask_elevation:
            return True
        _ask_elevation = True
        _auto_ping_pending = False
        _seed_ids = [p['id'] for p in _snapshot.get('peers', []) if p.get('id', '').isdigit()][:16]
        process = _process
    if process and process.poll() is None:
        try:
            process.terminate()
        except OSError:
            pass
    return True


def request_auto_ping():
    """Queue one UAC request when tracking starts, even if the game opens later."""
    global _ask_elevation, _auto_ping_pending, _seed_ids
    if not enabled():
        return False
    snapshot()  # Start the supervisor even if the page has not requested its status.
    with _lock:
        if _snapshot.get('ping_mode') in ('active', 'requesting') or _ask_elevation:
            return True
        _ask_elevation = True
        _auto_ping_pending = True
        _seed_ids = [p['id'] for p in _snapshot.get('peers', []) if p.get('id', '').isdigit()][:16]
        process = _process
    if process and process.poll() is None:
        try:
            process.terminate()
        except OSError:
            pass
    return True


def cancel_auto_ping():
    global _ask_elevation, _auto_ping_pending
    with _lock:
        if _auto_ping_pending:
            _ask_elevation = False
            _auto_ping_pending = False


def open_profile(steam_id, allow_historical=False):
    if not isinstance(steam_id, str) or not steam_id.isascii() or not steam_id.isdigit():
        return False
    with _lock:
        if not allow_historical and not any(p.get('id') == steam_id for p in _snapshot.get('peers', [])):
            return False
    with _command_lock:
        if _command_writer is None:
            return False
        try:
            _command_writer(steam_id)
            return True
        except (OSError, pywintypes.error, ValueError):
            return False


def _elevated_stream(log_path, seeds=()):
    # A random local-only pipe carries results from the elevated helper.
    name = 'EldenTracker-' + uuid.uuid4().hex
    def make_pipe(pipe_name):
        return win32pipe.CreateNamedPipe(
            r'\\.\pipe' + chr(92) + pipe_name, win32pipe.PIPE_ACCESS_DUPLEX,
            win32pipe.PIPE_TYPE_BYTE | win32pipe.PIPE_READMODE_BYTE | win32pipe.PIPE_NOWAIT | 8,
            1, 65536, 65536, 0, None)
    handle = make_pipe(name)
    command_handle = make_pipe(name + '-cmd')
    process_handle = None
    try:
        parameters = subprocess.list2cmdline([str(log_path), str(os.getpid()), name, ','.join(seeds)])
        launched = shell.ShellExecuteEx(fMask=shellcon.SEE_MASK_NOCLOSEPROCESS,
            lpVerb='runas', lpFile=str(HELPER), lpParameters=parameters,
            lpDirectory=str(HELPER.parent), nShow=win32con.SW_HIDE)
        process_handle = launched['hProcess']
        deadline = time.monotonic() + 20
        for pipe_handle in (handle, command_handle):
            while time.monotonic() < deadline:
                try:
                    win32pipe.ConnectNamedPipe(pipe_handle, None)
                    break
                except pywintypes.error as exc:
                    if exc.winerror == 535:
                        break
                    if exc.winerror not in (536, 231):
                        raise
                    if win32event.WaitForSingleObject(process_handle, 0) == win32event.WAIT_OBJECT_0:
                        raise OSError('Elevated helper exited before connecting')
                    time.sleep(.1)
            else:
                raise OSError('Elevated helper did not connect')
            win32pipe.SetNamedPipeHandleState(pipe_handle, win32pipe.PIPE_READMODE_BYTE | win32pipe.PIPE_WAIT, None, None)
        fd = msvcrt.open_osfhandle(handle.Detach(), os.O_RDONLY | os.O_BINARY)
        return os.fdopen(fd, 'r', encoding='utf-8-sig', errors='replace'), process_handle, command_handle
    except Exception:
        handle.Close()
        command_handle.Close()
        if process_handle:
            process_handle.Close()
        raise


def _worker():
    global _process, _ask_elevation, _auto_ping_pending, _command_writer
    while True:
        if not enabled():
            _publish('disabled')
            time.sleep(2)
            continue
        if not ctypes.windll.user32.FindWindowW(None, 'ELDEN RING™'):
            _publish('game_closed')
            time.sleep(3)
            continue
        steam = _steam_path()
        if not steam or not HELPER.exists():
            _publish('steam_unavailable')
            time.sleep(5)
            continue
        with _lock:
            elevated = _ask_elevation
            seeds = list(_seed_ids)
            _ask_elevation = False
            _auto_ping_pending = False
        _publish('starting', ping_mode='requesting' if elevated else 'admin_required')
        stream = None
        elevated_process = None
        write_handle = None
        try:
            log = steam / 'logs' / 'ipc_SteamClient.log'
            if elevated:
                stream, elevated_process, write_handle = _elevated_stream(log, seeds)
                with _command_lock:
                    _command_writer = lambda value: win32file.WriteFile(write_handle, (value + "\n").encode('ascii'))
            else:
                _process = subprocess.Popen([str(HELPER), str(log), str(os.getpid())],
                    cwd=str(HELPER.parent), stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    text=True, encoding='utf-8-sig', errors='replace',
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                stream = _process.stdout
                with _command_lock:
                    def write_stdin(value):
                        _process.stdin.write(value + "\n")
                        _process.stdin.flush()
                    _command_writer = write_stdin
            for line in stream:
                if not enabled() or _ask_elevation:
                    break
                try:
                    data = json.loads(line)
                    peers = data.get('peers', [])
                    if not isinstance(peers, list):
                        peers = []
                    safe = [{'id':str(p.get('id', '')), 'name':str(p.get('name', '')), 'ping':p.get('ping'), 'ip':p.get('ip'), 'relay':bool(p.get('relay')), 'country_code':country_code(p.get('ip'))}
                            for p in peers if isinstance(p, dict)][:16]
                    _publish(str(data.get('status', 'helper_error')), safe, str(data.get('ping_mode', 'admin_required')))
                except (ValueError, TypeError):
                    _publish('helper_error')
            if _process:
                _process.wait(timeout=3)
        except (OSError, subprocess.TimeoutExpired, pywintypes.error):
            if _process and _process.poll() is None:
                _process.kill()
            _publish('helper_error', ping_mode='denied' if elevated else 'admin_required')
        finally:
            with _command_lock:
                _command_writer = None
                if write_handle:
                    write_handle.Close()
            if stream:
                stream.close()
            if elevated_process:
                elevated_process.Close()
            _process = None
        time.sleep(1 if _ask_elevation else 4)

def snapshot():
    global _started
    with _lock:
        if not _started:
            _started = True
            threading.Thread(target=_worker, name='steam-peers', daemon=True).start()
        result = dict(_snapshot)
    result['enabled'] = enabled()
    return result

