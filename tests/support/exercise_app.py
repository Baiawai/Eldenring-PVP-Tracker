"""Exercise the real Flask application without opening a browser or using user data."""
import sys
import types
import html
import webbrowser
import sqlite3
import os
import tempfile
from contextlib import closing, nullcontext, ExitStack
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from pathlib import Path
import numpy as np
import base64
from itertools import count
from io import BytesIO
from PIL import Image

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))
from application import runtime_paths
from application import error_reports
error_reports.report = lambda *args, **kwargs: None
error_reports.start = lambda: None
test_images = Path(os.environ['APPDATA']) / 'test-runtime-images'
test_images.mkdir(parents=True, exist_ok=True)
runtime_paths.image_dir = lambda: test_images
webbrowser.open_new = lambda *args, **kwargs: True
module = types.ModuleType('__main__')
module.__file__ = str(root / 'ELDENRING_Tracker.py')
module.__dict__['__name__'] = 'isolated_tracker_test'
sys.modules['__main__'] = module
exec(compile(Path(module.__file__).read_bytes(), module.__file__, 'exec'), module.__dict__)

from application import functions, init, multi, player_sightings, secur, mode_stats
from application import tracker_overlay
from application import tracker_overlay_event, peer_rankings
from application.version import APP_VERSION
from cryptography.fernet import Fernet
client = module.app.test_client()

# Historical-avatar routes cannot be accessed by other pages or local clients
# lacking the tracker session, and unknown Steam IDs never trigger a request.
avatar_guard = module.app.test_client()
assert avatar_guard.get('/players/steam-avatar/76561198000000001').status_code == 403
assert avatar_guard.post('/players/steam-avatar/request', data={'steam_id':'76561198000000001'}).status_code == 403
assert avatar_guard.get('/', headers={'Accept-Language':'fr'}).status_code == 200
assert avatar_guard.post('/players/steam-avatar/request', data={'steam_id':'76561198000000001'},
                         headers={'Origin':'https://example.com'}).status_code == 403
assert avatar_guard.post('/players/steam-avatar/request', data={'steam_id':'76561198000000001'}).status_code == 404

# Explicit Steam logging retries use the same local-session and origin guard
# as other configuration changes; no real Steam process is started here.
with patch.object(functions.steam_log_auto, 'request_retry', return_value={'state': 'queued'}) as retry:
    retry_client = module.app.test_client()
    assert retry_client.post('/steam-log-auto/retry').status_code == 403
    assert retry_client.get('/', headers={'Accept-Language': 'fr'}).status_code == 200
    assert retry_client.post('/steam-log-auto/retry', headers={'Origin': 'https://example.com'}).status_code == 403
    retry.assert_not_called()
    response = retry_client.post('/steam-log-auto/retry')
    assert response.status_code == 200
    assert response.get_json() == {'request': 'success', 'state': 'queued'}
    retry.assert_called_once_with(functions.peer_tracking.enabled)

# The display-only Store version status remains protected by the local
# session, stays readable after the gate, and never starts a network lookup.
with patch.object(module.store_update, '_REQUIRED', True), \
     patch.object(module.store_update, '_AVAILABLE_VERSION', '1.0.12.0'), \
     patch.object(module.store_update, '_AVAILABLE_VERSION_SOURCE', 'site'), \
     patch.object(module.store_update, '_METADATA_LOOKUP_PENDING', False), \
     patch.object(module.store_update, '_query_store_update') as store_query, \
     patch.object(module.store_update, '_start_indicative_version_lookup') as metadata_query:
    status_client = module.app.test_client()
    assert status_client.get('/store-update-status').status_code == 403
    assert status_client.get('/').status_code == 200  # Establishes local session cookie.
    result = status_client.get('/store-update-status')
    assert result.status_code == 200
    assert result.get_json() == {'available_version': '1.0.12.0', 'version_source': 'site', 'lookup_pending': False}
    assert status_client.post('/start').status_code == 423
    store_query.assert_not_called()
    metadata_query.assert_not_called()

# A pending Store update must not interrupt a fight or permit the automatic
# game detector to start another monitor. Once the fight finishes the real
# monitor loop stops itself at its next iteration, before another capture.
with module.app.app_context():
    for pending, required in ((True, False), (False, True)):
        with patch.object(functions.store_update, 'is_pending', return_value=pending), \
             patch.object(functions.store_update, 'is_required', return_value=required), \
             patch.object(functions.threading, 'Thread') as monitor_thread:
            response, status = functions.start()
            assert status == 423 and response.get_json()['error'] == 'store_update_required'
            monitor_thread.assert_not_called()

with patch.object(functions.store_update, 'is_pending', return_value=True), \
     patch.object(functions, 'run_monitor', True), patch.object(functions, 'fight', True), \
     patch.object(functions, 'monitor_ready', False), patch.object(functions, 'tampo_text', ''), \
     patch.object(functions, 'stop', wraps=functions.stop) as monitor_stop, \
     patch.object(functions.peer_tracking, 'cancel_auto_ping'), \
     patch.object(functions, 'reset_monitor_state'), \
     patch.object(functions, 'emit_tracking_event'), \
     patch.object(functions.cv2, 'imread', return_value=None), \
     patch.object(functions.steam_overlay, 'OverlayDetector'):
    assert functions._stop_for_pending_store_update() is False
    assert functions.run_monitor is True
    monitor_stop.assert_not_called()
    functions.fight = False
    functions.monitor(None)
    assert functions.run_monitor is False
    monitor_stop.assert_called_once_with()

# Exercise the overlay coordinator without starting a real Windows window or
# reading the user's tracker state. The queue used by /interval is untouched.
class OverlayTestWindow:
    error = None
    def __init__(self, provider):
        self.provider = provider
        self.started = self.stopped = False
    def start(self):
        self.started = True
    def stop(self):
        self.stopped = True

overlay_windows, overlay_states = [], []
def make_overlay(provider):
    result = OverlayTestWindow(provider)
    overlay_windows.append(result)
    return result

class OverlayTestWait:
    def wait(self, _):
        overlay_states.append((tracker_overlay.status(), tracker_overlay._read_content(fake_tracking)))
        if len(overlay_states) == 4:
            raise StopIteration

fake_tracking = types.SimpleNamespace(
    langue_select='eng', run_monitor=True, monitor_ready=True, monitor_error=False,
    game_running=True, game_detected=True, capture_available=True, fight=True, mode_select='Arena', mode_detected=True,
    get_foreground_window=lambda: 123,
    get_window_text=lambda hwnd: 'ELDEN RING™' if hwnd == 123 else '',
    steam_overlay=types.SimpleNamespace(has_overlay_indicators=lambda hwnd: False),
    session_summary=types.SimpleNamespace(snapshot=lambda: {'last': {'result': 'victory', 'mode': 'Arena', 'opponent': 'A'}}),
    overlay_peer_roles=functions.overlay_peer_roles,
    peer_tracking=types.SimpleNamespace(passive_snapshot=lambda: {'status': 'active', 'enabled': True,
                                                                  'peers': [{'name': 'B', 'ping': 32}]}))

# Exercise the actual OCR recognizer and Steam observer together, then inspect
# the view published by the overlay worker. Everything here is synthetic.
peer_id = '76561198000000001'
peer_data = [{'id': peer_id, 'name': 'TestHunter', 'ping': 42, 'country_code': 'DE'}]
fake_roles = type(functions.overlay_peer_roles)()
role_tracking = types.SimpleNamespace(**vars(fake_tracking))
role_tracking.overlay_peer_roles = fake_roles
role_tracking.mode_select = 'Defense'
role_tracking.langue_select = 'fra'
role_tracking.peer_tracking = types.SimpleNamespace(passive_snapshot=lambda: {
    'status': 'active', 'enabled': True, 'peers': peer_data})
class OneOverlayCycle:
    def wait(self, _):
        raise StopIteration

with patch.object(functions, 'overlay_peer_roles', fake_roles), \
     patch.object(functions, 'sighting_tracker', player_sightings.SightingTracker()), \
     patch.object(functions, 'run_monitor', True), patch.object(functions, 'fight', True), \
     patch.object(functions, 'mode_select', 'Defense'), patch.object(functions, 'mode_detected', True), \
     patch.object(functions, 'game_locale', 'frafr'), \
     patch.object(functions.steam_history, 'observe', return_value=False), \
     patch.object(functions.steam_history, 'cancel_arena'), \
     patch.object(functions, '_cancel_pvp_encounter'), \
     patch.object(functions, 'record_sighting', return_value=False), \
     patch.object(functions, 'emit_tracking_event'):
    functions._observe_steam_peers('active', peer_data)
    text = 'Chasseur TestHunter invoqué.'
    functions.process_game_text(text, None, None, notification_text=text)
    assert fake_roles.annotate(peer_data)[0]['role'] == 'hunter'
    opts = dict(tracker_overlay.overlay_settings.DEFAULT_OPTIONS, show_avatars=False, show_rank=False,
                show_player_stats=False)
    with patch.object(tracker_overlay.overlay_settings, 'enabled', return_value=True), \
         patch.object(tracker_overlay.overlay_settings, 'options', return_value=opts), \
         patch.object(tracker_overlay.tracker_overlay_window, 'OverlayWindow', OverlayTestWindow), \
         patch.object(tracker_overlay.threading, 'Event', return_value=OneOverlayCycle()):
        try:
            tracker_overlay._worker(role_tracking)
        except StopIteration:
            pass
    assert tracker_overlay._view['cards'][0]['role'] == 'hunter'
    assert tracker_overlay._view['cards'][0]['country_name'] == 'Allemagne'
    functions._observe_steam_peers('active', [])
    functions._observe_steam_peers('active', peer_data)
    assert fake_roles.annotate(peer_data)[0]['role'] is None
    functions.process_game_text(text, None, None, notification_text=text)
    assert fake_roles.annotate(peer_data)[0]['role'] == 'hunter'
    functions.reset_monitor_state()
    assert fake_roles.annotate(peer_data)[0]['role'] is None

    # The first explicit invasion may arrive before a mode is detected. Its
    # separate overlay-only recognizer still requires confirmation, and does
    # not itself alter the monitor's mode or combat state.
    functions.run_monitor = True
    functions.mode_detected = False
    invader = [{'id': '76561198000000002', 'name': 'TestInvader', 'ping': 50}]
    functions._observe_steam_peers('active', invader)
    text = 'Le Doigt sanglant TestInvader a envahi votre monde !'
    with patch.object(functions, 'overlay_invasion_tracker', player_sightings.SightingTracker()), \
         patch.object(functions, 'handle_invasion', return_value=True):
        functions.process_game_text(text, None, None, notification_text='')
        assert fake_roles.annotate(invader)[0]['role'] is None
        # Mode detection can happen between two successive OCR readings.
        functions.mode_detected = True
        functions.mode_select = 'Defense'
        functions.process_game_text(text, None, None, notification_text='')
        assert fake_roles.annotate(invader)[0]['role'] == 'invader'
        assert functions.mode_detected is True and functions.fight is False
    functions.reset_monitor_state()
    assert fake_roles.annotate(invader)[0]['role'] is None

# A defense start already announces the invader. The following confirmed OCR
# still records the sighting and updates the overlay role, without announcing
# the same arrival twice. Different players and independent arrivals remain.
defense_roles = type(functions.overlay_peer_roles)()
defense_peer = {'id': '76561198000000999', 'name': 'DuplicateTest', 'ping': 50}
defense_roles.update_peers('active', [defense_peer])
from datetime import datetime as test_datetime
real_record_sighting = functions.record_sighting
def record_sighting_at_test_time(sighting):
    observed_at = test_datetime.fromtimestamp(1700000000 + clock.return_value).isoformat()
    return real_record_sighting(sighting, observed_at=observed_at)
with patch.object(functions, 'overlay_peer_roles', defense_roles), \
     patch.object(functions, 'sighting_tracker', player_sightings.SightingTracker()), \
     patch.object(functions, 'overlay_invasion_tracker', player_sightings.SightingTracker()), \
     patch.object(functions, 'run_monitor', True), patch.object(functions, 'fight', False), \
     patch.object(functions, 'mode_select', 'Arena'), patch.object(functions, 'mode_detected', False), \
     patch.object(functions, 'game_locale', 'frafr'), patch.object(functions, 'time_start', 0), \
     patch.object(functions, 'opponent_name', ''), patch.object(functions, 'invasion_phase', None), \
     patch.object(functions, '_begin_pvp_encounter'), patch.object(functions, 'apply_score'), \
     patch.object(functions.cv2, 'imread', return_value=np.zeros((30, 30, 3), dtype=np.uint8)), \
     patch.object(functions.cv2, 'imwrite', return_value=True), \
     patch.object(functions, 'record_sighting', side_effect=record_sighting_at_test_time) as record, \
     patch.object(functions, 'emit_tracking_event') as event, \
     patch.object(functions.time, 'time', return_value=1000) as clock:
    arrival = 'Le Doigt sanglant DuplicateTest a envahi votre monde !'
    functions.process_game_text(arrival, 'unused-test-image', None, notification_text=arrival)
    functions.process_game_text(arrival, 'unused-test-image', None, notification_text=arrival)
    assert [call.args[0] for call in event.call_args_list] == ['DuplicateTest a envahi votre monde']
    assert record.call_count >= 1
    recorded = player_sightings.read_sightings()
    assert any(item['name'] == 'DuplicateTest' and item['role'] == 'invader' and
               item['relation'] == 'opponent' and item['event'] == 'invaded' for item in recorded)
    assert defense_roles.annotate([defense_peer])[0]['role'] == 'invader'

    other = 'Le Doigt sanglant OtherTest a envahi votre monde !'
    functions.process_game_text(other, 'unused-test-image', None, notification_text=other)
    assert event.call_args.args[0] == 'Envahisseur arrivé : OtherTest'

    # A later independent arrival of the same name is not hidden indefinitely.
    clock.return_value = 1046
    functions.process_game_text(arrival, 'unused-test-image', None, notification_text=arrival)
    assert event.call_args.args[0] == 'Envahisseur arrivé : DuplicateTest'

    # The same observed name is a co-invader in Invasion, not a Defense start.
    functions.mode_select = 'Invasion'
    functions.process_game_text(arrival, 'unused-test-image', None, notification_text=arrival)
    assert event.call_args.args[0] == 'Autre envahisseur arrivé : DuplicateTest'

# The overlay can use the unique, currently connected arena participant that
# the existing history tracker observed, without reading or writing real data.
arena_tracking = types.SimpleNamespace(**vars(fake_tracking))
arena_tracking.overlay_peer_roles = type(functions.overlay_peer_roles)()
arena_tracking.steam_history = functions.steam_history
arena_tracking.peer_tracking = types.SimpleNamespace(passive_snapshot=lambda: {
    'status': 'active', 'enabled': True, 'peers': peer_data})
with patch.object(functions.steam_history, '_known', {}), \
     patch.object(functions.steam_history, '_arena', None), \
     patch.object(functions.steam_history, 'record_detection', return_value=42), \
     patch.object(tracker_overlay.overlay_settings, 'enabled', return_value=True), \
     patch.object(tracker_overlay.overlay_settings, 'options', return_value=opts), \
     patch.object(tracker_overlay.tracker_overlay_window, 'OverlayWindow', OverlayTestWindow), \
     patch.object(tracker_overlay.threading, 'Event', return_value=OneOverlayCycle()):
    functions.steam_history.observe('active', peer_data, 'Arena')
    functions.steam_history.begin_arena()
    try:
        tracker_overlay._worker(arena_tracking)
    except StopIteration:
        pass
    assert tracker_overlay._view['cards'][0]['role'] == 'duelist'
    arena_tracking.fight = False
    try:
        tracker_overlay._worker(arena_tracking)
    except StopIteration:
        pass
    assert tracker_overlay._view['cards'][0]['role'] is None

