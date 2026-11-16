"""Exercise capture metadata against a private, synthetic tracker profile."""
from contextlib import closing
from datetime import datetime
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import types
from unittest.mock import patch
import webbrowser

from cryptography.fernet import Fernet

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))
from application import runtime_paths
from application import error_reports
error_reports.report = lambda *args, **kwargs: None
error_reports.start = lambda: None

images = Path(os.environ['APPDATA']) / 'test-runtime-images'
images.mkdir(parents=True, exist_ok=True)
runtime_paths.image_dir = lambda: images
webbrowser.open_new = lambda *args, **kwargs: True

# Begin with an old Store-compatible nine-column database, containing one
# synthetic capture, so migration is tested rather than just fresh creation.
from application.secur import encrypt_value, decrypt_value
folder = runtime_paths.data_dir()
folder.mkdir(parents=True, exist_ok=True)
database = folder / 'database_capture.db'
legacy = ('Old character', 1, 0, 0, '12', '2026-10-01', 'Arena', 'aW1hZ2U=')
with closing(sqlite3.connect(database)) as db, db:
    db.execute('CREATE TABLE tabel_captures (id INTEGER PRIMARY KEY, name TEXT, victory BOOL, defeat BOOL, egality BOOL, time TEXT, date TEXT, mode TEXT, base64 TEXT)')
    db.execute('INSERT INTO tabel_captures VALUES (1,?,?,?,?,?,?,?,?)', tuple(encrypt_value(v) for v in legacy))

module = types.ModuleType('__main__')
module.__file__ = str(root / 'ELDENRING_Tracker.py')
module.__dict__['__name__'] = 'isolated_tracker_test'
sys.modules['__main__'] = module
exec(compile(Path(module.__file__).read_bytes(), module.__file__, 'exec'), module.__dict__)
from application import data_protection, functions, init, retention

with closing(sqlite3.connect(database)) as db:
    assert len(db.execute('PRAGMA table_info(tabel_captures)').fetchall()) == 9
    assert len(db.execute('SELECT * FROM tabel_captures').fetchone()) == 9
assert init.get_capture_page(50, 1)[0][0][1:] == [str(v) for v in legacy]

init.add_capture('', 1, 0, 0, '15', '2026-11-10', 'Arena', 'aW1hZ2U=', steam_name='Synthetic Steam')
init.add_capture('Game character', 1, 0, 0, '16', '2026-11-10', 'Defense', 'aW1hZ2U=', steam_name='Other Steam')
for n in range(49):
    init.add_capture('', 0, 1, 0, '17', '2026-11-10', 'Invasion', 'aW1hZ2U=')
init.add_capture('', 0, 1, 0, '17', '2026-11-10', 'Invasion', 'aW1hZ2U=', steam_name='Latest Steam')
with closing(sqlite3.connect(database)) as db:
    encrypted = db.execute('SELECT steam_name FROM capture_steam_names WHERE id=2').fetchone()[0]
    assert b'Synthetic Steam' not in encrypted
    assert decrypt_value(encrypted) == b'Synthetic Steam'
assert init.capture_steam_names(range(1, 1100)) == {2: 'Synthetic Steam', 3: 'Other Steam', 53: 'Latest Steam'}

# Failure encrypting the additional field must roll back the capture too.
def fail_steam(value):
    if value == 'fail synthetic encryption':
        raise ValueError('synthetic error')
    return encrypt_value(value)
with patch.object(init, 'encrypt_value', side_effect=fail_steam):
    try:
        init.add_capture('', 1, 0, 0, '1', '2026-11-10', 'Arena', 'aW1hZ2U=', steam_name='fail synthetic encryption')
        raise AssertionError('Expected encryption error')
    except ValueError:
        pass
with closing(sqlite3.connect(database)) as db:
    assert db.execute('SELECT COUNT(*) FROM tabel_captures').fetchone()[0] == 53
    assert db.execute('SELECT COUNT(*) FROM capture_steam_names').fetchone()[0] == 3

client = module.app.test_client()
assert client.get('/').status_code == 200
arena = client.get('/allCaptures?mode=Arena').get_json()
assert arena['steam_names'] == {'2': 'Synthetic Steam'}
assert len(arena['captures']) == 2 and all(len(row) == 9 for row in arena['captures'])
chart = client.get('/allCapturesChart?mode=Arena').get_json()
assert 'steam_names' not in chart and all(len(row) == 8 for row in chart['captures'])
with patch.object(functions, 'verify_identity', return_value=False):
    initial = client.get('/init').get_json()
    assert all(len(row) == 9 for row in initial['captures'][0])
    assert initial['steam_names'] == {'53': 'Latest Steam'}
    next_page = client.get('/nextCaptures').get_json()
    assert next_page['steam_names'] == {'2': 'Synthetic Steam', '3': 'Other Steam'}
    assert all(len(row) == 9 for row in next_page['captures'][0])
functions.captures_stats.append([True, '15', '2026-11-10', 'Arena', '', 'aW1hZ2U=', 'Synthetic Steam'])
live = client.get('/capture').get_json()
assert live['steam_name'] == 'Synthetic Steam' and live['opponent'] == ''

# Export encryption must re-encrypt the new field with the personal key.
copy = folder / 'synthetic-encrypted-copy.db'
shutil.copy2(database, copy)
key = Fernet.generate_key()
data_protection._migrate_db(copy, key)
with closing(sqlite3.connect(copy)) as db:
    converted = db.execute('SELECT steam_name FROM capture_steam_names WHERE id=2').fetchone()[0]
assert converted.startswith(b'v2:') and Fernet(key).decrypt(converted[3:]) == b'Synthetic Steam'

# Retention and old-version direct SQL deletes cannot leave a stale identity.
with closing(sqlite3.connect(database)) as db, db:
    db.execute('INSERT INTO capture_steam_names VALUES (?,?)', (1, encrypt_value('Old Steam')))
assert retention.cleanup(str(database), {'captures': 30, 'steam': 0}, decrypt_value,
                         now=datetime(2026, 11, 14))['captures'] == 1
assert init.capture_steam_names([1, 2]) == {2: 'Synthetic Steam'}
with closing(sqlite3.connect(database)) as db, db:
    db.execute('DELETE FROM tabel_captures WHERE id=2')
    assert db.execute('SELECT 1 FROM capture_steam_names WHERE id=2').fetchone() is None
    db.execute('INSERT INTO capture_steam_names VALUES (?,?)', (2, encrypt_value('Orphan Steam')))
    db.execute('INSERT INTO tabel_captures VALUES (2,?,?,?,?,?,?,?,?)', tuple(encrypt_value(v) for v in legacy))
    assert db.execute('SELECT 1 FROM capture_steam_names WHERE id=2').fetchone() is None
print('Capture Steam metadata database and route checks passed.')
