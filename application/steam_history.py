"""Persist Steam connection observations without guessing character identity."""
import logging
import queue
import threading
from application.detection_history import record_detection, update_detection
from application import steam_avatar_store

_lock = threading.Lock()
_known = {}
_arena = None
_pvp_encounter = None
_avatar_queue = queue.Queue(maxsize=32)
_avatar_worker_lock = threading.Lock()
_avatar_worker_started = False


def _avatar_worker():
    while True:
        sid, event_id, revision, image, on_changed = _avatar_queue.get()
        try:
            changed = steam_avatar_store.save(sid, event_id, image)
        except Exception:
            logging.getLogger(__name__).exception('Unable to save a Steam avatar')
            with _lock:
                state = _known.get(sid)
                if state and state.get('id') == event_id and state.get('avatar_revision') == revision:
                    state.pop('avatar_revision', None)
        else:
            if changed and on_changed:
                try:
                    on_changed()
                except Exception:
                    logging.getLogger(__name__).exception('Unable to refresh Steam avatar presentation')
        finally:
            _avatar_queue.task_done()


def _queue_avatar(sid, event_id, revision, image, on_changed):
    global _avatar_worker_started
    with _avatar_worker_lock:
        if not _avatar_worker_started:
            threading.Thread(target=_avatar_worker, name='steam-avatar-save', daemon=True).start()
            _avatar_worker_started = True
    try:
        _avatar_queue.put_nowait((sid, event_id, revision, image, on_changed))
        return True
    except queue.Full:
        return False


def clear_history_transaction(operation):
    """Serialize clearing history with Steam observations and forget stale IDs."""
    global _arena, _pvp_encounter
    with _lock:
        result = operation()
        if result:
            _known.clear()
            _arena = None
            _pvp_encounter = None
        return result

def _clean(peer):
    sid = str(peer.get('id', ''))
    if len(sid) != 17 or not sid.isascii() or not sid.isdigit():
        return None
    name = str(peer.get('name') or sid).strip()[:128] or sid
    item = {'id':sid, 'name':name, 'country_code':peer.get('country_code')}
    if type(peer.get('steam_friend')) is bool:
        item['steam_friend'] = peer['steam_friend']
    return item

def observe(status, peers, mode='Unknown'):
    if status not in ('active', 'game_closed', 'disabled', 'steam_unavailable'):
        return 0
    current = {}
    if status == 'active':
        for peer in peers:
            if isinstance(peer, dict):
                item = _clean(peer)
                if item:
                    current[item['id']] = item
    changed = 0
    with _lock:
        for sid, current_item in current.items():
            state = _known.get(sid)
            previous = state['steam'] if state else None
            item = dict(current_item)
            if previous:
                for field in ('outcome', 'match_date', 'steam_friend'):
                    if field in previous and field not in item:
                        item[field] = previous[field]
            if previous and not item['country_code']:
                item['country_code'] = previous.get('country_code')
            if previous and item['name'] == sid and previous['name'] != sid:
                item['name'] = previous['name']
            known_mode = mode if mode in ('Arena', 'Invasion', 'Defense') else 'Unknown'
            if state is None:
                event_id = record_detection('Joueur Steam rencontré : ' + item['name'], known_mode, 'steam_encounter', item)
                _known[sid] = {'steam':item, 'id':event_id, 'mode':known_mode}
                changed += 1
            else:
                updated_mode = known_mode if state['mode'] == 'Unknown' else state['mode']
                if item != previous or updated_mode != state['mode']:
                    update_detection(state['id'], 'Joueur Steam rencontré : ' + item['name'], updated_mode, item)
                    state.update(steam=item, mode=updated_mode)
                    changed += 1
        if _arena is not None and not _arena.get('sealed'):
            # A reconnected network peer is a new observation; do not reuse
            # its old overlay role during this encounter.
            _arena.setdefault('departed', set()).update(set(_arena['participants']) - set(current))
            if status == 'active':
                for sid, state in _known.items():
                    _arena['participants'][sid] = state
                if len(_arena['participants']) > 1:
                    _arena['ambiguous'] = True
        if _pvp_encounter is not None and status == 'active':
            for sid in current:
                _pvp_encounter['participants'][sid] = dict(_known[sid]['steam'])
            if len(_pvp_encounter['participants']) > 1:
                _pvp_encounter['ambiguous'] = True
        for sid in list(_known):
            if sid not in current:
                _known.pop(sid)
    return changed