# No OS window or monitor is started. The overlay provider must return no text
# as soon as monitoring is stopped, starting, errored or unable to capture,
# including when focus changes before the monitor has processed a new frame.
overlay_window_fixtures = ExitStack()
overlay_window_fixtures.enter_context(patch.object(tracker_overlay.win32gui, 'IsWindowVisible', side_effect=lambda hwnd: hwnd == 123))
overlay_window_fixtures.enter_context(patch.object(tracker_overlay.win32gui, 'IsIconic', return_value=False))
tracker_overlay._set_state(('test overlay',), 'running', options={'visibility_mode': 'capture'})
assert tracker_overlay._read_content(fake_tracking) == ('test overlay',)
assert tracker_overlay._window_content(fake_tracking) == {'lines': ('test overlay',), 'capture_active': True, 'options': {'visibility_mode': 'capture'}, 'view': None}
for attribute, unavailable in (('run_monitor', False), ('monitor_ready', False),
                               ('monitor_error', True), ('capture_available', False)):
    with patch.object(fake_tracking, attribute, unavailable):
        assert tracker_overlay._read_content(fake_tracking) == (), attribute
        assert tracker_overlay._window_content(fake_tracking) == [], attribute
with patch.object(fake_tracking, 'get_foreground_window', return_value=456):
    assert tracker_overlay._read_content(fake_tracking) == ()
with patch.object(fake_tracking, 'get_foreground_window', return_value=0):
    assert tracker_overlay._read_content(fake_tracking) == ()
with patch.object(fake_tracking.steam_overlay, 'has_overlay_indicators', return_value=True):
    assert tracker_overlay._read_content(fake_tracking) == ()
with patch.object(fake_tracking, 'get_foreground_window', side_effect=OSError('unavailable')):
    assert tracker_overlay._read_content(fake_tracking) == ()
with patch.object(fake_tracking.steam_overlay, 'has_overlay_indicators', side_effect=OSError('unavailable')):
    assert tracker_overlay._read_content(fake_tracking) == ()
assert tracker_overlay._read_content(fake_tracking) == ('test overlay',)

# Display policy uses independent foreground, window visibility and capture
# signals. These are all mocked: no real window is opened or inspected.
display_view = {'status': 'Running', 'labels': {'tracking': 'Tracker', 'capture_paused': 'Capture paused'}}
def set_display_policy(mode):
    tracker_overlay._set_state(('Running', 'Mode : Arena'), 'running',
                               options={'visibility_mode': mode, 'show_status': True}, view=display_view)

with patch.object(tracker_overlay.win32gui, 'FindWindow', return_value=123), \
     patch.object(tracker_overlay.win32gui, 'IsWindowVisible', return_value=True), \
     patch.object(tracker_overlay.win32gui, 'IsIconic', return_value=False):
    for policy in ('capture', 'game_visible', 'always'):
        set_display_policy(policy)
        content = tracker_overlay._window_content(fake_tracking)
        assert content['capture_active'] is True and content['view']['status'] == 'Running', policy
        assert tracker_overlay._read_content(fake_tracking) == content['lines']
    # A lost foreground hides only capture mode; other modes show a red state.
    with patch.object(fake_tracking, 'get_foreground_window', return_value=456):
        set_display_policy('capture')
        assert tracker_overlay._window_content(fake_tracking) == []
        for policy in ('game_visible', 'always'):
            set_display_policy(policy)
            content = tracker_overlay._window_content(fake_tracking)
            assert content['capture_active'] is False and content['view']['status'] == 'Capture paused', policy
            assert content['lines'][0] == 'Capture paused'
            assert display_view['status'] == 'Running'  # shared state was not changed
    # Steam overlay or stale/paused capture must turn the indicator red even
    # if Windows still considers the game window to be in the foreground.
    for context in (patch.object(fake_tracking.steam_overlay, 'has_overlay_indicators', return_value=True),
                    patch.object(fake_tracking, 'capture_available', False)):
        with context:
            set_display_policy('capture')
            assert tracker_overlay._window_content(fake_tracking) == []
            for policy in ('game_visible', 'always'):
                set_display_policy(policy)
                assert tracker_overlay._window_content(fake_tracking)['capture_active'] is False
    # Minimized or invisible game cannot produce capture, even if the last
    # foreground/capture readings are stale.
    for context in (patch.object(tracker_overlay.win32gui, 'IsWindowVisible', return_value=False),
                    patch.object(tracker_overlay.win32gui, 'IsIconic', return_value=True)):
        with context:
            for policy in ('capture', 'game_visible'):
                set_display_policy(policy)
                assert tracker_overlay._window_content(fake_tracking) == []
            set_display_policy('always')
            assert tracker_overlay._window_content(fake_tracking)['capture_active'] is False
    # A stopped, initialising or failed monitor may still be shown outside the
    # capture-only policy but cannot show a green indicator.
    for attribute, value in (('run_monitor', False), ('monitor_ready', False), ('monitor_error', True)):
        with patch.object(fake_tracking, attribute, value):
            set_display_policy('capture')
            assert tracker_overlay._window_content(fake_tracking) == []
            for policy in ('game_visible', 'always'):
                set_display_policy(policy)
                assert tracker_overlay._window_content(fake_tracking)['capture_active'] is False
    with patch.object(fake_tracking, 'get_foreground_window', side_effect=OSError('unavailable')):
        set_display_policy('capture')
        assert tracker_overlay._window_content(fake_tracking) == []
        set_display_policy('always')
        assert tracker_overlay._window_content(fake_tracking)['capture_active'] is False

for changes in ({'FindWindow': 0}, {'IsWindowVisible': False}, {'IsIconic': True}):
    with ExitStack() as contexts:
        contexts.enter_context(patch.object(tracker_overlay.win32gui, 'FindWindow', return_value=changes.get('FindWindow', 123)))
        contexts.enter_context(patch.object(tracker_overlay.win32gui, 'IsWindowVisible', return_value=changes.get('IsWindowVisible', True)))
        contexts.enter_context(patch.object(tracker_overlay.win32gui, 'IsIconic', return_value=changes.get('IsIconic', False)))
        contexts.enter_context(patch.object(fake_tracking, 'get_foreground_window', return_value=456))
        set_display_policy('game_visible')
        assert tracker_overlay._window_content(fake_tracking) == [], changes
        set_display_policy('always')
        assert tracker_overlay._window_content(fake_tracking)['capture_active'] is False, changes

with patch.object(tracker_overlay.win32gui, 'FindWindow', side_effect=OSError('unavailable')):
    set_display_policy('game_visible')
    assert tracker_overlay._window_content(fake_tracking) == []
    set_display_policy('always')
    assert tracker_overlay._window_content(fake_tracking)['capture_active'] is True
set_display_policy('unknown')
assert tracker_overlay._window_content(fake_tracking) == []
tracker_overlay._set_state((), 'disabled', options={'visibility_mode': 'always'})
assert tracker_overlay._window_content(fake_tracking) == []
tracker_overlay._set_state(('test overlay',), 'running', options={'visibility_mode': 'capture'})
snapshot = tracker_overlay.tracker_overlay_data.build_snapshot(
    language='eng', mode='Arena',
    session={'last': {'result': 'victory', 'mode': 'Arena', 'opponent': 'OLD_RESULT_OPPONENT'}},
    peers={'status': 'active', 'enabled': True,
           'peers': [{'name': f'Peer_{i:02}', 'ping': i * 10} for i in range(16)]})
message = 'detected event ' + 'message ' * 7
formatted = tracker_overlay._format(snapshot, message)
assert formatted[0] == snapshot['status_text']
assert snapshot['mode_text'] in formatted[1]
assert all(any(f'Peer_{i:02} · {i * 10} ms' == line for line in formatted) for i in range(16))
assert all('OLD_RESULT_OPPONENT' not in line for line in formatted)
assert snapshot['labels']['peers'] not in formatted
assert snapshot['labels']['last_event'] not in formatted
assert len(formatted[formatted.index('Peer_15 · 150 ms') + 1:]) == 2
assert 'detected event' in formatted[-2]
unknown_mode = tracker_overlay.tracker_overlay_data.build_snapshot(language='eng', mode='')
formatted_empty = tracker_overlay._format(unknown_mode, '')
assert unknown_mode['mode_text'] in formatted_empty[1]
assert unknown_mode['labels']['peers'] not in formatted_empty
assert unknown_mode['labels']['last_event'] not in formatted_empty
assert formatted_empty[-1] == unknown_mode['labels']['no_event']
for peer_status, peer_list, expected in [
        ('active', [], 0), ('active', [{'name': 'One'}, {'name': 'Two'}], 2),
        ('starting', [], None), ('disabled', [], None), ('game_closed', [], None),
        ('steam_unavailable', [], None), ('waiting_log', [], None), ('helper_error', [], None)]:
    count_snapshot = tracker_overlay.tracker_overlay_data.build_snapshot(
        language='eng', peers={'status': peer_status, 'enabled': peer_status != 'disabled', 'peers': peer_list})
    assert tracker_overlay._player_count(count_snapshot) == expected, peer_status
    count_lines = tracker_overlay._format(count_snapshot, '',
        {'show_status': False, 'show_mode': False, 'show_peers': False,
         'show_event': False, 'show_player_count': True})
    assert count_lines == [count_snapshot['labels']['player_count'] + ' : ' +
                           (str(expected) if expected is not None else '—')], peer_status
for peer_status, enabled in [('disabled', False), ('game_closed', True), ('starting', True),
                             ('helper_error', True), ('unexpected', True), ('active', False)]:
    stale = tracker_overlay.tracker_overlay_data.build_snapshot(language='eng', peers={
        'status': peer_status, 'enabled': enabled, 'peers': [{'name': 'Old'}]})
    assert tracker_overlay._player_count(stale) is None, (peer_status, enabled)
hidden = {'show_status': False, 'show_mode': False, 'show_peers': False, 'show_event': False}
assert tracker_overlay._format(snapshot, message, hidden) == []
for key, expected in [('show_status', snapshot['status_text']), ('show_mode', snapshot['mode_text']),
                      ('show_peers', 'Peer_00 · 0 ms'), ('show_event', 'detected event')]:
    only = dict(hidden, **{key: True})
    lines = tracker_overlay._format(snapshot, message, only)
    assert any(expected in line for line in lines), key
for language in ('fra', *tracker_overlay.tracker_overlay_data._packs()):
    localized = tracker_overlay.tracker_overlay_data.build_snapshot(language=language, running=True,
        ready=True, game_running=True, game_detected=True, fight=True)
    assert tracker_overlay._format(localized, '')[0] == localized['status_text'], language
# A small monitor still retains the most recent event at the bottom and makes
# omitted lines explicit rather than silently losing the event.
small_display = tracker_overlay.tracker_overlay_window._fit_lines(tuple(formatted), (0, 0, 800, 180))
assert small_display[-2:] == tuple(formatted[-2:])
assert any(line.startswith('… (+') for line in small_display)
with patch.dict(functions.array_stats, {'text': 'pending-event'}):
    tracker_overlay._read_content(fake_tracking)
    assert functions.array_stats['text'] == 'pending-event'
tracker_overlay_event.publish_html('Envahisseur arrivé')
with patch.object(tracker_overlay.overlay_settings, 'enabled', side_effect=[False, True, True, False]), \
     patch.object(tracker_overlay.overlay_settings, 'options', return_value=dict(tracker_overlay.overlay_settings.DEFAULT_OPTIONS, visibility_mode='capture')), \
     patch.object(tracker_overlay.tracker_overlay_window, 'OverlayWindow', side_effect=make_overlay), \
     patch.object(tracker_overlay.threading, 'Event', return_value=OverlayTestWait()):
    try:
        tracker_overlay._worker(fake_tracking)
    except StopIteration:
        pass
assert len(overlay_windows) == 1 and overlay_windows[0].started and overlay_windows[0].stopped
assert overlay_states[0] == ('disabled', ()) and overlay_states[-1] == ('disabled', ())
assert overlay_states[1][0] == 'running' and any('32 ms' in line for line in overlay_states[1][1])
assert any('Envahisseur arrivé' in line for line in overlay_states[1][1])
assert all('A' != line for line in overlay_states[1][1])
overlay_states.clear()
with patch.object(tracker_overlay.overlay_settings, 'enabled', side_effect=[True, True, True, False]), \
     patch.object(tracker_overlay.overlay_settings, 'options', return_value=dict(hidden)), \
     patch.object(fake_tracking.peer_tracking, 'passive_snapshot', side_effect=AssertionError('unexpected Steam read')), \
     patch.object(tracker_overlay.tracker_overlay_window, 'OverlayWindow', side_effect=make_overlay), \
     patch.object(tracker_overlay.threading, 'Event', return_value=OverlayTestWait()):
    try:
        tracker_overlay._worker(fake_tracking)
    except StopIteration:
        pass
assert overlay_states[0] == ('running', ())
overlay_states.clear()
class UnavailableOverlay(OverlayTestWindow):
    error = 'capture_exclusion_unavailable'
with patch.object(tracker_overlay.overlay_settings, 'enabled', side_effect=[True, True, False, False]), \
     patch.object(tracker_overlay.tracker_overlay_window, 'OverlayWindow', UnavailableOverlay), \
     patch.object(tracker_overlay.threading, 'Event', return_value=OverlayTestWait()):
    try:
        tracker_overlay._worker(fake_tracking)
    except StopIteration:
        pass
assert overlay_states[0] == ('capture_exclusion_unavailable', ())
assert overlay_states[-1] == ('disabled', ())
overlay_states.clear()
counted_peer = '76561198000000000'
count_options = dict(tracker_overlay.overlay_settings.DEFAULT_OPTIONS)
count_tracking = types.SimpleNamespace(**vars(fake_tracking))
count_tracking.peer_tracking = types.SimpleNamespace(
    passive_snapshot=lambda: {'status': 'active', 'enabled': True,
                              'peers': [{'id': counted_peer, 'name': 'Peer', 'ping': 42}]})
count_options['show_avatars'] = False
count_options['show_rank'] = False  # An obsolete saved rank value does not hide counts.
count_options['show_player_stats'] = True  # Preserve the legacy option name.
count_options['show_tracker_user'] = False  # Unrelated count tests make no member lookup.
with patch.object(tracker_overlay.overlay_settings, 'enabled', return_value=True), \
     patch.object(tracker_overlay.overlay_settings, 'options', return_value=count_options), \
     patch.object(tracker_overlay.tracker_overlay_window, 'OverlayWindow', side_effect=make_overlay), \
     patch.object(peer_rankings, 'locally_permitted', side_effect=AssertionError('ranking permission consulted')), \
     patch.object(peer_rankings, 'snapshot', side_effect=AssertionError('ranking requested')), \
     patch.object(tracker_overlay.steam_encounter_counts, 'snapshot', return_value={counted_peer: 9}) as lookup, \
     patch.object(tracker_overlay.threading, 'Event', return_value=OverlayTestWait()):
    try:
        tracker_overlay._worker(count_tracking)
    except StopIteration:
        pass
    assert lookup.call_args.args == ([counted_peer],)
    assert lookup.call_args.kwargs['enabled'] is True
    assert 'rank' not in tracker_overlay._view['cards'][0]
    assert tracker_overlay._view['cards'][0]['encounters'] == 9
    assert 'wins' not in tracker_overlay._view['cards'][0]
