"""Optional leaderboard: participation requires consent; public reads do not."""
import base64
import io
import json
import math
import os
import secrets
import sqlite3
import threading
import time
import uuid
import winreg
import ctypes
from ctypes import wintypes
from contextlib import closing
from pathlib import Path
from urllib.parse import urlparse, urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError
from flask import jsonify, request
from __main__ import app
from application import init, mode_stats
from application.runtime_paths import FROZEN, data_dir
from application.secur import decrypt_value
import win32crypt
import pywintypes
from PIL import Image, UnidentifiedImageError

_LOCK = threading.RLock()
_START_LOCK = threading.Lock()
_SCHEMA_LOCK = threading.Lock()
_RUNNING = False
_LAST_SYNC_START = None
_SYNC_INTERVAL_SECONDS = 10
_STATUS = {'state': 'idle'}
_DEFAULT_BASE_URL = 'https://eldenringpvp.com'
_LANGUAGE_SYNC_REQUIRED = False
_RECOVERY_GRANT = None
_LANGUAGES = frozenset(('fra', 'eng', 'deu', 'ita', 'spaes', 'spaar', 'por', 'pol', 'rus', 'jap', 'kor', 'chi', 'zht', 'tha', 'ara'))
_FIELDS = dict(victory=2, defeat=3, egality=4, combats=9, noResult=10,
               fight_exit=11, abandon=12, maxVictory=13, maxDefeat=14,
               ratioTime=15, connexionError=17, gameExit=18, ratio=7)


def _database():
    return init.database_setting


def _db():
    # URI support is needed for attaching the existing user DB in mode=rw;
    # normal absolute paths continue to work unchanged.
    db = sqlite3.connect(_database(), timeout=10, uri=True)
    try:
        with _SCHEMA_LOCK:
            db.execute('CREATE TABLE IF NOT EXISTS online_leaderboard (id INTEGER PRIMARY KEY CHECK(id=1), enabled INTEGER NOT NULL DEFAULT 0, uuid TEXT, token BLOB)')
            columns = {row[1] for row in db.execute('PRAGMA table_info(online_leaderboard)')}
            for name, definition in (
                ('delete_pending', 'INTEGER NOT NULL DEFAULT 0'), ('server_url', 'TEXT'),
                ('language_permission', 'INTEGER NOT NULL DEFAULT 0'), ('steam_permission', 'INTEGER NOT NULL DEFAULT 0'),
                ('steam_remove_pending', 'INTEGER NOT NULL DEFAULT 0'), ('language_remove_pending', 'INTEGER NOT NULL DEFAULT 0'),
                ('steam_login_cancel_pending', 'INTEGER NOT NULL DEFAULT 0'),
                ('rotation_token', 'BLOB'),
                ('recovery_payload', 'BLOB'),
                ('previous_token', 'BLOB'),
                ('event_permission', 'INTEGER NOT NULL DEFAULT 0'),
                ('server_transition_nonce', 'TEXT'),
                ('server_consent_url', 'TEXT'),
                ('legacy_unbound_guard', 'INTEGER NOT NULL DEFAULT 0'),
            ):
                if name not in columns:
                    db.execute('ALTER TABLE online_leaderboard ADD COLUMN ' + name + ' ' + definition)
            db.execute('INSERT OR IGNORE INTO online_leaderboard(id) VALUES (1)')
            if FROZEN:
                # An older Store build could have accepted participation while
                # configured to localhost without completing registration. Do
                # not let an already-open browser tab reuse that old approval
                # for the public service after this build starts.
                row = db.execute('SELECT enabled,uuid,token,server_url,server_consent_url,server_transition_nonce,legacy_unbound_guard FROM online_leaderboard WHERE id=1').fetchone()
                if row and row[0] and not any(row[1:4]) and row[4] != _DEFAULT_BASE_URL and (not row[5] or not row[6]):
                    db.execute('''UPDATE online_leaderboard SET server_transition_nonce=COALESCE(NULLIF(server_transition_nonce,''),?), legacy_unbound_guard=1
                        WHERE id=1 AND enabled=1 AND (uuid IS NULL OR uuid='')
                        AND (token IS NULL OR length(token)=0) AND (server_url IS NULL OR server_url='')
                        AND (server_transition_nonce IS NULL OR server_transition_nonce='' OR legacy_unbound_guard=0)
                        AND (server_consent_url IS NULL OR server_consent_url != ?)''',
                               (secrets.token_urlsafe(32), _DEFAULT_BASE_URL))
            db.commit()
    except Exception:
        db.close()
        raise
    return db


def _settings():
    with closing(_db()) as db:
        enabled, ident, token, pending, server = db.execute('SELECT enabled,uuid,token,delete_pending,server_url FROM online_leaderboard WHERE id=1').fetchone()
    return bool(enabled), ident, token, bool(pending), server


def _language_permission():
    with closing(_db()) as db:
        return db.execute('SELECT language_permission FROM online_leaderboard WHERE id=1').fetchone()[0]


def _event_permission():
    with closing(_db()) as db:
        return bool(db.execute('SELECT event_permission FROM online_leaderboard WHERE id=1').fetchone()[0])


def _steam_settings():
    with closing(_db()) as db:
        permission, pending = db.execute('SELECT steam_permission,steam_remove_pending FROM online_leaderboard WHERE id=1').fetchone()
        return bool(permission), bool(pending)


def _language_remove_pending():
    with closing(_db()) as db:
        return bool(db.execute('SELECT language_remove_pending FROM online_leaderboard WHERE id=1').fetchone()[0])


