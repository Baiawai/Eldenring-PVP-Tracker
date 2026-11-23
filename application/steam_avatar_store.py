"""Bounded encrypted avatars tied to locally recorded Steam encounters."""
import base64
import hashlib
import json
import sqlite3
import time
from contextlib import closing

from cryptography.fernet import InvalidToken

from application.secur import decrypt_value, encrypt_value
from application.steam_peer_enrichment import _decode_avatar, _valid_id

MAX_ENTRIES = 2048
MAX_EVENT_IDS = 128


def _database():
    from application.init import database_capture
    return database_capture


def _key(steam_id):
    return hashlib.sha256(('steam-avatar:' + steam_id).encode('ascii')).hexdigest()


def _has_table(db, name):
    return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone())


def _schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS steam_avatars (
        steam_key TEXT PRIMARY KEY, avatar BLOB NOT NULL,
        digest TEXT NOT NULL, updated_at INTEGER NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS steam_avatar_links (
        event_id INTEGER PRIMARY KEY, steam_key TEXT NOT NULL)''')
    db.execute('CREATE INDEX IF NOT EXISTS steam_avatar_links_key ON steam_avatar_links(steam_key)')


def _matches(encrypted, steam_id):
    if not encrypted:
        return False
    try:
        metadata = json.loads(decrypt_value(encrypted).decode('utf-8'))
        if not isinstance(metadata, dict):
            return False
        value = metadata.get('id')
        if isinstance(value, bool) or not isinstance(value, (str, int)):
            return False
        return str(value) == steam_id
    except (InvalidToken, RuntimeError, ValueError, TypeError, UnicodeDecodeError):
        return False


def _save_locked(db, steam_id, event_ids, encoded, digest):
    key = _key(steam_id)
    old = db.execute('SELECT digest,avatar FROM steam_avatars WHERE steam_key=?', (key,)).fetchone()
    valid_old = True
    if old:
        try:
            valid_old = _decode_avatar(decrypt_value(old[1]).decode('ascii')) is not None
        except (InvalidToken, ValueError, TypeError, UnicodeError):
            valid_old = False
    links = {row[0]: row[1] for row in db.execute('SELECT event_id,steam_key FROM steam_avatar_links WHERE steam_key=?', (key,))}
    missing = [event_id for event_id in event_ids if links.get(event_id) != key]
    changed = not old or old[0] != digest or not valid_old or bool(missing)
    if not old:
        # Least recently observed cached images may be evicted; the original
        # history and archives themselves are never altered.
        capacity = MAX_ENTRIES
        if _has_table(db, 'steam_avatar_cache_policy'):
            row = db.execute('SELECT capacity FROM steam_avatar_cache_policy WHERE id=1').fetchone()
            if row and type(row[0]) is int:
                capacity = max(capacity, row[0])
        count = db.execute('SELECT COUNT(*) FROM steam_avatars').fetchone()[0]
        # New live encounters can arrive while the one-time historical batch
        # is running. Grow only when needed so they cannot evict batch avatars.
        recovering = _has_table(db, 'steam_avatar_backfill') and db.execute(
            'SELECT 1 FROM steam_avatar_backfill WHERE completed=0 LIMIT 1').fetchone()
        if count >= capacity and recovering and _has_table(db, 'steam_avatar_cache_policy'):
            capacity = count + 1
            db.execute('''INSERT INTO steam_avatar_cache_policy(id,capacity) VALUES(1,?)
                ON CONFLICT(id) DO UPDATE SET capacity=MAX(capacity,excluded.capacity)''', (capacity,))
        while count >= capacity:
            oldest = db.execute('SELECT steam_key FROM steam_avatars ORDER BY updated_at, steam_key LIMIT 1').fetchone()[0]
            db.execute('DELETE FROM steam_avatar_links WHERE steam_key=?', (oldest,))
            db.execute('DELETE FROM steam_avatars WHERE steam_key=?', (oldest,))
            count -= 1
        db.execute('INSERT INTO steam_avatars VALUES(?,?,?,?)', (key, encrypt_value(encoded), digest, int(time.time())))
    elif old[0] != digest or not valid_old:
        db.execute('UPDATE steam_avatars SET avatar=?, digest=?, updated_at=? WHERE steam_key=?',
                   (encrypt_value(encoded), digest, int(time.time()), key))
    elif missing:
        db.execute('UPDATE steam_avatars SET updated_at=? WHERE steam_key=?', (int(time.time()), key))
    if missing:
        db.executemany('INSERT OR REPLACE INTO steam_avatar_links(event_id,steam_key) VALUES(?,?)',
                       [(event_id, key) for event_id in missing])
    return changed


def save(steam_id, event_id, data):
    """Save only a verified PNG for a still-present active Steam encounter.

    Returns whether an image or its active association changed. The original
    Steam ID and clear image are never stored in this cache.
    """
    if not _valid_id(steam_id) or not isinstance(event_id, int) or event_id <= 0 or not isinstance(data, bytes):
        return False
    encoded = base64.b64encode(data).decode('ascii')
    if _decode_avatar(encoded) != data:
        return False
    digest = hashlib.sha256(data).hexdigest()
    with closing(sqlite3.connect(_database(), timeout=10)) as db, db:
        _schema(db)
        db.execute('BEGIN IMMEDIATE')
        row = db.execute("SELECT metadata FROM detection_history WHERE id=? AND kind='steam_encounter'", (event_id,)).fetchone()
        if not row or not _matches(row[0], steam_id):
            return False
        return _save_locked(db, steam_id, [event_id], encoded, digest)


def active_event_matches(steam_id, event_ids):
    """Recheck an existing page's event IDs without scanning unrelated rows."""
    if not _valid_id(steam_id):
        return False
    ids = [value for value in event_ids if isinstance(value, int) and value > 0]
    if not ids:
        return False
    with closing(sqlite3.connect(_database(), timeout=10)) as db:
        for offset in range(0, len(ids), 400):
            chunk = ids[offset:offset + 400]
            placeholders = ','.join('?' for _ in chunk)
            rows = db.execute("SELECT metadata FROM detection_history WHERE kind='steam_encounter' AND id IN (" + placeholders + ')', chunk)
            if any(_matches(row[0], steam_id) for row in rows):
                return True
    return False


def save_historical(steam_id, data, event_ids):
    """Persist a retrieved image only while matching active history exists."""
    if not _valid_id(steam_id) or not isinstance(data, bytes):
        return False
    if not isinstance(event_ids, (list, tuple)):
        return False
    candidates = list(dict.fromkeys(value for value in event_ids[:MAX_EVENT_IDS]
                                    if isinstance(value, int) and not isinstance(value, bool) and value > 0))
    if not candidates:
        return False
    encoded = base64.b64encode(data).decode('ascii')
    if _decode_avatar(encoded) != data:
        return False
    with closing(sqlite3.connect(_database(), timeout=10)) as db, db:
        _schema(db)
        # Candidate event IDs came from the already loaded player history.
        # Verify them under the write lock: history may have been purged while
        # Steam was fetching the image, and never trust IDs without matching
        # the encrypted metadata to the requested Steam profile.
        db.execute('BEGIN IMMEDIATE')
        placeholders = ','.join('?' for _ in candidates)
        current = db.execute("SELECT id,metadata FROM detection_history WHERE kind='steam_encounter' AND id IN (" + placeholders + ')', candidates)
        ids = [row[0] for row in current if _matches(row[1], steam_id)]
        if not ids:
            return False
        return _save_locked(db, steam_id, ids, encoded, hashlib.sha256(data).hexdigest())


def available(steam_ids):
    """Return IDs with cached avatars associated with active Steam history."""
    ids = {value for value in steam_ids if _valid_id(value)}
    if not ids:
        return set()
    keys = {_key(value): value for value in ids}
    with closing(sqlite3.connect(_database(), timeout=10)) as db:
        if not _has_table(db, 'steam_avatars') or not _has_table(db, 'steam_avatar_links'):
            return set()
        found = set()
        values = list(keys)
        for offset in range(0, len(values), 400):
            chunk = values[offset:offset + 400]
            placeholders = ','.join('?' for _ in chunk)
            rows = db.execute('''SELECT DISTINCT a.steam_key FROM steam_avatars a
                JOIN steam_avatar_links l ON l.steam_key=a.steam_key
                JOIN detection_history h ON h.id=l.event_id AND h.kind='steam_encounter'
                WHERE a.steam_key IN (''' + placeholders + ')', chunk)
            found.update(keys[row[0]] for row in rows)
        return found


def avatar(steam_id):
    """Return a validated image only when linked to an active encounter."""
    if not _valid_id(steam_id):
        return None
    with closing(sqlite3.connect(_database(), timeout=10)) as db:
        if not _has_table(db, 'steam_avatars') or not _has_table(db, 'steam_avatar_links'):
            return None
        row = db.execute('''SELECT a.avatar FROM steam_avatars a
            JOIN steam_avatar_links l ON l.steam_key=a.steam_key
            JOIN detection_history h ON h.id=l.event_id AND h.kind='steam_encounter'
            WHERE a.steam_key=? LIMIT 1''', (_key(steam_id),)).fetchone()
    if not row:
        return None
    try:
        return _decode_avatar(decrypt_value(row[0]).decode('ascii'))
    except (ValueError, TypeError, UnicodeDecodeError, InvalidToken, RuntimeError):
        return None


def prune(db):
    """Remove cache entries no longer referenced by active or archived history."""
    if not _has_table(db, 'steam_avatars') or not _has_table(db, 'steam_avatar_links'):
        return
    archive = " AND NOT EXISTS (SELECT 1 FROM history_archive_events a WHERE a.original_id=l.event_id AND a.kind='steam_encounter')" if _has_table(db, 'history_archive_events') else ''
    db.execute("DELETE FROM steam_avatar_links AS l WHERE NOT EXISTS (SELECT 1 FROM detection_history h WHERE h.id=l.event_id AND h.kind='steam_encounter')" + archive)
    db.execute('DELETE FROM steam_avatars WHERE steam_key NOT IN (SELECT steam_key FROM steam_avatar_links)')