tracker_overlay._set_state((), 'disabled')
overlay_states.clear()
with patch.object(tracker_overlay.overlay_settings, 'enabled', return_value=True), \
     patch.object(tracker_overlay.overlay_settings, 'options', return_value=dict(count_options, show_rank=True, show_player_stats=False)), \
     patch.object(tracker_overlay.tracker_overlay_window, 'OverlayWindow', side_effect=make_overlay), \
     patch.object(peer_rankings, 'locally_permitted', side_effect=AssertionError('ranking permission consulted')), \
     patch.object(peer_rankings, 'snapshot', side_effect=AssertionError('ranking requested')), \
     patch.object(tracker_overlay.steam_encounter_counts, 'snapshot', return_value={}) as lookup, \
     patch.object(tracker_overlay.threading, 'Event', return_value=OverlayTestWait()):
    try:
        tracker_overlay._worker(count_tracking)
    except StopIteration:
        pass
    assert lookup.call_args.kwargs['enabled'] is False
    assert 'rank' not in tracker_overlay._view['cards'][0]
    assert 'wins' not in tracker_overlay._view['cards'][0]
tracker_overlay._set_state((), 'disabled')
overlay_states.clear()
count_options['visibility_mode'] = 'always'
with patch.object(tracker_overlay.overlay_settings, 'enabled', return_value=True), \
     patch.object(tracker_overlay.overlay_settings, 'options', return_value=count_options), \
     patch.object(tracker_overlay.tracker_overlay_window, 'OverlayWindow', side_effect=make_overlay), \
     patch.object(count_tracking, 'get_foreground_window', return_value=456), \
     patch.object(peer_rankings, 'locally_permitted', side_effect=AssertionError('ranking permission consulted')), \
     patch.object(peer_rankings, 'snapshot', side_effect=AssertionError('ranking requested')), \
     patch.object(tracker_overlay.steam_encounter_counts, 'snapshot', return_value={counted_peer: 0}) as lookup, \
     patch.object(tracker_overlay.threading, 'Event', return_value=OverlayTestWait()):
    try:
        tracker_overlay._worker(count_tracking)
    except StopIteration:
        pass
    assert lookup.call_args.kwargs['enabled'] is True
    assert tracker_overlay._view['cards'][0]['encounters'] == 0
tracker_overlay._set_state((), 'disabled')
overlay_states.clear()
with patch.object(tracker_overlay.overlay_settings, 'enabled', return_value=True), \
     patch.object(tracker_overlay.overlay_settings, 'options', return_value=dict(count_options, show_tracker_user=True)), \
     patch.object(tracker_overlay.tracker_overlay_window, 'OverlayWindow', side_effect=make_overlay), \
     patch.object(peer_rankings, 'tracker_members', return_value={counted_peer: True}) as members, \
     patch.object(tracker_overlay.steam_encounter_counts, 'snapshot', return_value={counted_peer: 0}), \
     patch.object(tracker_overlay.threading, 'Event', return_value=OverlayTestWait()):
    try:
        tracker_overlay._worker(count_tracking)
    except StopIteration:
        pass
    assert tracker_overlay._view['cards'][0]['tracker_member'] is True
    members.assert_called_with([counted_peer], enabled=True)
tracker_overlay._set_state((), 'disabled')
overlay_window_fixtures.close()
with tempfile.TemporaryDirectory() as overlay_temp, \
     patch.object(functions.peer_tracking, 'database_setting', str(Path(overlay_temp) / 'settings.db')), \
     patch.object(functions.peer_tracking, '_snapshot', {'status': 'active', 'peers': [{'name': 'B', 'ping': 32}]}), \
     patch.object(functions.peer_tracking.threading, 'Thread', side_effect=AssertionError('Steam supervisor started')):
    assert functions.peer_tracking.passive_snapshot()['peers'][0]['name'] == 'B'
    with closing(sqlite3.connect(functions.peer_tracking.database_setting)) as db, db:
        assert db.execute("SELECT name FROM sqlite_master WHERE name='steam_peers_setting'").fetchone() is None
        db.execute('CREATE TABLE steam_peers_setting (id INTEGER PRIMARY KEY, enabled INTEGER)')
        db.execute('INSERT INTO steam_peers_setting VALUES (1,0)')
    passive = functions.peer_tracking.passive_snapshot()
    assert passive['enabled'] is False and passive['status'] == 'disabled' and passive['peers'] == []

response = client.get('/', headers={'Accept-Language':'fr-FR,fr;q=0.9'})
assert response.status_code == 200

# App cards use observed roles and the shared local count, independently of
# overlay visibility. Neither card path may consult the remote ranking service.
peer_a = {'id': '76561198000000001', 'name': 'TestHunter', 'ping': 42,
          'average_ping': 48, 'quality': None, 'country_code': 'FR'}
peer_b = {'id': '76561198000000002', 'name': 'Other', 'ping': 88}
peer_snapshot = {'status': 'active', 'enabled': True, 'ping_mode': 'active', 'peers': [peer_a, peer_b]}
roles_for_app = type(functions.overlay_peer_roles)()
roles_for_app.update_peers('active', peer_snapshot['peers'])
roles_for_app.observe({'name': 'TestHunter', 'role': 'hunter', 'event': 'joined'})
with patch.object(functions.peer_tracking, 'snapshot', side_effect=lambda: dict(peer_snapshot)), \
     patch.object(functions, 'overlay_peer_roles', roles_for_app), \
     patch.object(functions, 'run_monitor', True), patch.object(functions, 'monitor_ready', True), \
     patch.object(functions, 'monitor_error', False), patch.object(functions, 'mode_detected', True), \
     patch.object(functions, 'mode_select', 'Defense'), patch.object(functions, 'fight', False), \
     patch.object(tracker_overlay, '_status', 'running'), \
     patch.object(functions.overlay_settings, 'options', return_value={'show_player_stats': True, 'show_tracker_user': False}), \
     patch.object(peer_rankings, 'locally_permitted', side_effect=AssertionError('ranking permission consulted')), \
     patch.object(peer_rankings, 'snapshot', side_effect=AssertionError('ranking requested')), \
     patch.object(functions.steam_encounter_counts, 'snapshot', return_value={peer_a['id']: 0, peer_b['id']: None}) as lookup:
    result = client.get('/steam-peers').get_json()
    assert result['mode_id'] == 'Defense' and len(result['peers']) == 2
    first, second = result['peers']
    assert (first['name'], first['ping'], first['country_code'], first['role']) == ('TestHunter', 42, 'FR', 'hunter')
    assert 'rank' not in first
    assert first['encounters'] == 0 and 'wins' not in first
    assert 'history_unverified' not in first and 'avatar' not in first
    assert second['role'] is None and 'rank' not in second and 'wins' not in second
    assert second['encounters'] is None
    assert 'role' not in peer_a and 'rank' not in peer_a
    lookup.assert_called_with([peer_a['id'], peer_b['id']], enabled=True)
    with patch.object(functions.overlay_settings, 'options', return_value={'show_player_stats': False, 'show_tracker_user': False}), \
         patch.object(functions.steam_encounter_counts, 'snapshot', return_value={}) as hidden_lookup:
        hidden = client.get('/steam-peers').get_json()['peers'][0]
        assert hidden['role'] == 'hunter' and hidden['encounters'] is None
        hidden_lookup.assert_called_once_with([peer_a['id'], peer_b['id']], enabled=False)
    with patch.object(functions, 'mode_select', 'Invasion'):
        changed = client.get('/steam-peers').get_json()
        assert changed['mode_id'] == 'Invasion' and 'rank' not in changed['peers'][0]
    with patch.object(functions, 'run_monitor', False):
        stopped = client.get('/steam-peers').get_json()
        assert stopped['mode_id'] == '' and all(peer['role'] is None for peer in stopped['peers'])
        assert all('rank' not in peer for peer in stopped['peers'])
    with patch.object(tracker_overlay, '_status', 'disabled'):
        no_overlay = client.get('/steam-peers').get_json()['peers'][0]
        assert no_overlay['role'] == 'hunter' and no_overlay['encounters'] == 0
    with patch.object(functions, 'mode_select', 'Arena'), patch.object(functions, 'fight', True), \
         patch.object(functions.steam_history, 'active_arena_participant_id', return_value=peer_a['id']):
        # A single matching peer can be the probable duelist; multiple peers cannot.
        multiple = client.get('/steam-peers').get_json()
        assert multiple['mode_id'] == 'Arena' and all(peer['role'] is None for peer in multiple['peers'])
        with patch.object(functions.peer_tracking, 'snapshot', return_value=dict(peer_snapshot, peers=[peer_a])):
            single = client.get('/steam-peers').get_json()
            assert single['peers'][0]['role'] == 'duelist'

# A badge is only attached to a positively matched SteamID, even when no mode
# has been detected. The source snapshot is not modified.
with patch.object(functions.peer_tracking, 'snapshot', side_effect=lambda: dict(peer_snapshot)), \
     patch.object(functions.overlay_settings, 'options', return_value={'show_player_stats': False, 'show_tracker_user': True}), \
     patch.object(functions.steam_encounter_counts, 'snapshot', return_value={}), \
     patch.object(peer_rankings, 'tracker_members', return_value={peer_a['id']: True}) as lookup, \
     patch.object(functions, 'mode_detected', False):
    result = client.get('/steam-peers').get_json()
    assert result['mode_id'] == ''
    assert result['peers'][0]['tracker_member'] is True
    assert 'tracker_member' not in result['peers'][1]
    assert 'tracker_member' not in peer_a
    lookup.assert_called_once_with([peer_a['id'], peer_b['id']], enabled=True)

with patch.object(functions.peer_tracking, 'enabled', return_value=True), \
     patch.object(functions.peer_tracking, 'avatar_png', return_value=b'fake-png') as avatar_reader:
    response_avatar = client.get('/steam-peer-avatar/76561198000000001')
    assert response_avatar.status_code == 200 and response_avatar.mimetype == 'image/png'
    assert response_avatar.headers['Cache-Control'] == 'no-store'
    assert client.get('/steam-peer-avatar/not-an-id').status_code == 404
    avatar_reader.assert_called_once_with('76561198000000001')
    assert module.app.test_client().get('/steam-peer-avatar/76561198000000001').status_code == 403
with patch.object(functions.peer_tracking, 'enabled', return_value=False), \
     patch.object(functions.peer_tracking, 'avatar_png') as avatar_reader:
    assert client.get('/steam-peer-avatar/76561198000000001').status_code == 404
    avatar_reader.assert_not_called()
tracker_overlay_event.clear()
with patch.dict(functions.array_stats, {'text': ''}), \
     patch.object(functions, 'record_detection', return_value=1), \
     patch.object(functions, 'localize_counter', side_effect=lambda text, language: text):
    functions.emit_tracking_event('<!--search-start-->Envahisseur arrivé : &lt;Joueur&gt;')
    assert tracker_overlay_event.latest() == 'Envahisseur arrivé : <Joueur>'
    assert '<!--search-start-->' in functions.array_stats['text']
    functions.emit_tracking_event('message technique', show_in_overlay=False)
    assert tracker_overlay_event.latest() == 'Envahisseur arrivé : <Joueur>'
    assert 'message technique' in functions.array_stats['text']
    functions.emit_tracking_event('Victoire<br> Time: 12 s', opponent='A & B', opponent_source='game', outcome='victory')
    assert 'A & B' in tracker_overlay_event.latest()
    assert 'Temps: 12 s' in tracker_overlay_event.latest(), repr(tracker_overlay_event.latest())
tracker_overlay_event.clear()
assert init.get_selected_language() == 'fra'
with patch.object(functions, 'langue_select', 'eng'), \
     patch.dict(functions.array_stats, {'text': ''}), \
     patch.object(functions, 'record_detection', return_value=1):
    functions.emit_tracking_event('Invocation de l’allié…')
    assert tracker_overlay_event.latest() == tracker_overlay_event._plain_text(
        functions.localize_counter('Invocation de l’allié…', 'eng'))
    assert tracker_overlay_event.latest() != 'Invocation de l’allié…'
    for language in ('fra', *functions.ui_packs()):
        assert tracker_overlay_event.latest(language) == tracker_overlay_event._plain_text(
            functions.localize_counter('Invocation de l’allié…', language)), language
    functions.emit_tracking_event('Victoire<br> Time: 12 s', opponent='A & B', opponent_source='game', outcome='victory')
    for language in ('fra', *functions.ui_packs()):
        value = tracker_overlay_event.latest(language)
        assert 'A & B' in value
        expected = 'Temps' if language == 'fra' else functions.ui_packs()[language]['modern']['time']
        assert expected + ': 12 s' in value, (language, value)
    with patch.object(functions, 'correspondly_active', functions.ui_packs()['eng']['backend']):
        functions.emit_tracking_event(functions.ui_packs()['eng']['backend'][9])
        for language in ('fra', *functions.ui_packs()):
            backend = functions.correspondly_fr if language == 'fra' else functions.ui_packs()[language]['backend']
            assert tracker_overlay_event.latest(language) == tracker_overlay_event._plain_text(backend[9]), language
tracker_overlay_event.clear()
assert functions.game_locale in functions.game_language.LANGUAGES
original_game = functions.game_locale
assert client.post('/interface-language', data={'language':'eng'}).status_code == 200
assert functions.game_locale == original_game
assert client.post('/game-language', data={'language':'frafr'}).status_code == 200
assert init.get_selected_language() == 'eng'
assert client.get('/game-language').json['language'] == 'frafr'
assert client.get('/interface-language').json['language'] == 'eng'
assert client.post('/interface-language', data={'language':'unknown'}).status_code == 400
assert client.post('/game-language', data={'language':'nld'}).status_code == 400
assert client.get('/', headers={'Accept-Language':'de-DE'}).status_code == 200
assert init.get_selected_language() == 'eng'
assert functions.game_language.selected('eng') == 'frafr'
with patch.object(functions, 'fight', True):
    assert client.post('/game-language', data={'language':'engus'}).status_code == 409
    assert client.post('/interface-language', data={'language':'fra'}).status_code == 200
    assert functions.game_locale == 'frafr'
assert client.post('/interface-language', data={'language':'eng'}).status_code == 200
new_ui_languages = {'ukr', 'ces', 'ron', 'hun', 'ell', 'swe', 'dan', 'nor', 'fin', 'ind', 'vie', 'hin', 'ptpt'}
assert new_ui_languages.issubset({item['id'] for item in client.get('/interface-language').json['languages']})
for language in new_ui_languages:
    assert client.post('/interface-language', data={'language':language}).status_code == 200
    assert client.get('/interface-language').json['language'] == language
    assert functions.game_locale == 'frafr'
assert client.post('/interface-language', data={'language':'eng'}).status_code == 200
with patch.object(module, 'accessible_data_directories', return_value=[Path('first'), Path('second')]), \
     patch.object(module.os, 'startfile') as open_folder:
    module.open_data_folder(None, None)
    assert [call.args[0] for call in open_folder.call_args_list] == [Path('first'), Path('second')]
assert b'data-store-build="false"' in response.data
assert ('data-i18n-title="environment_tracker">' + APP_VERSION + '</h5>').encode() in response.data
assert client.get('/', headers={'Host':'127.0.0.1:5000', 'Origin':'http://127.0.0.1:5000', 'Sec-Fetch-Site':'same-origin'}).status_code == 200
assert client.get('/exit', headers={'Origin':'https://example.com', 'Sec-Fetch-Site':'cross-site'}).status_code == 403
assert client.get('/start', headers={'Referer':'http://localhost:1234/'}).status_code == 403
assert client.get('/', headers={'Host':'attacker.example:5000'}).status_code == 403
assert client.get('/', headers={'Host':'elden-tracker.localhost', 'Sec-Fetch-Site':'none'}).status_code == 200
with patch.object(module, 'interface_url', 'http://elden-tracker.localhost/'):
    redirected = client.get('/', headers={'Host':'localhost:5000'})
    assert redirected.status_code == 302 and redirected.headers['Location'] == 'http://elden-tracker.localhost/'
