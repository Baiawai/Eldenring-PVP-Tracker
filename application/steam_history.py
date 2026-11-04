"""Persist Steam connection observations without guessing character identity."""
import ipaddress
import threading
from application.detection_history import record_detection, update_detection

_lock = threading.Lock()
_known = {}
_arena = None

def _clean(peer):
    sid = str(peer.get('id', ''))
    if len(sid) != 17 or not sid.isascii() or not sid.isdigit():
        return None
    name = str(peer.get('name') or sid).strip()[:128] or sid
    raw_ip = peer.get('ip')
    try:
        ip = str(ipaddress.ip_address(str(raw_ip))) if raw_ip else None
    except ValueError:
        ip = None
    return {'id':sid, 'name':name, 'ip':ip, 'relay':bool(peer.get('relay')) if ip else False}

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
                for field in ('outcome', 'match_date'):
                    if field in previous:
                        item[field] = previous[field]
            if previous and not item['ip']:
                item['ip'], item['relay'] = previous['ip'], previous['relay']
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
        if _arena is not None and status == 'active':
            for sid, state in _known.items():
                _arena['participants'][sid] = state
            if len(_arena['participants']) > 1:
                _arena['ambiguous'] = True
        for sid in list(_known):
            if sid not in current:
                _known.pop(sid)
    return changed


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
        _arena = {'participants':participants, 'ambiguous':len(participants) > 1}


def arena_opponent_name():
    """Return the unique Steam participant when the duel was unambiguous."""
    with _lock:
        if not _arena or _arena['ambiguous'] or len(_arena['participants']) != 1:
            return ''
        return next(iter(_arena['participants'].values()))['steam']['name']


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
        return True


def cancel_arena():
    global _arena
    with _lock:
        _arena = None

