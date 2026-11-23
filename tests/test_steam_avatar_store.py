import base64
import io
import importlib.util
import json
import sqlite3
import tempfile
import unittest
import sys
import threading
import types
from contextlib import closing
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image
from flask import Flask

from application import secur, steam_avatar_store as store


def png(color):
    output = io.BytesIO()
    Image.new('RGB', (8, 8), color).save(output, format='PNG')
    return output.getvalue()


class SteamAvatarStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = str(Path(self.temp.name) / 'capture.db')
        self.sid = '76561198000000001'
        self.second = '76561198000000002'
        self.image = png('red')
        self.database_patch = patch.object(store, '_database', return_value=self.database)
        self.database_patch.start()
        self.addCleanup(self.database_patch.stop)
        self.key_patch = patch.object(secur, 'active_data_key', return_value=None)
        self.key_patch.start()
        self.addCleanup(self.key_patch.stop)
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute('CREATE TABLE detection_history (id INTEGER PRIMARY KEY, kind TEXT NOT NULL, metadata BLOB)')
            db.execute("INSERT INTO detection_history VALUES(1,'steam_encounter',?)", (secur.encrypt_value(json.dumps({'id':self.sid})),))

    def test_persists_encrypted_avatar_only_for_recorded_active_encounter(self):
        self.assertTrue(store.save(self.sid, 1, self.image))
        self.assertFalse(store.save(self.sid, 1, self.image))
        self.assertEqual(store.avatar(self.sid), self.image)
        self.assertEqual(store.available([self.sid, self.second]), {self.sid})
        with closing(sqlite3.connect(self.database)) as db:
            key, encrypted = db.execute('SELECT steam_key,avatar FROM steam_avatars').fetchone()
            self.assertNotIn(self.sid, key)
            self.assertNotIn(self.image, encrypted)
            self.assertNotIn(base64.b64encode(self.image), encrypted)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM steam_avatars').fetchone()[0], 1)

    def test_deduplicates_images_and_tracks_purge_archive_and_restore(self):
        self.assertTrue(store.save(self.sid, 1, self.image))
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute("INSERT INTO detection_history VALUES(2,'steam_encounter',?)", (secur.encrypt_value(json.dumps({'id':self.sid})),))
        self.assertTrue(store.save(self.sid, 2, self.image))
        with closing(sqlite3.connect(self.database)) as db, db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM steam_avatars').fetchone()[0], 1)
            db.execute('CREATE TABLE history_archive_events (original_id INTEGER, kind TEXT)')
            db.execute("INSERT INTO history_archive_events VALUES(1,'steam_encounter')")
            db.execute('DELETE FROM detection_history')
            store.prune(db)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM steam_avatars').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM steam_avatar_links').fetchone()[0], 1)
        self.assertIsNone(store.avatar(self.sid))
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute("INSERT INTO detection_history VALUES(1,'steam_encounter',?)", (secur.encrypt_value(json.dumps({'id':self.sid})),))
        self.assertEqual(store.avatar(self.sid), self.image)
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute('DELETE FROM detection_history')
            db.execute('DELETE FROM history_archive_events')
            store.prune(db)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM steam_avatars').fetchone()[0], 0)

    def test_rejects_unrecorded_invalid_and_corrupt_data(self):
        self.assertFalse(store.save(self.sid, 77, self.image))
        self.assertFalse(store.save(self.second, 1, self.image))
        self.assertFalse(store.save('invalid', 1, self.image))
        self.assertFalse(store.save(self.sid, 1, b'not an image'))
        self.assertIsNone(store.avatar(self.sid))
        self.assertTrue(store.save(self.sid, 1, self.image))
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute('UPDATE steam_avatars SET avatar=?', (b'invalid',))
        self.assertIsNone(store.avatar(self.sid))

    def test_evicts_oldest_avatar_without_deleting_encounters(self):
        with patch.object(store, 'MAX_ENTRIES', 1):
            self.assertTrue(store.save(self.sid, 1, self.image))
            with closing(sqlite3.connect(self.database)) as db, db:
                db.execute("INSERT INTO detection_history VALUES(2,'steam_encounter',?)", (secur.encrypt_value(json.dumps({'id':self.second})),))
            self.assertTrue(store.save(self.second, 2, png('blue')))
            self.assertIsNone(store.avatar(self.sid))
            self.assertIsNotNone(store.avatar(self.second))
            with closing(sqlite3.connect(self.database)) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM detection_history').fetchone()[0], 2)

    def test_historical_save_rechecks_only_matching_active_events(self):
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute("INSERT INTO detection_history VALUES(2,'steam_encounter',?)", (secur.encrypt_value(json.dumps({'id':self.sid})),))
            db.execute("INSERT INTO detection_history VALUES(3,'steam_encounter',?)", (secur.encrypt_value(json.dumps({'id':self.second})),))
        self.assertTrue(store.active_event_matches(self.sid, [1, 2]))
        self.assertFalse(store.active_event_matches(self.second, [1, 2]))
        self.assertTrue(store.save_historical(self.sid, self.image, [1,2,3]))
        self.assertFalse(store.save_historical(self.sid, self.image, [1,2,3]))
        with closing(sqlite3.connect(self.database)) as db, db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM steam_avatar_links').fetchone()[0], 2)
            db.execute('DELETE FROM detection_history WHERE id IN (1,2)')
        self.assertFalse(store.active_event_matches(self.sid, [1, 2]))
        self.assertFalse(store.save_historical(self.sid, png('blue'), [1,2,3]))
        self.assertIsNone(store.avatar(self.sid))
        self.assertIsNone(store.avatar(self.second))

    def test_historical_numeric_steam_ids_remain_compatible(self):
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute('UPDATE detection_history SET metadata=? WHERE id=1',
                       (secur.encrypt_value(json.dumps({'id':int(self.sid)})),))
        self.assertTrue(store.active_event_matches(self.sid, [1]))
        self.assertTrue(store.save_historical(self.sid, self.image, [1]))
        self.assertEqual(store.avatar(self.sid), self.image)

    def test_live_observation_only_writes_new_avatar_revisions(self):
        fake = types.ModuleType('application.detection_history')
        fake.record_detection = Mock()
        fake.update_detection = Mock()
        spec = importlib.util.spec_from_file_location('application._steam_history_avatar_test',
            Path(__file__).resolve().parents[1] / 'application' / 'steam_history.py')
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'application.detection_history': fake}):
            spec.loader.exec_module(module)
        module._known[self.sid] = {'id': 1, 'steam': {'id':self.sid}, 'mode':'Arena'}
        peer = {'id':self.sid, 'avatar_available':True, 'avatar_revision':1}
        provider = Mock(return_value=self.image)
        saved = threading.Event()
        self.assertTrue(module.persist_avatars('active', [peer], provider, saved.set))
        self.assertTrue(saved.wait(5))
        self.assertEqual(store.avatar(self.sid), self.image)
        self.assertFalse(module.persist_avatars('active', [peer], provider))
        self.assertEqual(provider.call_count, 1)
        module._known.clear()  # An archive/purge clears the live observation.
        self.assertFalse(module.persist_avatars('active', [dict(peer, avatar_revision=2)], provider))
        self.assertEqual(provider.call_count, 1)

    def test_slow_avatar_storage_does_not_block_live_peer_observation(self):
        fake = types.ModuleType('application.detection_history')
        fake.record_detection = Mock()
        fake.update_detection = Mock()
        spec = importlib.util.spec_from_file_location('application._steam_history_async_test',
            Path(__file__).resolve().parents[1] / 'application' / 'steam_history.py')
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'application.detection_history': fake}):
            spec.loader.exec_module(module)
        module._known[self.sid] = {'id':1, 'steam':{'id':self.sid}, 'mode':'Arena'}
        started, release = threading.Event(), threading.Event()
        def slow_save(*_args):
            started.set()
            self.assertTrue(release.wait(5))
            return False
        with patch.object(store, 'save', side_effect=slow_save):
            try:
                peer = {'id':self.sid, 'avatar_available':True, 'avatar_revision':1}
                self.assertTrue(module.persist_avatars('active', [peer], lambda _sid:self.image))
                self.assertTrue(started.wait(2))
                # The storage thread is still blocked, but the next reading of
                # the Steam helper can queue a new revision immediately.
                self.assertTrue(module.persist_avatars('active', [dict(peer, avatar_revision=2)], lambda _sid:self.image))
            finally:
                release.set()
                module._avatar_queue.join()

    def test_historical_response_after_purge_does_not_restore_the_avatar(self):
        self.assertTrue(store.active_event_matches(self.sid, [1]))
        # The history can be purged while Steam is preparing its response.
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute('DELETE FROM detection_history WHERE id=1')
        self.assertFalse(store.save_historical(self.sid, self.image, [1]))
        self.assertIsNone(store.avatar(self.sid))

    def test_retention_removes_only_cache_without_active_or_archived_encounters(self):
        from application import retention
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute('ALTER TABLE detection_history ADD COLUMN recorded_at TEXT')
            db.execute("UPDATE detection_history SET recorded_at='2025-01-01 12:00:00' WHERE id=1")
            db.execute("INSERT INTO detection_history VALUES(2,'steam_encounter',?,'2025-01-02 12:00:00')",
                       (secur.encrypt_value(json.dumps({'id':self.second})),))
            db.execute('CREATE TABLE history_archive_events (original_id INTEGER, kind TEXT)')
            db.execute("INSERT INTO history_archive_events VALUES(1,'steam_encounter')")
        self.assertTrue(store.save(self.sid, 1, self.image))
        self.assertTrue(store.save(self.second, 2, png('blue')))
        result = retention.cleanup(self.database, {'captures':0, 'steam':30}, lambda value: value,
                                   now=datetime(2026, 1, 1))
        self.assertEqual(result['steam'], 2)
        with closing(sqlite3.connect(self.database)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM steam_avatars').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM steam_avatar_links').fetchone()[0], 1)
        self.assertIsNone(store.avatar(self.sid))

    def test_real_archive_restore_and_purge_keep_only_referenced_avatars(self):
        import application
        main = sys.modules['__main__']
        app = Flask('steam-avatar-archive-test')
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute('ALTER TABLE detection_history ADD COLUMN recorded_at TEXT')
            db.execute('ALTER TABLE detection_history ADD COLUMN mode TEXT')
            db.execute('ALTER TABLE detection_history ADD COLUMN message BLOB')
            db.execute("UPDATE detection_history SET recorded_at='2026-01-01 00:00:00',mode='Arena',message=? WHERE id=1",
                       (secur.encrypt_value('rencontre'),))
            db.execute('CREATE TABLE detection_history_sequence (id INTEGER PRIMARY KEY, last_id INTEGER)')
            db.execute('INSERT INTO detection_history_sequence VALUES (1,1)')
        self.assertTrue(store.save(self.sid, 1, self.image))
        history = types.SimpleNamespace(_connect=lambda:sqlite3.connect(self.database, timeout=10))
        functions = types.SimpleNamespace(run_monitor=False, monitor_lock=threading.Lock(), invasion_search_history_id=None)
        steam_history = types.SimpleNamespace(clear_history_transaction=lambda operation:operation())
        spec = importlib.util.spec_from_file_location('application._history_avatars_test',
            Path(__file__).resolve().parents[1] / 'application' / 'history_archives.py')
        module = importlib.util.module_from_spec(spec)
        with patch.object(main, 'app', app, create=True), \
             patch.object(application, 'detection_history', history, create=True), \
             patch.object(application, 'functions', functions, create=True), \
             patch.object(application, 'steam_history', steam_history, create=True):
            spec.loader.exec_module(module)
            client = app.test_client()
            self.assertEqual(client.post('/history-archives').get_json()['archived'], 1)
            self.assertIsNone(store.avatar(self.sid))
            self.assertEqual(client.post('/history-archives/1/restore').get_json()['restored'], 1)
            self.assertEqual(store.avatar(self.sid), self.image)
            with closing(sqlite3.connect(self.database)) as db, db:
                db.execute("INSERT INTO detection_history VALUES(2,'steam_encounter',?,'2026-01-01 00:01:00','Arena',?)",
                           (secur.encrypt_value(json.dumps({'id':self.second})), secur.encrypt_value('rencontre')))
            self.assertTrue(store.save(self.second, 2, png('blue')))
            self.assertEqual(client.post('/history-purge').get_json()['removed'], 2)
            self.assertIsNone(store.avatar(self.sid))
            with closing(sqlite3.connect(self.database)) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM steam_avatars').fetchone()[0], 1)
            self.assertEqual(client.post('/history-archives/1/restore').get_json()['restored'], 1)
            self.assertEqual(store.avatar(self.sid), self.image)
            self.assertIsNone(store.avatar(self.second))
            functions.run_monitor = True
            self.assertEqual(client.post('/history-archives/1/delete').status_code, 409)
            self.assertEqual(client.post('/history-archives/1/restore').status_code, 409)
            functions.run_monitor = False
            self.assertEqual(client.post('/history-archives/1/delete').get_json()['request'], 'success')
            self.assertEqual(client.post('/history-archives/1/delete').status_code, 404)
            self.assertEqual(store.avatar(self.sid), self.image)
            with closing(sqlite3.connect(self.database)) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM detection_history').fetchone()[0], 1)
                self.assertEqual(db.execute('SELECT COUNT(*) FROM history_archive_events').fetchone()[0], 0)

    def test_players_route_requires_current_active_history_for_fetch_and_request(self):
        import application
        main = sys.modules['__main__']
        app = Flask('steam-avatar-test')
        init = types.ModuleType('application.init')
        init.database_capture = self.database
        sightings = types.ModuleType('application.player_sightings')
        sightings.read_sightings = lambda: []
        history = types.ModuleType('application.detection_history')
        def read_events():
            with closing(sqlite3.connect(self.database)) as db:
                rows = db.execute("SELECT id,metadata FROM detection_history WHERE kind='steam_encounter'").fetchall()
            return [{'id':row[0], 'date':'2026-01-01 00:00:00', 'mode':'Arena', 'event':'steam_encounter',
                     'steam':json.loads(secur.decrypt_value(row[1]).decode())} for row in rows]
        history.read_steam_history = read_events
        tags = types.ModuleType('application.player_tags')
        tags.annotate = lambda entries: entries
        peer = types.SimpleNamespace(request_historical_avatar=Mock(return_value='queued'))
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute('CREATE TABLE tabel_captures (id INTEGER, name BLOB, victory BLOB, defeat BLOB, egality BLOB, time BLOB, date BLOB, mode BLOB)')
        spec = importlib.util.spec_from_file_location('application._players_avatar_test',
            Path(__file__).resolve().parents[1] / 'application' / 'players.py')
        module = importlib.util.module_from_spec(spec)
        with patch.object(main, 'app', app, create=True), patch.object(application, 'peer_tracking', peer, create=True), \
                patch.object(application, 'player_tags', tags, create=True), \
                patch.dict(sys.modules, {'application.init':init, 'application.player_sightings':sightings,
                                         'application.detection_history':history, 'application.player_tags':tags}):
            spec.loader.exec_module(module)
            client = app.test_client()
            self.assertEqual(client.post('/players/steam-avatar/request', data={'steam_id':self.sid}).status_code, 404)
            before = client.get('/players').get_json()['players']
            self.assertFalse(before[0]['steam']['avatar_available'])
            self.assertEqual(client.post('/players/steam-avatar/request', data={'steam_id':self.second}).status_code, 404)
            self.assertEqual(client.post('/players/steam-avatar/request', data={'steam_id':self.sid}).get_json()['state'], 'queued')
            peer.request_historical_avatar.assert_called_once_with(self.sid, (1,))
            self.assertTrue(store.save_historical(self.sid, self.image, [1]))
            image = client.get('/players/steam-avatar/' + self.sid)
            self.assertEqual(image.data, self.image)
            self.assertEqual(image.headers['Cache-Control'], 'no-store')
            self.assertTrue(client.get('/players').get_json()['players'][0]['steam']['avatar_available'])
            self.assertEqual(client.post('/players/steam-avatar/request', data={'steam_id':self.sid}).get_json()['state'], 'cached')
            with closing(sqlite3.connect(self.database)) as db, db:
                db.execute('DELETE FROM detection_history')
            self.assertEqual(client.post('/players/steam-avatar/request', data={'steam_id':self.sid}).status_code, 404)
            self.assertEqual(client.get('/players/steam-avatar/' + self.sid).status_code, 404)


if __name__ == '__main__':
    unittest.main()