assert client.post('/interface-mode', headers={'Host':'elden-tracker.localhost', 'Origin':'https://attacker.example', 'Sec-Fetch-Site':'cross-site'}, data={'mode':'window'}).status_code == 403
assert client.get('/preference-migration', headers={'Host':'localhost:5000'}).status_code == 403
frame = client.get('/preference-migration', headers={'Host':'localhost:5000', 'Sec-Fetch-Dest':'iframe'})
assert frame.status_code == 200 and 'frame-ancestors http://elden-tracker.localhost' in frame.headers['Content-Security-Policy']
assert client.get('/interface-mode').get_json()['mode'] == 'browser'
assert client.post('/interface-mode', data={'mode':'unknown'}).status_code == 400
with patch.object(module.interface_mode, 'open_interface') as launch, patch.object(module.icon, 'update_menu'):
    assert client.post('/interface-mode', data={'mode':'window'}).get_json()['mode'] == 'window'
    launch.assert_called_once_with(module.interface_url, 'window')
    assert client.get('/interface-mode').get_json()['mode'] == 'window'
    launch.side_effect = RuntimeError('unavailable')
    assert client.post('/interface-mode', data={'mode':'browser'}).status_code == 503
    assert module.interface_mode.get_mode() == 'window'
    module.interface_mode.set_mode('browser')
with patch.object(module.interface_mode, 'browser_executable', return_value='C:/test/chrome.exe'), \
     patch.object(module.interface_mode, '_app_windows', return_value=set()), \
     patch.object(module.interface_mode.threading, 'Thread') as worker, \
     patch.object(module.interface_mode.subprocess, 'Popen') as process:
    module.interface_mode.open_interface('http://elden-tracker.localhost/', 'window')
    assert process.call_args.args[0] == ['C:/test/chrome.exe', '--start-maximized', '--app=http://elden-tracker.localhost/']
    worker.return_value.start.assert_called_once()
with patch.object(module.interface_mode, 'browser_executable', return_value=None):
    try:
        module.interface_mode.open_interface('http://elden-tracker.localhost/', 'window')
        raise AssertionError('A missing browser must be reported')
    except RuntimeError:
        pass
anonymous = module.app.test_client(use_cookies=False)
assert anonymous.get('/modeStats').status_code == 403
assert anonymous.post('/history-purge').status_code == 403
assert anonymous.post('/initialization-notice').status_code == 403
assert anonymous.post('/initialization-error-log').status_code == 403
assert anonymous.post('/error-log/open').status_code == 403
assert anonymous.post('/tracker-presence/active').status_code == 403
with patch('application.tracker_presence.notify_browser') as pulse:
    assert client.post('/tracker-presence/active').status_code == 204
    pulse.assert_called_once()
with patch('application.error_log.open_log', return_value=True) as opened:
    assert client.post('/error-log/open').get_json()['opened'] is True
    opened.assert_called_once()
with patch('application.error_log.open_log', return_value=False):
    assert client.post('/error-log/open').status_code == 404
with patch.object(module.first_run, 'claim', return_value={'state':'ready', 'log_available':False}):
    assert client.post('/initialization-notice').get_json()['notice']['state'] == 'ready'
with patch.object(module.first_run, 'open_log', return_value=True) as opened:
    assert client.post('/initialization-error-log').get_json()['opened'] is True
    opened.assert_called_once()
if module.first_run.read_status().get('state') == 'pending':
    with closing(module.usage_metrics._connect()):
        pass
    module.first_run.finish()
    assert client.post('/initialization-notice').get_json()['notice'] == {'state':'ready', 'log_available':False}
    assert client.post('/initialization-notice').get_json()['notice'] is None
assert anonymous.get('/monitor-status').status_code == 200
cookie_response = anonymous.get('/')
assert 'HttpOnly' in cookie_response.headers['Set-Cookie'] and 'SameSite=Strict' in cookie_response.headers['Set-Cookie']
for path in ('/start', '/stop', '/exit', '/interval', '/capture', '/nextCaptures'):
    assert client.head(path).status_code == 405
for path in ('/start', '/stop', '/exit'):
    assert client.get(path).status_code == 405
assert client.get('/monitor-status').get_json()['running'] is False
assert client.get('/monitor-status').get_json()['instance'] == module.app.config['TRACKER_INSTANCE_ID']
security_response = client.get('/monitor-status')
assert security_response.headers['Cache-Control'] == 'no-store'
assert security_response.headers['X-Frame-Options'] == 'DENY'
assert security_response.headers['X-Content-Type-Options'] == 'nosniff'
assert client.post('/profile-legend', data=b'x' * (2 * 1024 * 1024 + 1), content_type='application/json').status_code == 413
for store_build in (False, True):
    with patch.object(functions, 'STORE_BUILD', store_build):
        response = client.get('/init')
        assert response.status_code == 200
        assert response.get_json()['development_build'] is (not store_build)
state = client.get('/interval').get_json()
assert state['fight'] is False and state['monitor_running'] is False

# Starting has to wait for a confirmed capture, and stopping hides it again.
with patch.object(functions.peer_tracking, 'request_auto_ping'), \
     patch.object(functions.peer_tracking, 'cancel_auto_ping'), \
     patch.object(functions.threading, 'Thread') as monitor_thread, \
     patch('application.tracker_presence.notify_tracking'):
    functions.capture_available = True
    assert client.post('/start').get_json()['request'] == 'success'
    assert functions.capture_available is False
    monitor_thread.return_value.start.assert_called_once()
    functions.capture_available = True
    assert client.post('/stop').get_json()['request'] == 'success'
    assert functions.capture_available is False
    functions.monitor_lock.release()  # The mocked monitor does not run its finally block.

with patch.object(functions, 'capture', 'synthetic-preview'):
    assert client.get('/interval').get_json()['capture'] == 'synthetic-preview'
    assert client.get('/interval', headers={'X-Tracker-Light':'1'}).get_json()['capture'] == ''

# Separate pages must not steal one another's live messages, and two identical
# events are distinct even when no different message appears in between.
with patch.object(functions, 'tracking_events', functions.deque(maxlen=512)), \
     patch.object(functions, 'tracking_event_sequence', 0), \
     patch.object(functions, 'array_stats', dict(functions.array_stats, text='')), \
     patch.object(functions, 'tampo_text', ''), \
     patch.object(functions, 'record_detection', return_value=1), \
     patch.object(functions.tracker_overlay_event, 'publish_html'):
    second_client = module.app.test_client()
    assert second_client.get('/').status_code == 200
    functions.emit_tracking_event('synthetic-event')
    first = client.get('/interval', headers={'X-Tracker-Events-After':'0'}).get_json()
    second = second_client.get('/interval', headers={'X-Tracker-Events-After':'0'}).get_json()
    assert first['datas']['text'] == second['datas']['text'] == 'synthetic-event'
    assert first['events_cursor'] == second['events_cursor'] == 1
    assert client.get('/interval', headers={'X-Tracker-Events-After':'1'}).get_json()['datas']['text'] == ''
    functions.emit_tracking_event('synthetic-event')
    assert client.get('/interval', headers={'X-Tracker-Events-After':'1'}).get_json()['datas']['text'] == 'synthetic-event'
    assert second_client.get('/interval', headers={'X-Tracker-Events-After':'1'}).get_json()['datas']['text'] == 'synthetic-event'
    assert client.get('/interval', headers={'X-Tracker-Events-After':'-1'}).status_code == 400
    assert client.get('/interval', headers={'X-Tracker-Events-After':'invalid'}).status_code == 400

# The Windows overlay signals gate capture without a separate Steam screenshot.
# The first frame attempt is interrupted before any real images or OCR are used.
for foreground, blocked, expected in ((True, False, True), (False, False, False), (True, True, False)):
    detector = types.SimpleNamespace(capture_blocked=blocked, update=lambda *a, **kw: blocked)
    game_window = types.SimpleNamespace(title='ELDEN RING™', _hWnd=123)
    window_id = 123 if foreground else 456
    with ExitStack() as stack:
        for key, value in (('run_monitor', True), ('monitor_ready', False), ('game_running', None),
                           ('game_detected', True), ('steam_overlay_open', False), ('capture_available', False),
                           ('count', 0), ('cout_total', 0), ('fight', False), ('capture_interval_seconds', 0),
                           ('width_screen', 1366), ('height_screen', 768)):
            stack.enter_context(patch.object(functions, key, value))
        for mocked in (
                patch.object(functions, 'emit_tracking_event'),
                patch.object(functions, 'update_game_display', side_effect=[None, functions._CaptureStopped()]),
                patch.object(functions.pygetwindow, 'getAllWindows', return_value=[game_window]),
                patch.object(functions, 'get_foreground_window', return_value=window_id),
                patch.object(functions, 'get_window_text', return_value='ELDEN RING™' if foreground else 'Other'),
                patch.object(functions.steam_overlay, 'OverlayDetector', return_value=detector),
                patch.object(functions.steam_overlay, 'is_steam_overlay_window', return_value=False)):
            stack.enter_context(mocked)
        screenshot = stack.enter_context(patch.object(functions, 'screenshot_with_retry', side_effect=functions._CaptureStopped()))
        try:
            functions.monitor(None)
        except functions._CaptureStopped:
            pass
        else:
            raise AssertionError('Expected synthetic capture interruption')
        assert functions.capture_available is expected, (foreground, blocked)
        assert screenshot.call_count == int(expected), (foreground, blocked, screenshot.call_count)

# A blocked secure desktop must never cause a false game-closed result.
with ExitStack() as stack:
    for key, value in (('run_monitor', True), ('fight', True), ('mode_select', 'Invasion'),
                       ('game_detected', True), ('count', 0), ('capture_interval_seconds', 0)):
        stack.enter_context(patch.object(functions, key, value))
    for mocked in (patch.object(functions, 'emit_tracking_event'), patch.object(functions, 'update_game_display'),
                   patch.object(functions.pygetwindow, 'getAllWindows', return_value=[]),
                   patch.object(functions, 'screenshot_with_retry', side_effect=functions._CaptureStopped())):
        stack.enter_context(mocked)
    score = stack.enter_context(patch.object(functions, 'apply_score'))
    try:
        functions.monitor(None)
    except functions._CaptureStopped:
        pass
    else:
        raise AssertionError('Expected blocked screen capture')
    score.assert_not_called()
    assert functions.fight is True

# Windows may restore the game while the secure-desktop probe waits.
game_window = types.SimpleNamespace(title='ELDEN RING™', _hWnd=123)
with ExitStack() as stack:
    for key, value in (('run_monitor', True), ('fight', True), ('mode_select', 'Invasion'),
                       ('game_detected', True), ('count', 0), ('capture_interval_seconds', 0)):
        stack.enter_context(patch.object(functions, key, value))
    for mocked in (patch.object(functions, 'emit_tracking_event'),
                   patch.object(functions, 'update_game_display', side_effect=[None, functions._CaptureStopped()]),
                   patch.object(functions.pygetwindow, 'getAllWindows', side_effect=[[], [game_window]]),
                   patch.object(functions, 'screenshot_with_retry', return_value=Image.new('RGB', (1, 1))),
                   patch.object(functions, 'get_foreground_window', return_value=456),
                   patch.object(functions, 'get_window_text', return_value='Other'),
                   patch.object(functions.steam_overlay, 'OverlayDetector', return_value=types.SimpleNamespace(capture_blocked=False, update=lambda *a, **kw: False)),
                   patch.object(functions.steam_overlay, 'is_steam_overlay_window', return_value=False)):
        stack.enter_context(mocked)
    score = stack.enter_context(patch.object(functions, 'apply_score'))
    try:
        functions.monitor(None)
    except functions._CaptureStopped:
        pass
    else:
        raise AssertionError('Expected synthetic iteration interruption')
    score.assert_not_called()
    assert functions.fight is True and functions.game_running is True

# When the screen is accessible and the game remains absent, record closure.
with ExitStack() as stack:
    for key, value in (('run_monitor', True), ('fight', True), ('mode_select', 'Invasion'),
                       ('game_detected', False), ('count', 0), ('capture_interval_seconds', 0)):
        stack.enter_context(patch.object(functions, key, value))
    for mocked in (patch.object(functions, 'emit_tracking_event'), patch.object(functions, '_seal_pvp_participant'),
                   patch.object(functions, 'update_game_display', side_effect=[None, functions._CaptureStopped()]),
                   patch.object(functions.pygetwindow, 'getAllWindows', return_value=[]),
                   patch.object(functions, 'screenshot_with_retry', return_value=Image.new('RGB', (1, 1))),
                   patch.object(functions, 'get_foreground_window', return_value=456),
                   patch.object(functions.steam_overlay, 'OverlayDetector', return_value=types.SimpleNamespace(capture_blocked=False, update=lambda *a, **kw: False))):
        stack.enter_context(mocked)
    score = stack.enter_context(patch.object(functions, 'apply_score'))
    try:
        functions.monitor(None)
    except functions._CaptureStopped:
        pass
    else:
        raise AssertionError('Expected synthetic iteration interruption')
    score.assert_called_once_with(0, 0, 0, 0, 0, 0, 0, 0, 1)
    assert functions.fight is False and functions.game_running is False

# A monitor error remains visible even when its log cannot be written.
with tempfile.TemporaryDirectory(dir=os.environ['APPDATA']) as directory:
    blocked_parent = Path(directory) / 'not-a-directory'
    blocked_parent.write_text('fixture', encoding='utf-8')
    with patch.object(functions, 'monitor', side_effect=RuntimeError('<capture> failed')), \
         patch.object(functions, 'data_dir', return_value=blocked_parent / 'logs'), \
         patch.object(functions, 'record_detection'), \
         patch.object(functions.tracker_notifications, 'notify') as notify:
        assert functions.monitor_lock.acquire(blocking=False)
        functions.run_monitor = True
        functions.capture_available = True
        functions._run_monitor()
        assert functions.capture_available is False
        error_state = client.get('/interval').get_json()
        assert error_state['monitor_error'] is True
        assert error_state['monitor_error_detail'] == 'RuntimeError: <capture> failed'
        notify.assert_called_once_with('monitor_error', 'RuntimeError: <capture> failed')
    functions.monitor_error = False
    functions.monitor_error_detail = ''
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
with patch.object(functions, 'run_monitor', True), patch.object(functions, 'active_capture_display', display), \
     patch.object(functions, 'capture_available', True), \
     patch.object(functions.capture_display, 'capture', side_effect=[OSError('screen grab failed'), 'fake']), \
     patch.object(functions.time, 'sleep', side_effect=lambda _: None):
    assert functions.screenshot_with_retry('fake.jpg') == 'fake'
    assert functions.capture_available is False
assert client.get('/auto-game-start').get_json()['enabled'] is False
with patch.object(functions.peer_tracking, 'snapshot', return_value={'status':'active', 'peers':[], 'enabled':True}) as peer_snapshot, \
     patch.object(functions, 'run_monitor', True), patch.object(functions, 'fight', True), \
     patch.object(functions, 'mode_select', 'Invasion'), patch.object(functions, 'opponent_name', 'Hôte Jeu'), \
     patch.object(functions, 'invasion_host_peer_id', None):
    assert client.get('/steam-peers').get_json()['world_host'] == {'name':'Hôte Jeu', 'peer_id':None}
    peer_snapshot.return_value['peers'] = [{'id':'76561198000000001'}, {'id':'76561198000000002'}]
    assert client.get('/steam-peers').get_json()['world_host']['peer_id'] == '76561198000000001'
    peer_snapshot.return_value['peers'].reverse()
    assert client.get('/steam-peers').get_json()['world_host']['peer_id'] == '76561198000000001'
    peer_snapshot.return_value['peers'] = [{'id':'76561198000000002'}]
    assert client.get('/steam-peers').get_json()['world_host']['peer_id'] == '76561198000000001'
    with patch.object(functions, 'mode_select', 'Defense'):
        assert client.get('/steam-peers').get_json()['world_host'] is None
    with patch.object(functions, 'fight', False):
        assert client.get('/steam-peers').get_json()['world_host'] is None
