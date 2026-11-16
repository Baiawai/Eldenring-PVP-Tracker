"""Minimal installation heartbeat independent of the optional leaderboard."""
import json
import sqlite3
import threading
import time
import uuid
from contextlib import closing
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from application.runtime_paths import database_path
from application import network_retry

ENDPOINT = 'https://eldenringpvp.com/api/v1/tracker-presence'
INTERVAL_SECONDS = 480
TIMEOUT_SECONDS = 5
_start_lock = threading.Lock()
_started = False
_pulse = threading.Event()
_last_browser_pulse = 0.0
_is_tracking = lambda: False


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def installation_id():
    database = database_path('usage_metrics.db')
    database.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(str(database), timeout=5)) as db, db:
        db.execute('CREATE TABLE IF NOT EXISTS tracker_presence_identity (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL)')
        db.execute('INSERT OR IGNORE INTO tracker_presence_identity(id,value) VALUES (1,?)', (uuid.uuid4().hex,))
        return db.execute('SELECT value FROM tracker_presence_identity WHERE id=1').fetchone()[0]


def send_heartbeat(active=False):
    payload = json.dumps({'installation_id': installation_id(), 'active': bool(active)}).encode('utf-8')
    request = Request(ENDPOINT, data=payload, headers={'Content-Type': 'application/json', 'Accept': 'application/json'}, method='POST')
    with build_opener(_NoRedirect()).open(request, timeout=TIMEOUT_SECONDS) as response:
        return response.status == 204


def _send_safely(active):
    try:
        network_retry.execute(lambda: send_heartbeat(active), safe=True)
    except (OSError, ValueError, sqlite3.Error, HTTPError, URLError):
        pass


def _run():
    # Register an installation without treating the background process as use.
    _send_safely(False)
    while True:
        signalled = _pulse.wait(INTERVAL_SECONDS)
        _pulse.clear()
        try:
            tracking = bool(_is_tracking())
        except Exception:
            tracking = False
        if signalled or tracking:
            _send_safely(True)


def notify_browser():
    global _last_browser_pulse
    now = time.monotonic()
    with _start_lock:
        if not _started or (_last_browser_pulse and now - _last_browser_pulse < 30):
            return
        _last_browser_pulse = now
        _pulse.set()


def notify_tracking():
    if _started:
        _pulse.set()


def start(is_tracking=None):
    global _started, _is_tracking
    with _start_lock:
        if _started:
            return
        _is_tracking = is_tracking if callable(is_tracking) else lambda: False
        _started = True
        threading.Thread(target=_run, name='tracker-presence', daemon=True).start()
