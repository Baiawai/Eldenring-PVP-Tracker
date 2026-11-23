"""Local opponent journal, derived from recorded captures."""
import sqlite3
import base64
import binascii
import secrets
import time
import threading
from datetime import datetime, timedelta
import unicodedata
from contextlib import closing

from flask import abort, jsonify, request, Response
from cryptography.fernet import InvalidToken
from __main__ import app
from application.init import database_capture
from application.secur import decrypt_rows
from application.player_sightings import read_sightings
from application.detection_history import read_steam_history
from application import steam_avatar_store, player_tags, steam_friendships


_steam_event_index_lock = threading.Lock()
_steam_event_index = {}
_player_snapshots_lock = threading.Lock()
_player_snapshots = {}
_PLAYER_SNAPSHOT_TTL = 90


@app.route('/players/categories', methods={'GET', 'POST'})
def player_categories():
    if request.method == 'GET':
        counts = player_tags.category_counts()
        friends = sum(steam_friendships.known_relationships(read_steam_history()).values())
        if friends:
            counts['steam_friend'] = friends
        return jsonify({'categories': player_tags.categories(), 'counts': counts, 'multi_category':True})
    payload = request.get_json(silent=True)
    try:
        category = player_tags.create_category(payload.get('name') if isinstance(payload, dict) else None,
                                               payload.get('color', player_tags.CUSTOM_COLOUR) if isinstance(payload, dict) else None)
    except ValueError as error:
        return jsonify(error=str(error)), 400
    return jsonify({'category': category}), 201


@app.route('/players/categories/<category_id>', methods={'DELETE'})
def delete_player_category(category_id):
    try:
        deleted = player_tags.delete_category(category_id)
    except ValueError:
        return jsonify(error='default_category'), 403
    if not deleted:
        return jsonify(error='invalid_category'), 404
    with _player_snapshots_lock:
        _player_snapshots.clear()
    return jsonify({'request': 'success'})


@app.route('/players/preferences', methods={'POST'})
def player_preferences():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error='invalid_request'), 400
    try:
        legacy = 'categories' not in payload
        changed = player_tags.set_preference(payload.get('source'), payload.get('identity'),
                                            payload.get('category') if legacy else payload.get('categories'), payload.get('favourite'), legacy=legacy)
    except ValueError as error:
        return jsonify(error=str(error)), 400
    with _player_snapshots_lock:
        key = player_tags.identity(payload['source'], payload['identity'])
        for token, cached in list(_player_snapshots.items()):
            filter_category = cached.get('category_filter', '')
            membership_changed = filter_category and ((filter_category in changed['previous_categories']) != (filter_category in changed['categories']))
            if membership_changed or (cached.get('filter') == 'favourite' and changed['favourite_changed']):
                _player_snapshots.pop(token, None)
                continue
            for player in cached['players']:
                try:
                    matches = player_tags.player_identity(player) == key
                except (KeyError, TypeError, ValueError):
                    matches = False
                if matches:
                    player['categories'] = (['steam_friend'] if player.get('steam') and player.get('steam_friend') is True else []) + changed['categories'][:]
                    player['category'] = changed['categories'][0] if changed['categories'] else None
                    player['favourite'] = changed['favourite']
    return jsonify({'request': 'success'})


@app.route('/players/steam-avatar/<steam_id>', methods={'GET'})
def player_steam_avatar(steam_id):
    # Only cached avatars linked to active Steam encounters are available.
    try:
        data = steam_avatar_store.avatar(steam_id)
    except (OSError, sqlite3.Error):
        data = None
    if not data:
        abort(404)
    response = Response(data, mimetype='image/png')
    response.headers['Cache-Control'] = 'no-store'
    return response


