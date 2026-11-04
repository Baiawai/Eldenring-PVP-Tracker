"""Persistent minimum interval between screen analysis cycles."""
import sqlite3
from contextlib import closing
from application.init import database_setting

ALLOWED_INTERVALS = (0.0, 0.5, 1.0, 2.0, 3.0, 5.0)

def load():
    with closing(sqlite3.connect(database_setting, timeout=10)) as con:
        con.execute("CREATE TABLE IF NOT EXISTS capture_speed (id INTEGER PRIMARY KEY CHECK (id=1), interval_seconds REAL NOT NULL)")
        row = con.execute("SELECT interval_seconds FROM capture_speed WHERE id=1").fetchone()
        con.commit()
    return float(row[0]) if row and row[0] in ALLOWED_INTERVALS else 0.0

def save(value):
    if value not in ALLOWED_INTERVALS:
        raise ValueError("Invalid capture interval")
    with closing(sqlite3.connect(database_setting, timeout=10)) as con:
        con.execute("CREATE TABLE IF NOT EXISTS capture_speed (id INTEGER PRIMARY KEY CHECK (id=1), interval_seconds REAL NOT NULL)")
        con.execute("INSERT INTO capture_speed(id,interval_seconds) VALUES(1,?) ON CONFLICT(id) DO UPDATE SET interval_seconds=excluded.interval_seconds", (value,))
        con.commit()
