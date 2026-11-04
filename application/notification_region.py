"""Notification region as fractions of the captured central game image."""
import math
import sqlite3
from contextlib import closing
from application.init import database_setting

DEFAULT_REGION = (0.4, 1.0)

def valid(top, bottom):
    return math.isfinite(top) and math.isfinite(bottom) and 0 <= top < bottom <= 1 and bottom - top >= 0.05 - 1e-9

def load(legacy=None, legacy_height=None):
    with closing(sqlite3.connect(database_setting, timeout=10)) as con:
        con.execute("CREATE TABLE IF NOT EXISTS notification_region (id INTEGER PRIMARY KEY CHECK(id=1), top REAL NOT NULL, bottom REAL NOT NULL)")
        row = con.execute("SELECT top, bottom FROM notification_region WHERE id=1").fetchone()
        if row and valid(*row):
            return tuple(row)
        region = DEFAULT_REGION
        try:
            top, bottom = float(legacy[0]), float(legacy[1])
            height = float(legacy_height)
            candidate = (top / height, (top + top - bottom - 8) / height)
            if top > 0 and bottom > 0 and valid(*candidate):
                region = candidate
        except (ValueError, TypeError, IndexError, ZeroDivisionError):
            pass
        con.execute("INSERT OR REPLACE INTO notification_region(id,top,bottom) VALUES(1,?,?)", region)
        con.commit()
        return region

def save(top, bottom):
    if not valid(top, bottom):
        raise ValueError("Invalid notification region")
    with closing(sqlite3.connect(database_setting, timeout=10)) as con:
        con.execute("CREATE TABLE IF NOT EXISTS notification_region (id INTEGER PRIMARY KEY CHECK(id=1), top REAL NOT NULL, bottom REAL NOT NULL)")
        con.execute("INSERT OR REPLACE INTO notification_region(id,top,bottom) VALUES(1,?,?)", (top,bottom))
        con.commit()

def crop_box(width, height, region):
    if width < 1 or height < 1 or not valid(*region):
        raise ValueError("Invalid image or region")
    top = min(height - 1, max(0, int(round(height * region[0]))))
    bottom = max(top + 1, min(height, int(round(height * region[1]))))
    return (0, top, width, bottom)
