"""Local, aggregate usage counters and current-process diagnostics."""
import ctypes
import os
import sqlite3
import threading
import time
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from application.runtime_paths import data_dir

FEATURES = {'statistics', 'captures', 'players', 'history', 'settings', 'leaderboard', 'information'}
DB = data_dir() / 'usage_metrics.db'
_lock = threading.RLock()
_session = None
_started = None
_cpu_sample = None
_metrics = {'ocr_count': 0, 'ocr_errors': 0, 'ocr_seconds': 0.0,
            'sync_ok': 0, 'sync_failed': 0, 'sync_seconds': 0.0, 'monitor_errors': 0}


def _connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(DB), timeout=5)
    db.executescript('''CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, started TEXT NOT NULL, seconds REAL NOT NULL DEFAULT 0);
      CREATE TABLE IF NOT EXISTS days (day TEXT PRIMARY KEY);
      CREATE TABLE IF NOT EXISTS features (name TEXT PRIMARY KEY, visits INTEGER NOT NULL DEFAULT 0);''')
    return db


def start():
    global _session, _started
    with _lock:
        if _session is not None:
            return
        ident, now, tick = uuid.uuid4().hex, datetime.now(), time.monotonic()
        with _connect() as db:
            db.execute('INSERT INTO sessions(id,started) VALUES (?,?)', (ident, now.isoformat(timespec='seconds')))
            db.execute('INSERT OR IGNORE INTO days(day) VALUES (?)', (now.date().isoformat(),))
        _session, _started = ident, tick
    def checkpoint_loop():
        while True:
            time.sleep(30)
            try:
                checkpoint()
            except Exception:
                # Instrumentation must never stop tracking.
                pass
    threading.Thread(target=checkpoint_loop, name='usage-checkpoint', daemon=True).start()


def checkpoint():
    with _lock:
        if _session is None:
            return
        with _connect() as db:
            db.execute('UPDATE sessions SET seconds=? WHERE id=?', (max(0, time.monotonic() - _started), _session))
            db.execute('INSERT OR IGNORE INTO days(day) VALUES (?)', (date.today().isoformat(),))


def visit(feature):
    if feature not in FEATURES:
        return False
    with _lock, _connect() as db:
        db.execute('INSERT INTO features(name,visits) VALUES (?,1) ON CONFLICT(name) DO UPDATE SET visits=visits+1', (feature,))
    return True


def usage():
    checkpoint()
    with _lock, _connect() as db:
        count, total = db.execute('SELECT COUNT(*), COALESCE(SUM(seconds),0) FROM sessions').fetchone()
        features = dict(db.execute('SELECT name,visits FROM features'))
        recent = [{'started': started, 'seconds': seconds} for started, seconds in
                  db.execute('SELECT started, seconds FROM sessions ORDER BY started DESC LIMIT 5')]
        days = {row[0] for row in db.execute('SELECT day FROM days')}
    today = date.today()
    cursor = today if today.isoformat() in days else today - timedelta(days=1)
    streak = 0
    while cursor.isoformat() in days:
        streak += 1
        cursor -= timedelta(days=1)
    return {'sessions': count, 'total_seconds': total, 'average_seconds': total / count if count else None,
            'streak_days': streak, 'features': features, 'recent_sessions': recent}


def record_ocr(seconds, failed=False):
    with _lock:
        _metrics['ocr_count'] += 1
        _metrics['ocr_errors'] += int(failed)
        _metrics['ocr_seconds'] += max(0, seconds)


def record_sync(seconds, success):
    with _lock:
        _metrics['sync_ok' if success else 'sync_failed'] += 1
        _metrics['sync_seconds'] += max(0, seconds)


def record_monitor_error():
    with _lock:
        _metrics['monitor_errors'] += 1


def system():
    global _cpu_sample
    with _lock:
        now, cpu = time.monotonic(), time.process_time()
        cpu_percent = None
        if _cpu_sample and now > _cpu_sample[0]:
            cpu_percent = max(0, (cpu - _cpu_sample[1]) / (now - _cpu_sample[0]) * 100 / (os.cpu_count() or 1))
        _cpu_sample = (now, cpu)
        data = dict(_metrics)
    data['cpu_percent'] = cpu_percent
    data['memory_bytes'] = None
    try:
        import win32api, win32process
        data['memory_bytes'] = win32process.GetProcessMemoryInfo(win32api.GetCurrentProcess())['WorkingSetSize']
    except (ImportError, AttributeError, OSError):
        pass
    return data
