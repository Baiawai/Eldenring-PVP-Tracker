"""Exercise consent, synchronization, and retry using private APPDATA only."""
import unittest.mock
from unittest.mock import patch
import json
import tempfile
from pathlib import Path
from flask import Flask
app = Flask(__name__)
from application import error_reports
error_reports.report = lambda *args, **kwargs: None
error_reports.start = lambda: None
from application import online_leaderboard as online
client = app.test_client()

# Presence uses only an existing account bound to the configured origin.
# These checks use synthetic credentials and never contact the network.
origin = 'https://example.invalid'
with patch.object(online, '_base_url', return_value=origin), \
        patch.object(online, '_settings', return_value=(True, 'test-id', b'test', False, origin)) as settings, \
        patch.object(online, '_login_cancel_pending', return_value=False), \
        patch.object(online, '_stored_token', return_value='synthetic-token') as stored, \
        patch.object(online, '_call') as activity_call:
    assert online.send_tracker_activity() is True
    activity_call.assert_called_once_with('POST', '/api/v1/profile/activity', token='synthetic-token', root=origin)
    for state in [(False, 'test-id', b'test', False, origin), (True, None, b'test', False, origin),
                  (True, 'test-id', None, False, origin), (True, 'test-id', b'test', True, origin),
                  (True, 'test-id', b'test', False, 'https://other.invalid')]:
        settings.return_value = state
        assert online.send_tracker_activity() is False
    assert activity_call.call_count == 1 and stored.call_count == 1

# Page sizes are relayed to the server while older cached front ends retain
# their historical five-row default. No remote calls are made in these tests.
from urllib.parse import parse_qs, urlsplit
with patch.object(online, '_call', return_value={'entries': []}) as read_entries:
    for size in (5, 10, 20):
        response = client.get('/online-leaderboard/entries', query_string={
            'mode': 'Arena', 'page': 2, 'per_page': size, 'search': 'Test', 'sort': 'score', 'direction': 'desc'})
        assert response.status_code == 200
        method, path = read_entries.call_args.args[:2]
        query = parse_qs(urlsplit(path).query)
        assert method == 'GET' and query['per_page'] == [str(size)] and query['page'] == ['2']
    assert client.get('/online-leaderboard/entries').status_code == 200
    assert parse_qs(urlsplit(read_entries.call_args.args[1]).query)['per_page'] == ['5']
    calls = read_entries.call_count
    for size in ('0', '-1', '21', '25', '100', 'abc', '1.5'):
        assert client.get('/online-leaderboard/entries', query_string={'per_page': size}).status_code == 400
    assert read_entries.call_count == calls

# In development, an explicit configuration remains authoritative.
with tempfile.TemporaryDirectory(prefix='leaderboard-config-test-') as directory:
    config_path = Path(directory) / 'leaderboard-config.json'
    with patch.object(online, 'data_dir', return_value=Path(directory)), patch.object(online, 'FROZEN', False):
        assert online._base_url() == 'https://eldenringpvp.com'
        config_path.write_text(json.dumps({'environment':'development', 'urls':{'development':'http://127.0.0.1:8000'}}), encoding='utf-8')
        assert online._base_url() == 'http://127.0.0.1:8000'
        config_path.write_text(json.dumps({'environment':'production', 'urls':{'production':''}}), encoding='utf-8')
        assert online._base_url() is None
        config_path.write_text('{invalid json', encoding='utf-8')
        assert online._base_url() is None
        config_path.write_text(json.dumps({'environment':'production', 'urls':{'production':'http://example.com'}}), encoding='utf-8')
        assert online._base_url() is None

# Store builds must ignore even malformed or previously valid local overrides,
# and may not contact an old server through an explicitly supplied root.
with tempfile.TemporaryDirectory(prefix='leaderboard-store-config-test-') as directory:
    config_path = Path(directory) / 'leaderboard-config.json'
    with patch.object(online, 'data_dir', return_value=Path(directory)), patch.object(online, 'FROZEN', True):
        for config in (None, '{invalid json',
                       json.dumps({'environment':'development', 'urls':{'development':'http://127.0.0.1:8000'}}),
                       json.dumps({'environment':'production', 'urls':{'production':'https://other.example'}}),
                       json.dumps({'environment':'production', 'urls':{'production':''}})):
            if config is not None:
                config_path.write_text(config, encoding='utf-8')
            assert online._base_url() == 'https://eldenringpvp.com'
        with patch.object(online, 'build_opener') as opener:
            for root in ('http://127.0.0.1:8000', 'https://other.example',
                         'https://eldenringpvp.com.attacker.example', 'http://eldenringpvp.com'):
                try:
                    online._call('DELETE', '/api/v1/profile', token='old-test-token', root=root)
                    raise AssertionError('Store build must reject non-production origins')
                except RuntimeError as error:
                    assert str(error) == 'server_not_allowed'
            opener.assert_not_called()
            opener.return_value.open.return_value.__enter__.return_value.read.return_value = b'{"ok":true}'
            assert online._call('GET', '/api/v1/leaderboards', root='https://eldenringpvp.com') == {'ok':True}
            opener.assert_called_once()

# A previously configured development server cannot be contacted by a Store
# build, including for pending withdrawals. The pending operation and encrypted
# credential must stay intact so they can be handled explicitly later.
with tempfile.TemporaryDirectory(prefix='leaderboard-store-pending-test-') as directory:
    database = str(Path(directory) / 'settings.db')
    local_token = online.win32crypt.CryptProtectData(b'local-test-token', 'test', None, None, None, 0)
    with patch.object(online, '_database', return_value=database), patch.object(online, 'FROZEN', True), \
         patch.object(online, 'build_opener') as opener, patch.object(online, '_clear_event_outbox') as clear_events:
        with online.closing(online._db()) as db, db:
            db.execute('UPDATE online_leaderboard SET uuid=?,token=?,server_url=? WHERE id=1',
                       ('local-fixture', local_token, 'http://127.0.0.1:8000'))
        for column, outcome in (('delete_pending', 'delete_failed'),
                                ('steam_login_cancel_pending', 'steam_cancel_failed'),
                                ('language_remove_pending', 'language_delete_failed'),
                                ('steam_remove_pending', 'steam_delete_failed')):
            with online.closing(online._db()) as db, db:
                db.execute('UPDATE online_leaderboard SET ' + column + '=1 WHERE id=1')
            assert online._sync() == outcome
            with online.closing(online._db()) as db:
                row = db.execute('SELECT ' + column + ',uuid,token,server_url FROM online_leaderboard WHERE id=1').fetchone()
            assert row == (1, 'local-fixture', local_token, 'http://127.0.0.1:8000')
            with online.closing(online._db()) as db, db:
                db.execute('UPDATE online_leaderboard SET ' + column + '=0 WHERE id=1')
        rotated = online.win32crypt.CryptProtectData(b'rotated-fixture-token', 'test', None, None, None, 0)
        with online.closing(online._db()) as db, db:
            db.execute('UPDATE online_leaderboard SET delete_pending=1,rotation_token=? WHERE id=1', (rotated,))
        assert online._sync() == 'delete_failed'
        with online.closing(online._db()) as db, db:
            assert db.execute('SELECT delete_pending,token,rotation_token FROM online_leaderboard WHERE id=1').fetchone() == (1, local_token, rotated)
            db.execute('UPDATE online_leaderboard SET delete_pending=0,rotation_token=NULL WHERE id=1')
        payload = json.dumps({'uuid':'local-fixture', 'new_token':'new-fixture-token', 'grant':'grant-fixture'}).encode('utf-8')
        protected_recovery = online.win32crypt.CryptProtectData(payload, 'test', None, None, None, 0)
        with online.closing(online._db()) as db, db:
            db.execute('UPDATE online_leaderboard SET delete_pending=1,recovery_payload=? WHERE id=1', (protected_recovery,))
        assert online._sync() == 'delete_failed'
        with online.closing(online._db()) as db, db:
            assert db.execute('SELECT delete_pending,token,recovery_payload FROM online_leaderboard WHERE id=1').fetchone() == (1, local_token, protected_recovery)
            db.execute('UPDATE online_leaderboard SET delete_pending=0,recovery_payload=NULL WHERE id=1')
        # Missing credentials do not prove that a withdrawal on the old
        # server happened, so the Store must not discard it or the outbox.
        with online.closing(online._db()) as db, db:
            db.execute('UPDATE online_leaderboard SET delete_pending=1,token=NULL WHERE id=1')
        assert online._sync() == 'delete_failed'
        with online.closing(online._db()) as db, db:
            assert db.execute('SELECT delete_pending,uuid,server_url FROM online_leaderboard WHERE id=1').fetchone() == (
                1, 'local-fixture', 'http://127.0.0.1:8000')
            db.execute('UPDATE online_leaderboard SET delete_pending=0,token=? WHERE id=1', (local_token,))
        with online.closing(online._db()) as db, db:
            db.execute('UPDATE online_leaderboard SET enabled=1,event_permission=1 WHERE id=1')
        online._sync()
        assert online._STATUS['state'] == 'server_changed'
        with online.closing(online._db()) as db:
            assert db.execute('SELECT uuid,token,server_url FROM online_leaderboard WHERE id=1').fetchone() == (
                'local-fixture', local_token, 'http://127.0.0.1:8000')
        opener.assert_not_called()
        clear_events.assert_not_called()

# The Store switch is explicit, never uses the network, and cannot race an
# active monitor or in-flight synchronization. It archives the old identity
# before requiring a fresh approval for the public server.
import threading
from types import SimpleNamespace
with tempfile.TemporaryDirectory(prefix='leaderboard-store-transition-test-') as directory:
    settings_path = str(Path(directory) / 'settings.db')
    user_path = str(Path(directory) / 'user.db')
    with online.closing(online.sqlite3.connect(user_path)) as db:
        db.execute('CREATE TABLE leaderboard_event_outbox (event_id TEXT)')
        db.execute('CREATE TABLE leaderboard_event_state (active_match TEXT, last_no_result TEXT)')
        db.commit()
    token = online.win32crypt.CryptProtectData(b'local-fixture-token', 'test', None, None, None, 0)
    tracking = SimpleNamespace(monitor_lock=threading.Lock(), run_monitor=False, fight=False)
    with patch.object(online, '_database', return_value=settings_path), \
         patch.object(online.init, 'database_user', user_path), patch.object(online, 'FROZEN', True), \
         patch.object(online, '_tracking_module', return_value=tracking), \
         patch.object(online, '_RUNNING', False), patch.object(online, '_RECOVERY_GRANT', None), \
         patch.object(online, 'build_opener') as opener:
        with online.closing(online._db()) as db, db:
            db.execute('UPDATE online_leaderboard SET enabled=1,event_permission=1,uuid=?,token=?,server_url=? WHERE id=1',
                       ('local-fixture', token, 'http://127.0.0.1:8000'))
        assert client.get('/online-leaderboard/settings').json['migration_available'] is True
        assert client.post('/online-leaderboard/migrate-server', json={}).status_code == 400
        with patch.object(online, 'FROZEN', False):
            assert client.post('/online-leaderboard/migrate-server', json={'confirm':True}).status_code == 404
        with tracking.monitor_lock:
            response = client.post('/online-leaderboard/migrate-server', json={'confirm':True})
            assert response.status_code == 409 and response.json['error'] == 'tracking_running'
        tracking.fight = True
        assert client.post('/online-leaderboard/migrate-server', json={'confirm':True}).json['error'] == 'tracking_running'
        tracking.fight = False
        tracking.run_monitor = True
        assert client.post('/online-leaderboard/migrate-server', json={'confirm':True}).json['error'] == 'tracking_running'
        tracking.run_monitor = False
        with patch.object(online, '_START_LOCK', threading.Lock()) as start_lock:
            with start_lock:
                assert client.post('/online-leaderboard/migrate-server', json={'confirm':True}).json['error'] == 'busy'
        with patch.object(online, '_RUNNING', True):
            assert client.post('/online-leaderboard/migrate-server', json={'confirm':True}).json['error'] == 'busy'
        with patch.object(online, '_RECOVERY_GRANT', 'pending-fixture'):
            assert client.post('/online-leaderboard/migrate-server', json={'confirm':True}).json['error'] == 'busy'
        with patch.object(online, '_LOCK', threading.Lock()) as lock:
            with lock:
                assert client.post('/online-leaderboard/migrate-server', json={'confirm':True}).json['error'] == 'busy'
        assert client.post('/online-leaderboard/migrate-server', json={'confirm':True}).json == {'ok':True}
        with online.closing(online._db()) as db:
            assert db.execute('SELECT server_url,uuid,token FROM online_leaderboard_archived_identities').fetchone() == (
                'http://127.0.0.1:8000', 'local-fixture', token)
            current = db.execute('SELECT enabled,uuid,token,event_permission,server_transition_nonce FROM online_leaderboard WHERE id=1').fetchone()
        assert current[:4] == (0, None, None, 0) and current[4]
        settings = client.get('/online-leaderboard/settings').json
        assert settings['migration_available'] is False and settings['transition_nonce'] == current[4]
        old_approval = {'enabled':True, 'consent':True, 'event_consent':True, 'language_consent':True}
        assert client.post('/online-leaderboard/settings', json=old_approval).status_code == 409
        transition_response = client.post('/online-leaderboard/settings', json={**old_approval, 'transition_nonce':current[4]})
        assert transition_response.status_code == 200, transition_response.json
        opener.assert_not_called()

