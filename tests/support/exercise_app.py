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
import base64
from io import BytesIO
from PIL import Image

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))
from application import runtime_paths
test_images = Path(os.environ['APPDATA']) / 'test-runtime-images'
test_images.mkdir(parents=True, exist_ok=True)
runtime_paths.image_dir = lambda: test_images
webbrowser.open_new = lambda *args, **kwargs: True
module = types.ModuleType('__main__')
module.__file__ = str(root / 'ELDENRING_Tracker.py')
module.__dict__['__name__'] = 'isolated_tracker_test'
sys.modules['__main__'] = module
exec(compile(Path(module.__file__).read_bytes(), module.__file__, 'exec'), module.__dict__)

from application import functions, init, multi, player_sightings, secur
from application.version import APP_VERSION
from cryptography.fernet import Fernet
client = module.app.test_client()

response = client.get('/', headers={'Accept-Language':'fr-FR,fr;q=0.9'})
assert response.status_code == 200
assert init.get_selected_language() == 'fra'
assert functions.game_locale == 'frafr'
assert client.post('/languages', data={'language':'eng'}).status_code == 200
assert client.get('/', headers={'Accept-Language':'de-DE'}).status_code == 200
assert init.get_selected_language() == 'eng'
assert b'data-store-build="false"' in response.data
assert ('data-i18n-title="environment_tracker">' + APP_VERSION + '</h5>').encode() in response.data
assert client.get('/', headers={'Host':'127.0.0.1:5000', 'Origin':'http://127.0.0.1:5000', 'Sec-Fetch-Site':'same-origin'}).status_code == 200
assert client.get('/exit', headers={'Origin':'https://example.com', 'Sec-Fetch-Site':'cross-site'}).status_code == 403
assert client.get('/start', headers={'Referer':'http://localhost:1234/'}).status_code == 403
assert client.get('/', headers={'Host':'attacker.example:5000'}).status_code == 403
assert client.get('/init').status_code == 200
state = client.get('/interval').get_json()
assert state['fight'] is False and state['monitor_running'] is False
assert client.get('/game-language').status_code == 200
assert client.get('/steam-log-auto').get_json()['enabled'] is True
assert client.post('/steam-log-auto', data={'enabled':'nope'}).status_code == 400
assert client.post('/steam-log-auto', data={'enabled':'false'}).get_json()['enabled'] is False
assert client.post('/steam-log-auto', data={'enabled':'true'}).get_json()['enabled'] is True
notifications = client.get('/tracking-notifications').get_json()['settings']
assert notifications == {'monitor_error':False, 'game_hidden':False, 'monitor_stop':False}
assert client.post('/tracking-notifications', data={'kind':'game_hidden','enabled':'true'}).get_json()['settings']['game_hidden'] is True
assert client.post('/tracking-notifications', data={'kind':'other','enabled':'true'}).status_code == 400
assert client.post('/tracking-notifications', data={'kind':'game_hidden','enabled':'false'}).get_json()['settings']['game_hidden'] is False
assert client.get('/retention-settings').get_json()['settings'] == {'captures':0, 'steam':0}
with patch.object(functions, 'run_monitor', True):
    assert client.post('/retention-settings', data={'kind':'captures','days':'30'}).status_code == 409
assert client.post('/retention-settings', data={'kind':'captures','days':'1'}).status_code == 400
assert client.post('/retention-settings', data={'kind':'captures','days':'30'}).get_json()['settings']['captures'] == 30
assert client.post('/retention-settings', data={'kind':'captures','days':'0'}).get_json()['settings']['captures'] == 0
display = {'name':'FAKE-DISPLAY', 'x':-100, 'y':0, 'width':100, 'height':80, 'primary':False}
with patch.object(functions, 'active_capture_display', None), \
     patch.object(functions, 'width_screen', 0), patch.object(functions, 'height_screen', 0), \
     patch.object(functions.capture_display, 'game_display', side_effect=[display, None, dict(display, x=0, width=200)]):
    functions.update_game_display()
    assert (functions.active_capture_display['x'], functions.width_screen, functions.height_screen) == (-100, 100, 80)
    functions.update_game_display()
    assert functions.active_capture_display['x'] == -100
    functions.update_game_display()
    assert (functions.active_capture_display['x'], functions.width_screen) == (0, 200)