@app.route('/players/capture/<int:capture_id>', methods={'GET'})
def player_capture_image(capture_id):
    """Load one existing image on demand, without changing capture state."""
    with closing(sqlite3.connect(database_capture, timeout=10)) as con:
        row = con.execute('SELECT id,base64 FROM tabel_captures WHERE id=?', (capture_id,)).fetchone()
    if not row or not row[1]:
        abort(404)
    try:
        image = base64.b64decode(decrypt_rows([row])[0][1], validate=True)
    except (ValueError, TypeError, UnicodeError, binascii.Error, InvalidToken):
        abort(404)
    if not image:
        abort(404)
    response = Response(image, mimetype='image/jpeg')
    response.headers['Cache-Control'] = 'no-store'
    return response


@app.route('/players/steam-avatar/request', methods={'POST'})
def request_player_steam_avatar():
    steam_id = request.form.get('steam_id', '')
    if len(steam_id) != 17 or not steam_id.isascii() or not steam_id.isdigit():
        abort(404)
    with _steam_event_index_lock:
        event_ids = tuple(_steam_event_index.get(steam_id, ())[:steam_avatar_store.MAX_EVENT_IDS])
    try:
        if not steam_avatar_store.active_event_matches(steam_id, event_ids):
            abort(404)
        if steam_avatar_store.avatar(steam_id):
            return jsonify({'state': 'cached'})
        # This only queues an existing helper: it cannot start Steam or the game.
        from application import peer_tracking
        enqueue = getattr(peer_tracking, 'request_historical_avatar', None)
        state = enqueue(steam_id, event_ids) if callable(enqueue) else 'unavailable'
        if state not in ('queued', 'unavailable', 'rate_limited'):
            state = 'unavailable'
        return jsonify({'state': state})
    except (OSError, sqlite3.Error):
        return jsonify({'state': 'unavailable'})


