"""Coordinate the optional window using read-only tracker snapshots."""
import logging
import threading
import textwrap
import win32gui

from application import overlay_settings, overlay_player_tags, peer_rankings, steam_encounter_counts, tracker_overlay_data, tracker_overlay_event, tracker_overlay_scene, tracker_overlay_window
from application.overlay_peer_roles import annotate_arena_duelist

_LOG = logging.getLogger(__name__)
_lock = threading.Lock()
_started = False
_content = ()
_options = {}
_view = None
_status = 'disabled'


def status():
    with _lock:
        return _status


def _set_state(content, state, options=None, view=None):
    global _content, _status, _options, _view
    with _lock:
        _content, _status = tuple(content), state
        if options is not None:
            _options = dict(options)
        _view = view


def _capture_is_available(functions):
    # Capture state is updated by the monitor. Check foreground again here so
    # a slow OCR cycle or capture interval cannot leave the overlay on another
    # application after the player switches away from the game.
    if not (functions.run_monitor and functions.monitor_ready and not functions.monitor_error
            and functions.capture_available):
        return False
    try:
        hwnd = functions.get_foreground_window()
        if (not hwnd or not win32gui.IsWindowVisible(hwnd) or win32gui.IsIconic(hwnd) or
                functions.get_window_text(hwnd) != 'ELDEN RING™' or
                functions.steam_overlay.has_overlay_indicators(hwnd)):
            return False
    except Exception:
        return False
    return True


def _game_is_visible():
    """Check the game's window without requiring it to own the foreground."""
    try:
        hwnd = win32gui.FindWindow(None, 'ELDEN RING™')
        return bool(hwnd and win32gui.IsWindowVisible(hwnd) and not win32gui.IsIconic(hwnd))
    except Exception:
        return False


def _window_content(functions):
    with _lock:
        lines = _content
        options = dict(_options)
        view = _view
    if not lines:
        return []
    capture_active = _capture_is_available(functions)
    visibility = options.get('visibility_mode', 'game_visible')
    if visibility == 'capture' and not capture_active:
        return []
    if visibility == 'game_visible' and not _game_is_visible():
        return []
    if visibility not in ('capture', 'game_visible', 'always'):
        return []
    # The monitor's status can lag after Alt-Tab or an interruption. Report
    # the current capture state without modifying the shared tracking state.
    if (not capture_active and functions.run_monitor and functions.monitor_ready and
            not functions.monitor_error and isinstance(view, dict)):
        view = dict(view)
        labels = view.get('labels') or {}
        paused = labels.get('capture_paused', 'Capture paused')
        view['status'] = paused
        if options.get('show_status', True):
            lines = (paused,) + lines[1:]
    return {'lines': lines, 'capture_active': capture_active, 'options': options, 'view': view}


def _read_content(functions):
    content = _window_content(functions)
    return content['lines'] if content else ()


def _player_count(snapshot):
    """An inactive Steam reader cannot confirm that the session is empty."""
    return len(snapshot['peers']) if snapshot.get('peer_status') == 'active' else None


def _format(snapshot, event, options=None):
    options = options or {}
    labels = snapshot['labels']
    lines = []
    if options.get('show_status', True):
        lines.append(snapshot['status_text'])
    if options.get('show_mode', True):
        lines.append(labels['mode'] + ' : ' + snapshot['mode_text'])
    if options.get('show_player_count', False):
        count = _player_count(snapshot)
        lines.append(labels['player_count'] + ' : ' + (str(count) if count is not None else '—'))
    if options.get('show_peers', True):
        if snapshot['peers']:
            for peer in snapshot['peers']:
                ping = str(peer['ping']) + ' ms' if peer['ping'] is not None else '—'
                lines.append((peer['name'] or '—') + ' · ' + ping)
        else:
            lines.append(snapshot['peer_status_text'])
    if options.get('show_event', True):
        event = event or labels['no_event']
        lines.extend(textwrap.wrap(event, width=42, max_lines=2, placeholder='…') or ['—'])
    return lines


