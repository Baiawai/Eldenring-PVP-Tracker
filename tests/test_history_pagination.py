"""History pages stay bounded, ordered and stable while events arrive."""
import importlib.util
import sqlite3
import sys
import tempfile
import types
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from flask import Flask


class HistoryPaginationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = str(Path(self.directory.name) / 'history.sqlite')
        app = Flask(__name__)
        fake_main = types.ModuleType('__main__')
        fake_main.app = app
        fake_init = types.ModuleType('application.init')
        fake_init.database_capture = self.path
        fake_secur = types.ModuleType('application.secur')
        fake_secur.encrypt_value = lambda value: str(value).encode()
        fake_secur.decrypt_value = lambda value: value if isinstance(value, bytes) else value.encode()
        fake_geo = types.ModuleType('application.geoip_country')
        fake_geo.country_code = lambda value: None
        with patch.dict(sys.modules, {'__main__': fake_main, 'application.init': fake_init,
                                      'application.secur': fake_secur, 'application.geoip_country': fake_geo}):
            spec = importlib.util.spec_from_file_location('_test_history_pagination', Path(__file__).resolve().parents[1] / 'application' / 'detection_history.py')
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        module._connect = lambda: sqlite3.connect(self.path)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('CREATE TABLE detection_history(id INTEGER PRIMARY KEY, recorded_at TEXT, mode TEXT, message BLOB, kind TEXT, metadata BLOB)')
            db.executemany('INSERT INTO detection_history VALUES (?, ?, ?, ?, ?, NULL)', [
                (i, '2026-01-01 12:00:00', 'Arena' if i % 2 else 'Defense', str(i).encode(),
                 'steam_suppressed' if i == 74 else 'detection') for i in range(1, 77)])
        self.client = app.test_client()

    def test_pages_do_not_duplicate_or_skip_when_new_event_arrives(self):
        first = self.client.get('/detection-history').get_json()
        self.assertEqual(len(first['events']), 30)
        self.assertTrue(first['has_more'])
        self.assertEqual(first['events'][0]['id'], 76)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("INSERT INTO detection_history VALUES(77, '2026-01-01 12:01:00', 'Arena', ?, 'detection', NULL)", (b'77',))
        second = self.client.get('/detection-history', query_string={'before': first['events'][-1]['id']}).get_json()
        third = self.client.get('/detection-history', query_string={'before': second['events'][-1]['id']}).get_json()
        self.assertEqual([len(second['events']), len(third['events'])], [30, 15])
        self.assertTrue(second['has_more'])
        self.assertFalse(third['has_more'])
        ids = [event['id'] for page in (first, second, third) for event in page['events']]
        self.assertEqual(ids, [i for i in range(76, 0, -1) if i != 74])

    def test_filters_and_invalid_cursors(self):
        first = self.client.get('/detection-history?mode=Defense').get_json()
        self.assertEqual(len(first['events']), 30)
        self.assertTrue(first['has_more'])
        self.assertTrue(all(event['mode'] == 'Defense' for event in first['events']))
        second = self.client.get('/detection-history', query_string={'mode': 'Defense', 'before': first['events'][-1]['id']}).get_json()
        self.assertEqual(len(second['events']), 7)
        self.assertFalse(second['has_more'])
        for query in ('before=-1', 'before=invalid', 'mode=invalid'):
            self.assertEqual(self.client.get('/detection-history?' + query).status_code, 400)


if __name__ == '__main__':
    unittest.main()