def persist_avatars(status, peers, avatar_provider, on_changed=None):
    """Queue live avatars without blocking the Steam helper's reader thread."""
    if status != 'active' or not callable(avatar_provider):
        return False
    queued = False
    # The same lock protects history deletion and clears _known. Never save a
    # late avatar for a row that was just purged.
    with _lock:
        for peer in peers[:16]:
            if not isinstance(peer, dict) or peer.get('avatar_available') is not True:
                continue
            sid, revision = peer.get('id'), peer.get('avatar_revision')
            state = _known.get(sid)
            if not state or not isinstance(revision, int) or revision <= 0 or state.get('avatar_revision') == revision:
                continue
            image = avatar_provider(sid)
            if image is None:
                continue
            if _queue_avatar(sid, state['id'], revision, image, on_changed):
                state['avatar_revision'] = revision
                queued = True
    return queued


def begin_arena():
    """Remember all peers seen during the duel, even if one disconnects early."""
    global _arena
    with _lock:
        participants = {}
        for sid, state in _known.items():
            # If the same peer stays connected across two duels, create a
            # separate encounter rather than overwriting the previous result.
            if state['steam'].get('outcome'):
                item = {key:value for key,value in state['steam'].items() if key not in ('outcome', 'match_date')}
                ident = record_detection('Joueur Steam rencontré : ' + item['name'], 'Arena', 'steam_encounter', item)
                state = {'steam':item, 'id':ident, 'mode':'Arena'}
                _known[sid] = state
            participants[sid] = state
        _arena = {'participants':participants, 'ambiguous':len(participants) > 1, 'sealed':False}


def seal_arena_participant():
    """Freeze the duel's participants at its result and return a unique Steam name."""
    with _lock:
        if not _arena:
            return ''
        if not _arena.get('sealed'):
            _arena['participants'] = {
                sid: {'steam':dict(state['steam']), 'id':state['id'], 'mode':state['mode']}
                for sid, state in _arena['participants'].items()
            }
            _arena['sealed'] = True
        if _arena['ambiguous'] or len(_arena['participants']) != 1:
            return ''
        state = next(iter(_arena['participants'].values()))
        if state['mode'] not in ('Unknown', 'Arena'):
            return ''
        steam = state['steam']
        name, ident = steam.get('name', '').strip(), steam.get('id', '')
        return name if name and name != ident else ''


def arena_opponent_name():
    """Return the unique Steam participant when the duel was unambiguous."""
    with _lock:
        if not _arena or _arena['ambiguous'] or len(_arena['participants']) != 1:
            return ''
        return next(iter(_arena['participants'].values()))['steam']['name']


def active_arena_participant_id():
    """Return the sole still-connected candidate in the current unsealed duel.

    This is a probable network participant, not a proven game identity. An
    encounter that has ever contained multiple peers remains ambiguous.
    """
    with _lock:
        if not _arena or _arena.get('sealed') or _arena.get('ambiguous') or len(_arena['participants']) != 1:
            return ''
        ident, state = next(iter(_arena['participants'].items()))
        current = _known.get(ident)
        if ident in _arena.get('departed', ()) or not current or current['id'] != state['id'] or state['mode'] not in ('Unknown', 'Arena'):
            return ''
        return ident


def finish_arena(outcome, match_date):
    global _arena
    if outcome not in ('victory', 'defeat', 'draw'):
        raise ValueError('Invalid arena result')
    with _lock:
        session, _arena = _arena, None
        if not session or session['ambiguous'] or len(session['participants']) != 1:
            return False
        state = next(iter(session['participants'].values()))
        if state['mode'] not in ('Unknown', 'Arena'):
            return False
        item = dict(state['steam'], outcome=outcome, match_date=match_date)
        if not update_detection(state['id'], 'Joueur Steam rencontré : ' + item['name'], 'Arena', item):
            return False
        state.update(steam=item, mode='Arena')
        current = _known.get(item['id'])
        if current and current['id'] == state['id']:
            current.update(steam=item, mode='Arena')
        return True


def cancel_arena():
    global _arena
    with _lock:
        _arena = None


def begin_pvp_encounter():
    """Remember Steam peers seen during an invasion or defense, without assigning roles."""
    global _pvp_encounter
    with _lock:
        participants = {sid:dict(state['steam']) for sid, state in _known.items()}
        _pvp_encounter = {'participants':participants, 'ambiguous':len(participants) > 1}


def seal_pvp_participant():
    """Finish observation and return a unique detected Steam name, if available."""
    global _pvp_encounter
    with _lock:
        session, _pvp_encounter = _pvp_encounter, None
        if not session or session['ambiguous'] or len(session['participants']) != 1:
            return ''
        steam = next(iter(session['participants'].values()))
        name, ident = steam.get('name', '').strip(), steam.get('id', '')
        return name if name and name != ident else ''


def cancel_pvp_encounter():
    global _pvp_encounter
    with _lock:
        _pvp_encounter = None

