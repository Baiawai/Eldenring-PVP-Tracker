"""Bounded, privacy-preserving diagnostics, independent of Steam and the leaderboard."""
import hashlib
import ipaddress
import json
import os
import re
import sqlite3
import threading
import time
import traceback
import uuid
from contextlib import closing
from urllib.request import HTTPRedirectHandler, Request, build_opener

from application.runtime_paths import database_path
from application.version import APP_VERSION

ENDPOINT = 'https://eldenringpvp.com/api/v1/tracker-errors'
MAX_PENDING = 100
MAX_AGE = 7 * 86400
REPEAT_INTERVAL = 600
_lock = threading.Lock()
_started = False
_wakeup = threading.Event()
_STAGES = frozenset(('application', 'initialization', 'capture', 'steam_login', 'steam_credentials', 'steam_status', 'steam_confirmation', 'steam_browser', 'leaderboard'))
_CATEGORIES = frozenset(('browser', 'http', 'tls', 'timeout', 'dns', 'storage', 'network', 'other'))
_ERRORS = frozenset(('OSError', 'FileNotFoundError', 'PermissionError', 'TimeoutError', 'ConnectionError', 'RuntimeError', 'ValueError', 'OperationalError', 'DatabaseError', 'IntegrityError', 'HTTPError', 'URLError', 'SSLError', 'gaierror', 'error'))


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _connect():
    path = database_path('error_reports.db')
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path), timeout=2)
    db.execute('CREATE TABLE IF NOT EXISTS pending (id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, created INTEGER NOT NULL, payload TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY CHECK(id=1), enabled INTEGER NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS recent (fingerprint TEXT PRIMARY KEY, created INTEGER NOT NULL)')
    return db


def enabled():
    with closing(_connect()) as db:
        row = db.execute('SELECT enabled FROM settings WHERE id=1').fetchone()
        return bool(row[0]) if row else True


def set_enabled(value):
    with _lock, closing(_connect()) as db, db:
        db.execute('INSERT OR REPLACE INTO settings(id, enabled) VALUES(1, ?)', (int(value),))
        if not value:
            db.execute('DELETE FROM pending')
            db.execute('DELETE FROM recent')
    if value:
        start()


_SOURCES = frozenset(('functions.py', 'online_leaderboard.py', 'first_run.py', 'init.py', 'ELDENRING_Tracker.py'))


def _redact(text):
    """Remove common secrets and identifiers; arbitrary free text cannot be guaranteed anonymous."""
    text = str(text).replace('\x00', '')[:12000]
    text = re.sub(r'(?i)https?://[^\s<>]+', '[URL]', text)
    text = re.sub(r'(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b', '[email]', text)
    text = re.sub(r'(?i)\b(?:bearer|basic)\s+[a-z0-9._~+/=-]+', '[identifiant]', text)
    text = re.sub(r'(?i)\b(token|password|passwd|secret|authorization|api[_-]?key|code|steam[_-]?id|player|username|user|joueur|pseudo)\b\s*[:=]\s*[^\s,;]+', r'\1=[masqué]', text)
    text = re.sub(r"[\"'][^\"'\r\n]{1,1000}[\"']", '[valeur masquée]', text)
    text = re.sub(r'(?i)\b[A-Z]:[\\/][^\s,;\)\]]+', '[chemin]', text)
    text = re.sub(r'(?<![\w])/(?:[^/\s]+/)*[^\s,;\)\]]+', '[chemin]', text)
    text = re.sub(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', '[adresse IP]', text)
    def hide_ipv6(match):
        candidate = match.group(0)
        try:
            return '[adresse IP]' if ipaddress.ip_address(candidate).version == 6 else candidate
        except ValueError:
            return candidate
    text = re.sub(r'(?<![\w:])(?:[0-9a-fA-F]{0,4}:){2,7}[0-9a-fA-F]{0,4}(?![\w:])', hide_ipv6, text)
    text = re.sub(r'(?i)\b[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\b', '[identifiant]', text)
    text = re.sub(r'(?i)\b[0-9a-f]{16,}\b', '[identifiant]', text)
    return text[:8000]


def _error_details(error):
    if error is None:
        return ''
    entries = []
    seen = set()
    while error is not None and id(error) not in seen and len(seen) < 4:
        seen.add(id(error))
        entries.append(error)
        error = error.__cause__ or (None if error.__suppress_context__ else error.__context__)
    lines = []
    for index, current in enumerate(reversed(entries)):
        if index:
            lines.append('\nException suivante :')
        frames = traceback.extract_tb(current.__traceback__)[-20:] if current.__traceback__ else []
        if frames:
            lines.append('Traceback (most recent call last):')
        for frame in frames:
            source = os.path.basename(frame.filename)
            source = source if source in _SOURCES else '[module]'
            function = frame.name if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.<>]{0,79}', frame.name) else '[fonction]'
            lines.append(f'  File {source}, line {frame.lineno}, in {function}')
            if frame.line:
                lines.append('    ' + _redact(frame.line.strip()))
        name = type(current).__name__
        name = name if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,79}', name) else 'Exception'
        lines.append(name + ': ' + _redact(current))
    return _redact('\n'.join(lines))[:8000]