assert client.post('/auto-game-start', data={'enabled':'true'}).get_json()['enabled'] is True
assert client.post('/auto-game-start', data={'enabled':'invalid'}).status_code == 400
assert client.post('/auto-game-start', data={'enabled':'false'}).get_json()['enabled'] is False
from application import tracker_overlay
with patch.object(tracker_overlay, 'status', return_value='capture_exclusion_unavailable'):
    overlay = client.get('/overlay-settings').get_json()
    original_overlay_enabled = overlay['enabled']
    assert overlay['status'] == 'capture_exclusion_unavailable'
    assert client.post('/overlay-settings', data={'enabled':'true'}).get_json()['enabled'] is True
    assert client.post('/overlay-settings', data={'enabled':'invalid'}).status_code == 400
    assert client.get('/overlay-settings').get_json()['enabled'] is True
    assert client.post('/overlay-settings', data={'enabled':'false'}).get_json()['enabled'] is False
    assert client.get('/overlay-settings').get_json()['enabled'] is False
    assert client.post('/overlay-settings', data={'enabled':str(original_overlay_enabled).lower()}).get_json()['enabled'] is original_overlay_enabled
    original_options = overlay['options']
    for show_border in (False, True, False):
        saved = client.post('/overlay-settings', json={'options': {'show_overlay_border': show_border}})
        assert saved.status_code == 200 and saved.json['options']['show_overlay_border'] is show_border
        assert client.get('/overlay-settings').json['options']['show_overlay_border'] is show_border
    invalid = client.post('/overlay-settings', json={'options': {'show_overlay_border': 'false', 'font_size': 12}})
    assert invalid.status_code == 400
    assert client.get('/overlay-settings').json['options']['show_overlay_border'] is False
    assert client.get('/overlay-settings').json['options']['font_size'] == original_options['font_size']
    for width in (60, 75, 100):
        saved_width = client.post('/overlay-settings', json={'options': {'width_percent': width}})
        assert saved_width.status_code == 200 and saved_width.json['options']['width_percent'] == width
        assert client.get('/overlay-settings').json['options']['width_percent'] == width
    for invalid_width in (59, 101, True, 75.5, '75'):
        invalid = client.post('/overlay-settings', json={'options': {'width_percent': invalid_width, 'font_size': 12}})
        assert invalid.status_code == 400
        assert client.get('/overlay-settings').json['options']['width_percent'] == 100
        assert client.get('/overlay-settings').json['options']['font_size'] == original_options['font_size']
    patch_options = {'font_size': 24, 'background_opacity': 25, 'show_mode': False, 'text_color': '#c0ffee',
                     'text_opacity': 32, 'border_radius': 30, 'border_color': '#123456'}
    response = client.post('/overlay-settings', json={'options': patch_options})
    assert response.status_code == 200
    assert all(response.json['options'][key] == value for key, value in patch_options.items())
    invalid = client.post('/overlay-settings', json={'options': {'font_size': 100, 'show_mode': True}})
    assert invalid.status_code == 400
    assert client.get('/overlay-settings').json['options']['show_mode'] is False
    invalid_border = client.post('/overlay-settings', json={'options': {'border_radius': 31, 'border_color': '#abcdef'}})
    assert invalid_border.status_code == 400
    saved_border = client.get('/overlay-settings').json['options']
    assert saved_border['border_radius'] == 30 and saved_border['border_color'] == '#123456'
    invalid_opacity = client.post('/overlay-settings', json={'options': {'text_opacity': 101, 'border_radius': 0}})
    assert invalid_opacity.status_code == 400
    assert client.get('/overlay-settings').json['options']['text_opacity'] == 32
    assert client.get('/overlay-settings').json['options']['border_radius'] == 30
    for visibility in ('capture', 'game_visible', 'always'):
        result = client.post('/overlay-settings', json={'options': {'visibility_mode': visibility}})
        assert result.status_code == 200 and result.json['options']['visibility_mode'] == visibility
        assert client.get('/overlay-settings').json['options']['visibility_mode'] == visibility
        assert result.json['options']['show_mode'] is False
    invalid = client.post('/overlay-settings', json={'options': {'visibility_mode': 'unknown', 'show_mode': True}})
    assert invalid.status_code == 400
    saved = client.get('/overlay-settings').json['options']
    assert saved['visibility_mode'] == 'always' and saved['show_mode'] is False
    assert client.post('/overlay-settings', json={'options': original_options}).status_code == 200
with patch.dict(functions.array_stats, {'text':'pending-event'}):
    assert client.get('/monitor-status').get_json()['running'] is False
    assert functions.array_stats['text'] == 'pending-event'
assert client.post('/capture-speed', data={'interval': '2'}).get_json()['interval'] == 2.0
assert client.post('/capture-speed', data={'interval': '999'}).status_code == 400
# Publish each preview frame and its own detected box atomically; changing
# images must never consume tracking events or retain an old rectangle.
with patch.object(functions, 'run_monitor', True), patch.object(functions, 'game_detected', True), \
     patch.object(functions, 'capture_revision', 90), patch.object(functions, 'capture', 'fake-frame'), \
     patch.object(functions, 'preview_notification_box', None), patch.object(functions, 'preview_notification_version', 3):
    assert functions._publish_preview_frame('next-frame', (.1, .2, .8, .4))
    before = dict(functions.array_stats)
    preview = client.get('/live-preview?after=90&boxAfter=3&wait=1').get_json()
    assert preview['capture'] == 'next-frame' and preview['boxVersion'] == 4
    assert preview['notification'] == {'frame':91, 'box':[.1, .2, .8, .4]}
    assert functions.array_stats == before
    assert functions._publish_preview_frame('following-frame', None)
    assert client.get('/live-preview?after=91').get_json()['notification'] is None
    with patch.object(functions, 'game_detected', False):
        assert not functions._publish_preview_frame('hidden-frame', (.1, .2, .8, .4))
        assert client.get('/live-preview?after=90').get_json()['notification'] is None
    with patch.object(functions, 'run_monitor', False):
        assert not functions._publish_preview_frame('stopped-frame', (.1, .2, .8, .4))
        assert client.get('/live-preview?after=90').get_json()['notification'] is None
assert client.get('/live-preview?boxAfter=invalid').status_code == 400
with patch.object(functions, 'run_monitor', True), patch.object(functions, 'monitor_ready', False), \
     patch.object(functions, 'game_running', None):
    status = client.get('/live-preview').get_json()
    assert status['monitorRunning'] is True and status['monitorReady'] is False
    assert status['gameRunning'] is None
    with patch.object(functions, 'monitor_ready', True), patch.object(functions, 'game_running', False):
        status = client.get('/live-preview?after=' + str(status['revision']) + '&wait=1&ready=0').get_json()
        assert status['monitorReady'] is True and status['gameRunning'] is False
synthetic_frame = np.zeros((100, 200), dtype=np.uint8)
synthetic_box = (.2, .3, .6, .5)
sampled_pixels = functions._preview_box_pixels(synthetic_frame, synthetic_box)
synthetic_frame[0, 0] = 255
assert np.array_equal(sampled_pixels, functions._preview_box_pixels(synthetic_frame, synthetic_box))
synthetic_frame[35, 50] = 255
assert not np.array_equal(sampled_pixels, functions._preview_box_pixels(synthetic_frame, synthetic_box))
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
    events = functions.classify(event_text, 'frafr')
    assert not functions._notification_localization_needed([], 'frafr', False, None)
    assert functions._notification_localization_needed(events, 'frafr', False, None)
    assert not functions._notification_localization_needed(events, 'frafr', True, None)
    assert not functions._notification_localization_needed(events, 'frafr', False, (.2, .7))
    changed_events = functions.classify(messages()['frafr']['2341413'].replace('<?matchRemainingCount?>', '2'), 'frafr')
    assert functions._notification_localization_needed(changed_events, 'frafr', False, (.2, .7))
    assert functions._notification_localization_needed(events, 'engus', False, (.2, .7))
    with patch.object(functions, 'notification_event_sample', {'identity':None}):
        assert functions._notification_localization_needed(events, 'frafr', False, (.2, .7))
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
    assert not unlocked['locked'] and (unlocked['top'], unlocked['bottom']) == (0.0,1.0)
    relocked = client.post('/notification-region', data={'locked':'true', 'preview_id':'2'}).get_json()
    assert relocked['locked'] and (relocked['top'], relocked['bottom']) == (.1,.9)
    # A two-line, readable event is required; temporary window loss must not
    # discard the lock, while a real window or display change must do so.
    functions.notification_region.set_locked_bounds(None)
    functions.notification_locked_bounds = None
    geometry = ['DISPLAY1', 0, 0, 1920, 1080, 0, 0, 1920, 1080, 0]
    functions.current_game_geometry = geometry
    assert not functions._auto_lock_notification({'bounds':(.2,.7), 'lines':1}, True)
    assert not functions._auto_lock_notification({'bounds':(.2,.7), 'lines':2}, False)
    assert functions._auto_lock_notification({'bounds':(.2,.7), 'lines':2}, True)
    assert functions.notification_region.load_lock_context() == geometry
    display = {'name':'DISPLAY1','x':0,'y':0,'width':1920,'height':1080}
    with patch.object(functions.capture_display, 'game_display', side_effect=[None, display, display]), \
         patch.object(functions.capture_display, 'game_geometry', side_effect=[geometry, geometry[:-1] + [1]]):
        functions.update_game_display()
        assert functions.notification_locked_bounds == (.2,.7)
        functions.update_game_display()
        assert functions.notification_locked_bounds == (.2,.7)
        functions.update_game_display()
        assert functions.notification_locked_bounds is None
        assert functions.notification_region.load_locked_bounds() is None
    # Keep the existing persistence assertion for the encrypted sample.
    functions.notification_region.set_locked_bounds((.1,.9))
    functions.notification_locked_bounds = (.1,.9)
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
    positioned['left'] = [100 + 12 * i for i in range(len(positioned['text']))]
    positioned['width'] = [10] * len(positioned['text'])
    detected_box = functions.notification_region.analyze_notification(positioned, 1000, locale, image_width=1500)
    assert detected_box and len(detected_box['box']) == 4, locale
    left, top, right, bottom = detected_box['box']
    assert 0 <= left < right <= 1 and 0 <= top < bottom <= 1, locale
    assert left <= 100 / 1500 and top < .52 and bottom > .585, locale
    # In a narrow locked crop, the original frame height still determines
    # whether two recognized lines are close enough to form one message.
    cropped = dict(positioned, top=[value - 505 for value in positioned['top']])
    crop_image = np.full((120, 1500), 128, dtype=np.uint8)
    localized = functions.locate_notification_crop(cropped, crop_image, 1000, 505, locale)
    assert localized and localized['lines'] == 2 and localized.get('box'), locale
    assert localized['box'][1] < .52 and localized['box'][3] > .585, locale
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
with patch.object(functions.ocr_runner, 'image_to_string', return_value='ok'):
    assert functions.measured_game_ocr(None) == 'ok'
with patch.object(functions.ocr_runner, 'image_to_string', side_effect=RuntimeError('ocr')):
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

# A single OCR invocation supplies both text and positions for the chosen zone.
words = {'text':['Vous', 'avez', 'gagné', 'Deuxième', 'ligne'],
         'block_num':[1, 1, 1, 1, 1], 'par_num':[1, 1, 1, 1, 1], 'line_num':[1, 1, 1, 2, 2]}
with patch.object(functions.ocr_runner, 'image_to_data', return_value=words) as read:
    text, data = functions.recognize_game_frame('notification crop', 'fra', '')
    assert text == 'Vous avez gagné\nDeuxième ligne' and data is words
    read.assert_called_once_with('notification crop', lang='fra', config='--psm 6 --oem 1')
with patch.object(functions.ocr_runner, 'image_to_data', side_effect=RuntimeError('OCR failed')):
    try:
        functions.recognize_game_frame('notification crop', 'fra', '')
        assert False, 'OCR error was lost'
    except RuntimeError as error:
        assert str(error) == 'OCR failed'
with patch.object(functions.notification_region, 'analyze_notification',
                  return_value={'bounds':(.2, .6), 'box':(.1, .25, .9, .5), 'lines':2}):
    located = functions.locate_notification_crop({}, np.zeros((200, 300), dtype=np.uint8), 500, 100, 'frafr')
    assert located['bounds'] == (.28, .44)
    assert located['box'] == (.1, .3, .9, .4)

# Real Tesseract reads the selected synthetic notification with one pass.
from PIL import ImageDraw, ImageFont
font_path = Path(os.environ.get('WINDIR', r'C:\Windows')) / 'Fonts' / 'arial.ttf'
if Path(runtime_paths.tesseract_path()).is_file() and font_path.is_file():
    for locale, model in [('frafr', 'fra'), ('engus', 'eng')]:
        if not (root / 'application' / 'locales' / 'tessdata' / (model + '.traineddata')).is_file():
            continue
        picture = Image.new('RGB', (1000, 240), 'white')
        ImageDraw.Draw(picture).text((20, 80), messages()[locale]['arena:88050'],
                                     fill='black', font=ImageFont.truetype(str(font_path), 48))
        gray = functions.cv2.cvtColor(np.array(picture), functions.cv2.COLOR_RGB2GRAY)
        text, data = functions.recognize_game_frame(gray[60:180], model, '')
        assert any(event['event'] == 'arena_victory' for event in functions.classify(text, locale))
        assert functions.locate_notification_crop(data, gray[60:180], gray.shape[0], 60, locale)
        two_lines = messages()[locale]['2341413'].replace('<?matchRemainingCount?>', '1').splitlines()
        picture = Image.new('RGB', (1800, 140), 'white')
        draw = ImageDraw.Draw(picture)
        font = ImageFont.truetype(str(font_path), 30)
        for index, line in enumerate(two_lines):
            draw.text((20, 10 + index * 48), line, fill='black', font=font)
        gray = functions.cv2.cvtColor(np.array(picture), functions.cv2.COLOR_RGB2GRAY)
        text, data = functions.recognize_game_frame(gray, model, '')
        located = functions.locate_notification_crop(data, gray, 1000, 400, locale)
        assert located and located['lines'] == 2 and located.get('box'), (locale, text, located)

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
    assert event.call_args.args[0] == 'Test a envahi votre monde'
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
# An invader death can be observed even when its arrival was missed. A
# repeated OCR frame must not add another sighting or victory.
with patch.object(functions, 'game_locale', 'frafr'), \
     patch.object(functions, 'fight', False), patch.object(functions, 'mode_select', 'Arena'), \
     patch.object(functions, 'mode_detected', False), patch.object(functions, 'invasion_phase', None), \
     patch.object(functions, 'sighting_tracker', type(functions.sighting_tracker)()), \
     patch.object(functions, 'apply_score') as score, \
     patch.object(functions, 'add_mode_score') as inferred_score, \
     patch.object(functions, 'session_summary'), \
     patch.object(functions, 'captures_stats', []), \
     patch.object(functions, 'add_capture') as capture, \
     patch.object(functions, 'emit_tracking_event') as event:
    death = 'Le Réfractaire MissingArrivalTest a péri.'
    functions.process_game_text(death, str(image_path), frame, death)
    functions.process_game_text(death, str(image_path), frame, death)
    assert event.call_count == 2 and event.call_args.kwargs['mode_override'] == 'Defense'
    assert 'MissingArrivalTest' in event.call_args.kwargs['opponent']
    assert not score.called and capture.call_count == 1 and inferred_score.call_count == 1 and not functions.fight
