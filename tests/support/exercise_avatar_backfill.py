"""Exercise one-time avatar recovery with synthetic, isolated databases."""
import io
import json
import os
import sqlite3
import sys
import tempfile
import types
from contextlib import closing
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image
from flask import Flask
app = Flask(__name__)
from application import runtime_paths
runtime_paths.image_dir = lambda: Path(os.environ['APPDATA']) / 'test-runtime-images'
from application import secur, steam_avatar_backfill as backfill, steam_avatar_store as store


def png(color):
    output = io.BytesIO()
    Image.new('RGB', (8, 8), color).save(output, format='PNG')
    return output.getvalue()


def add(db, event_id, sid):
    db.execute("INSERT INTO detection_history(id,kind,metadata) VALUES(?,'steam_encounter',?)",
               (event_id, secur.encrypt_value(json.dumps({'id':sid}))))


def rows(db, sql, args=()):
    with closing(sqlite3.connect(db)) as connection:
        return connection.execute(sql, args).fetchall()


def prepare(db):
    with closing(sqlite3.connect(db)) as connection, connection:
        connection.execute('CREATE TABLE detection_history (id INTEGER PRIMARY KEY, kind TEXT NOT NULL, metadata BLOB)')


def scan(worker):
    for _ in range(100):
        if rows(db, 'SELECT scanned FROM steam_avatar_backfill')[0][0]:
            return
        assert worker.step(now=100) == 'scanning'
    raise AssertionError('scan failed to finish')


