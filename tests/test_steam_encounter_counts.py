import json
import sqlite3
import tempfile
import threading
import unittest
from contextlib import closing, contextmanager
from pathlib import Path
from unittest.mock import patch

from application import steam_encounter_counts as counts


ALICE = '76561198000000001'
BOB = '76561198000000002'


def metadata(ident):
    return json.dumps({'id': ident}).encode('utf-8')


@contextmanager
def connection(path):
    with closing(sqlite3.connect(path)) as db:
        with db:
            yield db


class HistoryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'history.db'
        with connection(self.path) as db:
            db.executescript('''
                CREATE TABLE detection_history (id INTEGER PRIMARY KEY, kind TEXT, metadata BLOB);
                CREATE TABLE history_archive_events (archive_id INTEGER, original_id INTEGER,
                    kind TEXT, metadata BLOB, PRIMARY KEY (archive_id, original_id));
            ''')
        self.decrypt_calls = []
        self.reader = counts._VersionedReader(decrypt=self.decrypt)

    def tearDown(self):
        self.reader.close()
        self.temp.cleanup()

    def decrypt(self, value):
        self.decrypt_calls.append(value)
        return value

    def update(self, sql, params=()):
        with connection(self.path) as db:
            db.execute(sql, params)

    def test_archive_restore_purge_and_duplicate_archives(self):
        self.update("INSERT INTO detection_history VALUES (1, 'steam_encounter', ?)", (metadata(ALICE),))
        self.update("INSERT INTO detection_history VALUES (2, 'steam_encounter', ?)", (metadata(BOB),))
        self.assertEqual(self.reader(self.path), {ALICE: 1, BOB: 1})
        self.assertEqual(len(self.decrypt_calls), 2)
        self.assertEqual(self.reader(self.path), {ALICE: 1, BOB: 1})
        self.assertEqual(len(self.decrypt_calls), 2, 'unchanged database must not be decrypted again')
        with connection(self.path) as db:
            db.execute('INSERT INTO history_archive_events SELECT 1, id, kind, metadata FROM detection_history')
            db.execute('DELETE FROM detection_history')
        self.assertEqual(self.reader(self.path), {ALICE: 1, BOB: 1})
        with connection(self.path) as db:
            db.execute('INSERT INTO detection_history SELECT original_id, kind, metadata FROM history_archive_events')
            db.execute('INSERT INTO history_archive_events SELECT 2, id, kind, metadata FROM detection_history')
        self.assertEqual(self.reader(self.path), {ALICE: 1, BOB: 1})
        self.update('DELETE FROM detection_history')
        self.assertEqual(self.reader(self.path), {ALICE: 1, BOB: 1})
        self.update('DELETE FROM history_archive_events WHERE original_id=1')
        self.assertEqual(self.reader(self.path), {BOB: 1})

    def test_read_errors_and_missing_tables_are_not_false_counts(self):
        self.update("INSERT INTO detection_history VALUES (1, 'steam_encounter', ?)", (b'bad json',))
        with self.assertRaises(ValueError):
            self.reader(self.path)
        self.update('DELETE FROM detection_history')
        self.assertEqual(self.reader(self.path), {})
        self.update('DROP TABLE history_archive_events')
        self.assertEqual(self.reader(self.path), {})
        self.update('DROP TABLE detection_history')
        with self.assertRaises(ValueError):
            self.reader(self.path)
        with self.assertRaises(OSError):
            self.reader(self.path.parent / 'missing.db')

    def test_invalid_metadata_fails_closed(self):
        with connection(self.path) as db:
            db.executemany("INSERT INTO detection_history VALUES (?, 'steam_encounter', ?)",
                           [(1, metadata(ALICE)), (2, metadata(BOB))])
        self.update('UPDATE detection_history SET metadata=? WHERE id=2', (metadata('invalid'),))
        with self.assertRaises(ValueError):
            self.reader(self.path)

    def test_real_legacy_and_v2_encrypted_records(self):
        from application import secur
        from cryptography.fernet import Fernet
        key = Fernet.generate_key()
        with patch.object(secur, 'active_data_key', return_value=None):
            legacy = secur.encrypt_value(json.dumps({'id': ALICE}))
        with patch.object(secur, 'active_data_key', return_value=key):
            v2 = secur.encrypt_value(json.dumps({'id': BOB}))
            with connection(self.path) as db:
                db.executemany("INSERT INTO detection_history VALUES (?, 'steam_encounter', ?)",
                               [(1, legacy), (2, v2)])
            actual = counts._VersionedReader()
            try:
                self.assertEqual(actual(self.path), {ALICE: 1, BOB: 1})
            finally:
                actual.close()

    def test_wal_commits_are_seen_without_pinning_a_transaction(self):
        with connection(self.path) as db:
            db.execute('PRAGMA journal_mode=WAL')
        self.assertEqual(self.reader(self.path), {})
        self.update("INSERT INTO detection_history VALUES (1, 'steam_encounter', ?)", (metadata(ALICE),))
        self.assertEqual(self.reader(self.path), {ALICE: 1})
        with connection(self.path) as db:
            self.assertEqual(db.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()[0], 0)


