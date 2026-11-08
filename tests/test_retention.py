"""Retention is opt-in, and protects unrelated history."""
from contextlib import closing
from datetime import datetime
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from application import retention


class RetentionTests(unittest.TestCase):
    def test_settings_default_to_keep_and_validate(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(retention, '_settings_database', return_value=str(Path(tmp) / 'settings.db')):
            self.assertEqual(retention.load(), {'captures':0, 'steam':0})
            retention.save('captures', 30)
            self.assertEqual(retention.load(), {'captures':30, 'steam':0})
            with self.assertRaises(ValueError):
                retention.save('captures', 1)

    def test_only_old_selected_entries_are_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'capture.db'
            with closing(sqlite3.connect(path)) as db, db:
                db.execute('CREATE TABLE tabel_captures(id INTEGER PRIMARY KEY, date TEXT)')
                db.executemany('INSERT INTO tabel_captures(id,date) VALUES(?,?)', [(1,'2025-01-01'), (2,'2026-11-01'), (3,'unknown')])
                db.execute('CREATE TABLE detection_history(id INTEGER PRIMARY KEY, recorded_at TEXT, kind TEXT)')
                db.executemany('INSERT INTO detection_history VALUES(?,?,?)', [
                    (1,'2025-01-01 12:00:00','steam_encounter'), (2,'2025-01-01 12:00:00','monitor_stop'),
                    (3,'2026-11-01 12:00:00','steam_encounter'), (4,'invalid','steam_encounter')])
            now = datetime(2026, 11, 6, 12)
            keep = retention.cleanup(path, {'captures':0, 'steam':0}, lambda x:x, now=now)
            self.assertEqual(keep, {'captures':0, 'steam':0})
            deleted = retention.cleanup(path, {'captures':30, 'steam':30}, lambda x:x, now=now)
            self.assertEqual(deleted, {'captures':1, 'steam':1})
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(db.execute('SELECT id FROM tabel_captures ORDER BY id').fetchall(), [(2,), (3,)])
                self.assertEqual(db.execute('SELECT id FROM detection_history ORDER BY id').fetchall(), [(2,), (3,), (4,)])

    def test_failure_rolls_back_all_deletions(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'capture.db'
            with closing(sqlite3.connect(path)) as db, db:
                db.execute('CREATE TABLE tabel_captures(id INTEGER PRIMARY KEY, date TEXT)')
                db.execute("INSERT INTO tabel_captures VALUES(1,'2025-01-01')")
                db.execute('CREATE TABLE detection_history(id INTEGER PRIMARY KEY, recorded_at TEXT, kind TEXT)')
                db.execute("INSERT INTO detection_history VALUES(1,'2025-01-01','steam_encounter')")
                db.execute("CREATE TRIGGER prevent_delete BEFORE DELETE ON detection_history BEGIN SELECT RAISE(ABORT, 'test'); END")
            with self.assertRaises(sqlite3.IntegrityError):
                retention.cleanup(path, {'captures':30, 'steam':30}, lambda x:x, now=datetime(2026, 11, 6))
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM tabel_captures').fetchone()[0], 1)