def _worker(functions):
    window = None
    was_enabled = False
    while True:
        try:
            active = overlay_settings.enabled()
            if not active:
                _set_state((), 'disabled')
                if window is not None:
                    window.stop()
                    window = None
                was_enabled = False
            else:
                if not was_enabled:
                    was_enabled = True
                    try:
                        window = tracker_overlay_window.OverlayWindow(lambda: _window_content(functions))
                        window.start()
                    except Exception:
                        window = None
                        _LOG.exception('Unable to start tracker overlay window')
                error = window.error if window is not None else 'window_error'
                if error:
                    _set_state((), error)
                else:
                    options = overlay_settings.options()
                    need_peers = options['show_peers'] or options.get('show_player_count', False)
                    peer_snapshot = functions.peer_tracking.passive_snapshot() if need_peers else None
                    snapshot = tracker_overlay_data.build_snapshot(
                        language=functions.langue_select,
                        running=functions.run_monitor, ready=functions.monitor_ready,
                        error=functions.monitor_error, game_running=functions.game_running,
                        game_detected=functions.game_detected, fight=functions.fight,
                        mode=functions.mode_select if functions.mode_detected else '',
                        peers=peer_snapshot)
                    event = tracker_overlay_event.latest()
                    cards = tracker_overlay_scene.cards(peer_snapshot or {}, options,
                        getattr(functions.peer_tracking, 'avatar_png', None),
                        language=functions.langue_select)
                    cards = functions.overlay_peer_roles.annotate(cards)
                    arena_peer = ''
                    if (len(cards) == 1 and functions.run_monitor and functions.monitor_ready and
                            not functions.monitor_error and functions.fight and functions.mode_detected and
                            functions.mode_select == 'Arena'):
                        history = getattr(functions, 'steam_history', None)
                        if history is not None:
                            try:
                                arena_peer = history.active_arena_participant_id()
                            except Exception:
                                _LOG.exception('Unable to identify the arena peer')
                    cards = annotate_arena_duelist(cards, mode=functions.mode_select,
                        mode_detected=functions.mode_detected, running=functions.run_monitor,
                        ready=functions.monitor_ready, error=functions.monitor_error,
                        fight=functions.fight, participant_id=arena_peer)
                    try:
                        overlay_player_tags.annotate(cards, options, functions.langue_select)
                    except Exception:
                        _LOG.exception('Unable to read player categories for the overlay')
                    counts = steam_encounter_counts.snapshot(
                        [card['id'] for card in cards],
                        enabled=bool(options.get('show_player_stats')))
                    for card in cards:
                        card['encounters'] = counts.get(card['id'])
                    try:
                        matches = peer_rankings.tracker_members(
                            [card['id'] for card in cards],
                            enabled=options.get('show_tracker_user', True) is True)
                        for card in cards:
                            if matches.get(card['id']) is True:
                                card['tracker_member'] = True
                    except Exception:
                        _LOG.exception('Unable to read confirmed tracker participants')
                    view = {'status': snapshot['status_text'], 'mode': snapshot['mode_text'],
                            'mode_id': functions.mode_select if functions.mode_detected else '',
                            'peer_status': snapshot['peer_status_text'], 'labels': snapshot['labels'],
                            'cards': cards, 'player_count': _player_count(snapshot), 'event': event}
                    _set_state(_format(snapshot, event, options), 'running', options, view)
        except Exception:
            _set_state((), 'window_error')
            _LOG.exception('Unable to update tracker overlay')
        threading.Event().wait(1)


def start(functions):
    """Start one coordinator after the tracker has actually launched."""
    global _started
    with _lock:
        if _started:
            return False
        _started = True
    try:
        threading.Thread(target=_worker, args=(functions,), name='tracker-overlay-control', daemon=True).start()
    except Exception:
        with _lock:
            _started = False
        raise
    return True