def _payload(stage, category, error=None, status=None):
    name = type(error).__name__ if error is not None else 'other'
    result = {'report_id': uuid.uuid4().hex, 'version': APP_VERSION,
              'stage': stage if stage in _STAGES else 'leaderboard',
              'category': category if category in _CATEGORIES else 'other',
              'exception': name if name in _ERRORS else 'other'}
    details = _error_details(error)
    if details:
        result['details'] = details
    if type(status) is int and 100 <= status <= 599:
        result['http_status'] = status
    # Only recognized source file names and line numbers are sent as structured context.
    if error is not None and error.__traceback__:
        frames = [frame for frame in traceback.extract_tb(error.__traceback__)
                  if os.path.basename(frame.filename) in ('functions.py', 'online_leaderboard.py', 'first_run.py', 'init.py', 'ELDENRING_Tracker.py')
                  and 0 < frame.lineno < 100000]
        if frames:
            result['source'] = os.path.basename(frames[-1].filename)
            result['line'] = frames[-1].lineno
    return result


def _enqueue(payload):
    now = int(time.time())
    signature = {key: value for key, value in payload.items() if key not in ('report_id', 'details')}
    fingerprint = hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest()
    with _lock, closing(_connect()) as db, db:
        row = db.execute('SELECT enabled FROM settings WHERE id=1').fetchone()
        if row and not row[0]:
            return
        db.execute('DELETE FROM pending WHERE created < ?', (now - MAX_AGE,))
        db.execute('DELETE FROM recent WHERE created < ?', (now - REPEAT_INTERVAL,))
        if db.execute('SELECT 1 FROM recent WHERE fingerprint = ?', (fingerprint,)).fetchone():
            return
        db.execute('INSERT INTO recent VALUES (?, ?)', (fingerprint, now))
        db.execute('INSERT INTO pending VALUES (?, ?, ?, ?)', (payload['report_id'], fingerprint, now, json.dumps(payload)))
        db.execute('DELETE FROM pending WHERE id IN (SELECT id FROM pending ORDER BY created DESC, rowid DESC LIMIT -1 OFFSET ?)', (MAX_PENDING,))


def _send_pending():
    if not enabled():
        return
    with closing(_connect()) as db, db:
        db.execute('DELETE FROM pending WHERE created < ?', (int(time.time()) - MAX_AGE,))
        rows = db.execute('SELECT id, payload FROM pending ORDER BY created LIMIT 20').fetchall()
    for report_id, payload in rows:
        # Serialize disabling with in-flight sends; when disabling returns, no
        # previously queued request can start afterwards.
        with _lock:
            if not enabled():
                break
            request = Request(ENDPOINT, data=payload.encode(), headers={'Content-Type': 'application/json', 'Accept': 'application/json'}, method='POST')
            try:
                with build_opener(_NoRedirect()).open(request, timeout=5) as response:
                    if response.status != 204:
                        break
                with closing(_connect()) as db, db:
                    db.execute('DELETE FROM pending WHERE id = ?', (report_id,))
            except (OSError, ValueError):
                break


def _worker():
    while True:
        _wakeup.wait(60)
        _wakeup.clear()
        try:
            _send_pending()
        except (OSError, sqlite3.Error, ValueError):
            pass


def start():
    global _started
    with _lock:
        if not _started:
            _started = True
            threading.Thread(target=_worker, name='error-reports', daemon=True).start()
    _wakeup.set()


def report(stage, category='other', error=None, status=None):
    payload = _payload(stage, category, error, status)
    def queue():
        try:
            try:
                from application.init import get_selected_language
                language = get_selected_language()
                if language in ('fra', 'eng', 'deu', 'ita', 'spaes', 'spaar', 'por', 'pol', 'rus', 'jap', 'kor', 'chi', 'zht', 'tha', 'ara'):
                    payload['language'] = language
            except Exception:
                pass
            _enqueue(payload)
            start()
        except (OSError, sqlite3.Error, ValueError):
            pass
    try:
        threading.Thread(target=queue, name='queue-error-report', daemon=True).start()
    except RuntimeError:
        pass