def _build_players():
    global _steam_event_index
    with closing(sqlite3.connect(database_capture)) as con:
        records = con.execute(
            'SELECT id, name, victory, defeat, egality, time, date, mode '
            'FROM tabel_captures ORDER BY id DESC'
        ).fetchall()

    players_by_name = {}
    unnamed = 0
    def get_player(name):
        key = name.casefold()
        return players_by_name.setdefault(key, {
            'name': name, 'total': 0, 'victories': 0, 'defeats': 0,
            'draws': 0, 'sightings': 0, 'roles': [], 'relations': [],
            'last_seen': '', 'history': [], 'capture_refs': [],
        })

    def add_unique(values, value):
        if value not in values:
            values.append(value)

    decoded_records = decrypt_rows(records)
    steam_events = read_steam_history()
    friendships = steam_friendships.known_relationships(steam_events)
    # A recorded arena result identifies one Steam participant only when both
    # the capture and the Steam event are unique for the date and outcome.
    captures_by_result, events_by_result = {}, {}
    for row in decoded_records:
        flags = [str(value) == '1' for value in row[2:5]]
        outcome = ('victory' if flags == [True, False, False] else
                   'defeat' if flags == [False, True, False] else
                   'draw' if flags == [False, False, True] else None)
        if row[7] == 'Arena' and outcome:
            captures_by_result.setdefault((str(row[6]).strip(), outcome), []).append(row)
    for event in steam_events:
        steam = event['steam']
        if event['mode'] == 'Arena' and steam.get('match_date') and steam.get('outcome') in ('victory','defeat','draw'):
            events_by_result.setdefault((steam['match_date'], steam['outcome']), []).append(event)
    explicit_capture = {}
    for result_key, events in events_by_result.items():
        candidates_for_result = captures_by_result.get(result_key, [])
        if len(events) == 1 and len(candidates_for_result) == 1:
            explicit_capture[events[0]['id']] = candidates_for_result[0]
    record_by_id = {row[0]:row for row in decoded_records}

    def capture_ref(row, opponent=''):
        flags = [str(value) == '1' for value in row[2:5]]
        outcome = ('victory' if flags == [True, False, False] else
                   'defeat' if flags == [False, True, False] else
                   'draw' if flags == [False, False, True] else '')
        return {'id':row[0], 'date':str(row[6]).strip(), 'mode':str(row[7]),
                'outcome':outcome, 'duration':str(row[5]), 'opponent':opponent}
    index = {}
    for event in steam_events:
        value = event['steam'].get('id')
        sid = str(value) if isinstance(value, (str, int)) and not isinstance(value, bool) else ''
        if len(sid) == 17 and sid.isascii() and sid.isdigit():
            index.setdefault(sid, []).append(event['id'])
    with _steam_event_index_lock:
        _steam_event_index = index
    arena_matches = []
    for row in decoded_records:
        if str(row[7]) != 'Arena' or str(row[1]).strip():
            continue
        flags = [str(value) == '1' for value in row[2:5]]
        outcome = ('victory' if flags == [True, False, False] else
                   'defeat' if flags == [False, True, False] else
                   'draw' if flags == [False, False, True] else None)
        try:
            end = datetime.fromisoformat(str(row[6]))
            duration = float(row[5])
        except (ValueError, TypeError):
            continue
        if outcome and 0 <= duration <= 3600:
            arena_matches.append({'id':row[0], 'end':end, 'duration':duration, 'outcome':outcome})

    # Backfill old unnamed arena captures only when the timing identifies one
    # and only one Steam encounter, and that encounter matches one capture.
    matched_capture_ids, inferred = set(), {}
    for event in steam_events:
        steam = event['steam']
        if steam.get('outcome') in ('victory', 'defeat', 'draw') and steam.get('match_date'):
            same = [m for m in arena_matches if m['end'].strftime('%Y-%m-%d %H:%M:%S') == steam['match_date'] and m['outcome'] == steam['outcome']]
            if len(same) == 1:
                matched_capture_ids.add(same[0]['id'])
    candidates = {}
    reverse = {}
    for match in arena_matches:
        if match['id'] in matched_capture_ids:
            continue
        earliest = match['end'] - timedelta(seconds=match['duration'] + 45)
        possible = []
        for event in steam_events:
            if event['steam'].get('outcome'):
                continue
            try:
                observed = datetime.fromisoformat(event['date'])
            except (ValueError, TypeError):
                continue
            if earliest <= observed <= match['end']:
                possible.append(event)
        if len(possible) == 1 and possible[0]['mode'] == 'Arena':
            candidates[match['id']] = possible[0]
            reverse.setdefault(possible[0]['id'], []).append(match)
    for match in arena_matches:
        event = candidates.get(match['id'])
        if event and len(reverse[event['id']]) == 1:
            inferred[event['id']] = match
            matched_capture_ids.add(match['id'])

    for row in decoded_records:
        name = unicodedata.normalize('NFKC', str(row[1])).strip()
        if not any(character.isalnum() for character in name):
            if row[0] not in matched_capture_ids:
                unnamed += 1
            continue
        player = get_player(name)
        add_unique(player['roles'], 'opponent')
        add_unique(player['relations'], 'opponent')
        flags = [str(value) == '1' for value in row[2:5]]
        outcome = ('victory' if flags == [True, False, False] else
                   'defeat' if flags == [False, True, False] else
                   'draw' if flags == [False, False, True] else 'unknown')
        player['total'] += 1
        if outcome == 'victory':
            player['victories'] += 1
        elif outcome == 'defeat':
            player['defeats'] += 1
        elif outcome == 'draw':
            player['draws'] += 1
        date = str(row[6]).strip()
        player['last_seen'] = max(player['last_seen'], date)
        player['history'].append({'kind': 'combat', 'date': date, 'mode': str(row[7]), 'outcome': outcome, 'capture_id':row[0]})
        player['capture_refs'].append(capture_ref(row, name))

    for sighting in read_sightings():
        name = unicodedata.normalize('NFKC', sighting['name']).strip()
        if not any(character.isalnum() for character in name):
            continue
        player = get_player(name)
        add_unique(player['roles'], sighting['role'])
        add_unique(player['relations'], sighting['relation'])
        player['sightings'] += 1
        player['last_seen'] = max(player['last_seen'], sighting['date'])
        player['history'].append({'kind': 'sighting', 'date': sighting['date'], 'mode': sighting['mode'],
                                  'role': sighting['role'], 'relation': sighting['relation'], 'event': sighting['event']})

    # Steam profiles are keyed by Steam ID and remain distinct from OCR names:
    # identical display names do not prove that they are the same person.
    steam_capture_ids = {}
    for observed in steam_events:
        steam = observed['steam']
        sid = str(steam.get('id', ''))
        if not sid:
            continue
        key = ('steam', sid)
        if key not in players_by_name:
            players_by_name[key] = {
                'name': steam.get('name') or sid, 'total': 0, 'victories': 0,
                'defeats': 0, 'draws': 0, 'sightings': 0, 'roles': ['steam'],
                'relations': [], 'last_seen': '', 'history': [], 'capture_refs': [],
                'steam_friend': friendships.get(sid),
                'steam': {'id': sid, 'name': steam.get('name') or sid,
                          'country_code': steam.get('country_code'), 'mode': observed['mode']},
            }
        player = players_by_name[key]
        if not player['steam']['country_code'] and steam.get('country_code'):
            player['steam']['country_code'] = steam['country_code']
        player['last_seen'] = max(player['last_seen'], observed['date'])
        match = inferred.get(observed['id'])
        outcome = steam.get('outcome') if steam.get('outcome') in ('victory','defeat','draw') else (match['outcome'] if match else None)
        match_date = steam.get('match_date') or (match['end'].strftime('%Y-%m-%d %H:%M:%S') if match else observed['date'])
        if outcome and observed['mode'] == 'Arena':
            player['total'] += 1
            player[{'victory':'victories','defeat':'defeats','draw':'draws'}[outcome]] += 1
            add_unique(player['roles'], 'opponent')
            add_unique(player['relations'], 'opponent')
        matched_row = explicit_capture.get(observed['id']) or (record_by_id.get(match['id']) if match else None)
        entry = {'kind':'steam', 'date':match_date, 'mode':observed['mode'],
                 'event':observed['event'], 'outcome':outcome}
        if matched_row is not None:
            entry['capture_id'] = matched_row[0]
            seen = steam_capture_ids.setdefault(sid, set())
            if matched_row[0] not in seen:
                seen.add(matched_row[0])
                player['capture_refs'].append(capture_ref(matched_row, str(matched_row[1]).strip() or steam.get('name') or sid))
        player['history'].append(entry)

    result = list(players_by_name.values())
    for player in result:
        player['history'].sort(key=lambda match: match['date'], reverse=True)
        player['history'] = player['history'][:20]
        player['capture_refs'].sort(key=lambda capture: capture['id'], reverse=True)
    result.sort(key=lambda player: (player['last_seen'], player['name'].casefold()), reverse=True)
    return result, unnamed


