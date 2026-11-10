import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from application.leaderboard_migration import MigrationError, migrate


class LeaderboardMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='tracker-server-migration-')
        self.addCleanup(self.temp.cleanup)
        self.settings = Path(self.temp.name) / 'settings.db'
        self.user = Path(self.temp.name) / 'user.db'
        with closing(sqlite3.connect(self.settings)) as db, db:
            db.execute('''CREATE TABLE online_leaderboard (
                id INTEGER PRIMARY KEY, enabled INTEGER, uuid TEXT, token BLOB, server_url TEXT,
                language_permission INTEGER, steam_permission INTEGER, event_permission INTEGER,
                delete_pending INTEGER, steam_remove_pending INTEGER, language_remove_pending INTEGER,
                steam_login_cancel_pending INTEGER, rotation_token BLOB, recovery_payload BLOB,
                previous_token BLOB, server_transition_nonce TEXT, server_consent_url TEXT)''')
            db.execute('INSERT INTO online_leaderboard VALUES (1,1,?,?,?,1,1,1,0,0,0,0,NULL,NULL,NULL,NULL,NULL)',
                       ('old-uuid', b'encrypted-token', 'http://127.0.0.1:8000'))
        with closing(sqlite3.connect(self.user)) as db, db:
            db.execute('CREATE TABLE leaderboard_event_outbox (event_id TEXT)')
            db.execute('CREATE TABLE leaderboard_event_state (mode TEXT, active_match TEXT, last_no_result TEXT)')
            db.execute('INSERT INTO leaderboard_event_state VALUES (?,NULL,NULL)', ('Arena',))

    def test_archives_identity_and_requires_new_consent_without_touching_events(self):
        migrate(self.settings, self.user, 'https://eldenringpvp.com')
        with closing(sqlite3.connect(self.settings)) as db, db:
            archived = db.execute('SELECT server_url,uuid,token,enabled,language_permission,steam_permission,event_permission FROM online_leaderboard_archived_identities').fetchone()
            current = db.execute('SELECT enabled,uuid,token,server_url,language_permission,steam_permission,event_permission,server_transition_nonce FROM online_leaderboard').fetchone()
        self.assertEqual(archived, ('http://127.0.0.1:8000', 'old-uuid', b'encrypted-token', 1, 1, 1, 1))
        self.assertEqual(current[:7], (0, None, None, None, 0, 0, 0))
        self.assertTrue(current[7])
        with closing(sqlite3.connect(self.user)) as db, db:
            self.assertEqual(db.execute('SELECT * FROM leaderboard_event_state').fetchall(), [('Arena', None, None)])
            self.assertEqual(db.execute('SELECT COUNT(*) FROM leaderboard_event_outbox').fetchone()[0], 0)
        with self.assertRaisesRegex(MigrationError, 'no_identity'):
            migrate(self.settings, self.user, 'https://eldenringpvp.com')

    def test_refuses_pending_operations_without_changing_the_identity(self):
        for column in ('delete_pending', 'steam_remove_pending', 'language_remove_pending',
                       'steam_login_cancel_pending', 'rotation_token', 'recovery_payload',
                       'previous_token', 'server_transition_nonce'):
            with self.subTest(column=column):
                with closing(sqlite3.connect(self.settings)) as db, db:
                    db.execute(f'UPDATE online_leaderboard SET {column}=?', ('pending',))
                with self.assertRaisesRegex(MigrationError, 'pending_operations'):
                    migrate(self.settings, self.user, 'https://eldenringpvp.com')
                with closing(sqlite3.connect(self.settings)) as db, db:
                    self.assertEqual(db.execute('SELECT uuid,token,server_url FROM online_leaderboard').fetchone(),
                                     ('old-uuid', b'encrypted-token', 'http://127.0.0.1:8000'))
                    db.execute(f'UPDATE online_leaderboard SET {column}=?', (0 if column.endswith('_pending') else None,))

    def test_refuses_pending_event_or_unresolved_match(self):
        with closing(sqlite3.connect(self.user)) as db, db:
            db.execute('INSERT INTO leaderboard_event_outbox VALUES (?)', ('event',))
        with self.assertRaisesRegex(MigrationError, 'pending_events'):
            migrate(self.settings, self.user, 'https://eldenringpvp.com')
        with closing(sqlite3.connect(self.user)) as db, db:
            db.execute('DELETE FROM leaderboard_event_outbox')
            db.execute("UPDATE leaderboard_event_state SET active_match='match'")
        with self.assertRaisesRegex(MigrationError, 'active_match'):
            migrate(self.settings, self.user, 'https://eldenringpvp.com')
        with closing(sqlite3.connect(self.user)) as db, db:
            db.execute("UPDATE leaderboard_event_state SET active_match=NULL,last_no_result='match'")
        with self.assertRaisesRegex(MigrationError, 'active_match'):
            migrate(self.settings, self.user, 'https://eldenringpvp.com')
        with closing(sqlite3.connect(self.settings)) as db, db:
            self.assertEqual(db.execute('SELECT enabled,uuid FROM online_leaderboard').fetchone(), (1, 'old-uuid'))

    def test_refuses_current_or_missing_destination_data(self):
        with self.assertRaisesRegex(MigrationError, 'already_current'):
            migrate(self.settings, self.user, 'http://127.0.0.1:8000')
        with self.assertRaisesRegex(MigrationError, 'invalid_data'):
            migrate(self.settings, self.user.with_name('missing.db'), 'https://eldenringpvp.com')
        self.assertFalse(self.user.with_name('missing.db').exists())

    def test_failed_identity_update_rolls_back_archive(self):
        with closing(sqlite3.connect(self.settings)) as db, db:
            db.execute("CREATE TRIGGER reject_transition BEFORE UPDATE ON online_leaderboard BEGIN SELECT RAISE(ABORT, 'injected failure'); END")
        with self.assertRaisesRegex(MigrationError, 'invalid_data'):
            migrate(self.settings, self.user, 'https://eldenringpvp.com')
        with closing(sqlite3.connect(self.settings)) as db:
            self.assertEqual(db.execute('SELECT enabled,uuid,token FROM online_leaderboard').fetchone(), (1, 'old-uuid', b'encrypted-token'))
            self.assertIsNone(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='online_leaderboard_archived_identities'").fetchone())