# A previous Store participation without a completed identity is not consent
# to register on the production service. In-flight approvals from old tabs
# must fail until a new dialog has read the transition nonce.
with tempfile.TemporaryDirectory(prefix='leaderboard-store-unregistered-test-') as directory:
    settings_path = str(Path(directory) / 'settings.db')
    user_path = str(Path(directory) / 'user.db')
    with online.closing(online.sqlite3.connect(user_path)) as db:
        db.execute('CREATE TABLE leaderboard_event_outbox (event_id TEXT)')
        db.execute('CREATE TABLE leaderboard_event_state (active_match TEXT, last_no_result TEXT)')
        db.execute('INSERT INTO leaderboard_event_outbox VALUES (?)', ('orphan-event',))
        db.commit()
    tracking = SimpleNamespace(monitor_lock=threading.Lock(), run_monitor=False, fight=False)
    with patch.object(online, '_database', return_value=settings_path), patch.object(online, 'FROZEN', True), \
         patch.object(online.init, 'database_user', user_path), patch.object(online, '_tracking_module', return_value=tracking):
        with online.closing(online._db()) as db, db:
            db.execute('UPDATE online_leaderboard SET enabled=1,event_permission=1,uuid=NULL,token=NULL,server_url=NULL,server_consent_url=NULL WHERE id=1')
        with patch.object(online, '_call') as request:
            online._sync()
            assert online._STATUS['state'] == 'pending_events'
            request.assert_not_called()
        settings = client.get('/online-leaderboard/settings').json
        assert settings['server_consent_required'] is True and settings['transition_nonce'] and settings['transition_blocked'] is True
        assert settings['partial_identity'] is False
        approval = {'enabled':True, 'consent':True, 'event_consent':True, 'language_consent':True}
        assert client.post('/online-leaderboard/settings', json=approval).status_code == 409
        assert client.post('/online-leaderboard/settings', json={**approval, 'transition_nonce':'stale-fixture'}).status_code == 409
        with tracking.monitor_lock:
            blocked = client.post('/online-leaderboard/settings', json={**approval, 'transition_nonce':settings['transition_nonce']})
            assert blocked.status_code == 409 and blocked.json['error'] == 'tracking_running'
        blocked = client.post('/online-leaderboard/settings', json={**approval, 'transition_nonce':settings['transition_nonce']})
        assert blocked.status_code == 409 and blocked.json['error'] == 'pending_events'
        with online.closing(online.sqlite3.connect(user_path)) as db, db:
            assert db.execute('SELECT event_id FROM leaderboard_event_outbox').fetchall() == [('orphan-event',)]
            db.execute('DELETE FROM leaderboard_event_outbox')
            db.execute('INSERT INTO leaderboard_event_state VALUES (?,?)', ('old-match',None))
        blocked = client.post('/online-leaderboard/settings', json={**approval, 'transition_nonce':settings['transition_nonce']})
        assert blocked.status_code == 409 and blocked.json['error'] == 'active_match'
        with online.closing(online.sqlite3.connect(user_path)) as db, db:
            db.execute('UPDATE leaderboard_event_state SET active_match=NULL,last_no_result=?', ('old-match',))
        blocked = client.post('/online-leaderboard/settings', json={**approval, 'transition_nonce':settings['transition_nonce']})
        assert blocked.status_code == 409 and blocked.json['error'] == 'active_match'
        with online.closing(online.sqlite3.connect(user_path)) as db, db:
            db.execute('DELETE FROM leaderboard_event_state')
        missing_path = str(Path(directory) / 'missing-user.db')
        with patch.object(online.init, 'database_user', missing_path):
            assert client.get('/online-leaderboard/settings').json['transition_blocked'] is True
            blocked = client.post('/online-leaderboard/settings', json={**approval, 'transition_nonce':settings['transition_nonce']})
            assert blocked.status_code == 409 and blocked.json['error'] == 'invalid_data'
            assert not Path(missing_path).exists()
        # Once the check starts, neither the monitor nor another SQLite writer
        # can race an old event into the file before consent is committed.
        check_started, finish_check = threading.Event(), threading.Event()
        original_blocker = online._event_transition_blocker
        def slow_blocker(db, schema='main'):
            if schema == 'tracker_user':
                check_started.set()
                assert finish_check.wait(5)
            return original_blocker(db, schema)
        result = {}
        def approve_in_thread():
            with app.test_client() as concurrent_client:
                result['response'] = concurrent_client.post('/online-leaderboard/settings', json={**approval, 'transition_nonce':settings['transition_nonce']})
        with patch.object(online, '_event_transition_blocker', side_effect=slow_blocker):
            worker = threading.Thread(target=approve_in_thread)
            worker.start()
            assert check_started.wait(5)
            assert not tracking.monitor_lock.acquire(blocking=False)
            try:
                with online.closing(online.sqlite3.connect(user_path, timeout=.1)) as db, db:
                    db.execute('INSERT INTO leaderboard_event_outbox VALUES (?)', ('racing-event',))
                raise AssertionError('The transaction must prevent a concurrent event write')
            except online.sqlite3.OperationalError as error:
                assert 'locked' in str(error).lower()
            finally:
                finish_check.set()
            worker.join(5)
            assert not worker.is_alive()
        assert result['response'].status_code == 200, result['response'].json
        def register(method, path, data=None, token=None, root=None):
            assert (method, path, root) == ('POST', '/api/v1/installations', 'https://eldenringpvp.com')
            return {'uuid':data['uuid'], 'token':'new-fixture-token'}
        with patch.object(online, '_call', side_effect=register):
            assert online._credentials('https://eldenringpvp.com') == 'new-fixture-token'
        with online.closing(online._db()) as db:
            assert db.execute('SELECT server_url,server_consent_url,server_transition_nonce FROM online_leaderboard WHERE id=1').fetchone() == (
                'https://eldenringpvp.com', 'https://eldenringpvp.com', None)

# Previously registered production identities continue working, while a
# partial old identity is kept rather than overwritten during registration.
with tempfile.TemporaryDirectory(prefix='leaderboard-store-existing-test-') as directory:
    settings_path = str(Path(directory) / 'settings.db')
    protected = online.win32crypt.CryptProtectData(b'production-fixture-token', 'test', None, None, None, 0)
    with patch.object(online, '_database', return_value=settings_path), patch.object(online, 'FROZEN', True):
        with online.closing(online._db()) as db, db:
            db.execute('UPDATE online_leaderboard SET enabled=1,uuid=?,token=?,server_url=?,server_consent_url=NULL WHERE id=1',
                       ('production-fixture', protected, 'https://eldenringpvp.com'))
        assert online._credentials('https://eldenringpvp.com') == 'production-fixture-token'
        assert client.get('/online-leaderboard/settings').json['server_consent_required'] is False
        with online.closing(online._db()) as db, db:
            db.execute('UPDATE online_leaderboard SET uuid=?,token=NULL,server_url=? WHERE id=1',
                       ('partial-fixture', 'http://127.0.0.1:8000'))
        assert client.get('/online-leaderboard/settings').json['partial_identity'] is True
        with patch.object(online, '_call') as request:
            try:
                online._credentials('https://eldenringpvp.com')
                raise AssertionError('Partial old identity must not be overwritten')
            except RuntimeError as error:
                assert str(error) == 'server_changed'
            request.assert_not_called()
        with online.closing(online._db()) as db:
            assert db.execute('SELECT uuid,token,server_url FROM online_leaderboard WHERE id=1').fetchone() == (
                'partial-fixture', None, 'http://127.0.0.1:8000')

# Preserve the existing development behavior for an incomplete registration.
with tempfile.TemporaryDirectory(prefix='leaderboard-development-existing-test-') as directory:
    settings_path = str(Path(directory) / 'settings.db')
    user_path = str(Path(directory) / 'user.db')
    with online.closing(online.sqlite3.connect(user_path)) as db:
        db.execute('CREATE TABLE leaderboard_event_outbox (event_id TEXT)')
        db.execute('INSERT INTO leaderboard_event_outbox VALUES (?)', ('development-event',))
        db.commit()
    with patch.object(online, '_database', return_value=settings_path), patch.object(online, 'FROZEN', False), \
         patch.object(online.init, 'database_user', user_path):
        response = client.post('/online-leaderboard/settings', json={'enabled':True,'consent':True,'event_consent':True})
        assert response.status_code == 200 and response.json['transition_blocked'] is False
        with online.closing(online._db()) as db, db:
            db.execute('UPDATE online_leaderboard SET enabled=1,uuid=?,token=NULL,server_url=? WHERE id=1',
                       ('partial-fixture', 'http://127.0.0.1:8000'))
        def register_development(method, path, data=None, token=None, root=None):
            assert (method, path, root) == ('POST', '/api/v1/installations', 'http://127.0.0.1:8000')
            return {'uuid':data['uuid'], 'token':'development-fixture-token'}
        with patch.object(online, '_call', side_effect=register_development):
            assert online._credentials('http://127.0.0.1:8000') == 'development-fixture-token'

