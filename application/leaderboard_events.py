"""Durable local outbox for consensual online combat events."""
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from application.secur import encrypt_value


def _enabled(settings_path):
    try:
        with closing(sqlite3.connect(settings_path, timeout=2)) as db:
            row = db.execute('SELECT enabled,delete_pending,event_permission FROM online_leaderboard WHERE id=1').fetchone()
        return bool(row and row[0] and not row[1] and row[2])
    except sqlite3.Error:
        return False


def _schema(db):
    db.execute('CREATE TABLE IF NOT EXISTS leaderboard_event_outbox (event_id TEXT PRIMARY KEY, match_id TEXT NOT NULL, mode TEXT NOT NULL, kind TEXT NOT NULL, occurred_at TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS leaderboard_event_state (mode TEXT PRIMARY KEY, active_match TEXT, last_no_result TEXT)')


def _append(db, match, mode, kind):
    event_id = str(uuid.uuid4())
    occurred_at = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    db.execute('INSERT INTO leaderboard_event_outbox(event_id,match_id,mode,kind,occurred_at) VALUES(?,?,?,?,?)', (event_id, match, encrypt_value(mode), encrypt_value(kind), encrypt_value(occurred_at)))


def _record_delta(db, mode, args, settings_path):
    if not any(args):
        return
    _schema(db)
    enabled = _enabled(settings_path)
    db.execute('INSERT OR IGNORE INTO leaderboard_event_state(mode) VALUES(?)', (mode,))
    active = db.execute('SELECT active_match FROM leaderboard_event_state WHERE mode=?', (mode,)).fetchone()[0]
    if args[3]:
        match = str(uuid.uuid4()) if enabled else None
        db.execute('UPDATE leaderboard_event_state SET active_match=?,last_no_result=NULL WHERE mode=?', (match, mode))
        if match:
            _append(db, match, mode, 'start')
        return
    kinds = ((0, 'victory'), (1, 'defeat'), (2, 'draw'), (4, 'no_result'), (5, 'opponent_left'), (7, 'connection_error'), (8, 'game_closed'))
    kind = next((name for index, name in kinds if args[index]), None)
    if kind:
        if enabled and active:
            _append(db, active, mode, kind)
        db.execute('UPDATE leaderboard_event_state SET active_match=NULL,last_no_result=? WHERE mode=?', (active if enabled and kind == 'no_result' else None, mode))


def _record_correction(db, mode, settings_path):
    _schema(db)
    row = db.execute('SELECT last_no_result FROM leaderboard_event_state WHERE mode=?', (mode,)).fetchone()
    if row and row[0] and _enabled(settings_path):
        _append(db, row[0], mode, 'correct_connection_error')
        db.execute('UPDATE leaderboard_event_state SET last_no_result=NULL WHERE mode=?', (mode,))


def _safely_record(db, action, *args):
    db.execute('SAVEPOINT leaderboard_outbox_write')
    try:
        action(db, *args)
        db.execute('RELEASE SAVEPOINT leaderboard_outbox_write')
    except Exception:
        db.execute('ROLLBACK TO SAVEPOINT leaderboard_outbox_write')
        db.execute('RELEASE SAVEPOINT leaderboard_outbox_write')
        raise


def record_delta(db, mode, args, settings_path):
    """Append atomically within the caller's statistics transaction."""
    _safely_record(db, _record_delta, mode, args, settings_path)


def record_correction(db, mode, settings_path):
    _safely_record(db, _record_correction, mode, settings_path)
