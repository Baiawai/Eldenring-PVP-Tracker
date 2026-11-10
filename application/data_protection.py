"""Prepare an isolated, portable upgrade of legacy encrypted tracker data.

The running tracker never migrates data automatically.  The output folder is a
separate copy and can only be used by versions that understand v2 values.
"""
import base64
import getpass
import hashlib
import hmac
import json
import os
import shutil
import sqlite3
from contextlib import closing
from functools import lru_cache
from pathlib import Path

import win32crypt
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from application.runtime_paths import data_dir, _tracker_running

KEY_FILE = 'data-key.dpapi'
RECOVERY_FILE = 'data-key-recovery.json'
INCOMPLETE_FILE = 'data-migration-incomplete'
LEGACY_KEY = base64.urlsafe_b64encode(('_Elden_ring_Pvp_' * 2).encode('utf-8'))
FIELDS = {
    'tabel_user': None,
    'table_multi': None,
    'tabel_captures': ('name', 'victory', 'defeat', 'egality', 'time', 'date', 'mode', 'base64'),
    'detection_history': ('message', 'metadata'),
    'history_archive_events': ('message', 'metadata'),
    'player_sightings': ('name',),
    'notification_example': ('image',),
    'leaderboard_event_outbox': ('mode', 'kind', 'occurred_at'),
}


@lru_cache(maxsize=8)
def _unprotect(path, mtime, size):
    protected = Path(path).read_bytes()
    key = win32crypt.CryptUnprotectData(protected, None, None, None, 0)[1]
    Fernet(key)  # Fail closed if the file belongs to another user or is damaged.
    return key


def active_data_key():
    if (data_dir() / INCOMPLETE_FILE).exists():
        raise RuntimeError('La migration des données est incomplète. Conserve le dossier original.')
    path = data_dir() / KEY_FILE
    if not path.exists():
        return None
    stat = path.stat()
    return _unprotect(str(path), stat.st_mtime_ns, stat.st_size)


def _password_key(password, salt):
    if not isinstance(password, str) or len(password) < 12:
        raise ValueError('Le mot de passe doit contenir au moins 12 caractères.')
    derived = Scrypt(salt=salt, length=32, n=32768, r=8, p=1).derive(password.encode('utf-8'))
    return base64.urlsafe_b64encode(derived)


def make_recovery(key, password):
    Fernet(key)
    salt = os.urandom(16)
    wrapped = Fernet(_password_key(password, salt)).encrypt(key).decode('ascii')
    return json.dumps({'format':'tracker-data-key-v1', 'salt':base64.b64encode(salt).decode('ascii'), 'key':wrapped}, ensure_ascii=True).encode('ascii')


def recover_key(blob, password):
    if len(blob) > 4096:
        raise ValueError('Fichier de récupération invalide.')
    data = json.loads(blob)
    if not isinstance(data, dict) or data.get('format') != 'tracker-data-key-v1':
        raise ValueError('Fichier de récupération invalide.')
    salt = base64.b64decode(data['salt'], validate=True)
    if len(salt) != 16 or not isinstance(data.get('key'), str):
        raise ValueError('Fichier de récupération invalide.')
    key = Fernet(_password_key(password, salt)).decrypt(data['key'].encode('ascii'))
    Fernet(key)
    return key


def _write_new(path, data):
    with path.open('xb') as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())


def restore_key(folder, password):
    """Reprotect a copied key for this user, preserving an unusable old key."""
    folder = Path(folder)
    if (folder / INCOMPLETE_FILE).exists():
        raise ValueError('Cette copie est incomplète et ne peut pas être restaurée.')
    if folder.resolve() == data_dir().resolve() and _tracker_running():
        raise RuntimeError('Arrête le tracker avant de restaurer la clé.')
    key = recover_key((folder / RECOVERY_FILE).read_bytes(), password)
    protected = win32crypt.CryptProtectData(key, 'Elden Ring PvP Tracker data key', None, None, None, 0)
    target = folder / KEY_FILE
    if not target.exists():
        _write_new(target, protected)
        return
    try:
        existing = win32crypt.CryptUnprotectData(target.read_bytes(), None, None, None, 0)[1]
    except Exception:
        existing = None
    if existing == key:
        return
    if existing is not None:
        raise ValueError('Une autre clé utilisable existe déjà dans ce dossier.')
    old_copy = folder / (KEY_FILE + '.previous')
    old_data = target.read_bytes()
    if old_copy.exists():
        if old_copy.read_bytes() != old_data:
            raise ValueError('Une ancienne sauvegarde de clé différente existe déjà.')
    else:
        _write_new(old_copy, old_data)
    temporary = folder / (KEY_FILE + '.new')
    if temporary.exists():
        try:
            if win32crypt.CryptUnprotectData(temporary.read_bytes(), None, None, None, 0)[1] != key:
                raise ValueError('Une autre restauration de clé est en attente.')
        except ValueError:
            raise
        except Exception as error:
            raise ValueError('La clé temporaire est illisible.') from error
    else:
        _write_new(temporary, protected)
    os.replace(temporary, target)


def _quote(name):
    return '"' + name.replace('"', '""') + '"'