def _with_avatars(players):
    steam_ids = [player['steam']['id'] for player in players if player.get('steam')]
    try:
        cached_avatars = steam_avatar_store.available(steam_ids)
    except (OSError, sqlite3.Error):
        cached_avatars = set()
    # Avoid mutating cached snapshots while requests may overlap.
    return [{**player, 'steam': {**player['steam'], 'avatar_available': player['steam']['id'] in cached_avatars}}
            if player.get('steam') else player for player in players]


def _search_key(value):
    value = unicodedata.normalize('NFKD', value)
    return ''.join(c for c in value if not unicodedata.combining(c)).lower()


@app.route('/players', methods={'GET'})
def players():
    # Keep the original response for older cached clients.
    if request.args.get('limit') != '30':
        result, unnamed = _build_players()
        return jsonify({'request': 'success', 'players': _with_avatars(player_tags.annotate(result)), 'unnamed_captures': unnamed})
    try:
        offset = int(request.args.get('offset', '0'))
        if offset < 0:
            raise ValueError
    except ValueError:
        return jsonify(error='invalid_request'), 400
    token = request.args.get('snapshot', '')
    if token:
        now = time.monotonic()
        with _player_snapshots_lock:
            snapshot = _player_snapshots.get(token)
            if snapshot and now - snapshot['created'] <= _PLAYER_SNAPSHOT_TTL:
                snapshot['created'] = now
            else:
                _player_snapshots.pop(token, None)
                snapshot = None
        if snapshot is None:
            return jsonify(error='snapshot_expired'), 409
    else:
        result, unnamed = _build_players()
        result = player_tags.annotate(result)
        query = _search_key(request.args.get('q', '').strip())
        active_filter = request.args.get('filter', 'all')
        sort = request.args.get('sort', 'recent')
        category = request.args.get('category', '')
        target_id = request.args.get('target_id', '')
        target_source = request.args.get('target_source', '')
        target_name = _search_key(request.args.get('target_name', ''))
        if active_filter not in ('all', 'opponent', 'ally', 'hunter', 'victory', 'defeat', 'favourite') or sort not in ('recent', 'matches', 'name') or (category and category not in {c['id'] for c in player_tags.categories()}):
            return jsonify(error='invalid_request'), 400
        filtered = [p for p in result if (query in _search_key(p['name']) or (target_id and str(p.get('steam', {}).get('id', '')) == target_id)) and
                    (active_filter == 'all' or
                     active_filter in ('opponent', 'ally') and active_filter in p['relations'] or
                     active_filter == 'hunter' and 'hunter' in p['roles'] or
                     active_filter == 'victory' and p['victories'] > 0 or
                     active_filter == 'defeat' and p['defeats'] > 0 or
                     active_filter == 'favourite' and p['favourite']) and
                    (not category or category in p['categories'])]
        if sort == 'name':
            filtered.sort(key=lambda p: (_search_key(p['name']), p['name']))
        else:
            filtered.sort(key=lambda p: (_search_key(p['name']), p['name']))
            filtered.sort(key=lambda p: p['last_seen'], reverse=True)
            if sort == 'matches':
                filtered.sort(key=lambda p: p['total'], reverse=True)
        exact = [p for p in filtered if (str(p.get('steam', {}).get('id', '')) == target_id if target_id else
                 bool(target_name) and _search_key(p['name']) == target_name and
                 (target_source != 'steam' or bool(p.get('steam'))) and (target_source != 'game' or not p.get('steam')))]
        if len(exact) == 1:
            filtered.remove(exact[0])
            filtered.insert(0, exact[0])
        snapshot = {'created': time.monotonic(), 'players': filtered, 'unnamed': unnamed, 'filter':active_filter, 'category_filter':category,
                    'count': len(result), 'victories': sum(p['victories'] for p in result),
                    'defeats': sum(p['defeats'] for p in result),
                    'has_summoning': any(any(h.get('event') == 'summoning' for h in p['history']) for p in result),
                    'has_steam': any(bool(p.get('steam')) for p in result),
                    'exact_match': len(exact) == 1}
        token = secrets.token_urlsafe(18)
        with _player_snapshots_lock:
            now = time.monotonic()
            for old in [key for key, value in _player_snapshots.items() if now - value['created'] > _PLAYER_SNAPSHOT_TTL]:
                _player_snapshots.pop(old, None)
            while len(_player_snapshots) >= 3:
                _player_snapshots.pop(min(_player_snapshots, key=lambda key: _player_snapshots[key]['created']))
            _player_snapshots[token] = snapshot
    items = snapshot['players'][offset:offset + 30]
    return jsonify({'request': 'success', 'players': _with_avatars(items), 'unnamed_captures': snapshot['unnamed'],
                    'snapshot': token, 'next_offset': offset + len(items), 'has_more': offset + len(items) < len(snapshot['players']),
                    'filtered_count': len(snapshot['players']), 'count': snapshot['count'], 'victories': snapshot['victories'],
                    'defeats': snapshot['defeats'], 'has_summoning': snapshot['has_summoning'],
                    'has_steam': snapshot['has_steam'], 'exact_match': snapshot['exact_match']})