with patch.object(functions, 'run_monitor', True), patch.object(functions, 'active_capture_display', display), \
     patch.object(functions.capture_display, 'capture', return_value='fake') as grabbed:
    assert functions.screenshot_with_retry('fake.jpg', region=(1, 2, 3, 4)) == 'fake'
    assert grabbed.call_args.kwargs['region'] == (1, 2, 3, 4)
assert client.get('/auto-game-start').get_json()['enabled'] is False
assert client.post('/auto-game-start', data={'enabled':'true'}).get_json()['enabled'] is True
assert client.post('/auto-game-start', data={'enabled':'invalid'}).status_code == 400
assert client.post('/auto-game-start', data={'enabled':'false'}).get_json()['enabled'] is False
with patch.dict(functions.array_stats, {'text':'pending-event'}):
    assert client.get('/monitor-status').get_json()['running'] is False
    assert functions.array_stats['text'] == 'pending-event'
assert client.post('/capture-speed', data={'interval': '2'}).get_json()['interval'] == 2.0
assert client.post('/capture-speed', data={'interval': '999'}).status_code == 400
assert client.get('/notification-region').get_json()['manual'] is False
assert client.post('/notification-region', data={'locked':'true', 'preview_id':'0'}).get_json()['reason'] == 'no_lockable_preview'
assert client.post('/notification-region', data={'top': '.3', 'bottom': '.8'}).status_code == 409
assert client.post('/notification-region', data={'manual':'true'}).status_code == 200
assert client.post('/notification-region', data={'top': '.3', 'bottom': '.8'}).status_code == 200
assert client.post('/notification-region', data={'top': '.9', 'bottom': '.2'}).status_code == 400
assert client.get('/notification-region').get_json()['manual'] is True
assert client.post('/notification-region', data={'manual':'invalid'}).status_code == 400
assert client.post('/notification-region', data={'manual':'false'}).get_json()['manual'] is False
assert client.post('/notification-region', data={'top':'.2', 'bottom':'.9'}).status_code == 409
assert client.get('/notification-region').get_json()['top'] == 0.0
assert client.post('/notification-region', data={'manual':'true'}).get_json()['top'] == .3
from application.locale_catalog import messages
with patch.object(functions, 'capture', 'live-non-event'), \
     patch.object(functions, 'notification_event_sample', None), \
     patch.object(functions, 'notification_sample_revision', 0):
    assert client.get('/notification-region').get_json()['preview'] == ''
    assert client.post('/notification-ocr-test').status_code == 409
    preview_bytes = BytesIO()
    Image.new('RGB', (100, 100), 'white').save(preview_bytes, format='JPEG')
    sample_image = base64.b64encode(preview_bytes.getvalue()).decode()
    assert not functions._remember_notification_event(sample_image, 'unrelated game frame', 'frafr')
    event_text = messages()['frafr']['2341413'].replace('<?matchRemainingCount?>', '1')
    assert not functions._remember_notification_event(sample_image, event_text, 'frafr', lines=1)
    assert functions._remember_notification_event(sample_image, event_text, 'frafr', bounds=(.2,.7), lines=2)
    assert not functions._remember_notification_event(sample_image, event_text, 'frafr', bounds=(.2,.7), lines=2)
    assert not functions._remember_notification_event(sample_image, messages()['frafr']['2301200'], 'frafr', bounds=(.2,.9), lines=1)
    assert client.get('/notification-region').get_json()['preview_id'] == 1
    assert functions.flush_notification_sample(timeout=5)
    assert functions.notification_sample.load()['image'] == sample_image
    assert functions.notification_sample.load()['lines'] == 2
    with closing(sqlite3.connect(init.database_setting)) as db:
        encrypted_image = db.execute('SELECT image FROM notification_example WHERE id=1').fetchone()[0]
        assert sample_image.encode() not in encrypted_image
    sample = client.get('/notification-region').get_json()
    assert sample['preview'] == sample_image and sample['preview_id'] == 1
    assert client.post('/notification-ocr-test', data={'preview_id':'0'}).get_json()['reason'] == 'preview_changed'
    with patch.object(functions.pytesseract, 'image_to_string', return_value=event_text) as ocr:
        result = client.post('/notification-ocr-test', data={'preview_id':'1'}).get_json()
        assert result['text'] == event_text and result['matched'] is True
        assert ocr.call_args.args[0].shape == (50, 100)
    with patch.object(functions.pytesseract, 'image_to_string', return_value='unrelated'):
        assert client.post('/notification-ocr-test', data={'preview_id':'1'}).get_json()['matched'] is False
    assert client.post('/notification-region', data={'locked':'true', 'preview_id':'1'}).get_json()['reason'] == 'manual_mode'
    assert client.post('/notification-region', data={'manual':'false'}).get_json()['manual'] is False
    assert client.post('/notification-region', data={'locked':'true', 'preview_id':'0'}).get_json()['reason'] == 'preview_changed'
    locked = client.post('/notification-region', data={'locked':'true', 'preview_id':'1'}).get_json()
    assert locked['locked'] and (locked['top'], locked['bottom']) == (.2, .7)
    assert functions.notification_region.load_locked_bounds() == (.2, .7)
    next_text = messages()['frafr']['2341413'].replace('<?matchRemainingCount?>', '2')
    assert functions._remember_notification_event(sample_image, next_text, 'frafr', bounds=(.1,.9), lines=2)
    updated = client.get('/notification-region').get_json()
    assert updated['preview_id'] == 2 and (updated['top'], updated['bottom']) == (.2, .7)
    with patch.object(functions.pytesseract, 'image_to_string', return_value=next_text) as ocr:
        assert client.post('/notification-ocr-test', data={'preview_id':'2'}).get_json()['matched']
        assert ocr.call_args.args[0].shape == (50, 100)
    manual = client.post('/notification-region', data={'manual':'true'}).get_json()
    assert (manual['top'], manual['bottom']) == (.3,.8) and manual['locked']
    auto = client.post('/notification-region', data={'manual':'false'}).get_json()
    assert (auto['top'], auto['bottom']) == (.2,.7) and auto['locked']
    unlocked = client.post('/notification-region', data={'locked':'false'}).get_json()
    assert not unlocked['locked'] and (unlocked['top'], unlocked['bottom']) == (.1,.9)
    relocked = client.post('/notification-region', data={'locked':'true', 'preview_id':'2'}).get_json()
    assert relocked['locked'] and (relocked['top'], relocked['bottom']) == (.1,.9)
    assert functions.flush_notification_sample(timeout=5)
