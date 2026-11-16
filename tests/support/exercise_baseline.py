"""Baseline import regression: all paths use private temporary SQLite files."""
import json
import os
import sqlite3
import tempfile
import uuid
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from flask import Flask
app = Flask(__name__)
from application import online_leaderboard as online, leaderboard_baseline, mode_stats
from application.secur import encrypt_value

with tempfile.TemporaryDirectory(prefix='tracker-baseline-test-') as directory:
    root = Path(directory)
    os.environ['APPDATA'] = directory
    path = str(root / 'user.db')
    fields = ', '.join('c' + str(i) + ' TEXT' for i in range(1, 20))
    with closing(sqlite3.connect(path)) as db, db:
        db.execute('CREATE TABLE tabel_user (id INTEGER PRIMARY KEY, ' + fields + ')')
        data = ['0'] * 20
        data[1], data[2], data[3], data[4], data[9], data[19] = 'Personnage', '7', '2', '1', '10', '120'
        data[12] = '-1'  # A legacy Arena calculation could persist this value.
        db.execute('INSERT INTO tabel_user VALUES(' + ','.join('?' for _ in range(20)) + ')', [1] + [encrypt_value(v) for v in data[1:]])
        db.execute('CREATE TABLE mode_stats (mode TEXT PRIMARY KEY, ' + ', '.join(name + ' REAL NOT NULL DEFAULT 0' for name in mode_stats.FIELDS) + ')')
        db.execute('INSERT INTO mode_stats(mode,victory,defeat,combats) VALUES (?,?,?,?)', ('Invasion', 4, 1, 5))
        db.execute('CREATE TABLE leaderboard_event_outbox (event_id TEXT PRIMARY KEY, match_id TEXT NOT NULL, mode TEXT NOT NULL, kind TEXT NOT NULL, occurred_at TEXT NOT NULL)')
        first = str(uuid.uuid4())
        match = str(uuid.uuid4())
        def enqueue(identifier, kind):
            db.execute('INSERT INTO leaderboard_event_outbox VALUES(?,?,?,?,?)', (identifier, match, encrypt_value('Arena'), encrypt_value(kind), encrypt_value('2026-01-01T10:00:00Z')))
        enqueue(first, 'start')
    try:
        leaderboard_baseline.capture(path, 'https://test.example', 'installation', True)
        raise AssertionError('A running fight must postpone the initial snapshot')
    except ValueError as error:
        assert str(error) == 'baseline_wait'
    saved = {}
    calls = []
    def api(method, path, data=None, token=None, root=None, **kwargs):
        calls.append((path, data))
        if path == '/api/v1/events':
            return {'accepted':[event['event_id'] for event in data['events']]}
        if path == '/api/v1/baselines':
            if not saved:
                saved.update(data)
                raise OSError('simulated lost response after server commit')
            assert saved == data, 'A retry must use the identical durable snapshot'
            return {'import_id':data['import_id'], 'already_imported':False}
        raise AssertionError(path)
    with patch.object(online.init, 'database_user', path), \
         patch.object(online, '_settings', return_value=(True, 'installation', b'token', False, 'https://test.example')), \
         patch.object(online, '_event_permission', return_value=True), \
         patch.object(online, '_call', side_effect=api), \
         patch.object(online, '_db') as settings_db:
        class Settings:
            def execute(self, *args): return self
            def fetchone(self): return (1, 1)
            def close(self): pass
        settings_db.side_effect = Settings
        try:
            online._ensure_baseline('https://test.example', 'fixture-token')
            raise AssertionError('The simulated network failure was not propagated')
        except OSError:
            pass
        assert saved['modes']['Arena']['victory'] == 7
        assert saved['modes']['Arena']['combats'] == 10
        assert saved['modes']['Arena']['abandon'] == -1
        assert saved['modes']['Invasion']['victory'] == 4
        assert saved['modes']['Defense']['combats'] == 0
        second = str(uuid.uuid4())
        with closing(sqlite3.connect(path)) as db, db:
            enqueue(second, 'victory')
            db.execute('UPDATE tabel_user SET c2=? WHERE id=1', (encrypt_value('8'),))
        online._ensure_baseline('https://test.example', 'fixture-token')
        before = len(calls)
        online._ensure_baseline('https://test.example', 'fixture-token')
        assert len(calls) == before, 'A completed import must not be repeated'
        with closing(sqlite3.connect(path)) as db:
            assert db.execute('SELECT event_id FROM leaderboard_event_outbox').fetchall() == [(second,)]
            assert db.execute('SELECT COUNT(*) FROM leaderboard_baseline_events').fetchone()[0] == 0
        online._send_events('https://test.example', 'fixture-token')
        assert calls[-1][0] == '/api/v1/events' and calls[-1][1]['events'][0]['event_id'] == second
        assert [path for path, _ in calls] == ['/api/v1/events', '/api/v1/baselines', '/api/v1/baselines', '/api/v1/events']
print('Historical snapshot, pending events and lost-response retry passed.')
