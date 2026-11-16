"""Take a durable one-time local snapshot before importing older scores."""
import json
import math
import sqlite3
import uuid
from contextlib import closing

from application import init, mode_stats
from application.secur import encrypt_value, decrypt_value

COUNTERS = ('victory', 'defeat', 'egality', 'combats', 'noResult', 'fight_exit',
            'abandon', 'maxVictory', 'maxDefeat', 'connexionError', 'gameExit')
MODES = ('Arena', 'Invasion', 'Defense')


def _schema(db):
    db.execute('CREATE TABLE IF NOT EXISTS leaderboard_baseline_state (id INTEGER PRIMARY KEY CHECK(id=1), server TEXT NOT NULL, installation TEXT NOT NULL, import_id TEXT NOT NULL, payload BLOB NOT NULL, complete INTEGER NOT NULL DEFAULT 0)')
    db.execute('CREATE TABLE IF NOT EXISTS leaderboard_baseline_events (event_id TEXT PRIMARY KEY)')
    db.execute('CREATE TABLE IF NOT EXISTS leaderboard_event_outbox (event_id TEXT PRIMARY KEY, match_id TEXT NOT NULL, mode TEXT NOT NULL, kind TEXT NOT NULL, occurred_at TEXT NOT NULL)')


def _values(values):
    result = {}
    for name in COUNTERS:
        value = float(values.get(name, 0))
        # Older Arena versions could persist a negative derived abandon value.
        # Keep that historical value rather than rejecting the whole import.
        minimum = -100000000 if name == 'abandon' else 0
        if not math.isfinite(value) or not value.is_integer() or not minimum <= value <= 100000000:
            raise ValueError('invalid_statistics')
        result[name] = int(value)
    duration = float(values.get('ratioTime', 0))
    if not math.isfinite(duration) or not 0 <= duration <= 100000000:
        raise ValueError('invalid_statistics')
    result['ratioTime'] = duration
    return result


def _snapshot(db):
    arena = {}
    row = db.execute('SELECT * FROM tabel_user WHERE id=1').fetchone()
    if row:
        decoded = init.decrypt_rows([row])[0]
        arena = dict(zip(mode_stats.FIELDS, (decoded[index] for index in mode_stats.INDEXES)))
    modes = {'Arena': _values(arena)}
    has_modes = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='mode_stats'").fetchone()
    for mode in ('Invasion', 'Defense'):
        row = db.execute('SELECT ' + ','.join(mode_stats.FIELDS) + ' FROM mode_stats WHERE mode=?', (mode,)).fetchone() if has_modes else None
        modes[mode] = _values(dict(zip(mode_stats.FIELDS, row)) if row else {})
    return modes


def capture(path, server, installation, fight_active=False):
    """Freeze totals and the exact queued event IDs in one SQLite transaction."""
    with closing(sqlite3.connect(path, timeout=10)) as db:
        db.execute('BEGIN IMMEDIATE')
        _schema(db)
        row = db.execute('SELECT server,installation,import_id,payload,complete FROM leaderboard_baseline_state WHERE id=1').fetchone()
        if row and (row[0], row[1]) == (server, installation):
            if row[4]:
                db.commit()
                return None
            payload = json.loads(decrypt_value(row[3]).decode('utf-8'))
            db.commit()
            return payload
        if row and not row[4]:
            raise ValueError('baseline_conflict')
        if fight_active:
            raise ValueError('baseline_wait')
        ident = str(uuid.uuid4())
        payload = {'import_id':ident, 'modes':_snapshot(db)}
        encrypted = encrypt_value(json.dumps(payload, separators=(',', ':'), ensure_ascii=False))
        db.execute('DELETE FROM leaderboard_baseline_events')
        db.execute('INSERT INTO leaderboard_baseline_events(event_id) SELECT event_id FROM leaderboard_event_outbox')
        db.execute('INSERT OR REPLACE INTO leaderboard_baseline_state(id,server,installation,import_id,payload,complete) VALUES(1,?,?,?,?,0)', (server, installation, ident, encrypted))
        db.commit()
        return payload


def complete(path, server, installation, import_id):
    with closing(sqlite3.connect(path, timeout=10)) as db, db:
        remaining = db.execute('SELECT 1 FROM leaderboard_baseline_events LIMIT 1').fetchone()
        if remaining:
            raise ValueError('baseline_conflict')
        changed = db.execute('UPDATE leaderboard_baseline_state SET complete=1 WHERE id=1 AND server=? AND installation=? AND import_id=?', (server, installation, import_id)).rowcount
        if changed != 1:
            raise ValueError('baseline_conflict')
