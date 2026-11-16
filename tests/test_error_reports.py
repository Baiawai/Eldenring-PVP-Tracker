import json
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
from urllib.error import URLError
from application import error_reports


class ErrorReportsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'reports.db'
        self.patch = patch.object(error_reports, 'database_path', return_value=self.path)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_payload_excludes_sensitive_error_messages_and_paths(self):
        try:
            raise FileNotFoundError('C:/Users/secret/token=private player=SteamPlayer')
        except FileNotFoundError as error:
            payload = error_reports._payload('capture', 'storage', error)
        raw = json.dumps(payload)
        self.assertEqual(payload['exception'], 'FileNotFoundError')
        self.assertNotIn('secret', raw)
        self.assertNotIn('private', raw)
        self.assertNotIn('SteamPlayer', raw)
        self.assertNotIn('line', payload)  # Test paths are outside the approved application files.

    def test_detail_contains_a_redacted_trace_and_exception_chain(self):
        try:
            try:
                raise ValueError('token=secret HTTP request failed 2001:db8::1')
            except ValueError as cause:
                raise RuntimeError('Cannot open C:/Users/Alice/private.db email=test@example.com') from cause
        except RuntimeError as error:
            details = error_reports._payload('capture', 'other', error)['details']
        self.assertIn('ValueError', details)
        self.assertIn('RuntimeError', details)
        self.assertIn('Traceback', details)
        self.assertIn('HTTP request failed', details)
        self.assertNotIn('secret', details)
        self.assertNotIn('2001:db8::1', details)
        self.assertNotIn('Alice', details)
        self.assertNotIn('test@example.com', details)

    def test_deduplicates_bounds_and_deleting_pending_on_opt_out(self):
        payload = error_reports._payload('capture', 'other', ValueError('secret'))
        error_reports._enqueue(payload)
        error_reports._enqueue(error_reports._payload('capture', 'other', ValueError('another secret')))
        with closing(sqlite3.connect(self.path)) as db, db:
            self.assertEqual(db.execute('SELECT count(*) FROM pending').fetchone()[0], 1)
        error_reports.set_enabled(False)
        error_reports._enqueue(error_reports._payload('capture', 'other'))
        with closing(sqlite3.connect(self.path)) as db, db:
            self.assertEqual(db.execute('SELECT count(*) FROM pending').fetchone()[0], 0)
        self.assertFalse(error_reports.enabled())

    def test_queue_is_bounded(self):
        for status in range(100, 100 + error_reports.MAX_PENDING + 5):
            error_reports._enqueue(error_reports._payload('steam_login', 'http', status=status))
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM pending').fetchone()[0], error_reports.MAX_PENDING)

    def test_failure_keeps_pending_and_expired_reports_are_deleted(self):
        error_reports._enqueue(error_reports._payload('steam_login', 'network'))
        with patch.object(error_reports, 'build_opener') as opener:
            opener.return_value.open.side_effect = URLError('unavailable')
            error_reports._send_pending()
        with closing(sqlite3.connect(self.path)) as db, db:
            self.assertEqual(db.execute('SELECT count(*) FROM pending').fetchone()[0], 1)
            db.execute('UPDATE pending SET created = ?', (int(time.time()) - error_reports.MAX_AGE - 1,))
        error_reports._send_pending()
        with closing(sqlite3.connect(self.path)) as db, db:
            self.assertEqual(db.execute('SELECT count(*) FROM pending').fetchone()[0], 0)