# A fresh installation records the actual production destination when the
# user accepts; a previously registered production user can explicitly log
# in again after an expired registration without losing that consent.
with tempfile.TemporaryDirectory(prefix='leaderboard-store-new-test-') as directory:
    settings_path = str(Path(directory) / 'settings.db')
    with patch.object(online, '_database', return_value=settings_path), patch.object(online, 'FROZEN', True):
        assert client.get('/online-leaderboard/settings').json['transition_nonce'] is None
        assert client.post('/online-leaderboard/settings', json={
            'enabled':True, 'consent':True, 'event_consent':True, 'language_consent':True}).status_code == 200
        with online.closing(online._db()) as db:
            assert db.execute('SELECT server_consent_url FROM online_leaderboard WHERE id=1').fetchone()[0] == 'https://eldenringpvp.com'
        protected = online.win32crypt.CryptProtectData(b'old-production-token', 'test', None, None, None, 0)
        with online.closing(online._db()) as db, db:
            # Model an installation from a build predating server_consent_url.
            db.execute('UPDATE online_leaderboard SET uuid=?,token=?,server_url=?,server_consent_url=NULL WHERE id=1',
                       ('production-fixture', protected, 'https://eldenringpvp.com'))
        login_requests = []
        def expired_registration(method, path, data=None, token=None, root=None, **kwargs):
            assert root == 'https://eldenringpvp.com'
            login_requests.append(path)
            if path == '/api/v1/steam/login' and login_requests.count(path) == 1:
                raise online.HTTPError(root + path, 401, 'expired', {}, None)
            if path == '/api/v1/installations':
                return {'uuid':data['uuid'], 'token':'replacement-fixture-token'}
            if path == '/api/v1/steam/login':
                return {'url':'https://steamcommunity.com/openid/login?state=fixture'}
            raise AssertionError(path)
        with patch.object(online, '_call', side_effect=expired_registration):
            assert client.post('/online-leaderboard/steam-login').status_code == 200
        with online.closing(online._db()) as db:
            assert db.execute('SELECT server_url,server_consent_url FROM online_leaderboard WHERE id=1').fetchone() == (
                'https://eldenringpvp.com', 'https://eldenringpvp.com')

# These tests focus on synchronization and consent; verification itself is
# covered separately with explicit mocked Steam-status responses below.
verified_steam = online._verified_steam
online._verified_steam = lambda root, token: '76561198000000000'
real_event_consent = online._ensure_event_consent
online._ensure_event_consent = lambda root, token: None
# Baseline import has its own isolated integration tests; these older tests
# exercise the surrounding synchronization and consent behavior.
online._ensure_baseline = lambda root, token: None
with patch.object(online, '_call', return_value={'ok':True}) as request_consent:
    real_event_consent('https://events.example', 'test-token')
    assert request_consent.call_args.args[:3] == ('POST', '/api/v1/events/consent', {'consent':True, 'version':'events-1'})
assert client.get('/online-leaderboard/settings').json['enabled'] is False
assert client.get('/online-leaderboard/settings').json['steam_status_observe'] is True
# Old browser tabs and in-flight requests cannot reactivate the newly switched
# server using an approval collected for the old server.
with online.closing(online._db()) as db, db:
    db.execute('UPDATE online_leaderboard SET server_transition_nonce=? WHERE id=1', ('new-server-fixture',))
assert client.get('/online-leaderboard/settings').json['transition_nonce'] == 'new-server-fixture'
old_enable = {'enabled':True, 'consent':True, 'event_consent':True, 'language_consent':True}
assert client.post('/online-leaderboard/settings', json=old_enable).status_code == 409
assert client.post('/online-leaderboard/settings', json={'enabled':False, 'remove':False}).status_code == 409
with online.closing(online._db()) as db:
    assert db.execute('SELECT enabled,server_transition_nonce FROM online_leaderboard WHERE id=1').fetchone() == (0, 'new-server-fixture')
assert client.post('/online-leaderboard/settings', json={**old_enable, 'transition_nonce':'new-server-fixture'}).status_code == 200
with online.closing(online._db()) as db, db:
    assert db.execute('SELECT enabled,server_transition_nonce FROM online_leaderboard WHERE id=1').fetchone() == (1, None)
    db.execute('UPDATE online_leaderboard SET enabled=0,event_permission=0,language_permission=0 WHERE id=1')
with online.closing(online._db()) as db, db:
    db.execute('UPDATE online_leaderboard SET enabled=1,event_permission=0 WHERE id=1')
assert client.get('/online-leaderboard/settings').json['event_consent_pending'] is True
online._sync()
assert online._STATUS['state'] == 'event_consent_required'
assert client.post('/online-leaderboard/event-consent', json={'consent':True}).status_code == 200
with online.closing(online._db()) as db, db:
    db.execute('UPDATE online_leaderboard SET enabled=0 WHERE id=1')
for endpoint in ('settings', 'language-consent', 'steam-consent'):
    assert client.post('/online-leaderboard/' + endpoint, json=['invalid']).status_code == 400
calls = []
def api(method, path, data=None, token=None, root=None):
    calls.append((method, path, data, token))
    if method == 'POST': return {'uuid':data['uuid'], 'token':'secret'}
    return None
with patch.object(online, '_call', side_effect=api), patch.object(online, '_profile', return_value={'name':'test'}), patch.object(online, '_base_url', return_value='https://test.example'):
    online._sync()
    assert not calls
    assert client.post('/online-leaderboard/settings', json={'enabled':True}).status_code == 400
    assert client.post('/online-leaderboard/settings', json={'enabled':True,'consent':True,'event_consent':True}).json['enabled']
    online._sync()
    assert [c[0] for c in calls] == ['POST', 'PUT']
    assert calls[1][3] == 'secret'
    assert client.post('/online-leaderboard/settings', json={'enabled':False,'remove':False}).json['enabled'] is False
    online._sync()
    assert calls[-1][:2] == ('DELETE', '/api/v1/steam/login')
    assert client.post('/online-leaderboard/settings', json={'enabled':True,'consent':True,'event_consent':True}).json['enabled']
    with patch.object(online, 'start_sync', return_value='syncing') as start:
        assert client.post('/online-leaderboard/settings', json={'enabled':False,'remove':True}).json['state'] == 'delete_pending'
        start.assert_called_once()
    assert client.post('/online-leaderboard/settings', json={'enabled':True,'consent':True,'event_consent':True}).status_code == 409
    with patch.object(online, '_call', side_effect=OSError('offline')):
        online._sync()
        assert online._settings()[3] and online._settings()[2]
    online._sync()
    assert calls[-1][0] == 'DELETE'
    assert online._settings()[2:4] == (None, False)
    assert online._STATUS['state'] == 'deleted'
print('online leaderboard isolated checks passed')

# A lost reply leaves the exact same event IDs queued for safe retry.
from application import leaderboard_events
with online.closing(online._db()) as db, db:
    db.execute('UPDATE online_leaderboard SET enabled=1,event_permission=1,delete_pending=0 WHERE id=1')
with online.closing(online.sqlite3.connect(online.init.database_user)) as db, db:
    leaderboard_events.record_delta(db, 'Arena', (0,0,0,1,0,0,1,0,0), online._database())
    leaderboard_events.record_delta(db, 'Arena', (1,0,0,0,0,0,0,0,0), online._database())
sent_batches = []
def event_api(method, path, data=None, token=None, root=None):
    assert (method, path) == ('POST', '/api/v1/events')
    sent_batches.append(data['events'])
    if len(sent_batches) == 1:
        raise OSError('acknowledgement lost')
    return {'accepted':[event['event_id'] for event in data['events']]}
with patch.object(online, '_call', side_effect=event_api):
    try:
        online._send_events('https://events.example', 'test-token')
        raise AssertionError('Lost response must leave events queued')
    except OSError:
        pass
    online._send_events('https://events.example', 'test-token')
    assert sent_batches[0] == sent_batches[1]
    with online.closing(online.sqlite3.connect(online.init.database_user)) as db:
        assert db.execute('SELECT COUNT(*) FROM leaderboard_event_outbox').fetchone()[0] == 0

# A server must explicitly support extra Defense victories before an ordered
# batch containing one can be sent.  An old/malformed/temporarily unavailable
# server must leave the complete local outbox untouched for a later retry.
with tempfile.TemporaryDirectory(prefix='leaderboard-defense-extra-test-') as directory:
    test_user_db = str(Path(directory) / 'user.db')
    fixture_events = [
        ('00000000-0000-4000-8000-000000000001', '10000000-0000-4000-8000-000000000001', 'start'),
        ('00000000-0000-4000-8000-000000000002', '10000000-0000-4000-8000-000000000002', 'defense_extra_victory'),
        ('00000000-0000-4000-8000-000000000003', '10000000-0000-4000-8000-000000000001', 'victory'),
    ]
    with online.closing(online.sqlite3.connect(test_user_db)) as db, db:
        leaderboard_events._schema(db)
        db.execute('CREATE TABLE leaderboard_baseline_events (event_id TEXT PRIMARY KEY)')
        for event_id, match_id, kind in fixture_events:
            db.execute('INSERT INTO leaderboard_event_outbox VALUES (?,?,?,?,?)',
                       (event_id, match_id, leaderboard_events.encrypt_value('Defense'), leaderboard_events.encrypt_value(kind),
                        leaderboard_events.encrypt_value('2026-01-02T03:04:05Z')))
            db.execute('INSERT INTO leaderboard_baseline_events VALUES (?)', (event_id,))
    with patch.object(online.init, 'database_user', test_user_db):
        for malformed in (None, [], {}, {'capabilities': None}, {'capabilities': 'defense_extra_victory'}, {'capabilities': []}):
            with patch.object(online, '_remote_steam_status', return_value=malformed), patch.object(online, '_call') as send:
                try:
                    online._send_events('https://events.example', 'test-token')
                    raise AssertionError('Unadvertised capability must not send events')
                except ValueError as error:
                    assert str(error) == 'server_update_required', (malformed, error)
                send.assert_not_called()
            with online.closing(online.sqlite3.connect(test_user_db)) as db:
                assert [row[0] for row in db.execute('SELECT event_id FROM leaderboard_event_outbox ORDER BY rowid')] == [event[0] for event in fixture_events]

        from urllib.error import HTTPError
        unavailable = HTTPError('https://events.example', 503, 'temporary', {}, None)
        with patch.object(online, '_remote_steam_status', side_effect=unavailable), patch.object(online, '_call') as send:
            try:
                online._send_events('https://events.example', 'test-token')
                raise AssertionError('A transient error must be propagated')
            except HTTPError as error:
                assert error.code == 503
            send.assert_not_called()
        with online.closing(online.sqlite3.connect(test_user_db)) as db:
            assert db.execute('SELECT COUNT(*) FROM leaderboard_event_outbox').fetchone()[0] == 3

        batches = []
        def capable_api(method, path, data=None, token=None, root=None):
            assert (method, path) == ('POST', '/api/v1/events')
            batches.append(data['events'])
            if len(batches) == 1:
                raise OSError('acknowledgement lost')
            return {'accepted':[event['event_id'] for event in data['events']]}
        with patch.object(online, '_remote_steam_status', return_value={'capabilities':['defense_extra_victory']}), \
             patch.object(online, '_call', side_effect=capable_api):
            try:
                online._send_events('https://events.example', 'test-token', baseline_only=True)
                raise AssertionError('A lost reply must preserve the outbox')
            except OSError:
                pass
            with online.closing(online.sqlite3.connect(test_user_db)) as db:
                assert db.execute('SELECT COUNT(*) FROM leaderboard_event_outbox').fetchone()[0] == 3
                assert db.execute('SELECT COUNT(*) FROM leaderboard_baseline_events').fetchone()[0] == 3
            online._send_events('https://events.example', 'test-token', baseline_only=True)
        assert batches[0] == batches[1]
        assert [event['kind'] for event in batches[0]] == ['start', 'defense_extra_victory', 'victory']
        with online.closing(online.sqlite3.connect(test_user_db)) as db:
            assert db.execute('SELECT COUNT(*) FROM leaderboard_event_outbox').fetchone()[0] == 0
            assert db.execute('SELECT COUNT(*) FROM leaderboard_baseline_events').fetchone()[0] == 0

