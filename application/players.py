"""Local opponent journal, derived from recorded captures."""
import sqlite3
from datetime import datetime, timedelta
import unicodedata
from contextlib import closing

from flask import jsonify
from __main__ import app
from application.init import database_capture
from application.secur import renderArray
from application.player_sightings import read_sightings
from application.detection_history import read_steam_history
from application.geoip_country import country_code


@app.route('/players', methods={'GET'})
def players():
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
            'last_seen': '', 'history': [],
        })

    def add_unique(values, value):
        if value not in values:
            values.append(value)

    decoded_records = renderArray(records)
    steam_events = read_steam_history()
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
        player['history'].append({'kind': 'combat', 'date': date, 'mode': str(row[7]), 'outcome': outcome})

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
                'relations': [], 'last_seen': '', 'history': [],
                'steam': {'id': sid, 'name': steam.get('name') or sid,
                          'ip': steam.get('ip'), 'relay': bool(steam.get('relay')), 'country_code': country_code(steam.get('ip')), 'mode': observed['mode']},
            }
        player = players_by_name[key]
        if not player['steam']['ip'] and steam.get('ip'):
            player['steam']['ip'] = steam['ip']
            player['steam']['relay'] = bool(steam.get('relay'))
            player['steam']['country_code'] = country_code(steam.get('ip'))
        player['last_seen'] = max(player['last_seen'], observed['date'])
        match = inferred.get(observed['id'])
        outcome = steam.get('outcome') if steam.get('outcome') in ('victory','defeat','draw') else (match['outcome'] if match else None)
        match_date = steam.get('match_date') or (match['end'].strftime('%Y-%m-%d %H:%M:%S') if match else observed['date'])
        if outcome and observed['mode'] == 'Arena':
            player['total'] += 1
            player[{'victory':'victories','defeat':'defeats','draw':'draws'}[outcome]] += 1
            add_unique(player['roles'], 'opponent')
            add_unique(player['relations'], 'opponent')
        player['history'].append({'kind':'steam', 'date':match_date, 'mode':observed['mode'],
                                  'event':observed['event'], 'outcome':outcome,
                                  'ip':steam.get('ip'), 'relay':bool(steam.get('relay'))})

    result = list(players_by_name.values())
    for player in result:
        player['history'].sort(key=lambda match: match['date'], reverse=True)
        player['history'] = player['history'][:20]
    result.sort(key=lambda player: (player['last_seen'], player['name'].casefold()), reverse=True)
    return jsonify({'request': 'success', 'players': result, 'unnamed_captures': unnamed})
