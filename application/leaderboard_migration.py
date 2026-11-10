"""Archive an old server identity before requesting fresh participation consent."""

import secrets
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


class MigrationError(Exception):
    """A safe server transition cannot be completed in the current state."""


def migrate(settings_path, user_path, target):
    """Archive an identity and suspend participation, without network or event writes.

    The caller must serialize monitoring and leaderboard operations. Acquiring a
    SQLite write transaction on both databases additionally excludes a combat
    event transaction while the outbox and match markers are checked.
    """
    if not Path(settings_path).is_file() or not Path(user_path).is_file():
        raise MigrationError('invalid_data')
    try:
        # mode=rw prevents SQLite from creating a new empty database if a file
        # disappears between the existence check and opening either path.
        settings_uri = Path(settings_path).absolute().as_uri() + '?mode=rw'
        user_uri = Path(user_path).absolute().as_uri() + '?mode=rw'
        with closing(sqlite3.connect(settings_uri, timeout=5, uri=True)) as db:
            db.execute('ATTACH DATABASE ? AS tracker_user', (user_uri,))
            db.execute('BEGIN IMMEDIATE')
            columns = {row[1] for row in db.execute('PRAGMA table_info(online_leaderboard)')}
            fields = ('enabled', 'uuid', 'token', 'server_url', 'language_permission',
                      'steam_permission', 'event_permission', 'delete_pending',
                      'steam_remove_pending', 'language_remove_pending',
                      'steam_login_cancel_pending', 'rotation_token', 'recovery_payload',
                      'previous_token', 'server_transition_nonce', 'server_consent_url')
            if not set(fields).issubset(columns):
                raise MigrationError('invalid_data')
            raw = db.execute('SELECT ' + ','.join(fields) + ' FROM online_leaderboard WHERE id=1').fetchone()
            if not raw:
                raise MigrationError('invalid_data')
            state = dict(zip(fields, raw))
            if not state['uuid'] or not state['token'] or not state['server_url']:
                raise MigrationError('no_identity')
            if state['server_url'] == target:
                raise MigrationError('already_current')
            pending = ('delete_pending', 'steam_remove_pending', 'language_remove_pending',
                       'steam_login_cancel_pending', 'rotation_token', 'recovery_payload',
                       'previous_token', 'server_transition_nonce')
            if any(state[name] for name in pending):
                raise MigrationError('pending_operations')
            tables = {row[0] for row in db.execute("SELECT name FROM tracker_user.sqlite_master WHERE type='table'")}
            if 'leaderboard_event_outbox' in tables and db.execute('SELECT 1 FROM tracker_user.leaderboard_event_outbox LIMIT 1').fetchone():
                raise MigrationError('pending_events')
            if 'leaderboard_event_state' in tables and db.execute('SELECT 1 FROM tracker_user.leaderboard_event_state WHERE active_match IS NOT NULL OR last_no_result IS NOT NULL LIMIT 1').fetchone():
                raise MigrationError('active_match')
            db.execute('''CREATE TABLE IF NOT EXISTS online_leaderboard_archived_identities (
                id INTEGER PRIMARY KEY, archived_at TEXT NOT NULL, server_url TEXT NOT NULL,
                uuid TEXT NOT NULL, token BLOB NOT NULL, enabled INTEGER NOT NULL,
                language_permission INTEGER NOT NULL, steam_permission INTEGER NOT NULL,
                event_permission INTEGER NOT NULL, server_consent_url TEXT)''')
            db.execute('''INSERT INTO online_leaderboard_archived_identities
                (archived_at, server_url, uuid, token, enabled, language_permission, steam_permission, event_permission, server_consent_url)
                VALUES (?,?,?,?,?,?,?,?,?)''',
                (datetime.now(timezone.utc).isoformat(), state['server_url'], state['uuid'], state['token'],
                 state['enabled'], state['language_permission'], state['steam_permission'], state['event_permission'], state['server_consent_url']))
            db.execute('''UPDATE online_leaderboard SET enabled=0, uuid=NULL, token=NULL,
                server_url=NULL, language_permission=0, steam_permission=0, event_permission=0,
                server_consent_url=NULL, server_transition_nonce=? WHERE id=1''', (secrets.token_urlsafe(32),))
            db.commit()
    except MigrationError:
        raise
    except sqlite3.Error as error:
        raise MigrationError('invalid_data') from error