# A lost rotation response must not cause a subsequent deletion to use an old
# invalid token and falsely conclude that the remote profile was deleted.
from urllib.error import HTTPError
rotation_calls = []
new_token = None
def rotation_api(method, path, data=None, token=None, root=None):
    global new_token
    rotation_calls.append((method, path, token))
    if path.endswith('/rotate-token'):
        if new_token is None:
            new_token = data['new_token']
            raise OSError('response lost after commit')
        if token == 'old-token':
            raise HTTPError(root + path, 401, 'unauthorized', {}, None)
        assert token == new_token
        return {'ok':True}
    if path == '/api/v1/profile' and method == 'DELETE':
        assert token == new_token
        return None
    if path in ('/api/v1/steam/login', '/api/v1/profile/steam') and method == 'DELETE':
        assert token == new_token
        return None
    raise AssertionError((method, path))
encrypted_old = online.win32crypt.CryptProtectData(b'old-token', 'test', None, None, None, 0)
with online.closing(online._db()) as db, db:
    db.execute('UPDATE online_leaderboard SET enabled=1,token=?,server_url=?,delete_pending=0,rotation_token=NULL WHERE id=1', (encrypted_old, 'https://rotation.example'))
with patch.object(online, '_call', side_effect=rotation_api):
    try:
        online._rotate_token('https://rotation.example', 'old-token')
        raise AssertionError('Lost response should be retried')
    except OSError:
        pass
    with online.closing(online._db()) as db, db:
        db.execute('UPDATE online_leaderboard SET enabled=0,delete_pending=1 WHERE id=1')
    assert online._sync() == 'deleted'
    assert rotation_calls[-1] == ('DELETE', '/api/v1/profile', new_token)
new_token = None
rotation_calls.clear()
with online.closing(online._db()) as db, db:
    db.execute('UPDATE online_leaderboard SET enabled=1,token=?,server_url=?,delete_pending=0,rotation_token=NULL WHERE id=1', (encrypted_old, 'https://rotation.example'))
with patch.object(online, '_call', side_effect=rotation_api):
    try:
        online._rotate_token('https://rotation.example', 'old-token')
        raise AssertionError('Lost response should be retried')
    except OSError:
        pass
    with online.closing(online._db()) as db, db:
        db.execute('UPDATE online_leaderboard SET enabled=0,steam_login_cancel_pending=1,steam_remove_pending=1 WHERE id=1')
    online._sync()
    assert rotation_calls[-2:] == [('DELETE', '/api/v1/steam/login', new_token), ('DELETE', '/api/v1/profile/steam', new_token)]
with online.closing(online._db()) as db, db:
    db.execute('UPDATE online_leaderboard SET token=NULL,rotation_token=NULL,server_url=NULL,uuid=NULL WHERE id=1')

# Recovery is durable if the server committed the transfer but its response
# was lost and the one-time Steam grant subsequently expired.
import json
recovery_data = {'uuid':'423e4567-e89b-42d3-a456-426614174000', 'new_token':'a'*64, 'steam_id':'76561198000000000', 'grant':'b'*64}
recovery_blob = online.win32crypt.CryptProtectData(json.dumps(recovery_data).encode(), 'test', None, None, None, 0)
old_blob = online.win32crypt.CryptProtectData(b'old-recovery-token', 'test', None, None, None, 0)
with online.closing(online._db()) as db, db:
    db.execute('UPDATE online_leaderboard SET enabled=1,uuid=NULL,token=?,server_url=?,delete_pending=0,recovery_payload=? WHERE id=1', (old_blob, 'https://recovery.example', recovery_blob))
recovery_calls = []
def expired_recovery_api(method, path, data=None, token=None, root=None, extra_headers=None):
    recovery_calls.append((method, path, token))
    if path == '/api/v1/steam/recovery':
        raise HTTPError(root + path, 401, 'expired', {}, None)
    if path == '/api/v1/steam/status' and token == recovery_data['new_token']:
        return {'connected':True, 'steam_id':recovery_data['steam_id']}
    if path == '/api/v1/profile' and method == 'DELETE':
        assert token == recovery_data['new_token']
        return None
    raise AssertionError((method, path, token))
with patch.object(online, '_call', side_effect=expired_recovery_api):
    with online.closing(online._db()) as db, db:
        db.execute('UPDATE online_leaderboard SET enabled=0,delete_pending=1 WHERE id=1')
    assert online._sync() == 'deleted'
    assert recovery_calls[-1] == ('DELETE', '/api/v1/profile', recovery_data['new_token'])

# A rejected recovery leaves the current installation usable for another try.
with online.closing(online._db()) as db, db:
    db.execute('UPDATE online_leaderboard SET enabled=1,uuid=NULL,token=?,server_url=?,delete_pending=0,recovery_payload=? WHERE id=1', (old_blob, 'https://recovery.example', recovery_blob))
with patch.object(online, '_call', side_effect=HTTPError('https://recovery.example', 409, 'conflict', {}, None)):
    try:
        online._stored_token('https://recovery.example')
        raise AssertionError('Rejected recovery must report the conflict')
    except HTTPError as error:
        assert error.code == 409
with online.closing(online._db()) as db:
    assert db.execute('SELECT recovery_payload FROM online_leaderboard WHERE id=1').fetchone()[0] is None
with online.closing(online._db()) as db, db:
    db.execute('UPDATE online_leaderboard SET enabled=0,token=NULL,server_url=NULL WHERE id=1')

# After restoring a backup on another Windows account, an explicit login can
# create a fresh installation without discarding the old protected token.
with online.closing(online._db()) as db, db:
    db.execute('UPDATE online_leaderboard SET enabled=1,uuid=?,token=?,server_url=?,delete_pending=0,rotation_token=NULL,recovery_payload=NULL,steam_remove_pending=0,language_remove_pending=0,steam_login_cancel_pending=0,previous_token=NULL WHERE id=1', ('423e4567-e89b-42d3-a456-426614174000', b'foreign-dpapi-token', 'https://restored.example'))
def restored_login_api(method, path, data=None, token=None, root=None):
    if path == '/api/v1/installations':
        return {'uuid':data['uuid'], 'token':'c'*64}
    if path == '/api/v1/steam/login':
        assert token == 'c'*64
        return {'url':'https://steamcommunity.com/openid/login?state=fixture'}
    raise AssertionError((method, path))
with patch.object(online, '_base_url', return_value='https://restored.example'), patch.object(online, '_call', side_effect=restored_login_api):
    with online.closing(online._db()) as db, db:
        db.execute('UPDATE online_leaderboard SET steam_remove_pending=1 WHERE id=1')
    assert client.post('/online-leaderboard/steam-login').status_code == 503
    with online.closing(online._db()) as db, db:
        assert db.execute('SELECT token,previous_token FROM online_leaderboard').fetchone() == (b'foreign-dpapi-token', None)
        db.execute('UPDATE online_leaderboard SET steam_remove_pending=0 WHERE id=1')
    assert client.post('/online-leaderboard/steam-login').status_code == 200
    with online.closing(online._db()) as db:
        assert db.execute('SELECT previous_token FROM online_leaderboard').fetchone()[0] == b'foreign-dpapi-token'
with online.closing(online._db()) as db, db:
    db.execute('UPDATE online_leaderboard SET enabled=0,token=NULL,server_url=NULL,uuid=NULL,previous_token=NULL WHERE id=1')

# Withdrawal during an in-flight PUT returns immediately and queues deletion.
import threading, time
started = threading.Event()
release = threading.Event()
finished = threading.Event()
sequence = []
def slow_api(method, path, data=None, token=None, root=None):
    sequence.append(method)
    if method == 'POST': return {'uuid':data['uuid'], 'token':'secret2'}
    if method == 'PUT':
        started.set()
        assert release.wait(5)
    if method == 'DELETE': finished.set()
    return None
with patch.object(online, '_call', side_effect=slow_api), patch.object(online, '_profile', return_value={'name':'test'}), patch.object(online, '_base_url', return_value='https://test.example'):
    assert client.post('/online-leaderboard/settings', json={'enabled':True,'consent':True,'event_consent':True}).status_code == 200
    online.start_sync()
    assert started.wait(5)
    before = time.monotonic()
    result = client.post('/online-leaderboard/settings', json={'enabled':False,'remove':True})
    assert time.monotonic() - before < 1
    assert result.status_code == 200
    release.set()
    assert finished.wait(5)
    for _ in range(100):
        if not online._settings()[3]: break
        time.sleep(.01)
    assert online._settings()[2:4] == (None, False)
    assert sequence == ['POST', 'PUT', 'DELETE'], sequence

# A server switch must never silently send a token to a different service.
origins = []
def origin_api(method, path, data=None, token=None, root=None):
    origins.append((method, root))
    if method == 'POST': return {'uuid':data['uuid'], 'token':'origin-secret'}
    return None
with patch.object(online, '_call', side_effect=origin_api), patch.object(online, '_profile', return_value={'name':'test'}):
    with patch.object(online, '_base_url', return_value='https://original.example'):
        client.post('/online-leaderboard/settings', json={'enabled':True,'consent':True,'event_consent':True})
        online._sync()
    with patch.object(online, '_base_url', return_value='https://other.example'):
        online._sync()
        assert online._STATUS['state'] == 'server_changed'
        with patch.object(online, 'start_sync', return_value='syncing'):
            client.post('/online-leaderboard/settings', json={'enabled':False,'remove':True})
        online._sync()
    assert origins[-1] == ('DELETE', 'https://original.example'), origins
    assert all(origin != 'https://other.example' for _, origin in origins)

# Withdrawal arriving just as a worker completes must still schedule DELETE.
completed = threading.Event()
continue_worker = threading.Event()
deleted = threading.Event()
real_sync = online._sync
calls_to_sync = 0
def delayed_completion():
    global calls_to_sync
    calls_to_sync += 1
    if calls_to_sync == 1:
        completed.set()
        assert continue_worker.wait(5)
        return None
    return real_sync()
def delayed_api(method, path, data=None, token=None, root=None):
    if method == 'POST': return {'uuid':data['uuid'], 'token':'last-secret'}
    if method == 'DELETE': deleted.set()
    return None
with patch.object(online, '_call', side_effect=delayed_api), patch.object(online, '_profile', return_value={'name':'test'}), patch.object(online, '_base_url', return_value='https://test.example'):
    client.post('/online-leaderboard/settings', json={'enabled':True,'consent':True,'event_consent':True})
    real_sync()
    with patch.object(online, '_sync', side_effect=delayed_completion):
        online.start_sync()
        assert completed.wait(5)
        client.post('/online-leaderboard/settings', json={'enabled':False,'remove':True})
        continue_worker.set()
        assert deleted.wait(5)
        for _ in range(100):
            if not online._settings()[3]: break
            time.sleep(.01)
        assert not online._settings()[3]
        for _ in range(100):
            if not online._RUNNING: break
            time.sleep(.01)
        assert not online._RUNNING

# The server enforces the cooldown across requests and does not delay removals.
with patch.object(online, '_settings', return_value=(True, None, None, False, None)), \
        patch.object(online.threading, 'Thread') as thread, \
        patch.object(online.time, 'monotonic', side_effect=[100.0, 109.9, 109.9, 110.0, 110.0]):
    online._RUNNING = False
    online._LAST_SYNC_START = None
    online._LAST_SYNC_FINISH = None
    assert online.start_sync() == 'syncing'
    online._RUNNING = False
    blocked = client.post('/online-leaderboard/sync').json
    assert blocked['state'] == 'rate_limited'
    assert 100 <= blocked['retry_after_ms'] <= 101, blocked
    assert thread.call_count == 1
    restarted = client.post('/online-leaderboard/sync').json
    assert restarted['state'] == 'syncing' and restarted['retry_after_ms'] == 10000
    assert thread.call_count == 2
with patch.object(online, '_settings', return_value=(False, None, None, True, None)), \
        patch.object(online.threading, 'Thread') as thread, \
        patch.object(online.time, 'monotonic', return_value=110.1):
    online._RUNNING = False
    assert client.post('/online-leaderboard/sync').json['state'] == 'syncing'
    assert thread.call_count == 1

