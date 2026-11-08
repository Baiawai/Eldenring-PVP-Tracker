"""Opt-in retention applied only before monitoring starts."""
from contextlib import closing
from datetime import datetime, timedelta
import sqlite3
from cryptography.fernet import InvalidToken


DAYS = (0, 30, 90, 365)


def _settings_database():
    from application.init import database_setting
    return database_setting


def load():
    with closing(sqlite3.connect(_settings_database(), timeout=10)) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='retention_settings'").fetchone():
            return {'captures':0, 'steam':0}
        row = db.execute('SELECT capture_days,steam_days FROM retention_settings WHERE profile=?', ('default',)).fetchone()
        return {'captures':row[0], 'steam':row[1]} if row and all(value in DAYS for value in row) else {'captures':0, 'steam':0}


def save(kind, days):
    if kind not in ('captures', 'steam') or days not in DAYS:
        raise ValueError('Invalid retention setting')
    column = 'capture_days' if kind == 'captures' else 'steam_days'
    with closing(sqlite3.connect(_settings_database(), timeout=10)) as db, db:
        db.execute('CREATE TABLE IF NOT EXISTS retention_settings (profile TEXT PRIMARY KEY, capture_days INTEGER NOT NULL DEFAULT 0, steam_days INTEGER NOT NULL DEFAULT 0)')
        db.execute('INSERT OR IGNORE INTO retention_settings(profile) VALUES(?)', ('default',))
        db.execute('UPDATE retention_settings SET ' + column + '=? WHERE profile=?', (days, 'default'))


def cleanup(database, settings, decode, now=None):
    """Delete only known old entries; invalid dates remain untouched."""
    now = now or datetime.now()
    capture_days, steam_days = settings['captures'], settings['steam']
    if capture_days not in DAYS or steam_days not in DAYS:
        raise ValueError('Invalid retention setting')
    counts = {'captures':0, 'steam':0}
    if not capture_days and not steam_days:
        return counts
    with closing(sqlite3.connect(database, timeout=10)) as db:
        db.execute('BEGIN IMMEDIATE')
        if capture_days:
            cutoff = (now - timedelta(days=capture_days)).date()
            remove = []
            for ident, raw in db.execute('SELECT id,date FROM tabel_captures'):
                try:
                    value = decode(raw)
                    if isinstance(value, bytes):
                        value = value.decode('utf-8')
                    date = datetime.fromisoformat(str(value)).date()
                    if date < cutoff:
                        remove.append((ident,))
                except (TypeError, ValueError, UnicodeError, InvalidToken):
                    continue
            db.executemany('DELETE FROM tabel_captures WHERE id=?', remove)
            counts['captures'] = len(remove)
        if steam_days and db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='detection_history'").fetchone():
            columns = {row[1] for row in db.execute('PRAGMA table_info(detection_history)')}
            if {'kind', 'recorded_at'}.issubset(columns):
                cutoff = now - timedelta(days=steam_days)
                kinds = ('steam_encounter', 'steam_connected', 'steam_updated', 'steam_disconnected', 'steam_suppressed')
                placeholders = ','.join('?' for _ in kinds)
                remove = []
                for ident, value in db.execute('SELECT id,recorded_at FROM detection_history WHERE kind IN (' + placeholders + ')', kinds):
                    try:
                        recorded = datetime.fromisoformat(value)
                        if recorded.tzinfo is None and recorded < cutoff:
                            remove.append((ident,))
                    except (ValueError, TypeError):
                        continue
                db.executemany('DELETE FROM detection_history WHERE id=?', remove)
                counts['steam'] = len(remove)
        db.commit()
    return counts