# Positioned game messages localize the zone; missing or malformed OCR is safe.
for locale, catalog in messages().items():
    words = catalog['2301200'].split()
    data = {'text':words, 'conf':['95'] * len(words), 'top':[500] * len(words), 'height':[40] * len(words),
            'block_num':[1] * len(words), 'par_num':[1] * len(words), 'line_num':[1] * len(words)}
    detected = functions.notification_region.analyze_notification(data, 1000, locale)
    assert detected and detected['lines'] == 1, locale
    assert detected['bounds'][0] < .5 and detected['bounds'][1] > .54, locale
    assert detected['bounds'][1] - detected['bounds'][0] >= .16, locale
    two_lines = catalog['2341413'].replace('<?matchRemainingCount?>', '1').splitlines()
    positioned = {'text':[], 'conf':[], 'top':[], 'height':[], 'block_num':[], 'par_num':[], 'line_num':[]}
    for line_id, line in enumerate(two_lines, 1):
        for word in line.split():
            for key, value in [('text',word), ('conf','95'), ('top',480 + line_id * 40), ('height',25),
                               ('block_num',1), ('par_num',1), ('line_num',line_id)]:
                positioned[key].append(value)
    detected = functions.notification_region.analyze_notification(positioned, 1000, locale)
    assert detected and detected['lines'] == 2, (locale, detected)
    assert detected['bounds'][0] <= .52 and detected['bounds'][1] >= .585, locale
# A dark two-line strip is detected close to its edges; a one-line strip
# still receives enough height to fit a two-line message.
two_line_text = messages()['frafr']['2341413'].replace('<?matchRemainingCount?>', '1').splitlines()
def positioned_words(lines, heights):
    data = {'text':[], 'conf':[], 'top':[], 'height':[], 'block_num':[], 'par_num':[], 'line_num':[]}
    for line_id, (line, y) in enumerate(zip(lines, heights), 1):
        for word in line.split():
            for key, value in [('text',word), ('conf','95'), ('top',y), ('height',24),
                               ('block_num',1), ('par_num',1), ('line_num',line_id)]:
                data[key].append(value)
    return data
