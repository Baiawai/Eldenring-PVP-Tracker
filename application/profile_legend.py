"""Locally stored optional profile legend."""
import sqlite3
from contextlib import closing
from application.init import database_setting

MAX_LENGTH = 160

def load():
    with closing(sqlite3.connect(database_setting, timeout=10)) as con:
        con.execute('CREATE TABLE IF NOT EXISTS profile_legend (id INTEGER PRIMARY KEY CHECK (id=1), text TEXT NOT NULL)')
        row = con.execute('SELECT text FROM profile_legend WHERE id=1').fetchone()
        con.commit()
    return row[0] if row else ''

def save(value):
    if not isinstance(value, str) or len(value) > MAX_LENGTH:
        raise ValueError('Invalid legend')
    value = ' '.join(value.split())
    with closing(sqlite3.connect(database_setting, timeout=10)) as con:
        con.execute('CREATE TABLE IF NOT EXISTS profile_legend (id INTEGER PRIMARY KEY CHECK (id=1), text TEXT NOT NULL)')
        con.execute('INSERT INTO profile_legend(id,text) VALUES (1,?) ON CONFLICT(id) DO UPDATE SET text=excluded.text', (value,))
        con.commit()
    return value
