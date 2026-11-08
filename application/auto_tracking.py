"""Optional one-shot monitor start when the game window appears."""
import sqlite3
import threading
import time
from contextlib import closing

def _database():
    from application.init import database_setting
    return database_setting


def enabled():
    with closing(sqlite3.connect(_database(), timeout=10)) as db:
        exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='auto_game_start'").fetchone()
        if not exists:
            return False
        row = db.execute('SELECT enabled FROM auto_game_start WHERE id=1').fetchone()
        return bool(row and row[0] == 1)


def save(value):
    if not isinstance(value, bool):
        raise ValueError('Invalid setting')
    with closing(sqlite3.connect(_database(), timeout=10)) as db, db:
        db.execute('CREATE TABLE IF NOT EXISTS auto_game_start (id INTEGER PRIMARY KEY CHECK(id=1), enabled INTEGER NOT NULL CHECK(enabled IN (0,1)))')
        db.execute('INSERT INTO auto_game_start(id,enabled) VALUES(1,?) ON CONFLICT(id) DO UPDATE SET enabled=excluded.enabled', (int(value),))


class StartGate:
    def __init__(self):
        self.present = False

    def update(self, active, present):
        current = bool(active and present)
        start = current and not self.present
        self.present = current
        return start


def start_worker(app, functions):
    def worker():
        gate = StartGate()
        while True:
            try:
                active = enabled()
                game = bool(functions.ctypes.windll.user32.FindWindowW(None, 'ELDEN RING™')) if active else False
                if gate.update(active, game) and not functions.run_monitor:
                    with app.app_context():
                        functions.start()
            except Exception:
                app.logger.exception('Automatic game start failed')
            time.sleep(3)
    threading.Thread(target=worker, name='auto-game-start', daemon=True).start()