frame = np.full((810, 720), 180, dtype=np.uint8)
frame[505:600, :] = 35
auto = functions.notification_region.analyze_notification(positioned_words(two_line_text, [527,561]), 810, 'frafr', frame)
assert auto and auto['lines'] == 2
assert abs(auto['bounds'][0] * 810 - 505) <= 8 and abs(auto['bounds'][1] * 810 - 600) <= 8
frame[:] = 180
frame[526:577, :] = 35
single = functions.notification_region.analyze_notification(positioned_words([messages()['frafr']['arena:88050']], [546]), 810, 'frafr', frame)
assert single and single['lines'] == 1
assert (single['bounds'][1] - single['bounds'][0]) >= (auto['bounds'][1] - auto['bounds'][0])
assert functions.notification_region.detected_bounds({'text':['nothing']}, 1000, 'frafr') == (0.0, 1.0)
assert functions.notification_region.detected_bounds({}, 1000, 'frafr') == (0.0, 1.0)
assert client.post('/notification-ocr-test', headers={'Origin':'https://example.com'}).status_code == 403
assert client.get('/modeStats?mode=Invasion').status_code == 200
for removed in ('/character-profiles', '/close-behavior', '/dependency-status', '/data-restore-status'):
    assert client.get(removed).status_code == 404

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
assert client.get('/syncMulti').status_code == 404
system = client.get('/system-metrics').get_json()['system']
assert system['version'] == APP_VERSION
assert system['ocr_count'] == 2 and system['ocr_errors'] == 1
assert system['sync_ok'] == 0 and system['sync_failed'] == 0
assert system['steam_ping_ms'] is None
assert client.post('/usage-visit', data={'feature':'statistics'}, headers={'Origin':'https://example.com'}).status_code == 403

# System details are read from the isolated APPDATA and do not require Tesseract.
with patch('application.system_details.tesseract_version', return_value=None):
    details = client.get('/system-details').get_json()
assert details['request'] == 'success'
assert details['environment']['tracker'] == APP_VERSION
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
        functions.invasion_phase = None
        functions.invasion_search_visibility.reset()
        event.reset_mock()
        curly_search = 'Vous tentez d’envahir un autre monde… (Étendue : proches uniquement)'
        with patch.object(functions.time, 'monotonic') as clock:
            for now, text in [(0, curly_search), (1, curly_search), (2, ''), (4, ''), (7, ''), (8, curly_search), (9, curly_search)]:
                clock.return_value = now
                functions.process_game_text(text, str(image_path), frame)
        assert event.call_count == 2 and not functions.fight
        assert all(call.args[0].startswith('<!--search-start-->') for call in event.call_args_list)
        functions.invasion_search_visibility.reset()
        functions.invasion_phase = None
        functions.mode_select = 'Arena'
        functions.stape = 1
        functions.process_game_text(functions.detect_text_active[0], str(image_path), frame)
        assert functions.fight and functions.mode_select == 'Arena'
        functions.process_game_text(functions.detect_text_active[15], str(image_path), frame)
        assert not functions.fight and capture.call_args.args[3] == 1
        score_count = score.call_count
        functions.process_game_text(functions.detect_text_active[15], str(image_path), frame)
        assert score.call_count == score_count
# Failed ally summons produce one history event per notification, never a combat.
import html
from application.locale_catalog import messages as game_messages
for ui_language, locale in functions.game_language.UI_TO_GAME.items():
    expected = game_messages()[locale]['2490000']
    if ui_language != 'fra':
        expected = html.escape(expected, quote=False)
    assert functions.localize_counter("Impossible d'invoquer l'allié.", ui_language) == expected
functions.fight = False
functions.mode_select = 'Defense'
functions.mode_detected = True
functions.invasion_phase = None
functions.game_locale = 'frafr'
functions.langue_select = 'fra'
functions.ally_summon_failure_last_seen = None
functions.invasion_search_visibility.reset()
with patch.object(functions, 'apply_score') as score, \
     patch.object(functions, 'record_detection', wraps=functions.record_detection) as record, \
     patch.object(functions.sighting_tracker, 'observe', return_value=[]), \
     patch.object(functions.time, 'monotonic') as clock:
    for now, text in [(100, "Impossible d'invoquer l'allié."),
                      (101, "Impossible d'invoquer l'allié."),
                      (102, "Impossible d'invoquer l'allié.\nDélai expiré."),
                      (112, "Impossible d'invoquer l'allié.")]:
        clock.return_value = now
        functions.process_game_text(text, str(image_path), frame)
    assert record.call_count == 2 and score.call_count == 0 and not functions.fight
    recent = client.get('/detection-history?mode=Defense').get_json()['events']
    assert sum(event['message'] == "Impossible d'invoquer l'allié." for event in recent) >= 2
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