with tempfile.TemporaryDirectory(dir=os.environ['APPDATA']) as folder, patch.object(secur, 'active_data_key', return_value=None):
    db = str(Path(folder) / 'capture.db')
    sid1, sid2, sid3, sid4, sid5 = ('76561198000000001', '76561198000000002', '76561198000000003', '76561198000000004', '76561198000000005')
    prepare(db)
    with patch.object(backfill, '_database', return_value=db), patch.object(store, '_database', return_value=db), \
         patch.object(backfill, '_BATCH', 2), patch.object(store, 'MAX_ENTRIES', 2), \
         patch.object(backfill.peer_tracking, 'enabled', return_value=True), \
         patch.object(backfill.peer_tracking, 'snapshot', return_value={}), \
         patch.object(backfill.peer_tracking, 'request_historical_avatar', return_value='queued') as request, \
         patch.object(backfill.peer_tracking, 'historical_avatar_result', return_value='pending') as result:
        with closing(sqlite3.connect(db)) as connection, connection:
            add(connection, 1, sid1); add(connection, 2, sid2); add(connection, 3, sid3); add(connection, 4, sid1)
        # A cached historical avatar and an unrelated cached avatar must survive.
        assert store.save(sid2, 2, png('red'))
        with closing(sqlite3.connect(db)) as connection, connection:
            store._save_locked(connection, sid4, [99], __import__('base64').b64encode(png('blue')).decode(), 'archived-digest')
        backfill.initialize()
        with closing(sqlite3.connect(db)) as connection, connection:
            add(connection, 5, sid4)  # Encounter after startup is outside this one-time snapshot.
        worker = backfill.Backfill()
        assert worker.step(now=100) == 'scanning'
        backfill.initialize()  # Restart during the scan must keep the original upper bound.
        while rows(db, 'SELECT scanned FROM steam_avatar_backfill')[0][0] == 0:
            worker.step(now=100)
        assert rows(db, 'SELECT upper_id,total FROM steam_avatar_backfill') == [(4, 3)]
        assert rows(db, 'SELECT capacity FROM steam_avatar_cache_policy') == [(4,)]
        assert rows(db, 'SELECT COUNT(*) FROM steam_avatar_backfill_jobs') == [(3,)]
        raw_database = Path(db).read_bytes()
        assert all(sid.encode('ascii') not in raw_database for sid in (sid1, sid2, sid3))
        # Cached sid2 needs no network; missing sid1 is requested and persisted.
        while not request.called:
            worker.step(now=100)
        target, event_ids = request.call_args.args
        assert target in (sid1, sid3)
        assert worker.step(now=101) == 'waiting'
        assert store.save_historical(target, png('green'), event_ids)
        result.return_value = 'saved'
        assert worker.step(now=102) == 'processed'
        # Close and reopen the app: pending work remains, but completed work is not repeated.
        worker = backfill.Backfill(); request.reset_mock(); result.return_value = 'pending'
        for _ in range(10):
            state = worker.step(now=110)
            if state == 'queued': break
        assert state == 'queued' and request.call_args.args[0] in (sid1, sid3)
        assert request.call_args.args[0] != target
        pending_id, pending_events = request.call_args.args
        assert store.save_historical(pending_id, png('yellow'), pending_events)
        assert worker.step(now=111) == 'processed'
        # A new live encounter during recovery must not evict the batch or
        # the pre-existing archived avatar when the cache reaches its limit.
        with closing(sqlite3.connect(db)) as connection, connection: add(connection, 6, sid5)
        assert store.save(sid5, 6, png('cyan'))
        assert rows(db, 'SELECT capacity FROM steam_avatar_cache_policy') == [(5,)]
        for _ in range(5):
            if worker.step(now=112) == 'complete': break
        else: raise AssertionError('recovery did not complete')
        assert rows(db, 'SELECT completed,total,unavailable,removed FROM steam_avatar_backfill') == [(1,3,0,0)]
        assert rows(db, 'SELECT COUNT(*) FROM steam_avatar_backfill_jobs') == [(0,)]
        assert rows(db, 'SELECT COUNT(*) FROM steam_avatar_backfill_events') == [(0,)]
        assert set(store.available([sid1, sid2, sid3])) == {sid1, sid2, sid3}
        assert rows(db, 'SELECT COUNT(*) FROM steam_avatars') == [(5,)]
        backfill.initialize()
        assert backfill.Backfill().step(now=9999) == 'complete'
        assert request.call_count == 1

    db = str(Path(folder) / 'unavailable.db'); prepare(db)
    with patch.object(backfill, '_database', return_value=db), patch.object(store, '_database', return_value=db), \
         patch.object(backfill.peer_tracking, 'enabled', return_value=True), \
         patch.object(backfill.peer_tracking, 'snapshot', return_value={}), \
         patch.object(backfill.peer_tracking, 'historical_avatar_transport_available', return_value=True) as transport, \
         patch.object(backfill.peer_tracking, 'request_historical_avatar', return_value='unavailable') as request, \
         patch.object(backfill.peer_tracking, 'historical_avatar_result', return_value='unavailable') as result:
        with closing(sqlite3.connect(db)) as connection, connection:
            add(connection, 1, sid1)
        backfill.initialize(); worker = backfill.Backfill(); scan(worker)
        assert worker.step(now=100) == 'waiting'  # No game/Steam: never consume an attempt.
        assert rows(db, 'SELECT attempts FROM steam_avatar_backfill_jobs') == [(0,)]
        request.return_value = 'queued'
        assert worker.step(now=100) == 'queued'
        result.return_value = 'interrupted'
        assert worker.step(now=101) == 'waiting'  # An interrupted helper is not a refusal.
        assert rows(db, 'SELECT attempts FROM steam_avatar_backfill_jobs') == [(0,)]
        transport.return_value = False
        assert worker.step(now=131) == 'queued'
        result.return_value = 'unavailable'
        assert worker.step(now=132) == 'processed'
        assert rows(db, 'SELECT attempts FROM steam_avatar_backfill_jobs') == [(0,)]
        transport.return_value = True
        worker = backfill.Backfill()  # Resume persisted work after tracker restart.
        result.return_value = 'unavailable'
        for moment in (162, 463, 764):
            assert worker.step(now=moment) == 'queued'
            assert worker.step(now=moment+1) == 'processed'
        assert worker.step(now=766) == 'complete'
        assert rows(db, 'SELECT completed,total,unavailable FROM steam_avatar_backfill') == [(1,1,1)]
        assert store.avatar(sid1) is None

    db = str(Path(folder) / 'purged.db'); prepare(db)
    with patch.object(backfill, '_database', return_value=db), patch.object(store, '_database', return_value=db), \
         patch.object(backfill.peer_tracking, 'enabled', return_value=True), \
         patch.object(backfill.peer_tracking, 'snapshot', return_value={}), \
         patch.object(backfill.peer_tracking, 'request_historical_avatar', return_value='queued'), \
         patch.object(backfill.peer_tracking, 'historical_avatar_result', return_value='pending'):
        with closing(sqlite3.connect(db)) as connection, connection: add(connection, 1, sid1)
        backfill.initialize(); worker = backfill.Backfill(); scan(worker)
        assert worker.step(now=100) == 'queued'
        with closing(sqlite3.connect(db)) as connection, connection: connection.execute('DELETE FROM detection_history')
        assert worker.step(now=101) == 'processed'
        assert worker.step(now=102) == 'complete'
        assert rows(db, 'SELECT completed,removed FROM steam_avatar_backfill') == [(1,1)]
        assert store.avatar(sid1) is None

    db = str(Path(folder) / 'key-error.db'); prepare(db)
    with patch.object(backfill, '_database', return_value=db), patch.object(store, '_database', return_value=db):
        with closing(sqlite3.connect(db)) as connection, connection: add(connection, 1, sid1)
        backfill.initialize()
        with patch.object(backfill, 'decrypt_value', side_effect=RuntimeError('missing key')):
            try: backfill.Backfill().step(now=100)
            except RuntimeError: pass
            else: raise AssertionError('missing key must pause recovery')
        assert rows(db, 'SELECT cursor,scanned,completed FROM steam_avatar_backfill') == [(1,0,0)]
        worker = backfill.Backfill(); scan(worker)
        assert rows(db, 'SELECT total,completed FROM steam_avatar_backfill') == [(1,0)]

    db = str(Path(folder) / 'disabled.db'); prepare(db)
    with patch.object(backfill, '_database', return_value=db), patch.object(store, '_database', return_value=db), \
         patch.object(backfill.peer_tracking, 'enabled', return_value=False), \
         patch.object(backfill.peer_tracking, 'snapshot') as snapshot:
        with closing(sqlite3.connect(db)) as connection, connection: add(connection, 1, sid1)
        backfill.initialize(); worker = backfill.Backfill(); scan(worker)
        assert worker.step(now=100) == 'waiting'
        snapshot.assert_not_called()
        assert rows(db, 'SELECT attempts,status FROM steam_avatar_backfill_jobs') == [(0,'pending')]

    db = str(Path(folder) / 'corrupted-avatar.db'); prepare(db)
    with patch.object(backfill, '_database', return_value=db), patch.object(store, '_database', return_value=db), \
         patch.object(backfill.peer_tracking, 'enabled', return_value=True), \
         patch.object(backfill.peer_tracking, 'snapshot', return_value={}), \
         patch.object(backfill.peer_tracking, 'request_historical_avatar', return_value='queued') as request:
        with closing(sqlite3.connect(db)) as connection, connection: add(connection, 1, sid1)
        assert store.save(sid1, 1, png('red'))
        with closing(sqlite3.connect(db)) as connection, connection:
            connection.execute('UPDATE steam_avatars SET avatar=?', (b'corrupted',))
        backfill.initialize(); worker = backfill.Backfill(); scan(worker)
        assert worker.step(now=100) == 'queued'
        request.assert_called_once_with(sid1, (1,))

    db = str(Path(folder) / 'new-install.db'); prepare(db)
    with patch.object(backfill, '_database', return_value=db), patch.object(store, '_database', return_value=db):
        backfill.initialize(); worker = backfill.Backfill(); scan(worker)
        assert worker.step(now=100) == 'complete'
        with closing(sqlite3.connect(db)) as connection, connection: add(connection, 1, sid1)
        backfill.initialize()
        assert backfill.Backfill().step(now=200) == 'complete'
        assert rows(db, 'SELECT completed,total FROM steam_avatar_backfill') == [(1,0)]
        with patch.object(backfill, '_started', False), patch.object(backfill.threading, 'Thread') as thread:
            assert not backfill.start()
            thread.assert_not_called()

    db = str(Path(folder) / 'resume-after-save.db'); prepare(db)
    with patch.object(backfill, '_database', return_value=db), patch.object(store, '_database', return_value=db), \
         patch.object(backfill.peer_tracking, 'enabled', return_value=True), \
         patch.object(backfill.peer_tracking, 'snapshot', return_value={}), \
         patch.object(backfill.peer_tracking, 'request_historical_avatar', return_value='queued') as request:
        with closing(sqlite3.connect(db)) as connection, connection: add(connection, 1, sid1)
        backfill.initialize(); worker = backfill.Backfill(); scan(worker)
        assert worker.step(now=100) == 'queued'
        assert store.save_historical(sid1, png('green'), (1,))
        worker = backfill.Backfill()  # Exit after disk save, before the job was marked done.
        assert worker.step(now=101) == 'processed' and worker.step(now=102) == 'complete'
        assert request.call_count == 1

    db = str(Path(folder) / 'helper-integration.db'); prepare(db)
    peers = backfill.peer_tracking
    commands = []
    session = types.SimpleNamespace(steam_session=lambda: (1, 'synthetic', Path('steam.exe')))
    with patch.object(backfill, '_database', return_value=db), patch.object(store, '_database', return_value=db), \
         patch.object(peers, 'enabled', return_value=True), patch.object(peers, 'snapshot', return_value={}), \
         patch.object(peers.ctypes.windll.user32, 'FindWindowW', return_value=1), \
         patch.object(peers, '_snapshot', {'status':'active', 'peers':[]}), \
         patch.object(peers, '_command_writer', side_effect=commands.append), \
         patch.dict(sys.modules, {'application.steam_log_auto':session}):
        with closing(sqlite3.connect(db)) as connection, connection: add(connection, 1, sid1)
        backfill.initialize(); worker = backfill.Backfill(); scan(worker)
        assert worker.step(now=100) == 'queued'
        # A simultaneously visible page shares the same request.
        assert peers.request_historical_avatar(sid1, (1,)) == 'queued'
        assert commands == ['avatar:' + sid1]
        peers._handle_historical_avatar({'id':sid1, 'state':'ready', 'avatar_png':__import__('base64').b64encode(png('purple')).decode()})
        peers._historical_avatar_save_queue.join()
        assert peers.historical_avatar_result(sid1) == 'saved'
        assert worker.step(now=101) == 'processed' and worker.step(now=102) == 'complete'
        assert store.avatar(sid1) == png('purple')

print('One-time historical avatar recovery: snapshots, resume, retries, cache and purge OK')