# A long automatic upload must not overlap a manual upload, and its completion
# starts the same ten-second cooldown seen by the manual endpoint.
real_thread_class = threading.Thread
clock = [100.0]
upload_started = threading.Event()
finish_upload = threading.Event()
def long_automatic_upload():
    upload_started.set()
    assert finish_upload.wait(5)
    return 'success'

with patch.object(online, '_settings', return_value=(True, None, None, False, None)), \
     patch.object(online, '_steam_settings', return_value=(False, False)), \
     patch.object(online, '_language_remove_pending', return_value=False), \
     patch.object(online, '_login_cancel_pending', return_value=False), \
     patch.object(online, '_RUNNING', False), \
     patch.object(online, '_LAST_SYNC_START', None), \
     patch.object(online, '_LAST_SYNC_FINISH', None), \
     patch.object(online, '_STATUS', {'state':'syncing'}), \
     patch.object(online, '_SERVER_RETRY_UNTIL', 0.0), \
     patch.object(online, '_SCHEDULED_RETRY', None), \
     patch.object(online.time, 'monotonic', side_effect=lambda: clock[0]), \
     patch.object(online, '_sync', side_effect=long_automatic_upload) as upload, \
     patch.object(online.threading, 'Thread') as scheduled_thread:
    assert online.start_sync(rate_limit=True) == 'syncing'
    worker = real_thread_class(target=online._worker, daemon=True)
    worker.start()
    assert upload_started.wait(5)
    clock[0] = 111.0  # More than ten seconds after the start, still running.
    assert client.post('/online-leaderboard/sync').json['state'] == 'syncing'
    assert upload.call_count == 1 and scheduled_thread.call_count == 1
    finish_upload.set()
    worker.join(5)
    assert not worker.is_alive() and not online._RUNNING
    blocked = client.post('/online-leaderboard/sync').json
    assert blocked['state'] == 'rate_limited' and blocked['retry_after_ms'] == 10000, blocked
    clock[0] = 120.9
    blocked = client.post('/online-leaderboard/sync').json
    assert blocked['state'] == 'rate_limited' and 99 <= blocked['retry_after_ms'] <= 101, blocked
    clock[0] = 121.0
    assert client.post('/online-leaderboard/sync').json['state'] == 'syncing'
    assert upload.call_count == 1 and scheduled_thread.call_count == 2

# While the first snapshot waits for an ongoing fight, poll only local state.
# Stop waiting as soon as the fight ends or the user withdraws participation.
import sys
for outcome in ('fight_finished', 'withdraw', 'disable', 'event_consent'):
    tracker = SimpleNamespace(fight=True)
    state = {'enabled':True, 'pending':False, 'event_consent':True}
    sync_calls = []
    local_polls = []
    def current_settings():
        return (state['enabled'], 'fixture-id', b'fixture-token', state['pending'], 'https://example.invalid')
    def fake_sync():
        sync_calls.append((tracker.fight, state['enabled'], state['pending']))
        if len(sync_calls) == 1:
            online._STATUS['state'] = 'baseline_wait'
            return None
        if outcome == 'fight_finished':
            assert not tracker.fight
            online._STATUS['state'] = 'success'
            return 'success'
        if outcome == 'event_consent':
            assert tracker.fight and state['enabled'] and not state['event_consent']
            online._STATUS['state'] = 'event_consent_required'
            return None
        assert tracker.fight and not state['enabled']
        if outcome == 'withdraw':
            assert state['pending']
            state['pending'] = False
            online._STATUS['state'] = 'deleted'
            return 'deleted'
        assert not state['pending']
        online._STATUS['state'] = 'disabled'
        return None
    def poll_local(seconds):
        assert seconds == 2 and len(sync_calls) == 1
        local_polls.append(seconds)
        if outcome == 'fight_finished' and len(local_polls) == 3:
            tracker.fight = False
        elif outcome == 'withdraw':
            state.update(enabled=False, pending=True)
        elif outcome == 'disable':
            state['enabled'] = False
        elif outcome == 'event_consent':
            state['event_consent'] = False
    with patch.dict(sys.modules, {'application.functions':tracker}), \
         patch.object(online, '_settings', side_effect=current_settings), \
         patch.object(online, '_event_permission', side_effect=lambda: state['event_consent']), \
         patch.object(online, '_steam_settings', return_value=(False, False)), \
         patch.object(online, '_language_remove_pending', return_value=False), \
         patch.object(online, '_login_cancel_pending', return_value=False), \
         patch.object(online, '_RUNNING', True), \
         patch.object(online, '_STATUS', {'state':'syncing'}), \
         patch.object(online, '_PERIODIC_WAKE', unittest.mock.Mock()), \
         patch.object(online, '_sync', side_effect=fake_sync), \
         patch.object(online.time, 'sleep', side_effect=poll_local):
        online._worker()
        assert len(sync_calls) == 2 and not online._RUNNING, (outcome, sync_calls)
        assert len(local_polls) == (3 if outcome == 'fight_finished' else 1), outcome

# Unexpected local SQLite errors cannot strand the synchronization gate or
# discard an already requested removal, including while awaiting a fight.
for failure_stage in ('sync_start', 'baseline_wait'):
    tracker = SimpleNamespace(fight=True)
    state = {'enabled':True, 'pending':failure_stage == 'sync_start', 'fail_next_settings':False}
    calls = []
    def error_settings():
        if state['fail_next_settings']:
            state['fail_next_settings'] = False
            raise online.sqlite3.OperationalError('test database busy')
        return (state['enabled'], 'fixture-id', b'fixture-token', state['pending'], 'https://example.invalid')
    def error_sync():
        calls.append(failure_stage)
        if len(calls) == 1:
            if failure_stage == 'sync_start':
                raise online.sqlite3.OperationalError('test database busy')
            online._STATUS['state'] = 'baseline_wait'
            return None
        assert state['pending'], (failure_stage, state)
        state.update(enabled=False, pending=False)
        online._STATUS['state'] = 'deleted'
        return 'deleted'
    def fail_during_local_wait(seconds):
        assert failure_stage == 'baseline_wait' and seconds == 2
        state.update(enabled=False, pending=True, fail_next_settings=True)
    with patch.dict(sys.modules, {'application.functions':tracker}), \
         patch.object(online, '_settings', side_effect=error_settings), \
         patch.object(online, '_event_permission', return_value=True), \
         patch.object(online, '_steam_settings', return_value=(False, False)), \
         patch.object(online, '_language_remove_pending', return_value=False), \
         patch.object(online, '_login_cancel_pending', return_value=False), \
         patch.object(online, '_RUNNING', True), \
         patch.object(online, '_STATUS', {'state':'syncing'}), \
         patch.object(online, '_LAST_SYNC_START', None), \
         patch.object(online, '_LAST_SYNC_FINISH', None), \
         patch.object(online, '_SERVER_RETRY_UNTIL', 0.0), \
         patch.object(online, '_SCHEDULED_RETRY', None), \
         patch.object(online, '_PERIODIC_WAKE', unittest.mock.Mock()), \
         patch.object(online, '_sync', side_effect=error_sync), \
         patch.object(online.time, 'sleep', side_effect=fail_during_local_wait), \
         patch.object(online.threading, 'Thread') as worker_thread, \
         patch.object(online.threading, 'Timer') as local_timer, \
         patch.object(online.app.logger, 'exception'):
        online._worker()
        assert not online._RUNNING, failure_stage
        assert state['pending'] and len(calls) == 1, (failure_stage, state, calls)
        assert local_timer.call_args.args[0] == 60, local_timer.call_args
        assert online._SCHEDULED_RETRY is local_timer.return_value
        local_timer.return_value.start.assert_called_once()
        callback = local_timer.call_args.args[1]
        arguments = local_timer.call_args.kwargs['args']
        callback(*arguments)
        worker_thread.assert_called_once()
        assert online._RUNNING, failure_stage
        online._worker()
        assert not online._RUNNING and not state['pending'] and len(calls) == 2
        assert online._STATUS['state'] == 'deleted'
        callback(*arguments)
        worker_thread.assert_called_once()

# An automatic worker starts only once and waits ten minutes after the latest
# completed sync, even if a manual sync completes just before the first deadline.
class EndPeriodicTest(Exception):
    pass

clock = [0.0]
waits = []
class SimulatedWake:
    def wait(self, delay):
        waits.append(delay)
        if len(waits) == 1:
            assert delay == 600
            clock[0] = 500
            online._LAST_SYNC_FINISH = clock[0]
            return True
        if len(waits) == 2:
            assert delay == 600, waits
            clock[0] = 1100
            return False
        assert len(waits) == 3 and delay == 600, waits
        raise EndPeriodicTest()
    def clear(self):
        pass

with patch.object(online, '_settings', return_value=(True, None, None, False, None)), \
     patch.object(online, '_steam_settings', return_value=(False, False)), \
     patch.object(online, '_language_remove_pending', return_value=False), \
     patch.object(online, '_login_cancel_pending', return_value=False), \
     patch.object(online, '_RUNNING', False), \
     patch.object(online, '_LAST_SYNC_START', None), \
     patch.object(online, '_LAST_SYNC_FINISH', None), \
     patch.object(online, '_SERVER_RETRY_UNTIL', 0.0), \
     patch.object(online, '_SCHEDULED_RETRY', None), \
     patch.object(online, '_PERIODIC_WAKE', SimulatedWake()), \
     patch.object(online.time, 'monotonic', side_effect=lambda: clock[0]), \
     patch.object(online.threading, 'Thread') as scheduled_thread:
    try:
        online._periodic_worker()
        raise AssertionError('Simulated periodic worker should have stopped')
    except EndPeriodicTest:
        pass
    assert waits == [600, 600, 600], waits
    assert scheduled_thread.call_count == 1
    assert online._LAST_SYNC_START == 1100

# A transient local failure must not permanently kill the scheduler or spin.
clock = [0.0]
waits = []
class FailureWake:
    def wait(self, delay):
        waits.append(delay)
        if len(waits) == 1:
            clock[0] = 600
            return False
        if len(waits) == 2:
            clock[0] = 660
            return False
        raise EndPeriodicTest()
    def clear(self):
        pass

with patch.object(online, '_LAST_SYNC_FINISH', None), \
     patch.object(online, '_PERIODIC_WAKE', FailureWake()), \
     patch.object(online.time, 'monotonic', side_effect=lambda: clock[0]), \
     patch.object(online, '_periodic_tick', side_effect=[RuntimeError('local failure'), 'syncing']) as tick, \
     patch.object(online.app.logger, 'exception') as log:
    try:
        online._periodic_worker()
        raise AssertionError('Simulated periodic worker should have stopped')
    except EndPeriodicTest:
        pass
    assert waits == [600, 60, 600], waits
    assert tick.call_count == 2
    log.assert_called_once()

with patch.object(online, '_PERIODIC_STARTED', False), \
     patch.object(online.threading, 'Thread') as thread:
    online.start_periodic_sync()
    online.start_periodic_sync()
    thread.assert_called_once_with(target=online._periodic_worker, name='leaderboard-periodic-sync', daemon=True)
    thread.return_value.start.assert_called_once()