class DeferredThreads:
    def __init__(self):
        self.tasks = []

    def __call__(self, target, args, **kwargs):
        queue = self.tasks
        class Thread:
            def start(self):
                queue.append((target, args))
        return Thread()

    def run(self):
        target, args = self.tasks.pop(0)
        target(*args)


class CacheTest(unittest.TestCase):
    def test_loading_cache_expiry_invalidation_errors_and_disabled_profile(self):
        threads = DeferredThreads()
        now = [0]
        results = [{ALICE: 2}, {ALICE: 3}, {ALICE: 4}, RuntimeError('unavailable'), {}]
        def read(path):
            result = results.pop(0)
            if isinstance(result, Exception):
                raise result
            return result
        cache = counts.EncounterCounts(database=lambda: None, reader=read,
                                       clock=lambda: now[0], thread_factory=threads)
        self.assertEqual(cache.snapshot([ALICE], enabled=False), {})
        self.assertEqual(threads.tasks, [])
        self.assertEqual(cache.snapshot([ALICE, BOB]), {ALICE: None, BOB: None})
        self.assertEqual(cache.snapshot([ALICE]), {ALICE: None})
        self.assertEqual(len(threads.tasks), 1)
        threads.run()
        self.assertEqual(cache.snapshot([ALICE, BOB]), {ALICE: 2, BOB: 0})
        now[0] = 5
        self.assertEqual(cache.snapshot([ALICE]), {ALICE: 2})
        cache.invalidate()
        threads.run()  # A stale result must never be published.
        self.assertEqual(cache.snapshot([ALICE]), {ALICE: None})
        threads.run()
        self.assertEqual(cache.snapshot([ALICE]), {ALICE: 4})
        now[0] = 10
        cache.snapshot([ALICE])
        threads.run()
        self.assertEqual(cache.snapshot([ALICE]), {ALICE: None})
        self.assertEqual(len(threads.tasks), 0)
        now[0] = 15
        self.assertEqual(cache.snapshot([ALICE]), {ALICE: None})
        threads.run()
        self.assertEqual(cache.snapshot([ALICE]), {ALICE: 0})

    def test_slow_database_read_is_background(self):
        started = threading.Event()
        release = threading.Event()
        finished = threading.Event()
        def read(path):
            started.set()
            release.wait(2)
            finished.set()
            return {ALICE: 1}
        cache = counts.EncounterCounts(database=lambda: None, reader=read)
        try:
            self.assertEqual(cache.snapshot([ALICE]), {ALICE: None})
            self.assertTrue(started.wait(1))
            self.assertEqual(cache.snapshot([ALICE]), {ALICE: None})
        finally:
            release.set()
            self.assertTrue(finished.wait(2))


if __name__ == '__main__':
    unittest.main()
