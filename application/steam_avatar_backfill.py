"""Recover missing avatars once for Steam profiles already in active history.

The persistent work list contains only the same hashed Steam keys used by the
avatar cache and local event IDs. It never stores clear Steam IDs, IPs or
images. Existing history and images remain owned by their usual modules.
"""
import json
import logging
import sqlite3
import threading
import time
from contextlib import closing

from application import peer_tracking, steam_avatar_store
from application.secur import decrypt_value

_LOG = logging.getLogger(__name__)
_BATCH = 250
_MAX_ATTEMPTS = 3
_RETRY_SECONDS = 300
_RATE_RETRY_SECONDS = 30
_WAIT_SECONDS = 5
_RUN = 'historical-steam-avatars-v1'
_start_lock = threading.Lock()
_started = False


def _database():
    from application.init import database_capture
    return database_capture


def _schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS steam_avatar_backfill (
        name TEXT PRIMARY KEY, upper_id INTEGER NOT NULL, cursor INTEGER NOT NULL,
        scanned INTEGER NOT NULL DEFAULT 0, completed INTEGER NOT NULL DEFAULT 0,
        total INTEGER NOT NULL DEFAULT 0, unavailable INTEGER NOT NULL DEFAULT 0,
        removed INTEGER NOT NULL DEFAULT 0)''')
    db.execute('''CREATE TABLE IF NOT EXISTS steam_avatar_backfill_jobs (
        run TEXT NOT NULL, steam_key TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
        next_attempt REAL NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'pending',
        PRIMARY KEY(run,steam_key))''')
    db.execute('''CREATE TABLE IF NOT EXISTS steam_avatar_backfill_events (
        run TEXT NOT NULL, steam_key TEXT NOT NULL, event_id INTEGER NOT NULL,
        PRIMARY KEY (run,steam_key,event_id))''')
    db.execute('''CREATE TABLE IF NOT EXISTS steam_avatar_cache_policy (
        id INTEGER PRIMARY KEY CHECK(id=1), capacity INTEGER NOT NULL)''')


def initialize():
    """Fix a durable upper bound before the tracker records new encounters."""
    with closing(sqlite3.connect(_database(), timeout=1)) as db, db:
        db.execute('BEGIN IMMEDIATE')
        _schema(db)
        state = db.execute('SELECT completed FROM steam_avatar_backfill WHERE name=?', (_RUN,)).fetchone()
        if state:
            return not bool(state[0])
        upper = db.execute("SELECT COALESCE(MAX(id),0) FROM detection_history WHERE kind='steam_encounter'").fetchone()[0]
        db.execute('INSERT INTO steam_avatar_backfill(name,upper_id,cursor) VALUES(?,?,?)', (_RUN, upper, upper))
        return True


def _steam_id(metadata):
    if not isinstance(metadata, (bytes, str)):
        return None
    # A missing or invalid encryption key must pause recovery, not make a
    # profile look nonexistent and prematurely mark the one-time run done.
    decoded = decrypt_value(metadata).decode('utf-8')
    try:
        data = json.loads(decoded)
        value = data.get('id') if isinstance(data, dict) else None
        if isinstance(value, int) and not isinstance(value, bool):
            value = str(value)
        return value if peer_tracking._historical_avatar_id(value) else None
    except (ValueError, TypeError):
        return None


def _scan_batch():
    with closing(sqlite3.connect(_database(), timeout=10)) as db:
        state = db.execute('SELECT cursor,scanned,completed FROM steam_avatar_backfill WHERE name=?', (_RUN,)).fetchone()
        if not state or state[1] or state[2]:
            return
        rows = db.execute("SELECT id,metadata FROM detection_history WHERE kind='steam_encounter' AND id<=? ORDER BY id DESC LIMIT ?",
                          (state[0], _BATCH)).fetchall()
    candidates = []
    for event_id, encrypted in rows:
        sid = _steam_id(encrypted) if encrypted else None
        if sid:
            candidates.append((steam_avatar_store._key(sid), event_id))
    with closing(sqlite3.connect(_database(), timeout=10)) as db, db:
        db.execute('BEGIN IMMEDIATE')
        current = db.execute('SELECT cursor,scanned FROM steam_avatar_backfill WHERE name=?', (_RUN,)).fetchone()
        if not current or current != (state[0], 0):
            return
        db.executemany('INSERT OR IGNORE INTO steam_avatar_backfill_jobs(run,steam_key) VALUES(?,?)', [(_RUN, key) for key, _ in candidates])
        db.executemany('INSERT OR IGNORE INTO steam_avatar_backfill_events(run,steam_key,event_id) VALUES(?,?,?)',
                       [(_RUN, key, event_id) for key, event_id in candidates])
        if rows:
            db.execute('UPDATE steam_avatar_backfill SET cursor=? WHERE name=?', (rows[-1][0] - 1, _RUN))
        else:
            total = db.execute('SELECT COUNT(*) FROM steam_avatar_backfill_jobs WHERE run=?', (_RUN,)).fetchone()[0]
            existing_other = 0
            if steam_avatar_store._has_table(db, 'steam_avatars'):
                existing_other = db.execute('''SELECT COUNT(*) FROM steam_avatars a
                    WHERE NOT EXISTS (SELECT 1 FROM steam_avatar_backfill_jobs j WHERE j.run=? AND j.steam_key=a.steam_key)''', (_RUN,)).fetchone()[0]
            capacity = max(steam_avatar_store.MAX_ENTRIES, total + existing_other)
            db.execute('''INSERT INTO steam_avatar_cache_policy(id,capacity) VALUES(1,?)
                ON CONFLICT(id) DO UPDATE SET capacity=MAX(capacity,excluded.capacity)''', (capacity,))
            db.execute('UPDATE steam_avatar_backfill SET scanned=1,total=? WHERE name=?', (total, _RUN))


def _resolve(key):
    """Find still-active matching events; archives or purges are never undone."""
    with closing(sqlite3.connect(_database(), timeout=10)) as db:
        rows = db.execute('''SELECT h.id,h.metadata FROM steam_avatar_backfill_events c
            JOIN detection_history h ON h.id=c.event_id AND h.kind='steam_encounter'
            WHERE c.run=? AND c.steam_key=? ORDER BY h.id DESC''', (_RUN, key))
        found, ids = None, []
        for event_id, encrypted in rows:
            sid = _steam_id(encrypted) if encrypted else None
            if sid and steam_avatar_store._key(sid) == key:
                found = sid
                ids.append(event_id)
                if len(ids) >= steam_avatar_store.MAX_EVENT_IDS:
                    break
        return found, tuple(ids)


def _mark(key, status, *, now=0):
    with closing(sqlite3.connect(_database(), timeout=10)) as db, db:
        db.execute('BEGIN IMMEDIATE')
        if status == 'unavailable':
            db.execute('''UPDATE steam_avatar_backfill_jobs SET attempts=attempts+1,
                status=CASE WHEN attempts+1>=? THEN 'unavailable' ELSE 'pending' END,
                next_attempt=? WHERE run=? AND steam_key=? AND status='pending' ''', (_MAX_ATTEMPTS, now + _RETRY_SECONDS, _RUN, key))
        elif status == 'rate_limited':
            db.execute("UPDATE steam_avatar_backfill_jobs SET next_attempt=? WHERE run=? AND steam_key=? AND status='pending'",
                       (now + _RATE_RETRY_SECONDS, _RUN, key))
        else:
            db.execute("UPDATE steam_avatar_backfill_jobs SET status=? WHERE run=? AND steam_key=? AND status='pending'", (status, _RUN, key))


def _finish_if_done():
    with closing(sqlite3.connect(_database(), timeout=10)) as db, db:
        db.execute('BEGIN IMMEDIATE')
        state = db.execute('SELECT scanned,completed FROM steam_avatar_backfill WHERE name=?', (_RUN,)).fetchone()
        if not state or not state[0] or state[1] or db.execute("SELECT 1 FROM steam_avatar_backfill_jobs WHERE run=? AND status='pending' LIMIT 1", (_RUN,)).fetchone():
            return False
        counts = dict(db.execute('SELECT status,COUNT(*) FROM steam_avatar_backfill_jobs WHERE run=? GROUP BY status', (_RUN,)))
        db.execute('UPDATE steam_avatar_backfill SET completed=1,unavailable=?,removed=? WHERE name=?',
                   (counts.get('unavailable', 0), counts.get('removed', 0), _RUN))
        db.execute('DELETE FROM steam_avatar_backfill_events WHERE run=?', (_RUN,))
        db.execute('DELETE FROM steam_avatar_backfill_jobs WHERE run=?', (_RUN,))
        return True


class Backfill:
    def __init__(self):
        self.active = None

    def step(self, now=None):
        now = time.time() if now is None else now
        with closing(sqlite3.connect(_database(), timeout=10)) as db:
            state = db.execute('SELECT scanned,completed FROM steam_avatar_backfill WHERE name=?', (_RUN,)).fetchone()
        if not state or state[1]:
            return 'complete'
        if not state[0]:
            _scan_batch()
            return 'scanning'
        if self.active:
            key, sid = self.active
            if steam_avatar_store.avatar(sid) is not None:
                _mark(key, 'done')
                self.active = None
                return 'processed'
            if not _resolve(key)[1]:
                _mark(key, 'removed')
                self.active = None
                return 'processed'
            outcome = peer_tracking.historical_avatar_result(sid)
            if outcome == 'unavailable':
                _mark(key, 'unavailable' if peer_tracking.historical_avatar_transport_available() else 'rate_limited', now=now)
                self.active = None
                return 'processed'
            if outcome in ('interrupted', 'saved', None):
                # A broken connection or failed save is not a Steam refusal.
                _mark(key, 'rate_limited', now=now)
                self.active = None
            return 'waiting'
        if _finish_if_done():
            return 'complete'
        with closing(sqlite3.connect(_database(), timeout=10)) as db:
            row = db.execute("SELECT steam_key FROM steam_avatar_backfill_jobs WHERE run=? AND status='pending' AND next_attempt<=? ORDER BY rowid LIMIT 1", (_RUN, now)).fetchone()
        if not row:
            return 'waiting'
        key = row[0]
        sid, event_ids = _resolve(key)
        if not sid:
            _mark(key, 'removed')
            return 'processed'
        if steam_avatar_store.avatar(sid) is not None:
            _mark(key, 'done')
            return 'processed'
        if not peer_tracking.enabled():
            return 'waiting'
        peer_tracking.snapshot()  # Reuse the normal supervisor; it never starts the game or Steam.
        result = peer_tracking.request_historical_avatar(sid, event_ids)
        if result == 'queued':
            self.active = (key, sid)
            return 'queued'
        if result == 'rate_limited':
            _mark(key, 'rate_limited', now=now)
        return 'waiting'


def _worker(initialized=True):
    worker = Backfill()
    last_error_log = 0
    while True:
        try:
            if not initialized:
                if not initialize():
                    return
                initialized = True
            result = worker.step()
            if result == 'complete':
                return
        except Exception:
            now = time.monotonic()
            if not last_error_log or now - last_error_log >= 300:
                _LOG.exception('Unable to recover historical Steam avatars; retrying later')
                last_error_log = now
            result = 'waiting'
        time.sleep(.05 if result == 'scanning' else 1 if result in ('processed', 'queued') else _WAIT_SECONDS)


def start():
    global _started
    with _start_lock:
        if _started:
            return False
        initialized = False
        try:
            if not initialize():
                _started = True
                return False
            initialized = True
        except (sqlite3.Error, OSError):
            _LOG.warning('Historical Steam avatar recovery will retry initialization')
        _started = True
        try:
            threading.Thread(target=_worker, args=(initialized,), name='steam-avatar-backfill', daemon=True).start()
        except RuntimeError:
            _started = False
            raise
        return True