# A scheduled automatic upload must honor disabled consent, the server's
# Retry-After, and an existing scheduled retry without cancelling its backoff.
with patch.object(online, '_settings', return_value=(False, None, None, False, None)) as settings, \
     patch.object(online, '_steam_settings', return_value=(False, False)), \
     patch.object(online, '_language_remove_pending', return_value=False), \
     patch.object(online, '_login_cancel_pending', return_value=False), \
     patch.object(online, '_RUNNING', False), \
     patch.object(online, '_LAST_SYNC_START', None), \
     patch.object(online, '_LAST_SYNC_FINISH', None), \
     patch.object(online, '_SERVER_RETRY_UNTIL', 700.0), \
     patch.object(online, '_SCHEDULED_RETRY', unittest.mock.Mock()) as pending_retry, \
     patch.object(online.time, 'monotonic', return_value=600.0), \
     patch.object(online.threading, 'Thread') as thread:
    assert online._periodic_tick() == 'disabled'
    settings.return_value = (True, None, None, False, None)
    assert online._periodic_tick() == 'rate_limited'
    assert online.sync_cooldown_remaining_ms() == 100000
    online._SERVER_RETRY_UNTIL = 0.0
    assert online._periodic_tick() == 'retry_scheduled'
    assert online._SCHEDULED_RETRY is pending_retry
    pending_retry.cancel.assert_not_called()
    thread.assert_not_called()

# Existing participants explicitly choose whether their game language is public.
language_calls = []
def language_api(method, path, data=None, token=None, root=None):
    if method == 'POST': return {'uuid': data['uuid'], 'token': 'language-secret'}
    if method == 'PUT': language_calls.append(dict(data))
    return None
with patch.object(online, '_call', side_effect=language_api), \
        patch.object(online, '_profile', side_effect=lambda: {'name': 'test', 'language': 'fra'}), \
        patch.object(online, '_base_url', return_value='https://language.example'), \
        patch.object(online, 'start_sync', return_value='syncing'):
    with online.closing(online._db()) as db, db:
        db.execute('UPDATE online_leaderboard SET enabled=0,uuid=NULL,token=NULL,server_url=NULL,delete_pending=0,language_permission=0 WHERE id=1')
    assert client.post('/online-leaderboard/settings', json={'enabled':True,'consent':True,'event_consent':True}).status_code == 200
    assert client.get('/online-leaderboard/settings').json['language_consent_pending'] is True
    online._sync()
    assert language_calls[-1]['language'] is None
    assert client.post('/online-leaderboard/language-consent', json={'consent':False}).status_code == 200
    assert client.get('/online-leaderboard/settings').json['language_consent_pending'] is False
    online._sync()
    assert language_calls[-1]['language'] is None
    assert client.post('/online-leaderboard/language-consent', json={'consent':True}).status_code == 200
    assert client.get('/online-leaderboard/settings').json['language_shared'] is True
    online._sync()
    assert language_calls[-1]['language'] == 'fra'
    assert client.post('/online-leaderboard/language-consent', json={'consent':'yes'}).status_code == 400
    client.post('/online-leaderboard/settings', json={'enabled':False,'remove':False})
    assert client.post('/online-leaderboard/language-consent', json={'consent':True}).status_code == 409

profile = ['0'] * 20
profile[1], profile[5], profile[6], profile[19] = 'Test', 'spaar', '', '150'
with patch.object(online.init, 'load_user', return_value=[profile]), patch.object(online.mode_stats, 'mode_user', return_value=profile):
    with patch.object(online, 'STORE_BUILD', False):
        assert online._profile()['name'] == 'Test (dev)'
        assert online._profile()['language'] == 'spaar'
        assert profile[1] == 'Test'
        profile[1] = 'Test (dev)'
        assert online._profile()['name'] == 'Test (dev)'
        profile[1] = '가' * 80
        assert online._profile()['name'] == '가' * 74 + ' (dev)'
        assert profile[1] == '가' * 80
        with patch.object(online, 'FROZEN', True):
            assert online._profile()['name'] == '가' * 74 + ' (dev)'
    profile[1] = 'Test'
    with patch.object(online, 'STORE_BUILD', True):
        assert online._profile()['name'] == 'Test'
        profile[1] = '가' * 80
        assert online._profile()['name'] == '가' * 80
    profile[5] = '../fr'
    with patch.object(online.game_language, 'selected', return_value='deude'):
        assert online._profile()['language'] == 'deu'
    with patch.object(online.game_language, 'selected', return_value='unknown'):
        assert online._profile()['language'] is None

# A language decision during an in-flight upload causes a second upload.
upload_started = threading.Event()
finish_upload = threading.Event()
second_upload = threading.Event()
upload_languages = []
def concurrent_language_api(method, path, data=None, token=None, root=None):
    if method == 'POST': return {'uuid':data['uuid'], 'token':'race-secret'}
    if method == 'PUT':
        upload_languages.append(data.get('language'))
        if len(upload_languages) == 1:
            upload_started.set()
            assert finish_upload.wait(5)
        else:
            second_upload.set()
    return None
with patch.object(online, '_call', side_effect=concurrent_language_api), \
        patch.object(online, '_profile', side_effect=lambda: {'name':'test','language':'fra'}), \
        patch.object(online, '_base_url', return_value='https://race.example'):
    with online.closing(online._db()) as db, db:
        db.execute('UPDATE online_leaderboard SET enabled=1,uuid=NULL,token=NULL,server_url=NULL,delete_pending=0,language_permission=0 WHERE id=1')
    online._RUNNING = False
    online._LANGUAGE_SYNC_REQUIRED = False
    assert online.start_sync() == 'syncing'
    assert upload_started.wait(5)
    assert client.post('/online-leaderboard/language-consent', json={'consent':True}).status_code == 200
    finish_upload.set()
    assert second_upload.wait(5)
    assert upload_languages == [None, 'fra'], upload_languages
    for _ in range(100):
        if not online._RUNNING: break
        time.sleep(.01)
    assert not online._RUNNING

# Steam sharing is opt-in and withdrawal is retryable even without participation.
steam_calls = []
def steam_api(method, path, data=None, token=None, root=None):
    steam_calls.append((method, path, dict(data) if data else None))
    if method == 'POST': return {'uuid': data['uuid'], 'token': 'steam-secret'}
    return None
with patch.object(online, '_call', side_effect=steam_api), \
        patch.object(online, '_profile', side_effect=lambda: {'name':'test', 'language':'fra'}), \
        patch.object(online, '_base_url', return_value='https://steam-test.example'), \
        patch.object(online, 'start_sync', return_value='syncing') as start, \
        patch.object(online, '_active_steam_id', return_value='76561198000000000'):
    with online.closing(online._db()) as db, db:
        db.execute('UPDATE online_leaderboard SET enabled=1,uuid=NULL,token=NULL,server_url=NULL,delete_pending=0,steam_permission=0,steam_remove_pending=0 WHERE id=1')
    online._sync()
    assert steam_calls[-1][2]['steam_id'] is None
    start.reset_mock()
    before = len(steam_calls)
    assert client.post('/online-leaderboard/steam-consent', json={'consent':True}).status_code == 200
    assert client.post('/online-leaderboard/steam-consent', json={'consent':False}).status_code == 200
    assert client.post('/online-leaderboard/steam-consent', json={'consent':True}).status_code == 200
    assert len(steam_calls) == before and not start.called
    assert online._steam_settings() == (True, False)
    online._sync()
    assert steam_calls[-1][2]['steam_id'] == '76561198000000000'
    with patch.object(online, '_active_steam_id', return_value=None):
        online._sync()
        assert steam_calls[-1][2]['steam_id'] == '76561198000000000'
    client.post('/online-leaderboard/settings', json={'enabled':False, 'remove':False})
    online._sync()
    assert client.post('/online-leaderboard/steam-consent', json={'consent':False}).status_code == 200
    with patch.object(online, '_call', side_effect=OSError('offline')):
        assert online._sync() == 'steam_delete_failed'
        assert online._steam_settings() == (False, True)
    online._sync()
    assert steam_calls[-1][:2] == ('DELETE', '/api/v1/profile/steam')
    assert online._steam_settings() == (False, False)
    assert client.post('/online-leaderboard/steam-consent', json={'consent':True}).status_code == 409
    client.post('/online-leaderboard/settings', json={'enabled':True, 'consent':True, 'event_consent':True})
    with patch.object(online, '_verified_steam', return_value=None):
        assert client.post('/online-leaderboard/steam-consent', json={'consent':True}).status_code == 200
        online._sync()
        assert online._STATUS['state'] == 'steam_login_required'

# Withdrawal during a Steam ID upload waits for the next synchronization.
steam_started = threading.Event()
steam_release = threading.Event()
steam_deleted = threading.Event()
steam_sequence = []
def racing_steam_api(method, path, data=None, token=None, root=None):
    steam_sequence.append((method, path))
    if method == 'POST': return {'uuid': data['uuid'], 'token':'race-steam-secret'}
    if method == 'PUT' and data.get('steam_id'):
        steam_started.set()
        assert steam_release.wait(5)
    if method == 'DELETE' and path == '/api/v1/profile/steam': steam_deleted.set()
    return None
with patch.object(online, '_call', side_effect=racing_steam_api), \
        patch.object(online, '_profile', side_effect=lambda: {'name':'test','language':'fra'}), \
        patch.object(online, '_base_url', return_value='https://steam-race.example'), \
        patch.object(online, '_active_steam_id', return_value='76561198000000000'):
    with online.closing(online._db()) as db, db:
        db.execute('UPDATE online_leaderboard SET enabled=1,uuid=NULL,token=NULL,server_url=NULL,delete_pending=0,steam_permission=1,steam_remove_pending=0 WHERE id=1')
    online._RUNNING = False
    online.start_sync()
    assert steam_started.wait(5)
    assert client.post('/online-leaderboard/steam-consent', json={'consent':False}).status_code == 200
    steam_release.set()
    for _ in range(100):
        if not online._RUNNING: break
        time.sleep(.01)
    assert not steam_deleted.is_set() and online._steam_settings() == (False, True)
    online._sync()
    assert steam_deleted.is_set(), steam_sequence
    assert online._steam_settings() == (False, False)
    assert steam_sequence.index(('PUT', '/api/v1/profile')) < steam_sequence.index(('DELETE', '/api/v1/profile/steam'))

# A missing original server must not send a saved credential to the current
# configuration when retrying a deletion.
with online.closing(online._db()) as db, db:
    encrypted = online.win32crypt.CryptProtectData(b'private-token', 'test', None, None, None, 0)
    db.execute('UPDATE online_leaderboard SET enabled=0, token=?, server_url=NULL, delete_pending=1 WHERE id=1', (encrypted,))
with patch.object(online, '_call') as call, patch.object(online, '_base_url', return_value='https://other.example'):
    assert online._sync() == 'delete_failed'
    call.assert_not_called()
    assert online._settings()[3] is True

with patch.object(online, '_call', return_value={'connected': True, 'steam_id': '76561198000000000'}):
    assert verified_steam('https://test.example', 'test-token') == '76561198000000000'
with patch.object(online, '_call', return_value={'connected': False}):
    assert verified_steam('https://test.example', 'test-token') is None
with patch.object(online, '_call', return_value={'connected': True, 'steam_id': 'invalid'}):
    try:
        verified_steam('https://test.example', 'test-token')
        raise AssertionError('invalid Steam ID accepted')
    except ValueError:
        pass

# Consent alone must never publish a profile until Steam has been verified.
with online.closing(online._db()) as db, db:
    db.execute('UPDATE online_leaderboard SET enabled=1, token=NULL, uuid=NULL, server_url=NULL, delete_pending=0, steam_permission=0, steam_remove_pending=0 WHERE id=1')
unverified_calls = []
def unverified_api(method, path, data=None, token=None, root=None):
    unverified_calls.append((method, path))
    if path == '/api/v1/installations':
        return {'uuid': data['uuid'], 'token': 'test-token'}
    if path == '/api/v1/steam/status':
        return {'connected': False}
    raise AssertionError('unexpected call')