def _login_cancel_pending():
    with closing(_db()) as db:
        return bool(db.execute('SELECT steam_login_cancel_pending FROM online_leaderboard WHERE id=1').fetchone()[0])


def _active_steam_id():
    """Read the locally logged-in Steam account, never a recently seen peer."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam\ActiveProcess') as key:
            account, _ = winreg.QueryValueEx(key, 'ActiveUser')
            pid, _ = winreg.QueryValueEx(key, 'pid')
        if not isinstance(account, int) or not 0 < account <= 0xffffffff or not isinstance(pid, int) or pid <= 0:
            return None
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.QueryFullProcessImageNameW.argtypes = (wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD))
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return None
        try:
            length = wintypes.DWORD(32768)
            path = ctypes.create_unicode_buffer(length.value)
            if not kernel.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(length)) or Path(path.value).name.lower() != 'steam.exe':
                return None
        finally:
            kernel.CloseHandle(handle)
        return str(76561197960265728 + account)
    except (OSError, ValueError, TypeError):
        return None


def _base_url():
    # Store packages always use the public service, regardless of a previous
    # development configuration left in the user's data directory.
    if FROZEN:
        return _DEFAULT_BASE_URL
    # The source version can use an explicit local or production environment.
    path = data_dir() / 'leaderboard-config.json'
    if not path.is_file():
        return _DEFAULT_BASE_URL
    try:
        config = json.loads(path.read_text(encoding='utf-8'))
        environment = config.get('environment', 'production')
        url = config.get('urls', {}).get(environment, '').rstrip('/')
        parsed = urlparse(url)
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            return None
        if parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in ('localhost', '127.0.0.1', '::1')):
            return None
        return url if parsed.hostname else None
    except (OSError, ValueError, AttributeError, TypeError):
        return None


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _call(method, path, data=None, token=None, root=None, extra_headers=None):
    root = root or _base_url()
    if not root:
        raise RuntimeError('not_configured')
    # Pending withdrawals and token rotations pass their old origin explicitly.
    # Enforce the Store destination here too, before opening a connection or
    # attaching credentials, and let callers retain any pending operation.
    if FROZEN and root != _DEFAULT_BASE_URL:
        raise RuntimeError('server_not_allowed')
    headers = {'Accept': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    if extra_headers:
        headers.update(extra_headers)
    payload = json.dumps(data).encode('utf-8') if data is not None else None
    if payload:
        headers['Content-Type'] = 'application/json'
    try:
        with build_opener(_NoRedirect()).open(Request(root + path, data=payload, headers=headers, method=method), timeout=8) as response:
            body = response.read(2_000_001)
            if len(body) > 2_000_000:
                raise ValueError('Response too large')
            return json.loads(body) if body else None
    except HTTPError as error:
        if error.code == 422:
            try:
                if json.loads(error.read(4096)).get('error') == 'invalid_statistics':
                    raise ValueError('invalid_statistics') from error
            except (ValueError, AttributeError) as details_error:
                if str(details_error) == 'invalid_statistics':
                    raise
        raise


def _profile():
    profile = init.load_user()[0]
    name = str(profile[1]).strip()
    if not name or len(name) > 80:
        raise ValueError('profile_required')
    try:
        level = int(profile[19])
        if not 1 <= level <= 713:
            level = None
    except (ValueError, TypeError):
        level = None
    avatar = str(profile[6] or '')
    try:
        if avatar and not avatar.startswith('data:'):
            avatar = 'data:image/jpeg;base64,' + avatar
        prefix, encoded = avatar.split(',', 1)
        if prefix not in ('data:image/jpeg;base64', 'data:image/png;base64', 'data:image/webp;base64'):
            raise ValueError('Unsupported avatar')
        image_bytes = base64.b64decode(encoded, validate=True)
        with Image.open(io.BytesIO(image_bytes)) as image:
            if image.width > 8192 or image.height > 8192:
                raise ValueError('Avatar dimensions too large')
            if image.width > 1024 or image.height > 1024 or len(image_bytes) > 200_000:
                image.thumbnail((1024, 1024))
                output = io.BytesIO()
                image.convert('RGB').save(output, 'JPEG', quality=80, optimize=True)
                avatar = 'data:image/jpeg;base64,' + base64.b64encode(output.getvalue()).decode('ascii') if output.tell() <= 200_000 else None
    except (ValueError, TypeError, OSError, UnidentifiedImageError, Image.DecompressionBombError):
        avatar = None
    language = str(profile[5] or '').strip()
    return {'name': name, 'level': level, 'avatar': avatar, 'language': language if language in _LANGUAGES else None, 'event_protocol': 1}


def _event_transition_blocker(db, schema='main'):
    """Identify unresolved old combat data without reading its contents."""
    if schema not in ('main', 'tracker_user'):
        raise ValueError('invalid schema')
    tables = {row[0] for row in db.execute("SELECT name FROM " + schema + ".sqlite_master WHERE type='table'")}
    if 'leaderboard_event_outbox' in tables and db.execute('SELECT 1 FROM ' + schema + '.leaderboard_event_outbox LIMIT 1').fetchone():
        return 'pending_events'
    if 'leaderboard_event_state' in tables and db.execute('SELECT 1 FROM ' + schema + '.leaderboard_event_state WHERE active_match IS NOT NULL OR last_no_result IS NOT NULL LIMIT 1').fetchone():
        return 'active_match'
    return None


def _unbound_events_pending():
    """Fail closed if the old outbox cannot be inspected without writing."""
    try:
        path = Path(init.database_user)
        if not path.is_file():
            return 'invalid_data'
        with closing(sqlite3.connect(path.absolute().as_uri() + '?mode=ro', uri=True, timeout=5)) as db:
            return _event_transition_blocker(db)
    except (OSError, ValueError, sqlite3.Error):
        return 'invalid_data'


def _credentials(root):
    """Create or load the credential while holding _LOCK."""
    enabled, ident, encrypted, pending, server = _settings()
    if not enabled or pending:
        raise RuntimeError('disabled')
    if encrypted:
        if server != root:
            raise RuntimeError('server_changed')
        return _stored_token(root)
    # A Store build must not silently overwrite an incomplete old identity.
    if FROZEN and (ident or server):
        raise RuntimeError('server_changed')
    if FROZEN:
        with closing(_db()) as db:
            consent_url, legacy_guard = db.execute('SELECT server_consent_url,legacy_unbound_guard FROM online_leaderboard WHERE id=1').fetchone()
        if legacy_guard:
            raise RuntimeError(_unbound_events_pending() or 'fresh_consent_required')
        if consent_url != root:
            raise RuntimeError('fresh_consent_required')
    ident = str(uuid.uuid4())
    result = _call('POST', '/api/v1/installations', {'uuid': ident, 'consent_version': '1'}, root=root)
    if not isinstance(result, dict) or result.get('uuid') != ident or not isinstance(result.get('token'), str):
        raise ValueError('Invalid registration')
    token = result['token']
    encrypted = win32crypt.CryptProtectData(token.encode('utf-8'), 'Elden Ring PvP Tracker', None, None, None, 0)
    with closing(_db()) as db, db:
        db.execute('UPDATE online_leaderboard SET uuid=?,token=?,server_url=? WHERE id=1', (ident, encrypted, root))
    return token


def _stored_token(root):
    with closing(_db()) as db:
        current_token, pending_rotation, pending_recovery, server = db.execute('SELECT token,rotation_token,recovery_payload,server_url FROM online_leaderboard WHERE id=1').fetchone()
    if server != root or not current_token:
        raise RuntimeError('server_changed')
    token = win32crypt.CryptUnprotectData(current_token, None, None, None, 0)[1].decode('utf-8')
    if pending_rotation:
        token = _complete_token_rotation(root, token, pending_rotation)
    return _complete_recovery(root, token, pending_recovery) if pending_recovery else token


def _complete_token_rotation(root, old_token, encrypted_new):
    new_token = win32crypt.CryptUnprotectData(encrypted_new, None, None, None, 0)[1].decode('utf-8')
    try:
        result = _call('POST', '/api/v1/installations/rotate-token', {'new_token':new_token}, old_token, root=root)
    except HTTPError as error:
        if error.code != 401:
            raise
        # The server may have committed the rotation before its response was lost.
        result = _call('POST', '/api/v1/installations/rotate-token', {'new_token':new_token}, new_token, root=root)
    if not isinstance(result, dict) or result.get('ok') is not True:
        raise ValueError('invalid_rotation_response')
    with closing(_db()) as db, db:
        db.execute('UPDATE online_leaderboard SET token=?,rotation_token=NULL WHERE id=1 AND rotation_token=?', (encrypted_new, encrypted_new))
    return new_token


def _rotate_token(root, token):
    encrypted_new = win32crypt.CryptProtectData(secrets.token_hex(32).encode('ascii'), 'Elden Ring PvP Tracker', None, None, None, 0)
    with closing(_db()) as db, db:
        db.execute('UPDATE online_leaderboard SET rotation_token=? WHERE id=1', (encrypted_new,))
    return _complete_token_rotation(root, token, encrypted_new)


def _complete_recovery(root, token, encrypted_payload):
    payload = json.loads(win32crypt.CryptUnprotectData(encrypted_payload, None, None, None, 0)[1].decode('utf-8'))
    try:
        result = _call('POST', '/api/v1/steam/recovery', {'uuid':payload['uuid'], 'new_token':payload['new_token']}, token, root=root, extra_headers={'X-Steam-Recovery':payload['grant']})
        if not isinstance(result, dict) or result.get('ok') is not True:
            raise ValueError('invalid_recovery_response')
    except HTTPError as error:
        if error.code == 409:
            with closing(_db()) as db, db:
                db.execute('UPDATE online_leaderboard SET recovery_payload=NULL WHERE id=1 AND recovery_payload=?', (encrypted_payload,))
            raise
        if error.code != 401:
            raise
        # If the server committed before its response was lost, the new token
        # is already active even after the short-lived recovery grant expired.
        try:
            status = _remote_steam_status(root, payload['new_token'])
            if not status['connected'] or status['steam_id'] != payload['steam_id']:
                raise ValueError('invalid_recovery_identity')
        except HTTPError as token_error:
            if token_error.code == 401:
                with closing(_db()) as db, db:
                    db.execute('UPDATE online_leaderboard SET recovery_payload=NULL WHERE id=1 AND recovery_payload=?', (encrypted_payload,))
            raise
    encrypted_token = win32crypt.CryptProtectData(payload['new_token'].encode('ascii'), 'Elden Ring PvP Tracker', None, None, None, 0)
    with closing(_db()) as db, db:
        db.execute('UPDATE online_leaderboard SET uuid=?,token=?,recovery_payload=NULL,rotation_token=NULL WHERE id=1 AND recovery_payload=?', (payload['uuid'], encrypted_token, encrypted_payload))
    return payload['new_token']


def _remote_steam_status(root, token):
    result = _call('GET', '/api/v1/steam/status', token=token, root=root)
    if not isinstance(result, dict) or not isinstance(result.get('connected'), bool):
        raise ValueError('invalid_steam_status')
    if result['connected']:
        steam_id = result.get('steam_id')
        if not isinstance(steam_id, str) or len(steam_id) != 17 or not steam_id.isascii() or not steam_id.isdigit() or not '76561197960265729' <= steam_id <= '76561202255233023':
            raise ValueError('invalid_steam_identity')
    return result


def _verified_steam(root, token):
    result = _remote_steam_status(root, token)
    return result.get('steam_id') if result['connected'] else None


def _ensure_event_consent(root, token):
    try:
        result = _call('POST', '/api/v1/events/consent', {'consent':True, 'version':'events-1'}, token, root=root)
    except HTTPError as error:
        if error.code in (404, 405, 426):
            raise ValueError('server_update_required') from error
        raise
    if not isinstance(result, dict) or result.get('ok') is not True:
        raise ValueError('server_update_required')


def _send_events(root, token):
    """Send ordered batches and remove only IDs acknowledged by the server."""
    while True:
        with closing(sqlite3.connect(init.database_user, timeout=10)) as db:
            exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='leaderboard_event_outbox'").fetchone()
            if not exists:
                return
            rows = db.execute('SELECT event_id,match_id,mode,kind,occurred_at FROM leaderboard_event_outbox ORDER BY rowid LIMIT 100').fetchall()
        with closing(_db()) as settings:
            allowed = settings.execute('SELECT enabled,event_permission FROM online_leaderboard WHERE id=1').fetchone()
        if not rows or not allowed[0] or not allowed[1]:
            return
        try:
            events = [{'event_id':row[0], 'match_id':row[1], 'mode':decrypt_value(row[2]).decode('utf-8'), 'kind':decrypt_value(row[3]).decode('utf-8'), 'occurred_at':decrypt_value(row[4]).decode('utf-8')} for row in rows]
        except Exception as error:
            raise ValueError('event_conflict') from error
        try:
            result = _call('POST', '/api/v1/events', {'events':events}, token, root=root)
        except HTTPError as error:
            if error.code in (409, 422):
                raise ValueError('event_conflict') from error
            if error.code in (404, 405, 426):
                raise ValueError('server_update_required') from error
            raise
        identifiers = [row[0] for row in rows]
        if not isinstance(result, dict) or result.get('accepted') != identifiers:
            raise ValueError('invalid_event_acknowledgement')
        with closing(sqlite3.connect(init.database_user, timeout=10)) as db, db:
            db.executemany('DELETE FROM leaderboard_event_outbox WHERE event_id=?', [(ident,) for ident in identifiers])


def _clear_event_outbox():
    with closing(sqlite3.connect(init.database_user, timeout=10)) as db, db:
        for table in ('leaderboard_event_outbox', 'leaderboard_event_state'):
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
                db.execute('DELETE FROM ' + table)


def _sync():
    with _LOCK:
        enabled, ident, encrypted, pending, server = _settings()
        # An old or incomplete identity may still carry a pending operation.
        # Even without a readable token, a Store build must not treat that
        # operation as completed or clear its queued events locally.
        if FROZEN and server != _DEFAULT_BASE_URL and (server or ident or encrypted):
            if pending:
                _STATUS['state'] = 'delete_pending'
                return 'delete_failed'
            if _login_cancel_pending():
                _STATUS['state'] = 'steam_cancel_pending'
                return 'steam_cancel_failed'
            if _language_remove_pending():
                _STATUS['state'] = 'language_remove_pending'
                return 'language_delete_failed'
            if _steam_settings()[1]:
                _STATUS['state'] = 'steam_remove_pending'
                return 'steam_delete_failed'
        if pending:
            try:
                if encrypted:
                    # A bearer credential must never fall back to a newly
                    # configured server when its original destination is lost.
                    if not server:
                        raise RuntimeError('server_changed')
                    _call('DELETE', '/api/v1/profile', token=_stored_token(server), root=server)
                _clear_event_outbox()
                with closing(_db()) as db, db:
                    db.execute('UPDATE online_leaderboard SET uuid=NULL,token=NULL,rotation_token=NULL,recovery_payload=NULL,delete_pending=0,server_url=NULL,steam_permission=0,steam_remove_pending=0,language_remove_pending=0,steam_login_cancel_pending=0 WHERE id=1')
                _STATUS['state'] = 'deleted'
            except Exception:
                _STATUS['state'] = 'delete_pending'
                return 'delete_failed'
            return 'deleted'
        if _login_cancel_pending():
            try:
                if encrypted:
                    if not server:
                        raise RuntimeError('server_changed')
                    token = _stored_token(server)
                    _call('DELETE', '/api/v1/steam/login', token=token, root=server)
                with closing(_db()) as db, db:
                    db.execute('UPDATE online_leaderboard SET steam_login_cancel_pending=0 WHERE id=1')
            except Exception:
                _STATUS['state'] = 'steam_cancel_pending'
                return 'steam_cancel_failed'
        if _language_remove_pending():
            try:
                if encrypted:
                    if not server:
                        raise RuntimeError('server_changed')
                    token = _stored_token(server)
                    _call('DELETE', '/api/v1/profile/language', token=token, root=server)
                with closing(_db()) as db, db:
                    db.execute('UPDATE online_leaderboard SET language_remove_pending=0 WHERE id=1')
            except Exception:
                _STATUS['state'] = 'language_remove_pending'
                return 'language_delete_failed'
        steam_allowed, steam_pending = _steam_settings()
        if steam_pending:
            try:
                if encrypted:
                    if not server:
                        raise RuntimeError('server_changed')
                    token = _stored_token(server)
                    _call('DELETE', '/api/v1/profile/steam', token=token, root=server)
                with closing(_db()) as db, db:
                    db.execute('UPDATE online_leaderboard SET steam_remove_pending=0 WHERE id=1')
            except Exception:
                _STATUS['state'] = 'steam_remove_pending'
                return 'steam_delete_failed'
        if not enabled:
            _STATUS['state'] = 'disabled'
            return
        if not _event_permission():
            _STATUS['state'] = 'event_consent_required'
            return
        try:
            root = _base_url()
            if not root:
                raise RuntimeError('not_configured')
            token = _credentials(root)
            steam_id = _verified_steam(root, token)
            if not steam_id:
                _STATUS['state'] = 'steam_login_required'
                return
            if not _settings()[0] or not _event_permission():
                _STATUS['state'] = 'disabled' if not _settings()[0] else 'event_consent_required'
                return
            _ensure_event_consent(root, token)
            _send_events(root, token)
            profile = _profile()
            # Existing participants must separately approve the newly public language.
            if _language_permission() != 1:
                profile['language'] = None
            profile['steam_id'] = steam_id if steam_allowed else None
            # Consent can be withdrawn while the registration request is in flight.
            if not _settings()[0]:
                _STATUS['state'] = 'disabled'
                return
            _call('PUT', '/api/v1/profile', profile, token, root=root)
            _STATUS['state'] = 'success'
        except Exception as error:
            _STATUS['state'] = str(error) if str(error) in ('not_configured', 'profile_required', 'invalid_statistics', 'server_changed', 'fresh_consent_required', 'pending_events', 'active_match', 'invalid_data', 'event_conflict', 'server_update_required') else 'offline'


@app.route('/online-leaderboard/settings', methods=['GET', 'POST'])
def online_leaderboard_settings():
    global _RECOVERY_GRANT
    if request.method == 'POST':
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify(error='invalid_request'), 400
        enabled = data.get('enabled')
        if not isinstance(enabled, bool) or (enabled and data.get('consent') is not True) or (not enabled and data.get('remove') not in (True, False)):
            return jsonify(error='invalid_request'), 400
        # Do not transfer orphaned events from a prior, unbound installation
        # under a new server's consent. Lock both databases for the final check
        # and consent update; an old active monitor must first be stopped.
        tracking = None
        try:
            with closing(_db()) as db:
                prior = db.execute('SELECT uuid,token,server_url,server_consent_url,legacy_unbound_guard FROM online_leaderboard WHERE id=1').fetchone()
                inspect_old_events = bool(FROZEN and enabled and not any(prior[:3]) and prior[3] != _DEFAULT_BASE_URL)
                if inspect_old_events and prior[4]:
                    tracking = _tracking_module()
                    if not tracking.monitor_lock.acquire(blocking=False):
                        tracking = None
                        return jsonify(error='tracking_running'), 409
                    if tracking.run_monitor or tracking.fight:
                        return jsonify(error='tracking_running'), 409
                if inspect_old_events:
                    path = Path(init.database_user)
                    if not path.is_file():
                        return jsonify(error='invalid_data'), 409
                    db.execute('ATTACH DATABASE ? AS tracker_user', (path.absolute().as_uri() + '?mode=rw',))
                with db:
                    db.execute('BEGIN IMMEDIATE')
                    row = db.execute('SELECT delete_pending,steam_login_cancel_pending,server_transition_nonce,uuid,token,server_url,server_consent_url,legacy_unbound_guard FROM online_leaderboard WHERE id=1').fetchone()
                    pending, cancel_pending, transition_nonce = row[:3]
                    if enabled and (pending or cancel_pending):
                        return jsonify(error='delete_pending'), 409
                    supplied_nonce = data.get('transition_nonce')
                    if transition_nonce and (not isinstance(supplied_nonce, str) or not supplied_nonce.isascii()
                                             or not secrets.compare_digest(supplied_nonce, transition_nonce)):
                        return jsonify(error='fresh_consent_required'), 409
                    check_old_events = bool(FROZEN and enabled and not any(row[3:6]) and row[6] != _DEFAULT_BASE_URL)
                    if check_old_events:
                        if not inspect_old_events or (row[7] and tracking is None):
                            return jsonify(error='busy'), 409
                        blocker = _event_transition_blocker(db, 'tracker_user')
                        if blocker:
                            return jsonify(error=blocker), 409
                    if enabled:
                        db.execute('UPDATE online_leaderboard SET enabled=1,delete_pending=0,language_permission=?,event_permission=?,server_transition_nonce=NULL,server_consent_url=?,legacy_unbound_guard=0 WHERE id=1', (int(data.get('language_consent') is True), int(data.get('event_consent') is True), _base_url()))
                    else:
                        db.execute('UPDATE online_leaderboard SET enabled=0,delete_pending=?,steam_login_cancel_pending=? WHERE id=1', (int(data.get('remove') is True), int(data.get('remove') is False)))
        except (OSError, ValueError, sqlite3.Error):
            return jsonify(error='invalid_data'), 409
        finally:
            if tracking is not None:
                tracking.monitor_lock.release()
        if not enabled:
            _RECOVERY_GRANT = None
            _STATUS['state'] = 'delete_pending' if data.get('remove') else 'disabled'
            start_sync()
    enabled, ident, token, pending, server = _settings()
    permission = _language_permission()
    with closing(_db()) as db:
        event_value, transition_nonce, consent_url = db.execute('SELECT event_permission,server_transition_nonce,server_consent_url FROM online_leaderboard WHERE id=1').fetchone()
        event_permission = bool(event_value)
    migration_available = bool(FROZEN and ident and token and server and server != _DEFAULT_BASE_URL)
    server_consent_required = bool(FROZEN and enabled and not ident and not token and not server and consent_url != _DEFAULT_BASE_URL)
    partial_identity = bool(FROZEN and any((ident, token, server)) and not all((ident, token, server)))
    transition_blocked = bool(FROZEN and not any((ident, token, server)) and consent_url != _DEFAULT_BASE_URL and _unbound_events_pending())
    return jsonify(enabled=enabled, configured=bool(_base_url()), language_consent_pending=enabled and permission == 0, event_consent_pending=enabled and not event_permission, language_shared=permission == 1, steam_status_observe=True, language_remove_pending=_language_remove_pending(), steam_consent=_steam_settings()[0], steam_remove_pending=_steam_settings()[1], state='delete_pending' if pending else _STATUS['state'], retry_after_ms=sync_cooldown_remaining_ms(), transition_nonce=transition_nonce, migration_available=migration_available, server_consent_required=server_consent_required, partial_identity=partial_identity, transition_blocked=transition_blocked)


def _tracking_module():
    # Import only during this explicit action, once the tracker has started.
    from application import functions
    return functions


@app.route('/online-leaderboard/migrate-server', methods=['POST'])
def online_leaderboard_migrate_server():
    global _LAST_SYNC_START, _LANGUAGE_SYNC_REQUIRED
    if not FROZEN:
        return jsonify(error='not_available'), 404
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or data.get('confirm') is not True:
        return jsonify(error='invalid_request'), 400
    from application import leaderboard_migration
    tracking = _tracking_module()
    if not tracking.monitor_lock.acquire(blocking=False):
        return jsonify(error='tracking_running'), 409
    try:
        if tracking.run_monitor or tracking.fight:
            return jsonify(error='tracking_running'), 409
        if not _START_LOCK.acquire(blocking=False):
            return jsonify(error='busy'), 409
        try:
            if _RUNNING or _RECOVERY_GRANT:
                return jsonify(error='busy'), 409
            if not _LOCK.acquire(blocking=False):
                return jsonify(error='busy'), 409
            try:
                if _RECOVERY_GRANT:
                    return jsonify(error='busy'), 409
                # Ensure the settings schema is initialized before the
                # cross-database transaction reads its transition fields.
                with closing(_db()):
                    pass
                leaderboard_migration.migrate(_database(), init.database_user, _DEFAULT_BASE_URL)
                _LAST_SYNC_START = None
                _LANGUAGE_SYNC_REQUIRED = False
                _STATUS['state'] = 'disabled'
                return jsonify(ok=True)
            except leaderboard_migration.MigrationError as error:
                code = str(error)
                if code not in ('no_identity', 'already_current', 'pending_operations', 'pending_events', 'active_match', 'invalid_data'):
                    code = 'invalid_data'
                return jsonify(error=code), 409
            except sqlite3.Error:
                return jsonify(error='unavailable'), 503
            finally:
                _LOCK.release()
        finally:
            _START_LOCK.release()
    finally:
        tracking.monitor_lock.release()


@app.route('/online-leaderboard/event-consent', methods=['POST'])
def online_leaderboard_event_consent():
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or data.get('consent') is not True:
        return jsonify(error='invalid_request'), 400
    with closing(_db()) as db, db:
        db.execute('BEGIN IMMEDIATE')
        enabled, pending = db.execute('SELECT enabled,delete_pending FROM online_leaderboard WHERE id=1').fetchone()
        if not enabled or pending:
            return jsonify(error='participation_disabled'), 409
        db.execute('UPDATE online_leaderboard SET event_permission=1 WHERE id=1')
    return jsonify(ok=True)


@app.route('/online-leaderboard/language-consent', methods=['POST'])
def online_leaderboard_language_consent():
    global _LANGUAGE_SYNC_REQUIRED
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error='invalid_request'), 400
    consent = data.get('consent')
    if not isinstance(consent, bool):
        return jsonify(error='invalid_request'), 400
    with closing(_db()) as db, db:
        db.execute('BEGIN IMMEDIATE')
        enabled, pending = db.execute('SELECT enabled,delete_pending FROM online_leaderboard WHERE id=1').fetchone()
        if not enabled or pending:
            return jsonify(error='participation_disabled'), 409
        db.execute('UPDATE online_leaderboard SET language_permission=?, language_remove_pending=? WHERE id=1', (1 if consent else -1, 0 if consent else 1))
    # Also publish a null value when sharing is refused, removing any old flag.
    with _START_LOCK:
        _LANGUAGE_SYNC_REQUIRED = True
    start_sync()
    return jsonify(ok=True)


@app.route('/online-leaderboard/steam-consent', methods=['POST'])
def online_leaderboard_steam_consent():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error='invalid_request'), 400
    consent = data.get('consent')
    if not isinstance(consent, bool):
        return jsonify(error='invalid_request'), 400
    with closing(_db()) as db, db:
        db.execute('BEGIN IMMEDIATE')
        enabled, pending, token = db.execute('SELECT enabled,delete_pending,token FROM online_leaderboard WHERE id=1').fetchone()
        if consent and (not enabled or pending):
            return jsonify(error='participation_disabled'), 409
        db.execute('UPDATE online_leaderboard SET steam_permission=?,steam_remove_pending=? WHERE id=1',
                   (int(consent), int(not consent and (bool(token) or bool(enabled)) and not pending)))
    # The next normal synchronization verifies Steam before publishing.  Keep
    # this route local, even while a network request is already in progress.
    return jsonify(ok=True, steam_consent=consent, steam_remove_pending=_steam_settings()[1])


@app.route('/online-leaderboard/steam-login', methods=['POST'])
def online_leaderboard_steam_login():
    global _RECOVERY_GRANT
    _RECOVERY_GRANT = None
    try:
        with _LOCK:
            root = _base_url()
            if not root:
                return jsonify(error='not_configured'), 503
            try:
                token = _credentials(root)
            except pywintypes.error:
                # Preserve a Windows-protected token from another account or
                # PC. Re-register only on this explicit login action and never
                # while a previous withdrawal or recovery remains pending.
                with closing(_db()) as db, db:
                    db.execute('BEGIN IMMEDIATE')
                    row = db.execute('SELECT enabled,delete_pending,server_url,token,rotation_token,recovery_payload,steam_remove_pending,language_remove_pending,steam_login_cancel_pending FROM online_leaderboard WHERE id=1').fetchone()
                    if not row[0] or row[1] or row[2] != root or not row[3] or any(row[4:]):
                        raise
                    db.execute('UPDATE online_leaderboard SET previous_token=COALESCE(previous_token,token),uuid=NULL,token=NULL,server_url=NULL,server_consent_url=? WHERE id=1', (root,))
                token = _credentials(root)
            if not _settings()[0]:
                return jsonify(error='participation_disabled'), 409
            language = init.get_selected_language()
            selected = language if _language_permission() == 1 and language in _LANGUAGES else 'browser'
            try:
                result = _call('POST', '/api/v1/steam/login', {'language': selected}, token=token, root=root)
            except HTTPError as error:
                if error.code != 401 or not _settings()[0] or _settings()[3]:
                    raise
                # An abandoned unverified installation may have expired on the
                # server. Re-register only when the user explicitly reconnects.
                with closing(_db()) as db, db:
                    db.execute('UPDATE online_leaderboard SET uuid=NULL,token=NULL,rotation_token=NULL,recovery_payload=NULL,server_url=NULL,server_consent_url=? WHERE id=1 AND enabled=1 AND delete_pending=0', (root,))
                token = _credentials(root)
                result = _call('POST', '/api/v1/steam/login', {'language': selected}, token=token, root=root)
            url = result.get('url') if isinstance(result, dict) else None
            parsed = urlparse(url or '')
            if parsed.scheme != 'https' or parsed.netloc != 'steamcommunity.com' or parsed.path != '/openid/login' or not parsed.query or parsed.fragment:
                raise ValueError('invalid_login_url')
            if not _settings()[0]:
                return jsonify(error='participation_disabled'), 409
            return jsonify(url=url)
    except Exception:
        return jsonify(error='unavailable'), 503
    finally:
        if _settings()[3] or _login_cancel_pending():
            start_sync()


@app.route('/online-leaderboard/steam-cancel', methods=['POST'])
def online_leaderboard_steam_cancel():
    global _RECOVERY_GRANT
    _RECOVERY_GRANT = None
    try:
        with _LOCK:
            root = _base_url()
            if not root:
                return jsonify(error='not_configured'), 503
            _call('DELETE', '/api/v1/steam/login', token=_credentials(root), root=root)
        return jsonify(ok=True)
    except Exception:
        return jsonify(error='unavailable'), 503


@app.route('/online-leaderboard/steam-status', methods=['GET'])
def online_leaderboard_steam_status():
    global _LANGUAGE_SYNC_REQUIRED
    try:
        with _LOCK:
            root = _base_url()
            if not root:
                return jsonify(error='not_configured'), 503
            status = _remote_steam_status(root, _credentials(root))
            connected = status['connected']
        observe = request.args.get('observe') == '1'
        if connected and not observe:
            with _START_LOCK:
                _LANGUAGE_SYNC_REQUIRED = True
            start_sync()
        return jsonify(connected=connected, confirmation_pending=status.get('confirmation_pending') is True, observation_only=observe)
    except Exception:
        return jsonify(error='unavailable'), 503


@app.route('/online-leaderboard/steam-confirm', methods=['POST'])
def online_leaderboard_steam_confirm():
    global _RECOVERY_GRANT
    data = request.get_json(silent=True)
    code = data.get('code') if isinstance(data, dict) else None
    if not isinstance(code, str) or len(code) != 8 or not code.isascii() or not code.isdigit():
        return jsonify(error='invalid_code'), 400
    try:
        with _LOCK:
            root = _base_url()
            if not root:
                return jsonify(error='not_configured'), 503
            result = _call('POST', '/api/v1/steam/confirm', {'code': code}, _credentials(root), root=root)
            if not isinstance(result, dict) or result.get('connected') is not True:
                return jsonify(error='invalid_code'), 400
            grant = result.get('recovery_grant')
            _RECOVERY_GRANT = grant if isinstance(grant, str) and len(grant) == 64 and all(c in '0123456789abcdef' for c in grant) else None
            try:
                _rotate_token(root, _credentials(root))
            except Exception:
                # The saved pending token is retried before the next authenticated request.
                pass
        return jsonify(connected=True)
    except HTTPError as error:
        return jsonify(error='invalid_code' if error.code == 422 else 'unavailable'), (400 if error.code == 422 else 503)
    except Exception:
        return jsonify(error='unavailable'), 503


@app.route('/online-leaderboard/steam-recovery', methods=['GET', 'POST'])
def online_leaderboard_steam_recovery():
    if not _RECOVERY_GRANT:
        return jsonify(error='fresh_confirmation_required'), 401
    try:
        with _LOCK:
            root = _base_url()
            if not root:
                return jsonify(error='not_configured'), 503
            token = _credentials(root)
            if request.method == 'GET':
                result = _call('GET', '/api/v1/steam/recovery', token=token, root=root, extra_headers={'X-Steam-Recovery':_RECOVERY_GRANT})
                if not isinstance(result, dict) or not isinstance(result.get('installations'), list):
                    raise ValueError('invalid_recovery_response')
                return jsonify(installations=result['installations'])
            data = request.get_json(silent=True)
            uuid_value = data.get('uuid') if isinstance(data, dict) else None
            try:
                if not isinstance(uuid_value, str) or str(uuid.UUID(uuid_value, version=4)) != uuid_value:
                    raise ValueError('invalid_uuid')
            except (ValueError, AttributeError):
                return jsonify(error='invalid_request'), 400
            identity = _verified_steam(root, token)
            if not identity:
                return jsonify(error='steam_login_required'), 409
            payload = json.dumps({'uuid':uuid_value, 'new_token':secrets.token_hex(32), 'steam_id':identity, 'grant':_RECOVERY_GRANT}).encode('utf-8')
            protected = win32crypt.CryptProtectData(payload, 'Elden Ring PvP Tracker recovery', None, None, None, 0)
            with closing(_db()) as db, db:
                db.execute('UPDATE online_leaderboard SET recovery_payload=? WHERE id=1', (protected,))
            _complete_recovery(root, token, protected)
            return jsonify(ok=True)
    except HTTPError as error:
        return jsonify(error='fresh_confirmation_required' if error.code == 401 else 'unavailable'), (401 if error.code == 401 else 503)
    except Exception:
        return jsonify(error='unavailable'), 503


def _worker():
    global _RUNNING, _LANGUAGE_SYNC_REQUIRED
    while True:
        with _START_LOCK:
            _LANGUAGE_SYNC_REQUIRED = False
        result = _sync()
        with _START_LOCK:
            # A withdrawal during upload must be handled even if no browser
            # remains open. Do not spin when the server is unavailable.
            if _settings()[3] and result != 'delete_failed':
                _STATUS['state'] = 'syncing'
                continue
            if _login_cancel_pending() and result != 'steam_cancel_failed':
                _STATUS['state'] = 'syncing'
                continue
            if _LANGUAGE_SYNC_REQUIRED and (_settings()[0] or (_steam_settings()[1] and result != 'steam_delete_failed') or (_language_remove_pending() and result != 'language_delete_failed')):
                _STATUS['state'] = 'syncing'
                continue
            _RUNNING = False
            return


def start_sync(rate_limit=False):
    global _RUNNING, _LAST_SYNC_START
    with _START_LOCK:
        enabled, _, _, pending, _ = _settings()
        steam_pending = _steam_settings()[1]
        language_pending = _language_remove_pending()
        cancel_pending = _login_cancel_pending()
        if not enabled and not pending and not steam_pending and not language_pending and not cancel_pending:
            return 'disabled'
        if _RUNNING:
            return 'syncing'
        now = time.monotonic()
        if rate_limit and not pending and not steam_pending and not language_pending and not cancel_pending and _LAST_SYNC_START is not None and now - _LAST_SYNC_START < _SYNC_INTERVAL_SECONDS:
            return 'rate_limited'
        if not pending:
            _LAST_SYNC_START = now
        _RUNNING = True
        _STATUS['state'] = 'syncing'
        threading.Thread(target=_worker, daemon=True).start()
        return _STATUS['state']


def sync_cooldown_remaining_ms():
    with _START_LOCK:
        if _LAST_SYNC_START is None:
            return 0
        return max(0, math.ceil((_SYNC_INTERVAL_SECONDS - (time.monotonic() - _LAST_SYNC_START)) * 1000))


@app.route('/online-leaderboard/sync', methods=['POST'])
def online_leaderboard_sync():
    state = start_sync(rate_limit=True)
    return jsonify(state=state, retry_after_ms=sync_cooldown_remaining_ms())


@app.route('/online-leaderboard/status', methods=['GET'])
def online_leaderboard_status():
    return jsonify(state=_STATUS['state'])


@app.route('/online-leaderboard/entries', methods=['GET'])
def online_leaderboard_entries():
    mode = request.args.get('mode', 'Arena')
    if mode not in mode_stats.MODES:
        return jsonify(error='invalid_mode'), 400
    try:
        page = max(1, min(int(request.args.get('page', '1')), 1000000))
        search = request.args.get('search', '')
        sort = request.args.get('sort', 'rank')
        direction = request.args.get('direction', 'asc')
        if len(search) > 80 or sort not in ('rank', 'language', 'name', 'level', 'score', 'victory', 'defeat', 'egality', 'ratio', 'combats') or direction not in ('asc', 'desc'):
            return jsonify(error='invalid_request'), 400
        query = urlencode({'mode': mode, 'per_page': 5, 'page': page, 'search': search, 'sort': sort, 'direction': direction})
        return jsonify(_call('GET', '/api/v1/leaderboards?' + query))
    except Exception:
        return jsonify(error='unavailable'), 503
