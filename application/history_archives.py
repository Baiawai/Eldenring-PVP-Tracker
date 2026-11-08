"""Local, encrypted snapshots of detection history in the capture database."""
import sqlite3
from contextlib import closing
from datetime import datetime

from flask import jsonify
from __main__ import app
from application import detection_history, functions, steam_history


def _schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS history_archives (
        id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL,
        event_count INTEGER NOT NULL, payload_bytes INTEGER NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS history_archive_events (
        archive_id INTEGER NOT NULL, original_id INTEGER NOT NULL,
        recorded_at TEXT NOT NULL, mode TEXT NOT NULL, message BLOB NOT NULL,
        kind TEXT NOT NULL, metadata BLOB,
        PRIMARY KEY(archive_id, original_id))''')
    db.commit()


def _history_usage(db):
    count, payload = db.execute('''SELECT COUNT(*), COALESCE(SUM(
        length(message) + COALESCE(length(metadata),0) + length(recorded_at) + length(mode) + length(kind)),0)
        FROM detection_history''').fetchone()
    try:
        allocated = db.execute("SELECT COALESCE(SUM(pgsize),0) FROM dbstat WHERE name IN ('detection_history','detection_history_mode_id','detection_history_kind_id')").fetchone()[0]
    except sqlite3.DatabaseError:
        allocated = None
    return {'events':count, 'bytes':allocated if allocated is not None else payload,
            'estimated':allocated is None}


@app.route('/history-storage', methods=['GET'])
def history_storage():
    with closing(detection_history._connect()) as db:
        _schema(db)
        usage = _history_usage(db)
        archives = [{'id':row[0], 'created_at':row[1], 'events':row[2], 'bytes':row[3]}
                    for row in db.execute('SELECT id,created_at,event_count,payload_bytes FROM history_archives ORDER BY id DESC')]
    return jsonify({'request':'success', 'history':usage, 'archives':archives, 'monitor_running':functions.run_monitor})


def _when_stopped(operation):
    # The monitor holds this lock for its whole lifetime. Acquiring it also
    # prevents a new monitor from starting during the destructive transaction.
    if functions.run_monitor or not functions.monitor_lock.acquire(blocking=False):
        return None
    try:
        if functions.run_monitor:
            return None
        def change():
            with closing(detection_history._connect()) as db:
                _schema(db)
                db.execute('BEGIN IMMEDIATE')
                result = operation(db)
                db.commit()
            return result
        result = steam_history.clear_history_transaction(change)
        functions.invasion_search_history_id = None
        return result
    finally:
        functions.monitor_lock.release()


@app.route('/history-purge', methods=['POST'])
def history_purge():
    def purge(db):
        count = db.execute('SELECT COUNT(*) FROM detection_history').fetchone()[0]
        db.execute('DELETE FROM detection_history')
        return count
    count = _when_stopped(purge)
    if count is None:
        return jsonify({'request':'error', 'reason':'monitor_running'}), 409
    return jsonify({'request':'success', 'removed':count})


@app.route('/history-archives', methods=['POST'])
def history_archive():
    def archive(db):
        count, payload = db.execute('''SELECT COUNT(*), COALESCE(SUM(length(message) + COALESCE(length(metadata),0)
            + length(recorded_at) + length(mode) + length(kind)),0) FROM detection_history''').fetchone()
        if not count:
            return 0
        cursor = db.execute('INSERT INTO history_archives(created_at,event_count,payload_bytes) VALUES(?,?,?)',
                            (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), count, payload))
        db.execute('''INSERT INTO history_archive_events(archive_id,original_id,recorded_at,mode,message,kind,metadata)
            SELECT ?,id,recorded_at,mode,message,kind,metadata FROM detection_history''', (cursor.lastrowid,))
        db.execute('DELETE FROM detection_history')
        return count
    count = _when_stopped(archive)
    if count is None:
        return jsonify({'request':'error', 'reason':'monitor_running'}), 409
    if not count:
        return jsonify({'request':'error', 'reason':'empty'}), 409
    return jsonify({'request':'success', 'archived':count})


@app.route('/history-archives/<int:archive_id>/restore', methods=['POST'])
def history_restore(archive_id):
    with closing(detection_history._connect()) as db:
        _schema(db)
        db.execute('BEGIN IMMEDIATE')
        archive = db.execute('SELECT 1 FROM history_archives WHERE id=?', (archive_id,)).fetchone()
        if not archive:
            return jsonify({'request':'error', 'reason':'not_found'}), 404
        before = db.total_changes
        db.execute('''INSERT OR IGNORE INTO detection_history(id,recorded_at,mode,message,kind,metadata)
            SELECT original_id,recorded_at,mode,message,kind,metadata FROM history_archive_events WHERE archive_id=?''', (archive_id,))
        restored = db.total_changes - before
        db.execute('UPDATE detection_history_sequence SET last_id=MAX(last_id, (SELECT COALESCE(MAX(id),0) FROM detection_history)) WHERE id=1')
        db.commit()
    return jsonify({'request':'success', 'restored':restored})