with patch.object(online, '_verified_steam', side_effect=verified_steam), patch.object(online, '_call', side_effect=unverified_api), patch.object(online, '_base_url', return_value='https://test.example'):
    online._sync()
    assert online._STATUS['state'] == 'steam_login_required'
    assert unverified_calls == [('POST', '/api/v1/installations'), ('GET', '/api/v1/steam/status')]

# A rejected upload must not lose a language withdrawal; it is retried even
# if participation is then disabled while published data is retained.
with patch.object(online, 'start_sync', return_value='syncing'):
    assert client.post('/online-leaderboard/language-consent', json={'consent':False}).status_code == 200
    assert client.post('/online-leaderboard/settings', json={'enabled':False, 'remove':False}).status_code == 200
def cancel_then_offline(method, path, **kwargs):
    if path == '/api/v1/steam/login':
        return None
    raise OSError('offline')
with patch.object(online, '_call', side_effect=cancel_then_offline):
    assert online._sync() == 'language_delete_failed'
    assert online._language_remove_pending()
with patch.object(online, '_call', return_value=None) as remote:
    online._sync()
    assert remote.call_args.args[:2] == ('DELETE', '/api/v1/profile/language')
    assert not online._language_remove_pending()

# Disabling while the login link is being issued cancels it instead of
# returning a usable link after the user has withdrawn participation.
login_started, login_release = threading.Event(), threading.Event()
login_calls, login_result = [], []
def delayed_login_api(method, path, data=None, token=None, root=None):
    login_calls.append((method, path))
    if path == '/api/v1/installations':
        return {'uuid': data['uuid'], 'token': 'test-token'}
    if method == 'POST' and path == '/api/v1/steam/login':
        login_started.set()
        assert login_release.wait(5)
        return {'url':'https://steamcommunity.com/openid/login?test=1'}
    if method == 'DELETE' and path == '/api/v1/steam/login':
        return None
    raise AssertionError((method, path))
with online.closing(online._db()) as db, db:
    db.execute('UPDATE online_leaderboard SET enabled=1,token=NULL,uuid=NULL,server_url=NULL,delete_pending=0,steam_login_cancel_pending=0 WHERE id=1')
with patch.object(online, '_call', side_effect=delayed_login_api), patch.object(online, '_base_url', return_value='https://test.example'), patch.object(online, 'start_sync', return_value='syncing'):
    def request_login():
        login_result.append(app.test_client().post('/online-leaderboard/steam-login').status_code)
    thread = threading.Thread(target=request_login)
    thread.start()
    assert login_started.wait(5)
    assert client.post('/online-leaderboard/settings', json={'enabled':False,'remove':False}).status_code == 200
    login_release.set()
    thread.join(5)
    assert login_result == [409]
    assert online._login_cancel_pending()
    online._sync()
    assert not online._login_cancel_pending()
    assert login_calls[-1] == ('DELETE', '/api/v1/steam/login')

# Concurrent first requests must not race while adding the settings columns.
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import os
fresh_database = str(Path(os.environ['APPDATA']) / 'concurrent-settings.db')
def initialize_schema(_):
    with online.closing(online._db()) as db:
        return db.execute('SELECT steam_login_cancel_pending FROM online_leaderboard').fetchone()[0]
with patch.object(online, '_database', return_value=fresh_database):
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert list(pool.map(initialize_schema, range(16))) == [0] * 16

# Reading the connection indicator must not repeatedly upload the profile.
with patch.object(online, '_base_url', return_value='https://test.example'), \
        patch.object(online, '_credentials', return_value='test-token'), \
        patch.object(online, '_remote_steam_status', return_value={'connected':True, 'steam_id':'76561198000000000'}), \
        patch.object(online, 'start_sync', return_value='syncing') as start:
    observed = client.get('/online-leaderboard/steam-status?observe=1').get_json()
    assert observed == {'connected':True, 'confirmation_pending':False, 'observation_only':True}
    start.assert_not_called()
    assert client.get('/online-leaderboard/steam-status').get_json() == {'connected':True, 'confirmation_pending':False, 'observation_only':False}
    start.assert_called_once()

# The game language is sent to the login page only when sharing was accepted.
login_url = {'url':'https://steamcommunity.com/openid/login?openid.return_to=fixture'}
with patch.object(online, '_base_url', return_value='https://test.example'), \
        patch.object(online, '_credentials', return_value='test-token'), \
        patch.object(online, '_settings', return_value=(True, None, None, False, None)), \
        patch.object(online, '_login_cancel_pending', return_value=False), \
        patch.object(online.init, 'get_selected_language', return_value='fra'), \
        patch.object(online, '_call', return_value=login_url) as remote:
    with patch.object(online, '_language_permission', return_value=-1):
        assert client.post('/online-leaderboard/steam-login').status_code == 200
        assert remote.call_args.args[2]['language'] == 'browser'
        assert len(remote.call_args.args[2]['proof_challenge']) == 64
    with patch.object(online, '_language_permission', return_value=1):
        assert client.post('/online-leaderboard/steam-login').status_code == 200
        assert remote.call_args.args[2]['language'] == 'fra'
        assert len(remote.call_args.args[2]['proof_challenge']) == 64

# Proof-based confirmation never exposes its secret to the browser and falls
# back to the existing code flow when the server does not advertise support.
with patch.object(online, '_base_url', return_value='https://test.example'), \
     patch.object(online, '_credentials', return_value='token-fixture'), \
     patch.object(online, '_settings', return_value=(True, None, None, False, None)), \
     patch.object(online, '_login_cancel_pending', return_value=False), \
     patch.object(online, '_language_permission', return_value=1), \
     patch.object(online.init, 'get_selected_language', return_value='eng'), \
     patch.object(online, '_rotate_token') as rotate:
    sent = []
    def remote_auto(method, path, data=None, token=None, root=None, **kwargs):
        sent.append((path, data))
        if path == '/api/v1/steam/login':
            return {'url':'https://steamcommunity.com/openid/login?state=fixture', 'confirmation_method':'proof'}
        if path == '/api/v1/steam/confirm':
            assert online.hashlib.sha256(data['proof'].encode('ascii')).hexdigest() == sent[0][1]['proof_challenge']
            return {'connected':True, 'recovery_grant':'a'*64}
        raise AssertionError(path)
    with patch.object(online, '_call', side_effect=remote_auto):
        response = client.post('/online-leaderboard/steam-login').get_json()
        assert response['automatic'] is True and 'proof' not in str(response)
        assert client.post('/online-leaderboard/steam-auto-confirm').get_json()['connected'] is True
        assert client.post('/online-leaderboard/steam-auto-confirm').status_code == 409
        rotate.assert_called_once()
    with patch.object(online, '_call', return_value={'url':'https://steamcommunity.com/openid/login?state=fixture'}):
        assert client.post('/online-leaderboard/steam-login').get_json()['automatic'] is False
        assert client.post('/online-leaderboard/steam-auto-confirm').status_code == 409

# Diagnostic logs must include only a category and status, not exception URLs,
# tokens, installation IDs, or other potentially sensitive exception text.
with tempfile.TemporaryDirectory(prefix='steam-diagnostic-test-') as directory, \
     patch.object(online, 'data_dir', return_value=Path(directory)):
    online._STEAM_FAILURES.clear()
    with app.app_context():
        response, status = online._steam_failure('login', online.HTTPError('https://secret.example/token-secret', 502, 'secret-body', {}, None))
    assert status == 503 and response.get_json()['reason'] == 'http' and response.get_json()['http_status'] == 502
    log = (Path(directory) / 'tracker-errors.log').read_text(encoding='utf-8')
    assert 'stage=login' in log and 'http_status=502' in log and 'secret' not in log and 'https://' not in log
    assert response.get_json()['diagnostic'] == log.rstrip('\n')
    with app.app_context():
        repeated, repeated_status = online._steam_failure('login', online.HTTPError('https://other-secret.example', 502, 'private', {}, None))
    assert repeated_status == 503 and repeated.get_json()['diagnostic'] == log.rstrip('\n')
    assert (Path(directory) / 'tracker-errors.log').read_text(encoding='utf-8') == log

# Only a server-generated UUID is admitted to the shareable diagnostic.
with tempfile.TemporaryDirectory(prefix='steam-request-id-test-') as directory, \
     patch.object(online, 'data_dir', return_value=Path(directory)):
    online._STEAM_FAILURES.clear()
    request_id = '123e4567-e89b-42d3-a456-426614174000'
    with app.app_context():
        response, status = online._steam_failure('credentials', online.HTTPError('https://secret.example', 403, 'private', {'X-Request-ID': request_id}, None))
    assert status == 503 and 'request_id=' + request_id in response.get_json()['diagnostic']
    assert 'secret' not in response.get_json()['diagnostic']
    with app.app_context():
        response, status = online._steam_failure('credentials', online.HTTPError('https://secret.example', 403, 'private', {'X-Request-ID': '<script>secret</script>'}, None))
    assert 'secret' not in response.get_json()['diagnostic'] and 'request_id=' not in response.get_json()['diagnostic']

# A safe transient failure schedules a bounded retry and honours server cooldown.
with patch.object(online, '_sync', return_value=('retry_transient', 120, 'fixture-id', b'fixture-token')), \
     patch.object(online, '_settings', return_value=(True, 'fixture-id', b'fixture-token', False, 'https://example.invalid')), \
     patch.object(online, '_login_cancel_pending', return_value=False), \
     patch.object(online, '_language_remove_pending', return_value=False), \
     patch.object(online, '_steam_settings', return_value=(False, False)), \
     patch.object(online, '_RUNNING', True), patch.object(online, '_SCHEDULED_RETRY', None), \
     patch.object(online, '_RETRY_ATTEMPT', 0), patch.object(online, '_RETRY_GENERATION', 0), \
     patch.object(online, '_SERVER_RETRY_UNTIL', 0.0), \
     patch.object(online.time, 'monotonic', return_value=100), \
     patch.object(online.random, 'uniform', return_value=1.0), \
     patch.object(online.threading, 'Timer') as timer:
    online._worker()
    assert timer.call_args.args[0] >= 120
    assert online.sync_cooldown_remaining_ms() >= 120000
    assert online.start_sync(rate_limit=True) == 'rate_limited'
    with patch.object(online, '_start_sync_locked', return_value='syncing') as start:
        online._retry_scheduled('fixture-id', b'wrong-token', online._RETRY_GENERATION)
        start.assert_not_called()
        online._retry_scheduled('fixture-id', b'fixture-token', online._RETRY_GENERATION - 1)
        start.assert_not_called()
        online._retry_scheduled('fixture-id', b'fixture-token', online._RETRY_GENERATION)
        start.assert_called_once_with(rate_limit=True)

# A scheduled retry that arrives during the shared cooldown is rearmed for
# exactly the remaining local or server delay, then starts just one worker.
for server_until, expected_delay in ((0.0, 9.0), (130.0, 29.0)):
    clock = [101.0]
    fixture_timer = unittest.mock.Mock()
    with patch.object(online, '_settings', return_value=(True, 'fixture-id', b'fixture-token', False, 'https://example.invalid')), \
         patch.object(online, '_steam_settings', return_value=(False, False)), \
         patch.object(online, '_language_remove_pending', return_value=False), \
         patch.object(online, '_login_cancel_pending', return_value=False), \
         patch.object(online, '_RUNNING', False), \
         patch.object(online, '_STATUS', {'state':'success'}), \
         patch.object(online, '_LAST_SYNC_START', 99.0), \
         patch.object(online, '_LAST_SYNC_FINISH', 100.0), \
         patch.object(online, '_SERVER_RETRY_UNTIL', server_until), \
         patch.object(online, '_SCHEDULED_RETRY', fixture_timer), \
         patch.object(online, '_RETRY_GENERATION', 5), \
         patch.object(online.time, 'monotonic', side_effect=lambda: clock[0]), \
         patch.object(online.threading, 'Timer') as timer, \
         patch.object(online.threading, 'Thread') as worker_thread:
        online._retry_scheduled('fixture-id', b'fixture-token', 5)
        worker_thread.assert_not_called()
        assert timer.call_args.args[0] == expected_delay, timer.call_args
        assert online._SCHEDULED_RETRY is timer.return_value
        timer.return_value.start.assert_called_once()
        callback = timer.call_args.args[1]
        arguments = timer.call_args.kwargs['args']
        clock[0] += expected_delay
        callback(*arguments)
        worker_thread.assert_called_once()
        assert online._RUNNING and online._SCHEDULED_RETRY is None