def _migrate_db(path, new_key):
    legacy, current = Fernet(LEGACY_KEY), Fernet(new_key)
    with closing(sqlite3.connect(path, timeout=10)) as db:
        db.execute('PRAGMA secure_delete=ON')
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table, fields in FIELDS.items():
            if table not in tables:
                continue
            columns = [row[1] for row in db.execute('PRAGMA table_info(' + _quote(table) + ')')]
            selected = [name for name in (fields if fields is not None else columns) if name in columns and name != 'id']
            if not selected:
                continue
            cursor = db.execute('SELECT rowid,' + ','.join(_quote(name) for name in selected) + ' FROM ' + _quote(table))
            while rows := cursor.fetchmany(20):
                for row in rows:
                    changes = {}
                    for name, value in zip(selected, row[1:]):
                        raw = value.encode('ascii') if isinstance(value, str) and value.isascii() else value
                        if isinstance(raw, bytes) and raw.startswith(b'v2:'):
                            raise ValueError('Ce dossier contient déjà des données chiffrées avec une clé personnelle.')
                        if not isinstance(raw, bytes) or not raw.startswith(b'gAAAA'):
                            continue
                        try:
                            clear = legacy.decrypt(raw)
                        except InvalidToken as error:
                            raise ValueError('Donnée chiffrée illisible dans ' + table + '.') from error
                        converted = b'v2:' + current.encrypt(clear)
                        changes[name] = converted.decode('ascii') if isinstance(value, str) else converted
                        if table == 'player_sightings' and name == 'name' and 'name_key' in columns:
                            changes['name_key'] = hmac.new(new_key, clear.decode('utf-8').casefold().encode('utf-8'), hashlib.sha256).hexdigest()
                    if changes:
                        sql = 'UPDATE ' + _quote(table) + ' SET ' + ','.join(_quote(name) + '=?' for name in changes) + ' WHERE rowid=?'
                        db.execute(sql, [*changes.values(), row[0]])
        db.commit()
        db.execute('VACUUM')
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Vérification de la base échouée : ' + path.name)


def prepare_copy(source, destination, password):
    """Create a migrated copy; never modify or overwrite the original folder."""
    source, destination = Path(source).resolve(strict=True), Path(destination).resolve()
    if not source.is_dir() or destination.exists() or destination == source or source in destination.parents or destination in source.parents:
        raise ValueError('Choisis un nouveau dossier distinct de la source.')
    if source == data_dir().resolve() and _tracker_running():
        raise RuntimeError('Arrête le tracker avant de copier les données.')
    if not (source / 'database_user.db').is_file():
        raise ValueError('La base du profil est absente : vérifie le dossier source.')
    if (source / INCOMPLETE_FILE).exists():
        raise ValueError('Le dossier source contient une migration incomplète.')
    if (source / KEY_FILE).exists():
        raise ValueError('Ce dossier utilise déjà une clé personnelle.')
    for path in source.rglob('*'):
        if path.is_symlink():
            raise ValueError('La sauvegarde ne peut pas contenir de lien symbolique.')
    key = Fernet.generate_key()
    recovery = make_recovery(key, password)
    destination.mkdir(parents=False)
    marker = destination / INCOMPLETE_FILE
    _write_new(marker, b'Incomplete migration; retain the original data.\n')
    for path in source.rglob('*'):
        relative = path.relative_to(source)
        target = destination / relative
        if path.is_dir():
            target.mkdir(exist_ok=True)
        elif path.is_file() and not path.name.endswith(('.db-wal', '.db-shm', '.db-journal')):
            if path.suffix.lower() == '.db':
                with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as original, closing(sqlite3.connect(target)) as copy:
                    original.backup(copy)
                _migrate_db(target, key)
            else:
                shutil.copy2(path, target)
        elif not path.is_file():
            raise ValueError('Type de fichier non pris en charge.')
    protected = win32crypt.CryptProtectData(key, 'Elden Ring PvP Tracker data key', None, None, None, 0)
    _write_new(destination / KEY_FILE, protected)
    _write_new(destination / RECOVERY_FILE, recovery)
    marker.unlink()
    return destination


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Préparer une copie sécurisée ou restaurer sa clé sur ce PC.')
    parser.add_argument('operation', choices=('prepare', 'restore-key'))
    parser.add_argument('source', help='Dossier original pour prepare, ou copie sécurisée pour restore-key')
    parser.add_argument('destination', nargs='?', help='Nouveau dossier pour la copie sécurisée')
    args = parser.parse_args()
    if args.operation == 'prepare' and not args.destination:
        parser.error('prepare nécessite un nouveau dossier de destination')
    password = getpass.getpass('Mot de passe de récupération (12 caractères minimum) : ')
    if args.operation == 'prepare':
        if password != getpass.getpass('Confirme le mot de passe : '):
            raise ValueError('Les mots de passe ne correspondent pas.')
        print('Copie préparée :', prepare_copy(args.source, args.destination, password))
        print('Elle nécessite une version compatible v2 du tracker. Conserve le mot de passe séparément.')
    else:
        restore_key(args.source, password)
        print('Clé restaurée pour cet utilisateur Windows.')


if __name__ == '__main__':
    main()
