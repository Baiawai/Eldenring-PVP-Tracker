"""Persistent local history of messages emitted by the detection counter."""
import json
import sqlite3
from contextlib import closing
from datetime import datetime
from html.parser import HTMLParser

from flask import jsonify, request
from __main__ import app
from application.init import database_capture
from application.secur import encrypt_value, decrypt_value


class _MessageText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == 'br':
            self.parts.append('\n')

    def handle_data(self, data):
        self.parts.append(data)


def message_text(message):
    parser = _MessageText()
    parser.feed(message)
    return '\n'.join(line.strip() for line in ''.join(parser.parts).splitlines() if line.strip())


def _connect():
    con = sqlite3.connect(database_capture, timeout=10)
    con.execute('''CREATE TABLE IF NOT EXISTS detection_history (
        id INTEGER PRIMARY KEY, recorded_at TEXT NOT NULL, mode TEXT NOT NULL,
        message BLOB NOT NULL
    )''')
    columns = {row[1] for row in con.execute('PRAGMA table_info(detection_history)')}
    if 'metadata' not in columns:
        try:
            con.execute('ALTER TABLE detection_history ADD COLUMN metadata BLOB')
        except sqlite3.OperationalError as exc:
            if 'duplicate column' not in str(exc).lower():
                raise
    if 'kind' not in columns:
        try:
            con.execute("ALTER TABLE detection_history ADD COLUMN kind TEXT NOT NULL DEFAULT 'detection'")
        except sqlite3.OperationalError as exc:
            if 'duplicate column' not in str(exc).lower():
                raise
    con.execute('CREATE INDEX IF NOT EXISTS detection_history_mode_id ON detection_history(mode, id DESC)')
    con.execute('CREATE INDEX IF NOT EXISTS detection_history_kind_id ON detection_history(kind, id DESC)')
    con.commit()
    _consolidate_legacy_steam(con)
    _migrate_system_events(con)
    return con


def _consolidate_legacy_steam(con):
    # Preserve old detail rows, but hide them after folding them into the
    # connection that began the encounter. This migration runs only once.
    kinds = "('steam_connected','steam_updated','steam_disconnected')"
    if not con.execute('SELECT 1 FROM detection_history WHERE kind IN ' + kinds + ' LIMIT 1').fetchone():
        return
    con.execute('BEGIN IMMEDIATE')
    rows = con.execute('SELECT id,mode,kind,metadata FROM detection_history WHERE kind IN ' + kinds + ' ORDER BY id').fetchall()
    active, groups = {}, []
    for ident, mode, kind, encrypted in rows:
        if not encrypted:
            con.execute("UPDATE detection_history SET kind='steam_suppressed' WHERE id=?", (ident,))
            continue
        data = json.loads(decrypt_value(encrypted).decode('utf-8'))
        sid = str(data.get('id', ''))
        group = active.get(sid)
        if kind == 'steam_connected' or group is None:
            group = {'id':ident, 'mode':mode, 'steam':data, 'extra':[]}
            groups.append(group)
            active[sid] = group
        else:
            group['extra'].append(ident)
            old = group['steam']
            if data.get('name') and data['name'] != sid:
                old['name'] = data['name']
            if data.get('ip'):
                old['ip'], old['relay'] = data['ip'], bool(data.get('relay'))
            if group['mode'] == 'Unknown' and mode in ('Arena','Invasion','Defense'):
                group['mode'] = mode
        if kind == 'steam_disconnected':
            active.pop(sid, None)
    for group in groups:
        data = group['steam']
        text = 'Joueur Steam rencontré : ' + str(data.get('name') or data.get('id', ''))
        con.execute("UPDATE detection_history SET kind='steam_encounter', mode=?, message=?, metadata=? WHERE id=?",
                    (group['mode'], encrypt_value(text), encrypt_value(json.dumps(data, ensure_ascii=False)), group['id']))
        con.executemany("UPDATE detection_history SET kind='steam_suppressed' WHERE id=?", [(ident,) for ident in group['extra']])
    con.commit()



