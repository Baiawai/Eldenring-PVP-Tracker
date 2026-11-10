import hashlib
import hmac
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet, InvalidToken

from application import data_protection as protection


class DataProtectionTests(unittest.TestCase):
    def test_migrated_copy_preserves_original_and_can_restore_the_key(self):
        with tempfile.TemporaryDirectory(prefix='tracker-key-test-') as temporary:
            root = Path(temporary)
            source = root / 'original'
            source.mkdir()
            destination = root / 'Elden Ring PvP Tracker'
            legacy = Fernet(protection.LEGACY_KEY)
            with closing(sqlite3.connect(source / 'database_capture.db')) as db, db:
                db.execute('CREATE TABLE player_sightings (id INTEGER PRIMARY KEY, name BLOB, name_key TEXT)')
                db.execute('INSERT INTO player_sightings VALUES (1, ?, ?)', (legacy.encrypt('Joueur'.encode()), 'ancien'))
                db.execute('CREATE TABLE detection_history (id INTEGER PRIMARY KEY, message BLOB, metadata BLOB)')
                db.execute('INSERT INTO detection_history VALUES (1, ?, ?)', (legacy.encrypt(b'Victoire'), None))
                db.executemany('INSERT INTO detection_history VALUES (?, ?, NULL)', [(number, legacy.encrypt(str(number).encode())) for number in range(2, 47)])
                db.execute('CREATE TABLE history_archive_events (archive_id INTEGER, original_id INTEGER, message BLOB, metadata BLOB, PRIMARY KEY (archive_id,original_id))')
                db.execute('INSERT INTO history_archive_events VALUES (1, 1, ?, ?)', (legacy.encrypt(b'Archive'), None))
            with closing(sqlite3.connect(source / 'database_user.db')) as db, db:
                db.execute('CREATE TABLE tabel_user (id INTEGER PRIMARY KEY, name TEXT)')
                db.execute('INSERT INTO tabel_user VALUES (1, ?)', (legacy.encrypt(b'Personnage').decode('ascii'),))
            (source / 'autre.txt').write_text('conservé', encoding='utf-8')
            with patch.dict(os.environ, {'APPDATA':temporary}), patch.object(protection, '_tracker_running', return_value=False):
                protection.prepare_copy(source, destination, 'mot de passe robuste')
                key = protection.active_data_key()
                self.assertEqual(protection.recover_key((destination / protection.RECOVERY_FILE).read_bytes(), 'mot de passe robuste'), key)
                with self.assertRaises(InvalidToken):
                    protection.recover_key((destination / protection.RECOVERY_FILE).read_bytes(), 'mauvais mot de passe')
                with closing(sqlite3.connect(destination / 'database_capture.db')) as db:
                    name, name_key = db.execute('SELECT name,name_key FROM player_sightings').fetchone()
                    message = db.execute('SELECT message FROM detection_history').fetchone()[0]
                    messages = db.execute('SELECT id,message FROM detection_history ORDER BY id').fetchall()
                    archive = db.execute('SELECT message FROM history_archive_events').fetchone()[0]
                self.assertEqual(Fernet(key).decrypt(name[3:]).decode(), 'Joueur')
                with self.assertRaises(InvalidToken):
                    legacy.decrypt(name[3:])
                self.assertEqual(name_key, hmac.new(key, b'joueur', hashlib.sha256).hexdigest())
                self.assertEqual(Fernet(key).decrypt(message[3:]), b'Victoire')
                self.assertEqual([Fernet(key).decrypt(value[3:]) for ident, value in messages[1:]], [str(number).encode() for number in range(2, 47)])
                self.assertEqual(Fernet(key).decrypt(archive[3:]), b'Archive')
                with closing(sqlite3.connect(destination / 'database_user.db')) as db:
                    name_text = db.execute('SELECT name FROM tabel_user').fetchone()[0]
                self.assertEqual(Fernet(key).decrypt(name_text[3:].encode()), b'Personnage')
                with closing(sqlite3.connect(source / 'database_user.db')) as db:
                    original = db.execute('SELECT name FROM tabel_user').fetchone()[0]
                self.assertEqual(legacy.decrypt(original.encode()), b'Personnage')
                self.assertEqual((destination / 'autre.txt').read_text(encoding='utf-8'), 'conservé')
                check = "from flask import Flask; app=Flask(__name__); from application import secur; from cryptography.fernet import Fernet; old=Fernet(secur.key).encrypt(b'ancien'); assert secur.decrypt_value(old)==b'ancien'; token=secur.encrypt_value('nouveau'); assert token.startswith(b'v2:') and secur.decrypt_value(token)==b'nouveau'"
                result = subprocess.run([sys.executable, '-c', check], env=os.environ.copy(), capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                (destination / protection.KEY_FILE).write_bytes(b'not available on this PC')
                with self.assertRaises(InvalidToken):
                    protection.restore_key(destination, 'mauvais mot de passe')
                self.assertEqual((destination / protection.KEY_FILE).read_bytes(), b'not available on this PC')
                self.assertFalse((destination / (protection.KEY_FILE + '.previous')).exists())
                protection.restore_key(destination, 'mot de passe robuste')
                self.assertEqual(protection.active_data_key(), key)
                self.assertEqual((destination / (protection.KEY_FILE + '.previous')).read_bytes(), b'not available on this PC')

    def test_refuses_existing_or_nested_destination(self):
        with tempfile.TemporaryDirectory(prefix='tracker-key-test-') as temporary:
            root = Path(temporary)
            source = root / 'source'
            source.mkdir()
            with self.assertRaises(ValueError):
                protection.prepare_copy(source, source / 'nested', 'mot de passe robuste')
            with self.assertRaises(ValueError):
                protection.prepare_copy(source, source, 'mot de passe robuste')

    def test_incomplete_copy_cannot_be_used_after_a_migration_error(self):
        with tempfile.TemporaryDirectory(prefix='tracker-key-test-') as temporary:
            root = Path(temporary)
            source = root / 'original'
            source.mkdir()
            destination = root / 'Elden Ring PvP Tracker'
            with closing(sqlite3.connect(source / 'database_user.db')) as db, db:
                db.execute('CREATE TABLE tabel_user (id INTEGER PRIMARY KEY, name BLOB)')
                db.execute('INSERT INTO tabel_user VALUES (1, ?)', (b'gAAAA-corrupt',))
            with patch.dict(os.environ, {'APPDATA':temporary}), patch.object(protection, '_tracker_running', return_value=False):
                with self.assertRaises(ValueError):
                    protection.prepare_copy(source, destination, 'mot de passe robuste')
                self.assertTrue((destination / protection.INCOMPLETE_FILE).exists())
                with self.assertRaises(RuntimeError):
                    protection.active_data_key()
                with closing(sqlite3.connect(source / 'database_user.db')) as db:
                    self.assertEqual(db.execute('SELECT name FROM tabel_user').fetchone()[0], b'gAAAA-corrupt')

    def test_real_isolated_fixture_remains_readable_after_migration(self):
        project = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix='tracker-migration-fixture-') as temporary:
            root = Path(temporary)
            original_home = root / 'original'
            migrated_home = root / 'migrated'
            original_home.mkdir()
            migrated_home.mkdir()
            environment = os.environ.copy()
            environment['APPDATA'] = str(original_home)
            result = subprocess.run([sys.executable, str(project / 'tests/support/exercise_app.py')], cwd=project, env=environment, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            inspect = "import hashlib,json; from flask import Flask; app=Flask(__name__); from application import init,notification_sample; u=init.load_user(); s=notification_sample.load(); print(json.dumps({'user':u,'sample':hashlib.sha256(s['image'].encode()).hexdigest() if s else None},sort_keys=True))"
            before = subprocess.run([sys.executable, '-c', inspect], cwd=project, env=environment, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30)
            self.assertEqual(before.returncode, 0, before.stderr)
            with patch.dict(os.environ, {'APPDATA':str(original_home)}), patch.object(protection, '_tracker_running', return_value=False):
                protection.prepare_copy(original_home / 'Elden Ring PvP Tracker', migrated_home / 'Elden Ring PvP Tracker', 'mot de passe robuste')
            environment['APPDATA'] = str(migrated_home)
            after = subprocess.run([sys.executable, '-c', inspect], cwd=project, env=environment, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30)
            self.assertEqual(after.returncode, 0, after.stderr)
            self.assertEqual(after.stdout, before.stdout)


if __name__ == '__main__':
    unittest.main()