# A capture is only written after confirming its one-time token, in isolated APPDATA.
import win32gui
before_profile = init.load_user()[0]
fake_profile = {'name':'勇者', 'level':150, 'avatar':'image-test'}
with patch.object(win32gui, 'FindWindow', return_value=42), \
     patch.object(win32gui, 'GetForegroundWindow', return_value=42), \
     patch.object(win32gui, 'IsIconic', return_value=False), \
     patch.object(functions.capture_display, 'game_display', return_value=display), \
     patch.object(functions.capture_display, 'capture', return_value='image'), \
     patch.object(functions.profile_capture, 'read', return_value=fake_profile):
    captured = client.post('/profile-capture', data={'action':'read'}).get_json()
    assert captured['profile'] == fake_profile and init.load_user()[0] == before_profile
    assert client.post('/profile-capture', data={'action':'save','token':'invalid'}).status_code == 400
    assert init.load_user()[0] == before_profile
    assert client.post('/profile-capture', data={'action':'save','token':captured['token']}).status_code == 200
    assert client.post('/profile-capture', data={'action':'save','token':captured['token']}).status_code == 400
    saved_user = init.load_user()[0]
    assert saved_user[1] == '勇者' and saved_user[6] == 'image-test' and saved_user[19] == '150'

# Archive, purge and restore only the isolated history; capture and user data survive.
from application import detection_history, steam_history
before_user = init.load_user()
before_captures = init.get_capture_page(10, 1)
first_id = detection_history.record_detection('Événement de test', 'Arena')
steam_id = detection_history.record_detection('Joueur Steam rencontré : Test', 'Arena', 'steam_encounter',
                                               {'id':'76561198000000000','name':'Test','ip':'192.0.2.1','relay':False})
initial = client.get('/history-storage').get_json()
assert initial['history']['events'] > 1 and initial['history']['bytes'] > 0
with patch.object(functions, 'run_monitor', True):
    assert client.post('/history-archives').status_code == 409
    assert client.post('/history-purge').status_code == 409
assert functions.monitor_lock.acquire(blocking=False)
try:
    assert client.post('/history-purge').status_code == 409
finally:
    functions.monitor_lock.release()
with closing(detection_history._connect()) as db:
    db.execute("CREATE TRIGGER reject_history_delete BEFORE DELETE ON detection_history BEGIN SELECT RAISE(ABORT, 'blocked'); END")
    db.commit()
assert client.post('/history-archives').status_code == 500
assert client.get('/history-storage').get_json()['history']['events'] == initial['history']['events']
assert client.get('/history-storage').get_json()['archives'] == []
with closing(detection_history._connect()) as db:
    db.execute('DROP TRIGGER reject_history_delete')
    db.commit()
archived = client.post('/history-archives').get_json()
assert archived['request'] == 'success' and archived['archived'] == initial['history']['events']
status = client.get('/history-storage').get_json()
assert status['history']['events'] == 0 and len(status['archives']) == 1
archive_id = status['archives'][0]['id']
with closing(detection_history._connect()) as db:
    saved = db.execute('SELECT message,metadata FROM history_archive_events WHERE archive_id=? AND original_id=?', (archive_id,steam_id)).fetchone()
    assert saved and b'192.0.2.1' not in saved[1] and b'Test' not in saved[0]
assert detection_history.read_steam_history() == []
new_id = detection_history.record_detection('Nouvel événement', 'Invasion')
assert new_id > steam_id
restored = client.post(f'/history-archives/{archive_id}/restore').get_json()
assert restored['restored'] == initial['history']['events']
assert client.post(f'/history-archives/{archive_id}/restore').get_json()['restored'] == 0
assert detection_history.read_steam_history()[0]['steam']['ip'] == '192.0.2.1'
assert client.post('/history-archives/999999/restore').status_code == 404
assert client.post('/history-purge').get_json()['removed'] == initial['history']['events'] + 1
assert client.get('/history-storage').get_json()['history']['events'] == 0
assert client.post(f'/history-archives/{archive_id}/restore').get_json()['restored'] == initial['history']['events']
assert detection_history.record_detection('Après restauration', 'Arena') > new_id
with ThreadPoolExecutor(max_workers=4) as executor:
    ids = list(executor.map(lambda i: detection_history.record_detection('Concurrent ' + str(i), 'Arena'), range(12)))
assert len(set(ids)) == 12 and min(ids) > new_id
assert init.load_user() == before_user and init.get_capture_page(10, 1) == before_captures