def _migrate_system_events(con):
    """Classify existing tracking lifecycle events without changing combat events."""
    con.execute('CREATE TABLE IF NOT EXISTS detection_history_migrations (name TEXT PRIMARY KEY)')
    if con.execute("SELECT 1 FROM detection_history_migrations WHERE name='system_events_v1'").fetchone():
        return
    con.execute("UPDATE detection_history SET mode='System' WHERE kind IN ('monitor_start','monitor_stop','monitor_error')")
    rows = con.execute("SELECT id,message FROM detection_history WHERE kind='detection'").fetchall()
    for ident, encrypted in rows:
        try:
            text = decrypt_value(encrypted).decode('utf-8')
        except Exception:
            continue
        if text.startswith("Let's gooo !"):
            con.execute("UPDATE detection_history SET mode='System', kind='monitor_start' WHERE id=?", (ident,))
    con.execute("INSERT OR IGNORE INTO detection_history_migrations(name) VALUES ('system_events_v1')")
    con.commit()


def record_detection(message, mode, kind='detection', metadata=None):
    text = message_text(message)
    if not text:
        return
    if text.startswith("Let's gooo !"):
        text, kind = 'Suivi démarré', 'monitor_start'
    mode = 'System' if kind in ('monitor_start', 'monitor_stop', 'monitor_error') else (mode if mode in ('Arena', 'Invasion', 'Defense') else 'Unknown')
    encoded = encrypt_value(json.dumps(metadata, ensure_ascii=False)) if metadata is not None else None
    with closing(_connect()) as con:
        cursor = con.execute('INSERT INTO detection_history(recorded_at,mode,message,kind,metadata) VALUES (?,?,?,?,?)',
                    (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), mode, encrypt_value(text), kind, encoded))
        con.commit()
        return cursor.lastrowid


def update_detection(event_id, message, mode=None, metadata=None):
    text = message_text(message)
    if not event_id or not text:
        return False
    with closing(_connect()) as con:
        fields, values = ['message=?'], [encrypt_value(text)]
        if mode in ('Arena', 'Invasion', 'Defense'):
            fields.append('mode=?')
            values.append(mode)
        if metadata is not None:
            fields.append('metadata=?')
            values.append(encrypt_value(json.dumps(metadata, ensure_ascii=False)))
        values.append(event_id)
        cursor = con.execute('UPDATE detection_history SET ' + ','.join(fields) + ' WHERE id=?', values)
        con.commit()
        return cursor.rowcount == 1


@app.route('/detection-history', methods=['GET'])
def detection_history():
    mode = request.args.get('mode', 'all')
    if mode not in ('all', 'Arena', 'Invasion', 'Defense', 'Unknown', 'System'):
        return jsonify({'request': 'error'}), 400
    try:
        before = int(request.args.get('before', '0'))
    except ValueError:
        return jsonify({'request': 'error'}), 400
    if before < 0:
        return jsonify({'request': 'error'}), 400
    conditions, params = ["kind != 'steam_suppressed'"], []
    if mode != 'all':
        conditions.append('mode=?')
        params.append(mode)
    if before:
        conditions.append('id<?')
        params.append(before)
    where = ' WHERE ' + ' AND '.join(conditions) if conditions else ''
    with closing(_connect()) as con:
        rows = con.execute('SELECT id,recorded_at,mode,message,kind,metadata FROM detection_history' + where +
                           ' ORDER BY id DESC LIMIT 51', params).fetchall()
    events = []
    for row in rows[:50]:
        text = decrypt_value(row[3]).decode('utf-8')
        kind = row[4]
        if text.startswith("Let's gooo !"):
            text, kind = 'Suivi démarré', 'monitor_start'
        event_mode = 'System' if kind in ('monitor_start', 'monitor_stop', 'monitor_error') else row[2]
        metadata = json.loads(decrypt_value(row[5]).decode('utf-8')) if row[5] else None
        events.append({'id':row[0], 'date':row[1], 'mode':event_mode, 'message':text,
                       'kind':kind, 'metadata':metadata})
    return jsonify({'request':'success', 'events':events, 'has_more':len(rows)>50})


def read_steam_history():
    with closing(_connect()) as con:
        rows = con.execute("SELECT id,recorded_at,mode,kind,metadata FROM detection_history WHERE kind='steam_encounter' ORDER BY id DESC").fetchall()
    return [{'id':row[0], 'date':row[1], 'mode':row[2], 'event':row[3], 'steam':json.loads(decrypt_value(row[4]).decode('utf-8'))}
            for row in rows if row[4]]
