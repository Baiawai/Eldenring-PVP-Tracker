"""First-install verification and diagnostic reporting, without touching existing profiles."""
import ctypes
import json
import locale
import os
import sqlite3
import tempfile
import threading
import traceback
from contextlib import closing
from datetime import datetime
from pathlib import Path

from application.runtime_paths import data_dir, database_path, LEGACY_DATA_FOLDER
from application.browser_language import browser_language

MARKER = 'initialization-status.json'
_claim_lock = threading.Lock()
DATABASES = {
    'database_user.db': 'tabel_user',
    'database_capture.db': 'tabel_captures',
    'database_multi.db': 'table_multi',
    'database_setting.db': 'table_setting',
    'usage_metrics.db': 'sessions',
}


def _marker():
    return data_dir() / MARKER


def read_status():
    try:
        value = json.loads(_marker().read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(value):
    path = _marker()
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    os.replace(temporary, path)


def begin():
    """Mark only a genuinely new profile; never replace existing data."""
    status = read_status()
    if status:
        return status.get('state') in ('pending', 'failed')
    if (data_dir().parent / LEGACY_DATA_FOLDER).exists():
        return False
    if any(database_path(name).exists() for name in DATABASES):
        return False
    data_dir().mkdir(parents=True, exist_ok=True)
    _save({'state': 'pending'})
    return True


def log_error(details):
    """Save a diagnostic even when the data directory is unavailable."""
    for directory in (data_dir(), Path(tempfile.gettempdir()) / 'Elden Ring PvP Tracker'):
        try:
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / 'tracker-errors.log'
            with path.open('a', encoding='utf-8') as stream:
                stream.write(datetime.now().isoformat(timespec='seconds') + ' - initialization\n' + details + '\n')
            return path
        except OSError:
            continue
    return None


def finish():
    previous = read_status()
    if previous.get('state') not in ('pending', 'failed'):
        return
    try:
        for name, table in DATABASES.items():
            path = database_path(name)
            if not path.is_file():
                raise FileNotFoundError('Database missing: ' + str(path))
            with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=10)) as db:
                if db.execute('PRAGMA quick_check(1)').fetchone() != ('ok',):
                    raise RuntimeError('Database integrity check failed: ' + str(path))
                if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
                    raise RuntimeError('Required table missing: ' + name + ' / ' + table)
        _save({'state': 'ready'})
    except Exception:
        path = log_error(traceback.format_exc())
        _save({'state': 'failed', 'log': str(path) if path else '', 'shown': bool(previous.get('shown'))})


def claim():
    with _claim_lock:
        status = read_status()
        if status.get('state') not in ('ready', 'failed') or status.get('shown'):
            return None
        _save({**status, 'shown': True})
        return {'state': status['state'], 'log_available': bool(status.get('log'))}


def open_log():
    path = read_status().get('log')
    allowed = {(data_dir() / 'tracker-errors.log').resolve(),
               (Path(tempfile.gettempdir()) / 'Elden Ring PvP Tracker' / 'tracker-errors.log').resolve()}
    if not path or Path(path).resolve() not in allowed or not Path(path).is_file():
        return False
    os.startfile(path)
    return True


def report_fatal(details):
    path = log_error(details)
    language = browser_language([(locale.getlocale()[0] or 'en', 1)])
    try:
        packs = json.loads((Path(__file__).parent / 'locales' / 'ui_packs.json').read_text(encoding='utf-8'))
        modern = packs.get(language, {}).get('modern', {})
    except (OSError, ValueError, TypeError):
        modern = {}
    french = language == 'fra'
    if path:
        message = modern.get('initialization_fatal_open',
            "L'initialisation du tracker a échoué. Ouvrir le journal ?" if french else
            'Tracker initialization failed. Open the error log?') + '\n\n' + str(path)
    else:
        message = modern.get('initialization_fatal_no_log',
            "L'initialisation a échoué et le journal n'a pas pu être enregistré." if french else
            'Initialization failed and the error log could not be saved.') + '\n\n' + details[-1800:]
    try:
        result = ctypes.windll.user32.MessageBoxW(None, message, 'Elden PVP Tracker', 0x10 | (0x4 if path else 0))
        if path and result == 6:
            os.startfile(str(path))
    except (AttributeError, OSError):
        pass
