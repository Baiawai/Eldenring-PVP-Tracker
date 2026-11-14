"""Optional, local desktop notifications for tracking state changes."""
from contextlib import closing
import sqlite3
import sys
import threading

KINDS = ('monitor_error', 'game_hidden', 'monitor_stop')


def _database():
    from application.init import database_setting
    return database_setting


def load():
    result = {kind:False for kind in KINDS}
    with closing(sqlite3.connect(_database(), timeout=10)) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='tracking_notifications'").fetchone():
            return result
        for kind, enabled in db.execute('SELECT kind,enabled FROM tracking_notifications'):
            if kind in result:
                result[kind] = enabled == 1
    return result


def save(kind, enabled):
    if kind not in KINDS or not isinstance(enabled, bool):
        raise ValueError('Invalid notification setting')
    with closing(sqlite3.connect(_database(), timeout=10)) as db, db:
        db.execute('CREATE TABLE IF NOT EXISTS tracking_notifications (kind TEXT PRIMARY KEY, enabled INTEGER NOT NULL CHECK(enabled IN (0,1)))')
        db.execute('INSERT INTO tracking_notifications(kind,enabled) VALUES(?,?) ON CONFLICT(kind) DO UPDATE SET enabled=excluded.enabled', (kind, int(enabled)))


def _send(kind, detail=''):
    if kind not in KINDS:
        return
    try:
        if not load()[kind]:
            return
        from application.init import get_selected_language
        from application.ui_localization import packs
        language = get_selected_language()
        pack = packs().get(language, {})
        modern = pack.get('modern', {})
        if kind == 'monitor_error':
            message = modern.get('monitor_capture_error', 'La capture s’est arrêtée à cause d’une erreur.')
            if detail:
                message += '\n' + detail
        elif kind == 'monitor_stop':
            message = modern.get('monitor_stopped', 'Le suivi est arrêté.')
        else:
            counter = pack.get('counter', [])
            message = counter[6] if len(counter) > 6 else 'Jeu non visible pour la capture.'
        icon = getattr(sys.modules.get('__main__'), 'icon', None)
        if icon is not None and icon.HAS_NOTIFICATION:
            icon.notify(message, 'Elden PVP Tracker')
    except Exception:
        # The monitor and its saved results are more important than the alert.
        return


def notify(kind, detail=''):
    """Send asynchronously so desktop notifications never block tracking."""
    if kind not in KINDS:
        return
    try:
        threading.Thread(target=_send, args=(kind, detail), name='tracking-notification', daemon=True).start()
    except RuntimeError:
        return
