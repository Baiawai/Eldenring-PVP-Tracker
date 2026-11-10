"""Exercise consent, synchronization, and retry using private APPDATA only."""
from unittest.mock import patch
import json
import tempfile
from pathlib import Path
from flask import Flask
app = Flask(__name__)
from application import online_leaderboard as online
client = app.test_client()

# Production is the default only when there is no explicit configuration.
# Existing overrides, including an intentionally empty URL, never fall back.
with tempfile.TemporaryDirectory(prefix='leaderboard-config-test-') as directory:
    config_path = Path(directory) / 'leaderboard-config.json'
    with patch.object(online, 'data_dir', return_value=Path(directory)):
        assert online._base_url() == 'https://eldenringpvp.com'
        config_path.write_text(json.dumps({'environment':'development', 'urls':{'development':'http://127.0.0.1:8000'}}), encoding='utf-8')
        assert online._base_url() == 'http://127.0.0.1:8000'
        config_path.write_text(json.dumps({'environment':'production', 'urls':{'production':''}}), encoding='utf-8')
        assert online._base_url() is None
        config_path.write_text('{invalid json', encoding='utf-8')
        assert online._base_url() is None
        config_path.write_text(json.dumps({'environment':'production', 'urls':{'production':'http://example.com'}}), encoding='utf-8')
        assert online._base_url() is None

# These tests focus on synchronization and consent; verification itself is
# covered separately with explicit mocked Steam-status responses below.
verified_steam = online._verified_steam
online._verified_steam = lambda root, token: '76561198000000000'
real_event_consent = online._ensure_event_consent
online._ensure_event_consent = lambda root, token: None
with patch.object(online, '_call', return_value={'ok':True}) as request_consent:
    real_event_consent('https://events.example', 'test-token')
    assert request_consent.call_args.args[:3] == ('POST', '/api/v1/events/consent', {'consent':True, 'version':'events-1'})
assert client.get('/online-leaderboard/settings').json['enabled'] is False
assert client.get('/online-leaderboard/settings').json['steam_status_observe'] is True
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
    assert online._profile()['language'] == 'spaar'
    profile[5] = '../fr'
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
        assert remote.call_args.args[2] == {'language':'browser'}
    with patch.object(online, '_language_permission', return_value=1):
        assert client.post('/online-leaderboard/steam-login').status_code == 200
        assert remote.call_args.args[2] == {'language':'fra'}
