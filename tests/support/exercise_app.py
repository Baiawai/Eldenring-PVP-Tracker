"""Exercise the real Flask application without opening a browser or using user data."""
import sys
import types
import webbrowser
import sqlite3
import os
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from pathlib import Path
import numpy as np

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))
webbrowser.open_new = lambda *args, **kwargs: True
module = types.ModuleType('__main__')
module.__file__ = str(root / 'ELDENRING_Tracker.py')
module.__dict__['__name__'] = 'isolated_tracker_test'
sys.modules['__main__'] = module
exec(compile(Path(module.__file__).read_bytes(), module.__file__, 'exec'), module.__dict__)

from application import functions, init, multi, player_sightings, secur
from cryptography.fernet import Fernet
functions.sync_leaderboard_data = lambda: False
multi.requests.post = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('Unexpected network request'))
client = module.app.test_client()

response = client.get('/')
assert response.status_code == 200
assert b'data-store-build="false"' in response.data
assert client.get('/', headers={'Host':'127.0.0.1:5000', 'Origin':'http://127.0.0.1:5000', 'Sec-Fetch-Site':'same-origin'}).status_code == 200
assert client.get('/exit', headers={'Origin':'https://example.com', 'Sec-Fetch-Site':'cross-site'}).status_code == 403
assert client.get('/start', headers={'Referer':'http://localhost:1234/'}).status_code == 403
assert client.get('/', headers={'Host':'attacker.example:5000'}).status_code == 403
assert client.get('/init').status_code == 200
state = client.get('/interval').get_json()
assert state['fight'] is False and state['monitor_running'] is False
assert client.get('/game-language').status_code == 200
assert client.post('/capture-speed', data={'interval': '2'}).get_json()['interval'] == 2.0
assert client.post('/capture-speed', data={'interval': '999'}).status_code == 400
assert client.post('/notification-region', data={'top': '.3', 'bottom': '.8'}).status_code == 200
assert client.post('/notification-region', data={'top': '.9', 'bottom': '.2'}).status_code == 400
assert client.get('/modeStats?mode=Invasion').status_code == 200

# Usage and diagnostics stay in the isolated APPDATA and reject unknown features.
from application import usage_metrics
with patch.object(usage_metrics.threading.Thread, 'start'):
    usage_metrics.start()
    usage_metrics.start()  # A process has just one session.
assert client.post('/usage-visit', data={'feature':'statistics'}).status_code == 200
assert client.post('/usage-visit', data={'feature':'invalid'}).status_code == 400
usage = client.get('/usage-metrics').get_json()['usage']
assert usage['sessions'] == 1 and usage['streak_days'] == 1
assert usage['features']['statistics'] == 1 and usage['total_seconds'] >= 0
assert len(usage['recent_sessions']) == 1
with patch.object(usage_metrics.threading.Thread, 'start'):
    usage_metrics._session = None
    usage_metrics.start()
assert client.get('/usage-metrics').get_json()['usage']['sessions'] == 2
assert str(usage_metrics.DB).startswith(os.environ['APPDATA'])
with patch.object(functions.pytesseract, 'image_to_string', return_value='ok'):
    assert functions.measured_game_ocr(None) == 'ok'
with patch.object(functions.pytesseract, 'image_to_string', side_effect=RuntimeError('ocr')):
    try:
        functions.measured_game_ocr(None)
        assert False
    except RuntimeError:
        pass
with patch.object(multi, 'FROZEN', False), patch.object(multi, '_sync_leaderboard_data', return_value=True):
    assert multi.sync_leaderboard_data() is True
with patch.object(multi, 'FROZEN', False), patch.object(multi, '_sync_leaderboard_data', return_value=False):
    assert multi.sync_leaderboard_data() is False
system = client.get('/system-metrics').get_json()['system']
assert system['ocr_count'] == 2 and system['ocr_errors'] == 1
assert system['sync_ok'] == 1 and system['sync_failed'] == 1
assert system['steam_ping_ms'] is None
assert client.post('/usage-visit', data={'feature':'statistics'}, headers={'Origin':'https://example.com'}).status_code == 403

# System details are read from the isolated APPDATA and do not require Tesseract.
with patch('application.system_details.tesseract_version', return_value=None):
    details = client.get('/system-details').get_json()
assert details['request'] == 'success'
assert details['environment']['data_path'].startswith(os.environ['APPDATA'])
assert details['environment']['tesseract'] is None
assert details['storage']['database_bytes'] >= 0
assert any(item['name'] == 'database_capture.db' for item in details['storage']['databases'])

# Base-table initialization is idempotent, including partially missing databases.
init.add_capture('ArenaPlayer', 1, 0, 0, '1', '2026-01-01', 'Arena', 'image1')
init.add_capture('Invader', 0, 1, 0, '2', '2026-01-02', 'Invasion', 'image2')
init.add_capture('Defender', 1, 0, 0, '3', '2026-01-03', 'Defense', 'image3')
assert [row[1] for row in init.get_capture_page(2, 1)[0]] == ['Invader', 'Defender']
assert [row[1] for row in init.get_capture_page(2, 2)[0]] == ['ArenaPlayer']
for route in ('/allCaptures', '/allCapturesChart'):
    all_rows = client.get(route).get_json()['captures']
    assert [row[1] for row in all_rows] == ['ArenaPlayer', 'Invader', 'Defender']
    for mode, expected in [('Arena', 'ArenaPlayer'), ('Invasion', 'Invader'), ('Defense', 'Defender')]:
        rows = client.get(route, query_string={'mode': mode}).get_json()['captures']
        assert [row[1] for row in rows] == [expected]
        assert len(rows[0]) == (9 if route == '/allCaptures' else 8)
    assert client.get(route, query_string={'mode':'unknown'}).get_json()['captures'] == all_rows
