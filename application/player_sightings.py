"""Recognize and store observed cooperator and hunter notifications."""
import hashlib
import hmac
import re
import sqlite3
import time
import unicodedata
from contextlib import closing
from datetime import datetime

from application.init import database_capture
from application.secur import app_get, app_insert, app_name


def _connect():
    con = sqlite3.connect(database_capture, timeout=10)
    con.execute('''CREATE TABLE IF NOT EXISTS player_sightings (
        id INTEGER PRIMARY KEY, name BLOB NOT NULL, name_key TEXT NOT NULL,
        role TEXT NOT NULL, relation TEXT NOT NULL, mode TEXT NOT NULL,
        event TEXT NOT NULL, observed_at TEXT NOT NULL
    )''')
    con.execute('CREATE INDEX IF NOT EXISTS player_sightings_lookup ON player_sightings (name_key, role, relation, mode, observed_at)')
    con.commit()
    return con


def parse_sightings(text, mode, mode_detected, in_combat=True):
    """Only use phrases observed in actual game OCR; preserve uncertain context."""
    text = unicodedata.normalize('NFKC', text or '')
    context = mode if mode_detected and in_combat and mode in ('Arena', 'Invasion', 'Defense') else 'Unknown'
    result = []
    ally = re.search(r'\bdoigt\s+crochu\s+alli[ée]\s+([^\r\n]{1,64}?)\s+invoqu[ée]\b', text, re.IGNORECASE)
    if ally and context != 'Arena':
        name = ' '.join(ally.group(1).split()).strip(' .!…')
        if name and any(char.isalnum() for char in name):
            if context == 'Invasion':
                result.append({'name': name, 'role': 'cooperator', 'relation': 'opponent',
                               'mode': 'Invasion', 'event': 'joined'})
            else:
                result.append({'name': name, 'role': 'ally', 'relation': 'ally',
                               'mode': 'Defense', 'event': 'joined'})
    departure = re.search(r'\bdoigt\s+crochu(?:\s+alli[ée])?\s+([^\r\n]{1,64}?)\s+(est\s+retourn[ée]|a\s+[ée]t[ée]\s+renvoy[ée])\s+dans\s+son\s+monde\b', text, re.IGNORECASE)
    if departure and context != 'Arena':
        name = ' '.join(departure.group(1).split()).strip(' .!…')
        if name and any(char.isalnum() for char in name):
            hostile = context == 'Invasion'
            result.append({'name': name, 'role': 'cooperator' if hostile else 'ally',
                           'relation': 'opponent' if hostile else 'ally',
                           'mode': 'Invasion' if hostile else 'Defense',
                           'event': 'dismissed' if re.search(r'renvoy[ée]', departure.group(2), re.IGNORECASE) else 'left'})
    hunter = re.search(r'\binvocation\s+du\s+chasseur\s+([^\r\n]{1,64})', text, re.IGNORECASE)
    if hunter:
        name = ' '.join(hunter.group(1).split()).strip(' .!…')
        if name and any(char.isalnum() for char in name):
            relation = 'opponent' if context == 'Invasion' else 'ally' if context == 'Defense' else 'unknown'
            result.append({'name': name, 'role': 'hunter', 'relation': relation,
                           'mode': context, 'event': 'summoning'})
    hunter_event = re.search(r'\bchasseur\s+([^\r\n]{1,64}?)\s+(est\s+mort|est\s+retourn[ée]\s+dans\s+son\s+monde|a\s+[ée]t[ée]\s+renvoy[ée]\s+dans\s+son\s+monde|invoqu[ée]|a\s+rejoint\s+votre\s+monde)\b', text, re.IGNORECASE)
    if hunter_event:
        name = ' '.join(hunter_event.group(1).split()).strip(' .!…')
        if name and any(char.isalnum() for char in name):
            action = hunter_event.group(2).casefold()
            event = 'died' if 'mort' in action else 'dismissed' if 'renvoy' in action else 'left' if 'retourn' in action else 'joined'
            relation = 'opponent' if context == 'Invasion' else 'ally' if context == 'Defense' else 'unknown'
            result.append({'name': name, 'role': 'hunter', 'relation': relation, 'mode': context, 'event': event})
    if context in ('Invasion', 'Defense'):
        # A death identifies a participant, not who dealt the final blow.
        if context == 'Invasion':
            cooperator_death = re.search(r'\bdoigt\s+crochu(?:\s+alli[ée])?\s+([^\r\n]{1,64}?)\s+est\s+mort\b', text, re.IGNORECASE)
            if cooperator_death:
                name = ' '.join(cooperator_death.group(1).split()).strip(' .!…')
                if name and any(char.isalnum() for char in name):
                    result.append({'name': name, 'role': 'cooperator', 'relation': 'opponent',
                                   'mode': 'Invasion', 'event': 'died'})
        invader = re.search(
            r'\b(?:doigt\s+sanglant|(?:doigt\s+)?r[ée]fractaire)\s+([^\r\n]{1,64}?)\s+'
            r'(est\s+mort|a\s+p[ée]ri|a\s+envahi\s+votre\s+monde)\b', text, re.IGNORECASE)
        arrival = re.search(
            r'\binvasion\s+par\s+(?:le\s+)?(?:doigt\s+sanglant|r[ée]fractaire)\s+([^\r\n]{1,64})',
            text, re.IGNORECASE)
        if invader or arrival:
            match = invader or arrival
            name = ' '.join(match.group(1).split()).strip(' .!…')
            if name and any(char.isalnum() for char in name):
                action = invader.group(2).casefold() if invader else ''
                event = 'died' if action.startswith(('est', 'a péri', 'a peri')) else 'invaded'
                result.append({'name': name, 'role': 'invader',
                               'relation': 'coinvader' if context == 'Invasion' else 'opponent',
                               'mode': context, 'event': event})
    return result