# Failed ally summons produce one history event per notification, never a combat.
import html
from application.locale_catalog import messages as game_messages
for ui_language, locale in functions.game_language.UI_TO_GAME.items():
    expected = game_messages()[locale]['2490000']
    if ui_language != 'fra':
        expected = html.escape(functions.display_game_text(expected), quote=False)
    assert functions.localize_counter("Impossible d'invoquer l'allié.", ui_language) == expected

# Arena menu and matchmaking cancellation must not create events or terminate
# an active fight, even when the broad discovery region contains the menu.
with patch.object(functions, 'emit_tracking_event') as event, \
     patch.object(functions, 'apply_score') as score, \
     patch.object(functions.sighting_tracker, 'observe', return_value=[]):
    functions.langue_select = 'fra'
    functions.game_locale = 'frafr'
    functions.detect_text_active = functions.detect_text_fr
    functions.detect_mod_active = functions.detect_mod_fr
    functions.mode_select = 'Arena'
    functions.fight = True
    functions.mod_launch = 0
    for menu_text in ('Annuler le matchmaking', 'Matchmaking annulé', 'Le matchmaking a été annulé',
                      'Duel 2 combattants Interdit'):
        functions.process_game_text(menu_text, str(image_path), frame)
        assert functions.fight, menu_text
    event.assert_not_called()
    score.assert_not_called()
    functions.fight = False

# Exercise the live multilingual adapter, not only the catalog in isolation.
# Repeated frames must not start or score an invasion twice. All images and
# scoring are isolated.
with patch.object(functions, 'apply_score') as score, \
     patch.object(functions, 'emit_tracking_event', return_value=123), \
     patch.object(functions, 'add_capture') as capture, \
     patch.object(functions, 'captures_stats', []), \
     patch.object(functions, 'path_start_fight', str(image_path)), \
     patch.object(functions.sighting_tracker, 'observe', return_value=[]), \
     patch.object(functions.steam_history, 'begin_arena'), \
     patch.object(functions.steam_history, 'finish_arena', return_value=False), \
     patch.object(functions.cv2, 'imread', return_value=frame), \
     patch.object(functions.cv2, 'imwrite', return_value=True):
    for locale, entries in game_messages().items():
        if locale == 'frafr':
            continue
        functions.game_locale = locale
        functions.fight = False
        functions.mode_select = 'Arena'
        functions.mode_detected = False
        functions.invasion_phase = None
        functions.invasion_return_pending = None
        functions.recent_invasion_no_result = None
        functions.invasion_search_visibility.reset()
        score.reset_mock(); capture.reset_mock()
        search = entries['2331200']
        start = entries['2601200'].replace('<?hostName?>', 'TestPlayer')
        win = entries['2611200']
        for text in (search, search):
            functions.process_game_text(text, str(image_path), frame, text)
        assert not functions.fight and functions.mode_select == 'Invasion', locale
        for text in (start, start):
            functions.process_game_text(text, str(image_path), frame, text)
        assert functions.fight and functions.mode_select == 'Invasion', locale
        assert score.call_count == 1, (locale, score.call_args_list)
        for text in (win, win):
            functions.process_game_text(text, str(image_path), frame, text)
        assert not functions.fight and score.call_count == 2, (locale, score.call_args_list)
        assert capture.call_count == 1 and capture.call_args.args[1:4] == (1, 0, 0), locale
        assert base64.b64decode(capture.call_args.args[7]) == image_path.read_bytes(), locale

        # A return without a recognized result is counted once, not as a win
        # or a loss, including when both OCR readings contain the same text.
        score.reset_mock(); capture.reset_mock()
        with patch.object(functions.time, 'monotonic', return_value=100) as clock:
            functions.process_game_text(start, str(image_path), frame, start)
            returned = entries['2631200']
            functions.process_game_text(returned, str(image_path), frame, returned)
            assert functions.fight, locale
            clock.return_value = 105
            functions.process_game_text(returned, str(image_path), frame, returned)
            functions.process_game_text(returned, str(image_path), frame, returned)
        assert not functions.fight and score.call_count == 2, (locale, score.call_args_list)
        assert score.call_args.args[4] == 1 and not capture.called, locale

        # Defense is a separate mode; only the invading opponent's death
        # finishes the encounter, and a repeated notification is ignored.
        score.reset_mock(); capture.reset_mock()
        defense = entries['2600200'].replace('<?joinName?>', 'TestPlayer')
        died = entries['2620200'].replace('<?deadName?>', 'TestPlayer')
        for text in (defense, defense):
            functions.process_game_text(text, str(image_path), frame, text)
        assert functions.fight and functions.mode_select == 'Defense', locale
        for text in (died, died):
            functions.process_game_text(text, str(image_path), frame, text)
        assert not functions.fight and score.call_count == 2, (locale, score.call_args_list)
        assert capture.call_count == 1 and capture.call_args.args[6] == 'Defense', locale
        assert base64.b64decode(capture.call_args.args[7]) == image_path.read_bytes(), locale

        # Arena recognition uses the game's selected language while the French
        # adapter and original OCR coexist. Score each repeated victory once.
        score.reset_mock(); capture.reset_mock()
        functions.detect_text_active = functions.detect_text_en if locale == 'engus' else functions.detect_text_fr
        functions.detect_mod_active = functions.detect_mod_en if locale == 'engus' else functions.detect_mod_fr
        functions.mode_select = 'Arena'
        functions.mode_detected = False
        functions.invasion_phase = None
        functions.stape = 0
        arena_start = entries['arena:88000'].replace('<?matchDuel_TotalTime?>', '180')
        arena_win = entries['arena:88050']
        with patch.object(functions.time, 'time', return_value=100) as clock:
            for text in (arena_start, arena_start):
                functions.process_game_text(text, str(image_path), frame, text)
            assert functions.fight and functions.mode_select == 'Arena', locale
            clock.return_value = 110
            for text in (arena_win, arena_win):
                functions.process_game_text(text, str(image_path), frame, text)
        assert not functions.fight and score.call_count == 2, (locale, score.call_args_list)
        assert capture.call_count == 1 and capture.call_args.args[1:4] == (1, 0, 0), locale

        # Victory, defeat and draw are distinct arena outcomes.
        for message_id, expected_outcome in [('arena:88052', (0, 1, 0)), ('arena:88051', (0, 0, 1))]:
            score.reset_mock(); capture.reset_mock()
            functions.fight = False
            functions.mode_select = 'Arena'
            functions.mode_detected = False
            functions.invasion_phase = None
            functions.stape = 1
            result_text = entries[message_id]
            with patch.object(functions.time, 'time', return_value=200) as clock:
                functions.process_game_text(arena_start, str(image_path), frame, arena_start)
                assert functions.fight and functions.mode_select == 'Arena', (locale, message_id)
                clock.return_value = 210
                for text in (result_text, result_text):
                    functions.process_game_text(text, str(image_path), frame, text)
            assert not functions.fight and score.call_count == 2, (locale, message_id, score.call_args_list)
            assert capture.call_count == 1 and capture.call_args.args[1:4] == expected_outcome, (locale, message_id)

functions.detect_text_active = functions.detect_text_fr
functions.detect_mod_active = functions.detect_mod_fr

# A confirmed invader death without an observed arrival is a Defense win.
# Repeated frames and fights in other modes must not add duplicates, while a
# different invader can die during an already active Defense encounter.
with patch.object(functions, 'add_capture') as missing_capture, \
     patch.object(functions, 'add_mode_score') as missing_score, \
     patch.object(functions, 'session_summary') as missing_session, \
     patch.object(functions, 'record_sighting', return_value=True), \
     patch.object(functions, '_recent_saved_defense_victory', return_value=False), \
     patch.object(functions, 'emit_tracking_event'), \
     patch.object(functions, 'captures_stats', []):
    for locale, entries in game_messages().items():
        functions.game_locale = locale
        functions.fight = False
        functions.mode_select = 'Arena'
        functions.mode_detected = False
        functions.invasion_phase = None
        functions.recent_defense_victories.clear()
        functions.sighting_tracker.pending.clear()
        missing_capture.reset_mock(); missing_score.reset_mock(); missing_session.reset_mock()
        death = entries['2620200'].replace('<?deadName?>', 'TestPlayer')
        for _ in range(5):
            functions.process_game_text(death, str(image_path), frame)
        assert missing_capture.call_count == 1, (locale, missing_capture.call_args_list)
        assert missing_capture.call_args.args[1:7] == (1, 0, 0, '—', missing_capture.call_args.args[5], 'Defense'), locale
        missing_score.assert_called_once_with('Defense', 1, 0, 0, 1, 0, 0, 0, 0, 0, independent_victory=True)
        missing_session.independent_victory.assert_called_once_with('Defense', 'TestPlayer')
        assert not functions.fight and functions.mode_select == 'Defense', locale
    for mode in ('Arena', 'Invasion', 'Defense'):
        functions.fight = True
        functions.mode_select = mode
        functions.invasion_phase = 'fight'
        functions.opponent_name = 'OtherPlayer'
        functions.sighting_tracker.pending.clear()
        functions.recent_defense_victories.clear()
        missing_score.reset_mock()
        for _ in range(3):
            functions.process_game_text('Le Doigt sanglant TestPlayer est mort.', str(image_path), frame)
        assert missing_score.call_count == (1 if mode == 'Defense' else 0), (mode, missing_score.call_args_list)
        assert functions.fight, mode
        assert functions.opponent_name == 'OtherPlayer', mode
    # A second invader's catalogued death must be recognized regardless of
    # the game's selected language; the principal invader remains active.
    for locale, entries in game_messages().items():
        functions.game_locale = locale
        functions.fight = True
        functions.mode_select = 'Defense'
        functions.mode_detected = True
        functions.invasion_phase = 'fight'
        functions.opponent_name = 'PrimaryPlayer'
        functions.sighting_tracker = player_sightings.SightingTracker()
        functions.recent_defense_victories.clear()
        missing_score.reset_mock()
        death = entries['2620210'].replace('<?deadName?>', 'SecondaryPlayer')
        for _ in range(3):
            functions.process_game_text(death, str(image_path), frame, death)
        assert missing_score.call_count == 1, (locale, missing_score.call_args_list)
        assert functions.fight and functions.opponent_name == 'PrimaryPlayer', locale
        # A hunter's defeat must not be reclassified as a Defense victory.
        hunter_death = entries['2620304'].replace('<?deadName?>', 'FriendlyHunter')
        for _ in range(3):
            functions.process_game_text(hunter_death, str(image_path), frame, hunter_death)
        assert missing_score.call_count == 1, (locale, missing_score.call_args_list)
        assert functions.fight and functions.opponent_name == 'PrimaryPlayer', locale
    functions.fight = False
    functions.invasion_phase = None
    functions.game_locale = 'frafr'

# A recently saved victory also suppresses a repeated notification after restart.
with tempfile.TemporaryDirectory() as temporary:
    recent_db = Path(temporary) / 'captures.db'
    with closing(sqlite3.connect(recent_db)) as db, db:
        db.execute('CREATE TABLE tabel_captures(id INTEGER PRIMARY KEY, name BLOB, victory BLOB, mode BLOB, date BLOB)')
        db.execute('INSERT INTO tabel_captures VALUES(1,?,?,?,?)', tuple(secur.encrypt_value(value) for value in
                   ('TestPlayer', '1', 'Defense', functions.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))))
    with patch.object(init, 'database_capture', str(recent_db)):
        assert functions._recent_saved_defense_victory(functions._defense_name_key('TestPlayer'))
        assert not functions._recent_saved_defense_victory(functions._defense_name_key('OtherPlayer'))

# Exercise actual isolated capture, mode counters and online outbox together.
with tempfile.TemporaryDirectory() as temporary:
    tmp = Path(temporary)
    captures_db, user_db, settings_db = tmp / 'captures.db', tmp / 'user.db', tmp / 'settings.db'
    with closing(sqlite3.connect(captures_db)) as db, db:
        db.execute('CREATE TABLE tabel_captures(id INTEGER PRIMARY KEY, name BLOB, victory BLOB, defeat BLOB, egality BLOB, time BLOB, date BLOB, mode BLOB, base64 BLOB)')
        db.execute('CREATE TABLE capture_steam_names(id INTEGER, steam_name BLOB)')
        db.execute('CREATE TABLE tracker_first_game_event(id INTEGER PRIMARY KEY)')
        db.execute('CREATE TABLE tracker_onboarding(id INTEGER PRIMARY KEY, first_capture INTEGER)')
    with closing(sqlite3.connect(settings_db)) as db, db:
        db.execute('CREATE TABLE online_leaderboard(id INTEGER PRIMARY KEY, enabled INTEGER, delete_pending INTEGER, event_permission INTEGER)')
        db.execute('INSERT INTO online_leaderboard VALUES(1,1,0,1)')
    with patch.object(init, 'database_capture', str(captures_db)), \
         patch.object(mode_stats, 'DATABASE', str(user_db)), \
         patch.object(mode_stats, 'database_setting', str(settings_db)), \
         patch.object(functions, 'captures_stats', []), \
         patch.object(functions, 'session_summary', functions.SessionSummary()), \
         patch.object(functions, 'fight', False), patch.object(functions, 'invasion_phase', None), \
         patch.object(functions, 'emit_tracking_event'):
        functions.recent_defense_victories.clear()
        item = {'name':'SavedInvader', 'role':'invader', 'event':'died', 'relation':'unknown', 'mode':'Unknown'}
        assert functions._untracked_defense_victory(item, str(image_path))
        assert not functions._untracked_defense_victory(item, str(image_path))
        functions.recent_defense_victories.clear()
        assert not functions._untracked_defense_victory(item, str(image_path))
        with closing(sqlite3.connect(user_db)) as db:
            assert db.execute("SELECT victory,combats FROM mode_stats WHERE mode='Defense'").fetchone() == (1, 1)
            rows = db.execute('SELECT match_id,kind FROM leaderboard_event_outbox ORDER BY rowid').fetchall()
            assert rows[0][0] == rows[1][0]
            assert [secur.decrypt_value(row[1]).decode() for row in rows] == ['start', 'victory']
        with closing(sqlite3.connect(captures_db)) as db:
            row = db.execute('SELECT name,time,mode FROM tabel_captures').fetchone()
            assert [secur.decrypt_value(value).decode() for value in row] == ['SavedInvader', '—', 'Defense']
        assert functions.session_summary.snapshot()['victories'] == 1