with patch.object(init, 'decrypt_rows', wraps=init.decrypt_rows) as decrypt:
    rows = client.get('/allCaptures?mode=Defense').get_json()['captures']
    assert rows[0][8] == 'image3'
    assert sum(len(call.args[0][0]) == 9 for call in decrypt.call_args_list) == 1
with closing(player_sightings._connect()) as db:
    plan = db.execute('EXPLAIN QUERY PLAN SELECT id FROM player_sightings WHERE name_key=? AND role=? AND event=? AND observed_at<=? ORDER BY observed_at DESC LIMIT 1', ('key', 'ally', 'joined', '2026')).fetchall()
    assert any('player_sightings_event_lookup' in row[3] for row in plan)

legacy_fernet = Fernet(secur.encryption_key())
def check_cipher(value):
    token = secur.encrypt_value(value)
    assert legacy_fernet.decrypt(token).decode() == value
    assert secur.decrypt_value(legacy_fernet.encrypt(value.encode())).decode() == value
with ThreadPoolExecutor(max_workers=8) as pool:
    list(pool.map(check_cipher, [str(i) for i in range(100)]))

for endpoint in ('allCaptures', 'allCapturesChart', 'addUser', 'nextCaptures', 'autoStart', 'updateNotify'):
    assert endpoint in module.app.view_functions

# Real catalog messages: search is not a fight, repeated frames must not
# count a combat twice, and a return without a result is counted once.
image_path = Path(os.environ['APPDATA']) / 'isolated-frame.jpg'
image_path.write_bytes(b'isolated frame')
frame = np.zeros((30, 30, 3), dtype=np.uint8)
with patch.object(functions, 'apply_score') as score, \
     patch.object(functions, 'emit_tracking_event', return_value=123) as event, \
     patch.object(functions, 'add_capture') as capture, \
     patch.object(functions.cv2, 'imread', return_value=frame), \
     patch.object(functions.cv2, 'imwrite', return_value=True):
    functions.fight = False
    functions.mode_select = 'Arena'
    functions.invasion_phase = ''
    search = "Vous tentez d'envahir un autre monde… (Étendue : proches uniquement)"
    start = "Invasion d'un autre monde.\nTerrassez Test, Hôte des Doigts !"
    win = 'Hôte des Doigts vaincu.\nRetour dans votre monde.'
    assert functions.handle_invasion(search, str(image_path), frame) and not functions.fight
    functions.handle_invasion(search, str(image_path), frame)
    assert event.call_count == 1 and score.call_count == 0
    functions.handle_invasion(start, str(image_path), frame)
    functions.handle_invasion(start, str(image_path), frame)
    assert functions.fight and functions.mode_select == 'Invasion' and score.call_count == 1
    functions.handle_invasion(win, str(image_path), frame)
    functions.handle_invasion(win, str(image_path), frame)
    assert not functions.fight and capture.call_count == 1 and score.call_count == 2

    functions.handle_invasion(start, str(image_path), frame)
    with patch.object(functions.time, 'monotonic', side_effect=[100, 100, 105, 105]):
        functions.handle_invasion('Retour dans votre monde…', str(image_path), frame)
        functions.handle_invasion('Retour dans votre monde…', str(image_path), frame)
    assert not functions.fight and score.call_args.args[4] == 1
    score_count = score.call_count
    functions.handle_invasion('Retour dans votre monde…', str(image_path), frame)
    assert score.call_count == score_count

    functions.handle_invasion('Le Doigt sanglant Test a envahi votre monde !', str(image_path), frame)
    assert functions.fight and functions.mode_select == 'Defense'
    functions.handle_invasion('Le Doigt sanglant Autre est mort.', str(image_path), frame)
    assert functions.fight
    functions.handle_invasion('Le Doigt sanglant Test est mort.', str(image_path), frame)
    assert not functions.fight and capture.call_args.args[6] == 'Defense'
    score_count = score.call_count
    functions.handle_invasion('Le Doigt sanglant Test est mort.', str(image_path), frame)
    assert score.call_count == score_count

    functions.game_locale = 'frafr'
    functions.fight = False
    functions.mode_select = 'Arena'
    functions.stape = 1
    with patch.object(functions, 'path_start_fight', str(image_path)), \
         patch.object(functions.sighting_tracker, 'observe', return_value=[]), \
         patch.object(functions.steam_history, 'begin_arena'), \
         patch.object(functions.steam_history, 'finish_arena', return_value=False):
        functions.process_game_text(functions.detect_text_active[0], str(image_path), frame)
        assert functions.fight and functions.mode_select == 'Arena'
        functions.process_game_text(functions.detect_text_active[15], str(image_path), frame)
        assert not functions.fight and capture.call_args.args[3] == 1
        score_count = score.call_count
        functions.process_game_text(functions.detect_text_active[15], str(image_path), frame)
        assert score.call_count == score_count
image_path.unlink()
before = init.load_user()
init.create_tables()
assert init.load_user() == before and init.get_capture_page(10, 1)[2][0] == 3
missing_settings = Path(os.environ['APPDATA']) / 'isolated-missing-settings.db'
with patch.object(init, 'database_setting', str(missing_settings)):
    try:
        init.create_tables()
        with closing(sqlite3.connect(missing_settings)) as db:
            assert db.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='table_setting'").fetchone()[0] == 1
    finally:
        missing_settings.unlink(missing_ok=True)
