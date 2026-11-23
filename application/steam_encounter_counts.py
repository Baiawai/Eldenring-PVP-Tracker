"""Read a cached count of local Steam encounter observations.

An observation is a Steam connection logged by the tracker, not a proven
combat or a link between a Steam account and an OCR character. Reads include
archives and never modify history or contact a remote service.
"""
from collections import Counter
from contextlib import closing
import atexit
import json
from pathlib import Path
import sqlite3
import threading
import time

from application.runtime_paths import database_path

_REFRESH_SECONDS = 5.0


def _valid_id(value):
    return isinstance(value, str) and len(value) == 17 and value.isascii() and value.isdigit()


def _database():
    # Match the currently selected installed/Store data profile, including
    # Windows' private package path resolution.
    return database_path('database_capture.db')


def _decrypt(value):
    from application.secur import decrypt_value
    return decrypt_value(value)


def _count_connection(db, decrypt):
    """Count unique event IDs in one transactionally stable view.

    Restoration keeps both an archived copy and an active row; subsequent
    archives may contain the same original ID again. Active records take
    priority, and every original event ID is counted at most once.
    """
    db.execute('BEGIN')
    try:
        tables = {row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('detection_history','history_archive_events')")}
        if 'detection_history' not in tables:
            raise ValueError('Steam encounter history is unavailable')
        queries = []
        if 'detection_history' in tables:
            queries.append("SELECT id, metadata FROM detection_history WHERE kind='steam_encounter' ORDER BY id")
        if 'history_archive_events' in tables:
            queries.append("SELECT original_id, metadata FROM history_archive_events WHERE kind='steam_encounter' ORDER BY archive_id DESC, original_id")
        counts, seen = Counter(), set()
        for query in queries:
            for event_id, encrypted in db.execute(query):
                if event_id in seen:
                    continue
                if type(event_id) is not int or event_id < 1 or not encrypted:
                    raise ValueError('Invalid Steam encounter record')
                decoded = decrypt(encrypted)
                data = json.loads(decoded.decode('utf-8') if isinstance(decoded, bytes) else decoded)
                ident = data.get('id') if isinstance(data, dict) else None
                if not _valid_id(ident):
                    raise ValueError('Invalid Steam encounter identity')
                seen.add(event_id)
                counts[ident] += 1
        return dict(counts)
    finally:
        # Never retain a transaction between polls: it would pin a WAL snapshot
        # and prevent data_version from reporting subsequent changes.
        db.rollback()


def _read_counts(path, decrypt=_decrypt):
    """Read all counts from a fresh read-only connection (also useful in tests)."""
    uri = Path(path).resolve().as_uri() + '?mode=ro'
    with closing(sqlite3.connect(uri, uri=True, timeout=2)) as db:
        return _count_connection(db, decrypt)


class _VersionedReader:
    """Keep a read-only observer so SQLite data_version can detect commits."""

    def __init__(self, decrypt=_decrypt):
        self._decrypt = decrypt
        self._lock = threading.Lock()
        self._db = None
        self._identity = None
        self._version = None
        self._values = None

    def _close(self):
        if self._db is not None:
            self._db.close()
        self._db = self._identity = self._version = self._values = None

    def close(self):
        with self._lock:
            self._close()

    def __call__(self, path):
        path = Path(path).resolve()
        with self._lock:
            try:
                info = path.stat()
                identity = (str(path), info.st_dev, info.st_ino)
                if self._db is None or identity != self._identity:
                    self._close()
                    self._db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True,
                                               timeout=2, check_same_thread=False)
                    self._identity = identity
                version = self._db.execute('PRAGMA data_version').fetchone()[0]
                if self._values is None or self._version != version:
                    values = _count_connection(self._db, self._decrypt)
                    # A commit between the version read and the transaction is
                    # harmless: the next poll will detect it and read again.
                    self._values, self._version = values, version
                return self._values
            except Exception:
                self._close()
                raise


class EncounterCounts:
    """Refresh the shared history count asynchronously, without blocking UI."""

    def __init__(self, database=_database, reader=_read_counts, clock=time.monotonic,
                 interval=_REFRESH_SECONDS, thread_factory=threading.Thread):
        self._database, self._reader, self._clock = database, reader, clock
        self._interval, self._thread_factory = interval, thread_factory
        self._lock = threading.Lock()
        self._values = None
        self._next_refresh = 0.0
        self._running = False
        self._generation = 0

    def invalidate(self):
        """Forget previous results and prevent an older read being published."""
        with self._lock:
            self._generation += 1
            self._values = None
            self._next_refresh = 0.0

    def snapshot(self, ids, enabled=True):
        """Return known counts immediately; None means loading or unavailable."""
        if not enabled or not isinstance(ids, (list, tuple, set)):
            return {}
        requested = list(dict.fromkeys(ident for ident in ids if _valid_id(ident)))
        if not requested:
            return {}
        with self._lock:
            if not self._running and self._clock() >= self._next_refresh:
                self._running = True
                generation = self._generation
                try:
                    self._thread_factory(target=self._refresh, args=(generation,),
                                         name='steam-encounter-counts', daemon=True).start()
                except Exception:
                    self._running = False
                    self._values = None
                    self._next_refresh = self._clock() + self._interval
            values = self._values
            return {ident: (values.get(ident, 0) if values is not None else None) for ident in requested}

    def _refresh(self, generation):
        try:
            values = self._reader(self._database())
            if not isinstance(values, dict):
                raise ValueError('Invalid Steam encounter counts')
        except Exception:
            values = None
        with self._lock:
            self._running = False
            if generation == self._generation:
                self._values = values
                self._next_refresh = self._clock() + self._interval


_reader = _VersionedReader()
atexit.register(_reader.close)
_cache = EncounterCounts(reader=_reader)


def snapshot(ids, enabled=True):
    return _cache.snapshot(ids, enabled=enabled)


def invalidate():
    _cache.invalidate()