def record_sighting(sighting, observed_at=None):
    """Coalesce repeated frames without merging separate arrivals."""
    if sighting['role'] == 'ally' and (sighting['relation'] != 'ally' or sighting['mode'] != 'Defense'):
        raise ValueError('An invoked ally must belong to Defense')
    observed = datetime.fromisoformat(observed_at) if observed_at else datetime.now()
    timestamp = observed.strftime('%Y-%m-%d %H:%M:%S')
    name = unicodedata.normalize('NFKC', sighting['name']).strip()
    key = hmac.new(app_name(), name.casefold().encode('utf-8'), hashlib.sha256).hexdigest()
    with closing(_connect()) as con:
        con.execute('BEGIN IMMEDIATE')
        previous = con.execute('''SELECT id, observed_at, relation, mode FROM player_sightings
            WHERE name_key=? AND role=? AND event=? AND observed_at<=?
            ORDER BY observed_at DESC LIMIT 1''',
            (key, sighting['role'], sighting['event'], timestamp)).fetchone()
        if previous and 0 <= (observed - datetime.fromisoformat(previous[1])).total_seconds() < 45:
            if previous[2] == 'unknown' and sighting['relation'] != 'unknown':
                con.execute('UPDATE player_sightings SET relation=?, mode=? WHERE id=?',
                            (sighting['relation'], sighting['mode'], previous[0]))
                con.commit()
                return True
            if previous[2] == sighting['relation']:
                if previous[3] == 'Unknown' and sighting['mode'] != 'Unknown':
                    con.execute('UPDATE player_sightings SET mode=? WHERE id=?', (sighting['mode'], previous[0]))
                    con.commit()
                    return True
                con.commit()
                return False
        con.execute('''INSERT INTO player_sightings
            (name, name_key, role, relation, mode, event, observed_at) VALUES (?,?,?,?,?,?,?)''',
            (app_insert(name), key, sighting['role'], sighting['relation'], sighting['mode'], sighting['event'], timestamp))
        con.commit()
    return True


def read_sightings():
    with closing(_connect()) as con:
        rows = con.execute('SELECT name, role, relation, mode, event, observed_at FROM player_sightings').fetchall()
    return [{'name': app_get(row[0]).decode('utf-8'), 'role': row[1], 'relation': row[2],
             'mode': row[3], 'event': row[4], 'date': row[5]} for row in rows]


class SightingTracker:
    """Confirm a name using both OCR readings or two successive frames."""
    def __init__(self):
        self.pending = {}

    def observe(self, primary, alternate, mode, mode_detected, now=None, in_combat=True):
        now = time.monotonic() if now is None else now
        self.pending = {key: seen for key, seen in self.pending.items() if now - seen <= 15}
        first = parse_sightings(primary, mode, mode_detected, in_combat)
        second = parse_sightings(alternate, mode, mode_detected, in_combat)
        key_for = lambda item: (item['name'].casefold(), item['role'], item['relation'], item['mode'], item['event'])
        primary_keys = {key_for(item) for item in first}
        secondary_keys = {key_for(item) for item in second}
        roles_in_second = {item['role'] for item in second}
        candidates = second + [item for item in first if item['role'] not in roles_in_second]
        confirmed = []
        for candidate in candidates:
            key = key_for(candidate)
            if (key in primary_keys and key in secondary_keys) or key in self.pending:
                self.pending.pop(key, None)
                confirmed.append(candidate)
            else:
                self.pending[key] = now
        return confirmed