# Several invaders can be defeated while the first one is still present.
# Exercise real isolated captures, Defense counters, session state and the
# leaderboard outbox, including duplicate/reordered OCR and non-invaders.
with tempfile.TemporaryDirectory() as temporary:
    tmp = Path(temporary)
    captures_db, user_db, settings_db = tmp / 'captures.db', tmp / 'user.db', tmp / 'settings.db'
    with closing(sqlite3.connect(captures_db)) as db, db:
        db.execute('CREATE TABLE tabel_captures(id INTEGER PRIMARY KEY, name BLOB, victory BLOB, defeat BLOB, egality BLOB, time BLOB, date BLOB, mode BLOB, base64 BLOB)')
        db.execute('CREATE TABLE capture_steam_names(id INTEGER, steam_name BLOB)')
        db.execute('CREATE TABLE tracker_first_game_event(id INTEGER PRIMARY KEY)')
        db.execute('CREATE TABLE tracker_onboarding(id INTEGER PRIMARY KEY, first_capture INTEGER)')
    with closing(sqlite3.connect(settings_db)) as db, db:
        db.execute('CREATE TABLE online_leaderboard(id INTEGER PRIMARY KEY, enabled INTEGER, delete_pending INTEGER, event_permission INTEGER)')
        db.execute('INSERT INTO online_leaderboard VALUES(1,1,0,1)')
    with ExitStack() as patches:
        for change in (
            patch.object(init, 'database_capture', str(captures_db)),
            patch.object(player_sightings, 'database_capture', str(captures_db)),
            patch.object(mode_stats, 'DATABASE', str(user_db)),
            patch.object(mode_stats, 'database_setting', str(settings_db)),
            patch.object(functions, 'captures_stats', []),
            patch.object(functions, 'session_summary', functions.SessionSummary()),
            patch.object(functions, 'recent_defense_victories', {}),
            patch.object(functions, 'recent_defense_reentries', {}),
            patch.object(functions, 'sighting_tracker', player_sightings.SightingTracker()),
            patch.object(functions, 'fight', False), patch.object(functions, 'run_monitor', False),
            patch.object(functions, 'mode_select', 'Arena'), patch.object(functions, 'mode_detected', False),
            patch.object(functions, 'invasion_phase', None), patch.object(functions, 'opponent_name', ''),
            patch.object(functions, 'game_locale', 'frafr'), patch.object(functions, 'langue_select', 'fra'),
            patch.object(functions, 'path_start_fight', str(tmp / 'start.jpg')),
            patch.object(functions, '_begin_pvp_encounter'), patch.object(functions, '_seal_pvp_participant', return_value=''),
            patch.object(functions, 'emit_tracking_event'),
            patch.object(functions.cv2, 'imread', return_value=frame), patch.object(functions.cv2, 'imwrite', return_value=True),
        ):
            patches.enter_context(change)
        def observe_french(message):
            for _ in range(3):
                functions.process_game_text(message, str(image_path), frame, message)

        observe_french('Le Réfractaire Alpha a envahi votre monde !')
        assert functions.fight and functions.mode_select == 'Defense' and functions.opponent_name == 'Alpha'
        with closing(sqlite3.connect(user_db)) as db:
            assert db.execute("SELECT victory,combats,abandon FROM mode_stats WHERE mode='Defense'").fetchone() == (0, 1, 0)
            primary = db.execute("SELECT active_match FROM leaderboard_event_state WHERE mode='Defense'").fetchone()[0]
            assert primary

        observe_french('Le Réfractaire Bravo a envahi votre monde !')
        observe_french('Le Réfractaire Bravo a péri.')
        with closing(sqlite3.connect(user_db)) as db:
            assert db.execute("SELECT victory,combats,abandon FROM mode_stats WHERE mode='Defense'").fetchone() == (1, 2, 0)
            assert db.execute("SELECT active_match FROM leaderboard_event_state WHERE mode='Defense'").fetchone()[0] == primary
        assert functions.fight and functions.opponent_name == 'Alpha'
        assert functions.session_summary.snapshot()['victories'] == 1

        # An allied hunter and summoned ally are not invading opponents.
        observe_french('Le Chasseur Helper est mort.')
        observe_french('Le Doigt crochu Friend est mort.')
        observe_french('Le Doigt sanglant Charlie a envahi votre monde !')
        observe_french('Le Doigt sanglant Charlie est mort.')
        # A previously read death may reappear after a different notification.
        observe_french('Le Réfractaire Bravo a péri.')
        with closing(sqlite3.connect(user_db)) as db:
            assert db.execute("SELECT victory,combats,abandon FROM mode_stats WHERE mode='Defense'").fetchone() == (2, 3, 0)
            assert db.execute("SELECT active_match FROM leaderboard_event_state WHERE mode='Defense'").fetchone()[0] == primary
        assert functions.fight and functions.opponent_name == 'Alpha'
        assert functions.session_summary.snapshot()['victories'] == 2

        # The same invader can genuinely return and be defeated again before
        # 45 seconds have elapsed; repeated OCR frames must still count once.
        observe_french('Le Réfractaire Bravo a envahi votre monde !')
        observe_french('Le Réfractaire Bravo a péri.')
        observe_french('Le Réfractaire Bravo a péri.')
        with closing(sqlite3.connect(user_db)) as db:
            assert db.execute("SELECT victory,combats,abandon FROM mode_stats WHERE mode='Defense'").fetchone() == (3, 4, 0)
            assert db.execute("SELECT active_match FROM leaderboard_event_state WHERE mode='Defense'").fetchone()[0] == primary
        assert functions.fight and functions.opponent_name == 'Alpha'
        assert functions.session_summary.snapshot()['victories'] == 3

        observe_french('Le Réfractaire Alpha a péri.')
        observe_french('Le Réfractaire Alpha a péri.')
        assert not functions.fight
        with closing(sqlite3.connect(user_db)) as db:
            assert db.execute("SELECT victory,combats,abandon FROM mode_stats WHERE mode='Defense'").fetchone() == (4, 4, 0)
            assert db.execute("SELECT active_match FROM leaderboard_event_state WHERE mode='Defense'").fetchone()[0] is None
            outbox = [(match, secur.decrypt_value(kind).decode()) for match, kind in db.execute('SELECT match_id,kind FROM leaderboard_event_outbox ORDER BY rowid')]
        assert [kind for _, kind in outbox] == ['start', 'defense_extra_victory', 'defense_extra_victory', 'defense_extra_victory', 'victory']
        assert outbox[0][0] == outbox[-1][0] == primary
        assert outbox[1][0] != primary
        assert outbox[2][0] not in (primary, outbox[1][0])
        assert outbox[3][0] not in (primary, outbox[1][0], outbox[2][0])
        with closing(sqlite3.connect(captures_db)) as db:
            captures = [secur.decrypt_value(row[0]).decode() for row in db.execute('SELECT name FROM tabel_captures ORDER BY id')]
        assert captures == ['Bravo', 'Charlie', 'Bravo', 'Alpha'], captures
        assert functions.session_summary.snapshot()['victories'] == 4

# Arena captures retain the start frame and keep an optional, explicitly
# separate Steam name. Exercise real participant disambiguation with fake peers;
# the capture, scoring, Steam history and image writes remain isolated/mocked.
arena_start_image = Path(os.environ['APPDATA']) / 'isolated-arena-start.jpg'
arena_start_image.write_bytes(b'frame from beginning of duel')
result_image = image_path.read_bytes()
start_image = arena_start_image.read_bytes()
assert start_image != result_image
one_peer = {'id':'76561198000000001', 'name':'SteamTestPlayer'}
other_peer = {'id':'76561198000000002', 'name':'OtherSteamPlayer'}
id_only_peer = {'id':'76561198000000003'}
arena_cases = [
    ('victory', 1, [one_peer], 'SteamTestPlayer', (1, 0, 0)),
    ('defeat', 9, [], '', (0, 1, 0)),
    ('draw', 15, [one_peer, other_peer], '', (0, 0, 1)),
    ('id-only', 1, [id_only_peer], '', (1, 0, 0)),
    ('late-peer', 1, [one_peer], 'SteamTestPlayer', (1, 0, 0)),
    ('steam-unavailable', 1, [one_peer], '', (1, 0, 0)),
]
with patch.object(functions, 'apply_score') as score, \
     patch.object(functions, 'emit_tracking_event', return_value=123), \
     patch.object(functions, 'add_capture') as capture, \
     patch.object(functions, 'captures_stats', []), \
     patch.object(functions, 'captures', []), \
     patch.object(functions, 'path_start_fight', str(arena_start_image)), \
     patch.object(functions.sighting_tracker, 'observe', return_value=[]), \
     patch.object(functions.steam_history, '_known', {}), \
     patch.object(functions.steam_history, '_arena', None), \
     patch.object(functions.steam_history, 'record_detection', side_effect=count(100)), \
     patch.object(functions.steam_history, 'update_detection', return_value=True) as steam_update, \
     patch.object(functions.cv2, 'imread', return_value=frame), \
     patch.object(functions.cv2, 'imwrite', return_value=True):
    for label, outcome_index, peers, expected_steam, expected_result in arena_cases:
        functions.steam_history._known.clear()
        functions.steam_history._arena = None
        functions.steam_history.observe('active', peers, 'Arena')
        initial_id = functions.steam_history._known[one_peer['id']]['id'] if one_peer in peers else None
        functions.game_locale = 'frafr'
        functions.fight = False
        functions.mode_select = 'Arena'
        functions.mode_detected = False
        functions.invasion_phase = None
        functions.invasion_return_pending = None
        functions.stape = 1
        score.reset_mock(); capture.reset_mock(); steam_update.reset_mock(); functions.captures_stats.clear()
        original_seal = functions.steam_history.seal_arena_participant
        def seal_then_arrival():
            result = original_seal()
            functions.steam_history.observe('active', [one_peer, other_peer], 'Arena')
            return result
        if label == 'steam-unavailable':
            seal = patch.object(functions.steam_history, 'seal_arena_participant', side_effect=RuntimeError('Steam unavailable'))
        elif label == 'late-peer':
            seal = patch.object(functions.steam_history, 'seal_arena_participant', side_effect=seal_then_arrival)
        else:
            seal = nullcontext()
        with seal, patch.object(functions.time, 'time', return_value=300) as clock:
            functions.process_game_text(functions.detect_text_active[0], str(image_path), frame)
            assert functions.fight and functions.mode_select == 'Arena', label
            clock.return_value = 310
            for _ in range(2):
                functions.process_game_text(functions.detect_text_active[outcome_index], str(image_path), frame)
        assert not functions.fight and score.call_count == 2 and capture.call_count == 1, label
        args, kwargs = capture.call_args
        assert args[0] == '' and args[1:4] == expected_result and args[6] == 'Arena', label
        assert base64.b64decode(args[7]) == start_image, label
        assert kwargs.get('steam_name', '') == expected_steam, (label, kwargs)
        recent = client.get('/capture').get_json()
        assert base64.b64decode(recent['datas']) == start_image, label
        assert recent['mode'] == 'Arena' and recent['opponent'] == '', label
        assert recent.get('steam_name', '') == expected_steam, label
        if label == 'late-peer':
            assert steam_update.call_count == 1 and steam_update.call_args.args[0] == initial_id, (label, steam_update.call_args_list)
arena_start_image.unlink()

# Arena screenshots must contain the entire frame seen at the beginning of
# the duel, rather than a cropped section or the later result frame. Use real
# JPEG reads/writes in the private image directory so cropping is observable.
arena_source = test_images / 'arena-full-frame-source.jpg'
arena_start = test_images / 'arena-full-frame-start.jpg'
arena_finish = test_images / 'arena-full-frame-finish.jpg'
full_start_frame = np.empty((80, 120, 3), dtype=np.uint8)
full_start_frame[:] = (0, 0, 220)
full_start_frame[40:, 60:] = (0, 220, 0)
full_result_frame = np.full((80, 120, 3), (220, 0, 0), dtype=np.uint8)
with patch.object(functions, 'apply_score') as score, \
     patch.object(functions, 'emit_tracking_event', return_value=123), \
     patch.object(functions, 'add_capture') as capture, \
     patch.object(functions, 'captures_stats', []), \
     patch.object(functions, 'captures', []), \
     patch.object(functions, 'path_start_fight', str(arena_start)), \
     patch.object(functions, 'path_finish_fight', str(arena_finish)), \
     patch.object(functions.sighting_tracker, 'observe', return_value=[]), \
     patch.object(functions.steam_history, 'begin_arena'), \
     patch.object(functions.steam_history, 'seal_arena_participant', return_value=''), \
     patch.object(functions.steam_history, 'finish_arena', return_value=False):
    for label, outcome_index, expected_result in [
        ('victory', 1, (1, 0, 0)),
        ('defeat', 9, (0, 1, 0)),
        ('draw', 15, (0, 0, 1)),
    ]:
        assert functions.cv2.imwrite(str(arena_source), full_start_frame)
        functions.game_locale = 'frafr'
        functions.fight = False
        functions.mode_select = 'Arena'
        functions.mode_detected = False
        functions.invasion_phase = None
        functions.invasion_return_pending = None
        functions.stape = 1
        score.reset_mock(); capture.reset_mock(); functions.captures_stats.clear()
        with patch.object(functions.time, 'time', return_value=400) as clock:
            functions.process_game_text(functions.detect_text_fr[0], str(arena_source), full_start_frame)
            assert functions.fight, label
            assert functions.cv2.imwrite(str(arena_source), full_result_frame)
            clock.return_value = 410
            functions.process_game_text(functions.detect_text_fr[outcome_index], str(arena_source), full_result_frame)
        assert capture.call_count == 1 and capture.call_args.args[1:4] == expected_result, label
        stored = base64.b64decode(capture.call_args.args[7])
        decoded = functions.cv2.imdecode(np.frombuffer(stored, dtype=np.uint8), functions.cv2.IMREAD_COLOR)
        assert decoded.shape == full_start_frame.shape, (label, decoded.shape)
        assert np.max(np.abs(decoded[15, 15].astype(int) - full_start_frame[15, 15])) < 25, label
        assert np.max(np.abs(decoded[65, 105].astype(int) - full_start_frame[65, 105])) < 25, label
        assert base64.b64decode(client.get('/capture').get_json()['datas']) == stored, label

