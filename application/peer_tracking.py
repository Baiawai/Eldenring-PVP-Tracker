"""Supervise the Steam session reader and report peer observations."""
import ctypes
import base64
import binascii
import json
import logging
import os
import queue
import sqlite3
import subprocess
import sys
import threading
import time
import winreg
import uuid
import msvcrt
from collections import OrderedDict
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
from application.runtime_paths import STORE_BUILD
from application.steam_peer_enrichment import PeerCache
from application.steam_log_diagnostics import LogProbe

HELPER = Path(__file__).with_name('steam_peers') / 'TrackerSteamPeersV8.exe'
_lock = threading.Lock()
_started = False
_process = None
_command_writer = None
_command_lock = threading.Lock()
_snapshot = {'status': 'starting', 'ping_mode': 'steam_only' if STORE_BUILD else 'admin_required', 'peers': []}
_ask_elevation = False
_auto_ping_pending = False
_last_elevation_failure = None
_seed_ids = []
_observer = None
_peer_cache = PeerCache()
_log_diagnostic = 'unknown'
_log_receiving_until = None

# Historical avatar requests reuse the existing Steam helper.  Keep only a
# small number in flight, and avoid repeatedly asking Steam for unavailable
# avatars.  These IDs never appear in the public status snapshot or logs.
_HISTORICAL_AVATAR_MAX_PENDING = 4
_HISTORICAL_AVATAR_TIMEOUT = 35.0
_HISTORICAL_AVATAR_COOLDOWN = 300.0
_HISTORICAL_AVATAR_MAX_COOLDOWNS = 512
_HISTORICAL_AVATAR_MAX_BASE64 = 4 * ((128 * 1024 + 2) // 3)
_HISTORICAL_AVATAR_MAX_EVENT_IDS = 128
_historical_avatar_lock = threading.Lock()
_historical_avatar_pending = {}
_historical_avatar_cooldown = OrderedDict()
_historical_avatar_save_queue = queue.Queue(maxsize=_HISTORICAL_AVATAR_MAX_PENDING)
_historical_avatar_save_start_lock = threading.Lock()
_historical_avatar_save_thread = None


def _historical_avatar_id(value):
    return (isinstance(value, str) and len(value) == 17 and value.isascii() and value.isdigit()
            and '76561197960265729' <= value <= '76561202255233023')


def _historical_avatar_set_cooldown(steam_id, now):
    _historical_avatar_cooldown.pop(steam_id, None)
    _historical_avatar_cooldown[steam_id] = now + _HISTORICAL_AVATAR_COOLDOWN
    while len(_historical_avatar_cooldown) > _HISTORICAL_AVATAR_MAX_COOLDOWNS:
        _historical_avatar_cooldown.popitem(last=False)


def _prune_historical_avatar_requests(now):
    for steam_id, request in list(_historical_avatar_pending.items()):
        if not request['saving'] and now - request['started'] >= _HISTORICAL_AVATAR_TIMEOUT:
            del _historical_avatar_pending[steam_id]
            _historical_avatar_set_cooldown(steam_id, now)
    for steam_id, until in list(_historical_avatar_cooldown.items()):
        if now >= until:
            del _historical_avatar_cooldown[steam_id]


def request_historical_avatar(steam_id, event_ids):
    """Ask an already-running V7 helper for an authorized historical avatar.

    The caller checks that the ID occurs in active history.  The store repeats
    that check atomically when a response arrives.  Never starts Steam or the
    helper, including when Elden Ring is closed.
    """
    if (not _historical_avatar_id(steam_id) or HELPER.name not in ('TrackerSteamPeersV7.exe', 'TrackerSteamPeersV8.exe')
            or not isinstance(event_ids, (list, tuple)) or not event_ids
            or len(event_ids) > _HISTORICAL_AVATAR_MAX_EVENT_IDS
            or any(type(value) is not int or not 0 < value <= 9223372036854775807 for value in event_ids)):
        return 'unavailable'
    event_ids = tuple(dict.fromkeys(event_ids))
    try:
        if not enabled() or not ctypes.windll.user32.FindWindowW(None, 'ELDEN RING™'):
            return 'unavailable'
        steam = sys.modules.get('application.steam_log_auto')
        steam_session = getattr(steam, 'steam_session', None)
        if not callable(steam_session) or steam_session() is None:
            return 'unavailable'
    except (OSError, sqlite3.Error):
        return 'unavailable'
    with _lock:
        if _snapshot.get('status') not in ('active', 'waiting_log'):
            return 'unavailable'
    with _command_lock:
        if _command_writer is None:
            return 'unavailable'
        now = time.monotonic()
        with _historical_avatar_lock:
            _prune_historical_avatar_requests(now)
            if steam_id in _historical_avatar_pending:
                request = _historical_avatar_pending[steam_id]
                request['event_ids'] = tuple(dict.fromkeys(event_ids + request['event_ids']))[:_HISTORICAL_AVATAR_MAX_EVENT_IDS]
                return 'queued'
            if steam_id in _historical_avatar_cooldown or len(_historical_avatar_pending) >= _HISTORICAL_AVATAR_MAX_PENDING:
                return 'rate_limited'
            _historical_avatar_pending[steam_id] = {'started': now, 'saving': False, 'event_ids': event_ids}
            try:
                _command_writer('avatar:' + steam_id)
            except (OSError, pywintypes.error, ValueError):
                _historical_avatar_pending.pop(steam_id, None)
                _historical_avatar_set_cooldown(steam_id, now)
                return 'unavailable'
    return 'queued'


def _save_historical_avatars():
    """Persist off the peer-reader thread so a busy database cannot stall ping."""
    global _historical_avatar_save_thread
    while True:
        try:
            steam_id, png, request = _historical_avatar_save_queue.get(timeout=5)
        except queue.Empty:
            with _historical_avatar_save_start_lock:
                if _historical_avatar_save_queue.empty():
                    _historical_avatar_save_thread = None
                    return
            continue
        try:
            from application import steam_avatar_store
            with _historical_avatar_lock:
                event_ids = request['event_ids']
            steam_avatar_store.save_historical(steam_id, png, event_ids)
        except Exception:
            # A storage failure must never stop Steam peer detection. Avoid
            # logging identifiers or file paths from exception details.
            logging.getLogger(__name__).warning('Unable to save a historical Steam avatar')
        finally:
            with _historical_avatar_lock:
                if _historical_avatar_pending.get(steam_id) is request:
                    _historical_avatar_pending.pop(steam_id, None)
                    _historical_avatar_set_cooldown(steam_id, time.monotonic())
            _historical_avatar_save_queue.task_done()


def _enqueue_historical_avatar_save(steam_id, png, request):
    global _historical_avatar_save_thread
    with _historical_avatar_save_start_lock:
        try:
            _historical_avatar_save_queue.put_nowait((steam_id, png, request))
        except queue.Full:
            return False
        if _historical_avatar_save_thread is None:
            _historical_avatar_save_thread = threading.Thread(
                target=_save_historical_avatars, name='historical-steam-avatars', daemon=True)
            try:
                _historical_avatar_save_thread.start()
            except RuntimeError:
                _historical_avatar_save_thread = None
                # Starting failed, so no other thread can have taken this item.
                _historical_avatar_save_queue.get_nowait()
                _historical_avatar_save_queue.task_done()
                return False
    return True


def _handle_historical_avatar(data):
    """Consume only a response to a pending request; leave peer state intact."""
    steam_id = data.get('id')
    if not _historical_avatar_id(steam_id):
        return
    now = time.monotonic()
    with _historical_avatar_lock:
        _prune_historical_avatar_requests(now)
        request = _historical_avatar_pending.get(steam_id)
        if request is None or request['saving']:
            return
        encoded = data.get('avatar_png')
        if data.get('state') != 'ready' or not isinstance(encoded, str) or len(encoded) > _HISTORICAL_AVATAR_MAX_BASE64:
            del _historical_avatar_pending[steam_id]
            _historical_avatar_set_cooldown(steam_id, now)
            return
        try:
            png = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            del _historical_avatar_pending[steam_id]
            _historical_avatar_set_cooldown(steam_id, now)
            return
        request['saving'] = True
    if not _enqueue_historical_avatar_save(steam_id, png, request):
        with _historical_avatar_lock:
            if _historical_avatar_pending.get(steam_id) is request:
                _historical_avatar_pending.pop(steam_id, None)
                _historical_avatar_set_cooldown(steam_id, time.monotonic())


def _clear_historical_avatar_requests():
    now = time.monotonic()
    with _historical_avatar_lock:
        _prune_historical_avatar_requests(now)
        for steam_id in _historical_avatar_pending:
            _historical_avatar_set_cooldown(steam_id, now)
        _historical_avatar_pending.clear()


def _set_log_diagnostic(value, receiving_until=None):
    global _log_diagnostic, _log_receiving_until
    with _lock:
        _log_diagnostic = value
        _log_receiving_until = receiving_until if value == 'receiving' else None


def _observe_log(probe, path):
    value = probe.observe(path)
    _set_log_diagnostic(value, probe.receiving_until)


def _diagnostic():
    # Neither the path nor the log content is exposed to the browser.
    with _lock:
        log = _log_diagnostic
        if log == 'receiving' and (_log_receiving_until is None or time.monotonic() >= _log_receiving_until):
            log = 'waiting'
    auto = sys.modules.get('application.steam_log_auto')
    return {'log': log, 'auto': auto.status() if auto is not None else 'unknown'}

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
    if STORE_BUILD:
        ping_mode = 'steam_only'
    with _lock:
        safe = _peer_cache.update(peers or [])
        _snapshot = {'status': status, 'ping_mode': ping_mode, 'peers': safe}
    if _observer:
        try:
            _observer(status, safe)
        except Exception:
            logging.getLogger(__name__).exception('Unable to record Steam observations')

def activate_ping():
    global _ask_elevation, _auto_ping_pending, _seed_ids, _last_elevation_failure
    if not enabled() or not ctypes.windll.user32.FindWindowW(None, 'ELDEN RING™'):
        return False
    if STORE_BUILD:
        snapshot()
        return True
    with _lock:
        if _snapshot.get('ping_mode') in ('active', 'requesting') or _ask_elevation:
            return True
        _ask_elevation = True
        _auto_ping_pending = False
        _last_elevation_failure = None
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
    global _ask_elevation, _auto_ping_pending, _seed_ids, _last_elevation_failure
    if not enabled():
        return False
    snapshot()  # Start the supervisor even if the page has not requested its status.
    if STORE_BUILD:
        return True
    with _lock:
        if _snapshot.get('ping_mode') in ('active', 'requesting') or _ask_elevation:
            return True
        _ask_elevation = True
        _auto_ping_pending = True
        _last_elevation_failure = None
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
    global _process, _ask_elevation, _auto_ping_pending, _command_writer, _last_elevation_failure
    log_probe = LogProbe()
    while True:
        if not enabled():
            log_probe.reset()
            _set_log_diagnostic('unknown')
            _publish('disabled')
            time.sleep(2)
            continue
        if not ctypes.windll.user32.FindWindowW(None, 'ELDEN RING™'):
            log_probe.reset()
            _set_log_diagnostic('unknown')
            _publish('game_closed')
            time.sleep(3)
            continue
        steam = _steam_path()
        if not steam or not HELPER.exists():
            log_probe.reset()
            _set_log_diagnostic('unknown')
            _publish('steam_unavailable')
            time.sleep(5)
            continue
        with _lock:
            elevated = _ask_elevation and not STORE_BUILD
            seeds = list(_seed_ids)
            _ask_elevation = False
            _auto_ping_pending = False
        # A newly started helper must observe fresh file activity itself;
        # evidence from a previous reader session is not proof for this one.
        log_probe.reset()
        _set_log_diagnostic('unknown')
        _publish('starting', ping_mode='requesting' if elevated else (_last_elevation_failure or 'admin_required'))
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
                if not enabled() or (_ask_elevation and not STORE_BUILD):
                    break
                _observe_log(log_probe, log)
                try:
                    data = json.loads(line)
                    if isinstance(data, dict) and data.get('type') == 'avatar':
                        _handle_historical_avatar(data)
                        continue
                    peers = data.get('peers', [])
                    if not isinstance(peers, list):
                        peers = []
                    safe = [{'id':str(p.get('id', '')), 'name':str(p.get('name', '')), 'ping':p.get('ping'),
                             'average_ping':p.get('average_ping'), 'jitter':p.get('jitter'), 'quality':p.get('quality'),
                             'avatar_png':p.get('avatar_png'), 'country_code':country_code(p.get('ip')),
                             'steam_friend':p.get('steam_friend') if type(p.get('steam_friend')) is bool else None}
                            for p in peers if isinstance(p, dict)][:16]
                    ping_mode = str(data.get('ping_mode', 'admin_required'))
                    if elevated and ping_mode == 'active':
                        _last_elevation_failure = None
                    elif not elevated and _last_elevation_failure and ping_mode == 'admin_required':
                        ping_mode = _last_elevation_failure
                    _publish(str(data.get('status', 'helper_error')), safe, ping_mode)
                except (ValueError, TypeError):
                    _publish('helper_error')
            if _process:
                _process.wait(timeout=3)
        except (OSError, subprocess.TimeoutExpired, pywintypes.error) as error:
            if _process and _process.poll() is None:
                _process.kill()
            if elevated:
                _last_elevation_failure = 'denied' if getattr(error, 'winerror', None) == 1223 else 'unavailable'
            _observe_log(log_probe, steam / 'logs' / 'ipc_SteamClient.log')
            _publish('helper_error', ping_mode=_last_elevation_failure or 'admin_required')
        finally:
            with _command_lock:
                _command_writer = None
                if write_handle:
                    write_handle.Close()
            _clear_historical_avatar_requests()
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
    result['diagnostic'] = _diagnostic()
    return result


def passive_snapshot():
    """Read existing observations without starting the Steam supervisor."""
    with closing(sqlite3.connect(database_setting, timeout=10)) as db:
        exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='steam_peers_setting'").fetchone()
        row = db.execute('SELECT enabled FROM steam_peers_setting WHERE id=1').fetchone() if exists else None
    is_enabled = bool(row[0]) if row else True
    with _lock:
        result = dict(_snapshot)
        result['peers'] = [dict(peer) for peer in _snapshot.get('peers', [])] if is_enabled else []
    result['enabled'] = is_enabled
    if not is_enabled:
        result['status'] = 'disabled'
    result['diagnostic'] = _diagnostic()
    return result


def avatar_png(steam_id):
    """Return an in-memory PNG for a currently observed Steam peer only."""
    with _lock:
        return _peer_cache.avatar(steam_id)

