"""Persist the last recognized notification example in the local settings DB."""
import base64
import sqlite3
from contextlib import closing
from io import BytesIO
from PIL import Image
from application.init import database_setting
from application.secur import encrypt_value, decrypt_value
from application.locale_catalog import messages
from application.notification_region import valid


def load():
    with closing(sqlite3.connect(database_setting, timeout=10)) as db:
        exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='notification_example'").fetchone()
        if not exists:
            return None
        columns = {item[1] for item in db.execute('PRAGMA table_info(notification_example)')}
        line_column = 'line_count' if 'line_count' in columns else 'NULL'
        row = db.execute('SELECT image, language, top, bottom, ' + line_column + ' FROM notification_example WHERE id=1').fetchone()
    if not row or row[1] not in messages():
        return None
    try:
        image = decrypt_value(row[0]).decode('ascii')
        raw = base64.b64decode(image, validate=True)
        with Image.open(BytesIO(raw)) as decoded:
            decoded.verify()
        bounds = (float(row[2]), float(row[3])) if row[2] is not None and row[3] is not None else None
        if bounds is not None and not valid(*bounds):
            return None
        return {'image':image, 'language':row[1], 'bounds':bounds, 'lines':row[4]}
    except Exception:
        return None


def save(image, language, bounds, lines):
    if language not in messages() or (bounds is not None and not valid(*bounds)) or not isinstance(lines, int) or lines < 2:
        raise ValueError('Invalid notification example')
    top, bottom = bounds if bounds is not None else (None, None)
    with closing(sqlite3.connect(database_setting, timeout=10)) as db, db:
        db.execute('CREATE TABLE IF NOT EXISTS notification_example (id INTEGER PRIMARY KEY CHECK(id=1), image BLOB NOT NULL, language TEXT NOT NULL, top REAL, bottom REAL, line_count INTEGER)')
        columns = {item[1] for item in db.execute('PRAGMA table_info(notification_example)')}
        if 'line_count' not in columns:
            db.execute('ALTER TABLE notification_example ADD COLUMN line_count INTEGER')
        db.execute('INSERT INTO notification_example(id,image,language,top,bottom,line_count) VALUES(1,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET image=excluded.image,language=excluded.language,top=excluded.top,bottom=excluded.bottom,line_count=excluded.line_count',
                   (encrypt_value(image), language, top, bottom, lines))