# Victory notifications use game names first and a unique Steam profile only
# as a fallback. Inspect the public event queue and isolated history rather
# than only the implementation's calls; no real Steam or game is involved.
game_name = 'Ocr<Name>, & Hero'
steam_name = 'Steam<Name>, & Hero'
named_peer = {'id':'76561198000000011', 'name':steam_name}
second_peer = {'id':'76561198000000012', 'name':'AnotherSteam'}
victory_cases = [
    ('arena-steam', 'Arena', 'fra', [named_peer], 'contre', steam_name, 'win'),
    ('arena-none', 'Arena', 'fra', [], '', '', 'win'),
    ('arena-ambiguous', 'Arena', 'fra', [named_peer, second_peer], '', '', 'win'),
    ('arena-defeat', 'Arena', 'fra', [named_peer], 'contre', steam_name, 'loss'),
    ('arena-draw', 'Arena', 'fra', [named_peer], 'égalité avec', steam_name, 'draw'),
    ('arena-draw-unknown', 'Arena', 'fra', [], '', '', 'draw'),
    ('arena-draw-ambiguous', 'Arena', 'fra', [named_peer, second_peer], '', '', 'draw'),
    ('invasion-game', 'Invasion', 'fra', [named_peer], 'contre', game_name, 'win'),
    ('invasion-loss', 'Invasion', 'fra', [named_peer], 'contre', game_name, 'loss'),
    ('invasion-steam', 'Invasion', 'fra', [named_peer], 'contre', steam_name, 'win'),
    ('invasion-no-peer', 'Invasion', 'fra', [], '', '', 'win'),
    ('invasion-id-only', 'Invasion', 'fra', [id_only_peer], '', '', 'win'),
    ('invasion-ambiguous', 'Invasion', 'fra', [named_peer, second_peer], '', '', 'win'),
    ('invasion-peer-joins', 'Invasion', 'fra', [named_peer], '', '', 'win'),
    ('invasion-peer-leaves', 'Invasion', 'fra', [named_peer], 'contre', steam_name, 'win'),
    ('invasion-ambiguous-then-leaves', 'Invasion', 'fra', [named_peer], '', '', 'win'),
    ('defense-game', 'Defense', 'fra', [named_peer], 'contre', game_name, 'win'),
    ('defense-loss', 'Defense', 'fra', [named_peer], 'contre', game_name, 'loss'),
    ('arena-english', 'Arena', 'eng', [named_peer], 'defeated', steam_name, 'win'),
]
with patch.object(functions, 'apply_score') as score, \
     patch.object(functions, 'add_capture') as capture, \
     patch.object(functions, 'captures_stats', []), \
     patch.object(functions, 'array_stats', dict(functions.array_stats)), \
     patch.object(functions, 'tampo_text', ''), \
     patch.object(functions, 'path_start_fight', str(image_path)), \
     patch.object(functions.sighting_tracker, 'observe', return_value=[]), \
     patch.object(functions.steam_history, '_known', {}), \
     patch.object(functions.steam_history, '_arena', None), \
     patch.object(functions.steam_history, '_pvp_encounter', None), \
     patch.object(functions.steam_history, 'record_detection', side_effect=count(1000)), \
     patch.object(functions.steam_history, 'update_detection', return_value=True), \
     patch.object(functions.cv2, 'imread', return_value=frame), \
     patch.object(functions.cv2, 'imwrite', return_value=True):
    for label, combat_mode, language, peers, expected_label, expected_name, outcome in victory_cases:
        functions.steam_history._known.clear()
        functions.steam_history._arena = None
        functions.steam_history._pvp_encounter = None
        functions.steam_history.observe('active', peers, combat_mode)
        functions.game_locale = 'engus' if language == 'eng' else 'frafr'
        functions.langue_select = language
        functions.detect_text_active = functions.detect_text_en if language == 'eng' else functions.detect_text_fr
        functions.detect_mod_active = functions.detect_mod_en if language == 'eng' else functions.detect_mod_fr
        functions.fight = False
        functions.mode_select = 'Arena'
        functions.mode_detected = False
        functions.invasion_phase = None
        functions.invasion_return_pending = None
        functions.recent_invasion_no_result = None
        functions.stape = 1
        functions.array_stats['text'] = ''
        functions.tampo_text = ''
        score.reset_mock(); capture.reset_mock(); functions.captures_stats.clear()
        if combat_mode == 'Arena':
            start_text = functions.detect_text_active[0]
            result_text = functions.detect_text_active[9 if outcome == 'loss' else 15 if outcome == 'draw' else 1]
        elif combat_mode == 'Invasion':
            host = game_name if label in ('invasion-game', 'invasion-loss') else ' '
            start_text = "Invasion d'un autre monde.\nTerrassez " + host + ', Hôte des Doigts !'
            result_text = ('Vous avez péri.\nRetour dans votre monde.' if outcome == 'loss' else
                           'Hôte des Doigts vaincu.\nRetour dans votre monde.')
        else:
            start_text = 'Le Doigt sanglant ' + game_name + ' a envahi votre monde !'
            result_text = 'Vous avez péri.' if outcome == 'loss' else 'Le Doigt sanglant ' + game_name + ' est mort.'
        with patch.object(functions.time, 'time', return_value=400) as clock:
            functions.process_game_text(start_text, str(image_path), frame, start_text)
            assert functions.fight and functions.mode_select == combat_mode, label
            if label == 'invasion-peer-joins':
                functions.steam_history.observe('active', [named_peer, second_peer], combat_mode)
            if label == 'invasion-peer-leaves':
                functions.steam_history.observe('active', [], combat_mode)
            if label == 'invasion-ambiguous-then-leaves':
                functions.steam_history.observe('active', [named_peer, second_peer], combat_mode)
                functions.steam_history.observe('active', [named_peer], combat_mode)
            clock.return_value = 410
            for _ in range(2):
                functions.process_game_text(result_text, str(image_path), frame, result_text)
        assert not functions.fight and capture.call_count == 1 and score.call_count == 2, label
        queue = client.get('/interval').get_json()['datas']['text']
        if expected_name:
            encoded = html.escape(expected_name, quote=False).replace(',', '&#44;')
            fragment = expected_label + ' ' + encoded
            assert queue.count('combat-result-text') == 1 and fragment in queue, (label, queue)
            assert 'victory-opponent-detail' not in queue and 'Profil Steam :' not in queue, (label, queue)
            assert expected_name not in queue and '<Name>' not in queue, (label, queue)
            events = client.get('/detection-history', query_string={'mode':combat_mode}).get_json()['events']
            matching = [entry for entry in events if expected_label + ' ' + expected_name in entry['message']]
            assert matching, label
            assert matching[0]['metadata'] == {'opponent': expected_name, 'opponent_source': 'game' if expected_name == game_name else 'steam'}, label
        else:
            assert 'combat-result-text' not in queue and 'victory-opponent-detail' not in queue, (label, queue)
functions.detect_text_active = functions.detect_text_fr
functions.detect_mod_active = functions.detect_mod_fr

# Every translated sentence must preserve the result marker used by live
# capture detection and safely include the participant in the same sentence.
with patch.object(functions, 'array_stats', dict(functions.array_stats)), \
     patch.object(functions, 'record_detection', return_value=1):
    for language, pack in functions.ui_packs().items():
        for outcome, idx in (('victory', 8), ('defeat', 9), ('draw', 12)):
            functions.langue_select = language
            functions.array_stats['text'] = ''
            functions.emit_tracking_event('result<br> Time: 17 s', opponent='A<B>, C', opponent_source='steam', outcome=outcome)
            queue = functions.array_stats['text']
            assert pack['counter'][idx] in queue, (language, outcome)
            assert 'A&lt;B&gt;&#44; C' in queue and '<B>' not in queue, (language, outcome)
            assert 'combat-result-text' in queue and 'Time: 17 s' in queue, (language, outcome)
            assert '{opponent}' not in queue, (language, outcome)

# Preserve the recognized game notification after it disappears from the frame.
with patch.object(functions, 'apply_score') as score, \
     patch.object(functions, 'emit_tracking_event', return_value=123) as event, \
     patch.object(functions, 'add_capture'), \
     patch.object(functions.sighting_tracker, 'observe', return_value=[]), \
     patch.object(functions.cv2, 'imread', return_value=frame), \
     patch.object(functions.cv2, 'imwrite', return_value=True), \
     patch.object(functions, 'correct_invasion_no_result', return_value=True) as correct:
    for locale, entries in game_messages().items():
        functions.game_locale = locale
        functions.fight = False
        functions.mode_select = 'Arena'
        functions.mode_detected = False
        functions.invasion_phase = None
        functions.invasion_return_pending = None
        functions.invasion_return_message = None
        functions.recent_invasion_no_result = None
        score.reset_mock(); event.reset_mock(); correct.reset_mock()
        start = entries['2601200'].replace('<?hostName?>', 'TestPlayer')
        goal = entries['2661210']
        with patch.object(functions.time, 'monotonic', return_value=100) as clock:
            functions.process_game_text(start, str(image_path), frame, start)
            functions.process_game_text(goal, str(image_path), frame, goal)
            assert functions.fight, locale
            clock.return_value = 105
            functions.process_game_text('', str(image_path), frame, '')
        assert not functions.fight and score.call_count == 2, locale
        assert score.call_args.args[4] == 1, locale
        shown = event.call_args.args[0]
        assert shown.startswith('<!--invasion-no-result-->'), (locale, shown)
        display_goal = functions.display_game_text(goal)
        assert functions.message_text(shown) == display_goal, (locale, shown, display_goal)
        with patch.object(functions.time, 'monotonic', return_value=110):
            functions.handle_invasion('Une erreur de connexion est survenue.', str(image_path), frame)
        assert correct.call_args.args[1] == display_goal, locale

# Thai game-font glyphs are converted for both the live event and persistent
# history, without changing the catalog used for OCR.
thai_goal = game_messages()['thath']['2661210']
thai_display = functions.display_game_text(thai_goal)
assert thai_goal != thai_display
with patch.object(functions, 'apply_score'), \
     patch.object(functions, 'array_stats', dict(functions.array_stats, text='')), \
     patch.object(functions, 'tampo_text', ''), \
     patch.object(functions, 'game_locale', 'thath'), \
     patch.object(functions, 'langue_select', 'tha'), \
     patch.object(functions, 'fight', True), \
     patch.object(functions, 'mode_select', 'Invasion'), \
     patch.object(functions, 'mode_detected', True), \
     patch.object(functions, 'invasion_return_pending', 100), \
     patch.object(functions, 'invasion_return_message', thai_goal), \
     patch.object(functions, 'time_start', 90), \
     patch.object(functions.time, 'monotonic', return_value=105):
    functions.handle_invasion('', str(image_path), frame)
    visible = client.get('/interval').get_json()['datas']['text']
    assert functions.message_text(visible) == thai_display
    recent = client.get('/detection-history?mode=Invasion').get_json()['events']
    assert any(entry['message'] == thai_display for entry in recent)
    assert game_messages()['thath']['2661210'] == thai_goal

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
# Simulate an old archive containing an IP, then run the one-time privacy migration.
from application.secur import encrypt_value, decrypt_value
import json
with closing(detection_history._connect()) as db:
    legacy = {'id':'76561198000000000', 'name':'Test', 'ip':'8.8.8.8', 'relay':False}
    db.execute('UPDATE history_archive_events SET metadata=? WHERE archive_id=? AND original_id=?',
               (encrypt_value(json.dumps(legacy)), archive_id, steam_id))
    db.execute("UPDATE detection_history SET kind='steam_encounter',metadata=? WHERE id=?", (encrypt_value(json.dumps(legacy)), new_id))
    db.execute("DELETE FROM detection_history_migrations WHERE name='steam_country_without_ip_v1'")
    db.commit()
with patch.object(detection_history, 'country_code', return_value='US'):
    with closing(detection_history._connect()) as db:
        encrypted = db.execute('SELECT metadata FROM history_archive_events WHERE archive_id=? AND original_id=?', (archive_id, steam_id)).fetchone()[0]
        migrated = json.loads(decrypt_value(encrypted).decode('utf-8'))
        active = json.loads(decrypt_value(db.execute('SELECT metadata FROM detection_history WHERE id=?', (new_id,)).fetchone()[0]).decode('utf-8'))
assert active['country_code'] == 'US' and 'ip' not in active
assert migrated['country_code'] == 'US' and 'ip' not in migrated and 'relay' not in migrated
restored = client.post(f'/history-archives/{archive_id}/restore').get_json()
assert restored['restored'] == initial['history']['events']
assert client.post(f'/history-archives/{archive_id}/restore').get_json()['restored'] == 0
assert all(item['steam']['country_code'] == 'US' and 'ip' not in item['steam'] for item in detection_history.read_steam_history())
assert client.post('/history-archives/999999/restore').status_code == 404
assert client.post('/history-purge').get_json()['removed'] == initial['history']['events'] + 1
assert client.get('/history-storage').get_json()['history']['events'] == 0
assert client.post(f'/history-archives/{archive_id}/restore').get_json()['restored'] == initial['history']['events']
assert detection_history.record_detection('Après restauration', 'Arena') > new_id
with ThreadPoolExecutor(max_workers=4) as executor:
    ids = list(executor.map(lambda i: detection_history.record_detection('Concurrent ' + str(i), 'Arena'), range(12)))
assert len(set(ids)) == 12 and min(ids) > new_id
assert init.load_user() == before_user and init.get_capture_page(10, 1) == before_captures

# A hunter completing their objective is a departure observation, not a PvP
# result for this tracker. Exercise both OCR readings, persistence, the live
# overlay role, and the history on the isolated application database.
from application.locale_catalog import messages as game_messages
for hunter_mode, detected, in_fight, hunter_relation, hunter_name, hunter_language, ui_language in (
        ('Defense', True, True, 'ally', 'ObjectiveHunterDefense', 'frafr', 'fra'),
        ('Invasion', True, True, 'opponent', 'ObjectiveHunterInvasion', 'frafr', 'fra'),
        ('Invasion', True, True, 'opponent', 'ObjectiveHunterEnglish', 'engus', 'eng'),
        ('Defense', True, True, 'ally', 'ObjectiveHunter, & Co', 'engus', 'fra'),
        ('Defense', True, True, 'ally', 'ObjectiveHunterFrenchGame', 'frafr', 'eng'),
        ('Arena', False, False, 'unknown', 'ObjectiveHunterUnknown', 'frafr', 'fra')):
    hunter_peer = {'id': '76561198000000888', 'name': hunter_name, 'ping': 50}
    hunter_roles = type(functions.overlay_peer_roles)()
    hunter_roles.update_peers('active', [hunter_peer])
    hunter_roles.observe({'name': hunter_name, 'role': 'hunter', 'event': 'joined'})
    assert hunter_roles.annotate([hunter_peer])[0]['role'] == 'hunter'
    hunter_notice = game_messages()[hunter_language]['2610304'].replace('<?leaveName?>', hunter_name)
    ui_game_language = 'frafr' if ui_language == 'fra' else 'engus'
    expected_message = game_messages()[ui_game_language]['2610304'].replace('<?leaveName?>', hunter_name)
    expected_html = html.escape(expected_message, quote=False).replace('\n', '<br>').replace(',', '&#44;')
    expected_overlay = ' '.join(expected_message.split())
    expected_mode = hunter_mode if detected and in_fight else 'Unknown'
    with closing(mode_stats._connect()) as db:
        scores_before = db.execute('SELECT * FROM mode_stats ORDER BY mode').fetchall()
    with patch.object(functions, 'overlay_peer_roles', hunter_roles), \
         patch.object(functions, 'sighting_tracker', player_sightings.SightingTracker()), \
         patch.object(functions, 'run_monitor', True), patch.object(functions, 'fight', in_fight), \
         patch.object(functions, 'mode_select', hunter_mode), patch.object(functions, 'mode_detected', detected), \
         patch.object(functions, 'game_locale', hunter_language), patch.object(functions, 'langue_select', ui_language), \
         patch.object(functions, 'array_stats', dict(functions.array_stats, text='')), \
         patch.object(functions, 'sightings_revision', functions.sightings_revision), \
         patch.object(tracker_overlay_event, 'publish_html', wraps=tracker_overlay_event.publish_html) as publish, \
         patch.object(functions, 'apply_score', side_effect=AssertionError('hunter departure changed score')), \
         patch.object(functions, 'add_mode_score', side_effect=AssertionError('hunter departure changed score')):
        functions.process_game_text(hunter_notice, 'unused-test-image', None, notification_text=hunter_notice)
        functions.process_game_text(hunter_notice, 'unused-test-image', None, notification_text=hunter_notice)
        assert functions.array_stats['text'] == expected_html, repr(functions.array_stats['text'])
        assert functions.fight is in_fight and functions.mode_select == hunter_mode
        assert publish.call_count == 1 and publish.call_args.args == (expected_html,)
        assert publish.call_args.kwargs['language'] == ui_language and callable(publish.call_args.kwargs['renderer'])
        assert tracker_overlay_event.latest() == expected_overlay, tracker_overlay_event.latest()
        assert hunter_roles.annotate([hunter_peer])[0]['role'] is None
    rows = [item for item in player_sightings.read_sightings() if item['name'].startswith(hunter_name)]
    assert len(rows) == 1 and rows[0]['name'] == hunter_name and rows[0]['role'] == 'hunter' and rows[0]['event'] == 'completed'
    assert rows[0]['relation'] == hunter_relation and rows[0]['mode'] == expected_mode
    events = client.get('/detection-history', query_string={'mode': expected_mode}).get_json()['events']
    assert sum(item['message'] == expected_message for item in events) == 1
    with closing(mode_stats._connect()) as db:
        assert db.execute('SELECT * FROM mode_stats ORDER BY mode').fetchall() == scores_before

# Previously recorded hunter observations with incomplete context become
# consistent in the Players API when another event identifies that episode.
for name, mode, relation in (('ContextAlly', 'Defense', 'ally'), ('ContextEnemy', 'Invasion', 'opponent')):
    player_sightings.record_sighting({'name':name, 'role':'hunter', 'event':'joined', 'mode':mode, 'relation':relation},
                                     observed_at='2026-06-01 12:00:00')
    player_sightings.record_sighting({'name':name, 'role':'hunter', 'event':'completed', 'mode':'Unknown', 'relation':'unknown'},
                                     observed_at='2026-06-01 12:02:00')
    response = client.get('/players', query_string={'limit':30, 'q':name}).get_json()
    player = next(p for p in response['players'] if p['name'] == name)
    assert player['relations'] == [relation]
    assert {entry['mode'] for entry in player['history']} == {mode}
    assert {entry['relation'] for entry in player['history']} == {relation}
    assert client.get('/players', query_string={'limit':30, 'q':name, 'filter':relation}).get_json()['filtered_count'] == 1
