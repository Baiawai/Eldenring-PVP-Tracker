import sqlite3
import os
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from application import leaderboard_events
from application.secur import decrypt_value


class LeaderboardEventsTests(unittest.TestCase):
    def test_consent_start_finish_and_correction_use_a_durable_match_id(self):
        with tempfile.TemporaryDirectory(prefix='leaderboard-events-') as temporary:
            root = Path(temporary)
            settings = root / 'settings.db'
            with closing(sqlite3.connect(settings)) as db, db:
                db.execute('CREATE TABLE online_leaderboard (id INTEGER PRIMARY KEY, enabled INTEGER, delete_pending INTEGER, event_permission INTEGER)')
                db.execute('INSERT INTO online_leaderboard VALUES(1,1,0,0)')
            with patch.dict(os.environ, {'APPDATA':temporary}), closing(sqlite3.connect(root / 'user.db')) as db, db:
                leaderboard_events.record_delta(db, 'Invasion', (0,0,0,1,0,0,1,0,0), settings)
                leaderboard_events.record_delta(db, 'Invasion', (1,0,0,0,0,0,0,0,0), settings)
                self.assertEqual(db.execute('SELECT COUNT(*) FROM leaderboard_event_outbox').fetchone()[0], 0)
                with closing(sqlite3.connect(settings)) as config, config:
                    config.execute('UPDATE online_leaderboard SET event_permission=1')
                leaderboard_events.record_delta(db, 'Invasion', (0,0,0,1,0,0,1,0,0), settings)
                leaderboard_events.record_delta(db, 'Invasion', (0,0,0,0,1,0,0,0,0), settings)
                leaderboard_events.record_correction(db, 'Invasion', settings)
                leaderboard_events.record_correction(db, 'Invasion', settings)
                rows = db.execute('SELECT event_id,match_id,mode,kind FROM leaderboard_event_outbox ORDER BY rowid').fetchall()
                self.assertEqual([decrypt_value(row[3]).decode() for row in rows], ['start', 'no_result', 'correct_connection_error'])
                self.assertEqual(len({row[1] for row in rows}), 1)
                self.assertEqual(len({row[0] for row in rows}), 3)

    def test_end_without_consented_start_is_not_sent(self):
        with tempfile.TemporaryDirectory(prefix='leaderboard-events-') as temporary:
            root = Path(temporary)
            settings = root / 'settings.db'
            with closing(sqlite3.connect(settings)) as db, db:
                db.execute('CREATE TABLE online_leaderboard (id INTEGER PRIMARY KEY, enabled INTEGER, delete_pending INTEGER, event_permission INTEGER)')
                db.execute('INSERT INTO online_leaderboard VALUES(1,1,0,0)')
            with patch.dict(os.environ, {'APPDATA':temporary}), closing(sqlite3.connect(root / 'user.db')) as db, db:
                leaderboard_events.record_delta(db, 'Arena', (0,0,0,1,0,0,1,0,0), settings)
                with closing(sqlite3.connect(settings)) as config, config:
                    config.execute('UPDATE online_leaderboard SET event_permission=1')
                leaderboard_events.record_delta(db, 'Arena', (1,0,0,0,0,0,0,0,0), settings)
                self.assertEqual(db.execute('SELECT COUNT(*) FROM leaderboard_event_outbox').fetchone()[0], 0)

    def test_failed_queue_write_rolls_back_its_partial_state(self):
        with tempfile.TemporaryDirectory(prefix='leaderboard-events-') as temporary:
            root = Path(temporary)
            settings = root / 'settings.db'
            with closing(sqlite3.connect(settings)) as db, db:
                db.execute('CREATE TABLE online_leaderboard (id INTEGER PRIMARY KEY, enabled INTEGER, delete_pending INTEGER, event_permission INTEGER)')
                db.execute('INSERT INTO online_leaderboard VALUES(1,1,0,1)')
            with patch.dict(os.environ, {'APPDATA':temporary}), closing(sqlite3.connect(root / 'user.db')) as db, db:
                with patch.object(leaderboard_events, '_append', side_effect=sqlite3.OperationalError('disk error')):
                    with self.assertRaises(sqlite3.OperationalError):
                        leaderboard_events.record_delta(db, 'Arena', (0,0,0,1,0,0,1,0,0), settings)
                self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='leaderboard_event_state'").fetchone())