# A local failure to create a worker must restore the gate and preserve an
# existing scheduled retry, so an outbox cannot be stranded indefinitely.
fixture_timer = unittest.mock.Mock()
with patch.object(online, '_settings', return_value=(True, 'fixture-id', b'fixture-token', False, 'https://example.invalid')), \
     patch.object(online, '_steam_settings', return_value=(False, False)), \
     patch.object(online, '_language_remove_pending', return_value=False), \
     patch.object(online, '_login_cancel_pending', return_value=False), \
     patch.object(online, '_RUNNING', False), \
     patch.object(online, '_STATUS', {'state':'success'}), \
     patch.object(online, '_LAST_SYNC_START', 90.0), \
     patch.object(online, '_LAST_SYNC_FINISH', 95.0), \
     patch.object(online, '_SERVER_RETRY_UNTIL', 0.0), \
     patch.object(online, '_SCHEDULED_RETRY', fixture_timer), \
     patch.object(online, '_RETRY_GENERATION', 10), \
     patch.object(online.time, 'monotonic', return_value=120.0), \
     patch.object(online.threading, 'Thread') as worker_thread:
    worker_thread.return_value.start.side_effect = RuntimeError('thread unavailable')
    try:
        online.start_sync(rate_limit=True)
        raise AssertionError('Worker start unexpectedly succeeded')
    except RuntimeError as error:
        assert str(error) == 'thread unavailable'
    assert not online._RUNNING and online._LAST_SYNC_START == 90.0
    assert online._STATUS['state'] == 'success'
    assert online._SCHEDULED_RETRY is fixture_timer and online._RETRY_GENERATION == 10
    fixture_timer.cancel.assert_not_called()

# A locally recovered worker also honors the server cooldown, and a stale
# callback cannot cause a second upload once that retry has been consumed.
clock = [110.0]
with patch.object(online, '_settings', return_value=(True, 'fixture-id', b'fixture-token', False, 'https://example.invalid')), \
     patch.object(online, '_steam_settings', return_value=(False, False)), \
     patch.object(online, '_language_remove_pending', return_value=False), \
     patch.object(online, '_login_cancel_pending', return_value=False), \
     patch.object(online, '_RUNNING', False), \
     patch.object(online, '_STATUS', {'state':'offline'}), \
     patch.object(online, '_LAST_SYNC_START', 90.0), \
     patch.object(online, '_LAST_SYNC_FINISH', 100.0), \
     patch.object(online, '_SERVER_RETRY_UNTIL', 130.0), \
     patch.object(online, '_SCHEDULED_RETRY', unittest.mock.Mock()), \
     patch.object(online, '_RETRY_GENERATION', 5), \
     patch.object(online.time, 'monotonic', side_effect=lambda: clock[0]), \
     patch.object(online.threading, 'Timer') as local_timer, \
     patch.object(online.threading, 'Thread') as worker_thread:
    online._retry_after_local_failure(4)
    local_timer.assert_not_called()
    online._retry_after_local_failure(5)
    assert local_timer.call_args.args[0] == 20.0
    worker_thread.assert_not_called()
    callback = local_timer.call_args.args[1]
    arguments = local_timer.call_args.kwargs['args']
    clock[0] = 130.0
    callback(*arguments)
    worker_thread.assert_called_once()
    callback(*arguments)
    worker_thread.assert_called_once()

# A callback from a timer invalidated by a manual sync is harmless even if it
# reaches the synchronization gate after that manual worker has already ended.
fixture_timer = unittest.mock.Mock()
clock = [100.0]
with patch.object(online, '_settings', return_value=(True, 'fixture-id', b'fixture-token', False, 'https://example.invalid')), \
     patch.object(online, '_steam_settings', return_value=(False, False)), \
     patch.object(online, '_language_remove_pending', return_value=False), \
     patch.object(online, '_login_cancel_pending', return_value=False), \
     patch.object(online, '_RUNNING', False), \
     patch.object(online, '_STATUS', {'state':'idle'}), \
     patch.object(online, '_LAST_SYNC_START', None), \
     patch.object(online, '_LAST_SYNC_FINISH', None), \
     patch.object(online, '_SERVER_RETRY_UNTIL', 0.0), \
     patch.object(online, '_SCHEDULED_RETRY', fixture_timer), \
     patch.object(online, '_RETRY_GENERATION', 10), \
     patch.object(online, '_PERIODIC_WAKE', unittest.mock.Mock()), \
     patch.object(online, '_sync', return_value='success') as upload, \
     patch.object(online.time, 'monotonic', side_effect=lambda: clock[0]), \
     patch.object(online.threading, 'Timer') as timer, \
     patch.object(online.threading, 'Thread') as worker_thread:
    assert client.post('/online-leaderboard/sync').json['state'] == 'syncing'
    fixture_timer.cancel.assert_called_once()
    assert online._RETRY_GENERATION != 10
    clock[0] = 112.0
    online._worker()
    assert not online._RUNNING and online._LAST_SYNC_FINISH == 112.0
    online._retry_scheduled('fixture-id', b'fixture-token', 10)
    assert worker_thread.call_count == 1 and upload.call_count == 1
    timer.assert_not_called()
    blocked = client.post('/online-leaderboard/sync').json
    assert blocked['state'] == 'rate_limited' and blocked['retry_after_ms'] == 10000

# A retry paused while checking its identity keeps the same gate locked. A
# simultaneous manual request cannot start and finish another worker in between.
retry_checked = threading.Event()
allow_retry = threading.Event()
manual_started = threading.Event()
manual_finished = threading.Event()
manual_results = []
settings_calls = [0]
def blocked_retry_settings():
    if threading.current_thread().name == 'test-scheduled-retry' and settings_calls[0] == 0:
        settings_calls[0] += 1
        retry_checked.set()
        assert allow_retry.wait(5)
    return (True, 'fixture-id', b'fixture-token', False, 'https://example.invalid')
def request_manual_sync():
    with app.test_client() as local_client:
        manual_started.set()
        manual_results.append(local_client.post('/online-leaderboard/sync').json['state'])
        manual_finished.set()

with patch.object(online, '_settings', side_effect=blocked_retry_settings), \
     patch.object(online, '_steam_settings', return_value=(False, False)), \
     patch.object(online, '_language_remove_pending', return_value=False), \
     patch.object(online, '_login_cancel_pending', return_value=False), \
     patch.object(online, '_RUNNING', False), \
     patch.object(online, '_STATUS', {'state':'idle'}), \
     patch.object(online, '_LAST_SYNC_START', None), \
     patch.object(online, '_LAST_SYNC_FINISH', None), \
     patch.object(online, '_SERVER_RETRY_UNTIL', 0.0), \
     patch.object(online, '_SCHEDULED_RETRY', unittest.mock.Mock()), \
     patch.object(online, '_RETRY_GENERATION', 10), \
     patch.object(online.time, 'monotonic', return_value=100.0), \
     patch.object(online.threading, 'Thread') as worker_thread:
    retry_thread = real_thread_class(target=online._retry_scheduled,
                                     args=('fixture-id', b'fixture-token', 10),
                                     name='test-scheduled-retry')
    manual_thread = real_thread_class(target=request_manual_sync, name='test-manual-sync')
    retry_thread.start()
    assert retry_checked.wait(5)
    manual_thread.start()
    assert manual_started.wait(5)
    assert not manual_finished.wait(.1), 'Manual sync bypassed the retry gate'
    allow_retry.set()
    retry_thread.join(5)
    manual_thread.join(5)
    assert not retry_thread.is_alive() and not manual_thread.is_alive()
    assert manual_results == ['syncing']
    worker_thread.assert_called_once()

# A failed Timer.start must never publish a nonexistent scheduled retry.
# If another retry was already present, it must remain untouched.
for helper, arguments in ((online._schedule_retry_locked, ('fixture-id', b'fixture-token', 7, 60)),
                          (online._schedule_local_retry_locked, (7, 60))):
    for existing in (None, unittest.mock.Mock()):
        with patch.object(online, '_SCHEDULED_RETRY', existing), \
             patch.object(online.threading, 'Timer') as timer:
            timer.return_value.start.side_effect = RuntimeError('timer unavailable')
            try:
                with online._START_LOCK:
                    helper(*arguments)
                raise AssertionError('Timer start unexpectedly succeeded')
            except RuntimeError as error:
                assert str(error) == 'timer unavailable'
            assert online._SCHEDULED_RETRY is existing
            if existing is not None:
                existing.cancel.assert_not_called()

# If both the network retry timer and local fallback fail to start, the gate is
# still released and the periodic worker can attempt synchronization again.
with patch.object(online, '_settings', return_value=(True, 'fixture-id', b'fixture-token', False, 'https://example.invalid')), \
     patch.object(online, '_steam_settings', return_value=(False, False)), \
     patch.object(online, '_language_remove_pending', return_value=False), \
     patch.object(online, '_login_cancel_pending', return_value=False), \
     patch.object(online, '_RUNNING', True), \
     patch.object(online, '_STATUS', {'state':'syncing'}), \
     patch.object(online, '_SCHEDULED_RETRY', None), \
     patch.object(online, '_RETRY_GENERATION', 0), \
     patch.object(online, '_SERVER_RETRY_UNTIL', 0.0), \
     patch.object(online, '_PERIODIC_WAKE', unittest.mock.Mock()), \
     patch.object(online, '_sync', return_value=('retry_transient', None, 'fixture-id', b'fixture-token')), \
     patch.object(online.time, 'monotonic', return_value=100.0), \
     patch.object(online.threading, 'Timer') as timer, \
     patch.object(online.app.logger, 'exception'):
    timer.return_value.start.side_effect = RuntimeError('timer unavailable')
    online._worker()
    assert timer.call_count == 2
    assert not online._RUNNING and online._SCHEDULED_RETRY is None
    assert online._STATUS['state'] == 'offline'

# Replay-safe API calls retry on transient failures; registration never replays.
with patch.object(online, 'build_opener') as make_opener, \
     patch.object(online.network_retry.time, 'sleep') as retry_sleep, \
     patch.object(online.network_retry.random, 'uniform', return_value=1.0):
    opener = make_opener.return_value
    opener.open.side_effect = online.HTTPError('https://example.invalid', 503, 'error', {}, None)
    try:
        online._call('POST', '/api/v1/installations', {'uuid':'fixture'}, root=online._DEFAULT_BASE_URL)
        raise AssertionError('Registration unexpectedly succeeded')
    except online.HTTPError:
        pass
    assert opener.open.call_count == 1
    retry_sleep.assert_not_called()
    opener.open.reset_mock()
    reply = unittest.mock.MagicMock()
    reply.__enter__.return_value.read.return_value = b'{"accepted": []}'
    opener.open.side_effect = [online.HTTPError('https://example.invalid', 503, 'error', {}, None), reply]
    assert online._call('POST', '/api/v1/events', {'events':[]}, root=online._DEFAULT_BASE_URL) == {'accepted': []}
    assert opener.open.call_count == 2
