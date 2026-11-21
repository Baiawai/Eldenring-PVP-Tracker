"""Persistent preferences for the optional in-game overlay."""
import json
import re
import sqlite3
from contextlib import closing

from application.init import database_setting

DEFAULT_OPTIONS = {
    'background_opacity': 50,
    'text_opacity': 50,
    'background_color': '#1a1a1a',
    'text_color': '#c7c7c7',
    'border_color': '#cab486',
    'border_radius': 4,
    'show_overlay_border': False,
    'font_size': 15,
    'width_percent': 80,
    'position': 'top_right',
    'visibility_mode': 'game_visible',
    'show_status': True,
    'show_mode': True,
    'show_peers': True,
    'show_event': True,
    'show_avatars': True,
    'show_player_name': True,
    'show_role': True,
    'show_steam_id': False,
    'show_country': True,
    'show_ping': True,
    'show_ping_average': False,
    'show_jitter': False,
    'show_quality': False,
    'show_duration': True,
    'show_player_count': False,
    'show_rank': True,
    'show_player_stats': True,
    'avatar_size': 48,
    'card_spacing': 8,
    'card_size': 60,
    'ping_good_color': '#85cda4',
    'ping_medium_color': '#e1c16e',
    'ping_bad_color': '#de7777',
}

_BOOL_OPTIONS = {key for key, value in DEFAULT_OPTIONS.items() if isinstance(value, bool)}
_COLOR_OPTIONS = {'background_color', 'text_color', 'border_color', 'ping_good_color', 'ping_medium_color', 'ping_bad_color'}
_INT_OPTIONS = {'background_opacity': (0, 100), 'text_opacity': (0, 100), 'font_size': (12, 32),
                'border_radius': (0, 30), 'width_percent': (60, 100), 'avatar_size': (24, 96),
                'card_spacing': (0, 24), 'card_size': (48, 160)}

# The first new-installation preset was stored under the name ``current``.
# Keep its complete effective values fixed even when later presets change:
# older installations may not have saved every individual option.
CURRENT_V1_DEFAULT_OPTIONS = {
    'background_opacity': 50, 'text_opacity': 50,
    'background_color': '#1a1a1a', 'text_color': '#c7c7c7',
    'border_color': '#cab486', 'border_radius': 4, 'show_overlay_border': False,
    'font_size': 15, 'width_percent': 80, 'position': 'top_right',
    'visibility_mode': 'game_visible', 'show_status': True, 'show_mode': True,
    'show_peers': True, 'show_event': True, 'show_avatars': True,
    'show_player_name': True, 'show_role': True, 'show_steam_id': False,
    'show_country': True, 'show_ping': True, 'show_ping_average': True,
    'show_jitter': False, 'show_quality': True, 'show_duration': True,
    'show_player_count': True, 'show_rank': True, 'show_player_stats': True,
    'avatar_size': 48, 'card_spacing': 8, 'card_size': 60,
    'ping_good_color': '#85cda4', 'ping_medium_color': '#e1c16e',
    'ping_bad_color': '#de7777',
}

# Defaults used before the new-installation preset was introduced. Keeping a
# separate baseline also preserves the effective value of invalid saved rows,
# without changing or deleting those rows.
LEGACY_DEFAULT_OPTIONS = {
    'background_opacity': 60, 'text_opacity': 25,
    'background_color': '#1b1818', 'text_color': '#f2f2f2',
    'border_color': '#cab486', 'border_radius': 4, 'show_overlay_border': True,
    'font_size': 15, 'width_percent': 100, 'position': 'top_right',
    'visibility_mode': 'game_visible', 'show_status': True, 'show_mode': True,
    'show_peers': True, 'show_event': True, 'show_avatars': True,
    'show_player_name': True, 'show_steam_id': True, 'show_ping': True,
    'show_ping_average': True, 'show_jitter': True, 'show_quality': True,
    'show_duration': True, 'show_player_count': True, 'show_rank': True,
    'show_player_stats': True, 'avatar_size': 48, 'card_spacing': 8,
    'card_size': 60, 'ping_good_color': '#85cda4',
    'ping_medium_color': '#e1c16e', 'ping_bad_color': '#de7777',
}


def initialize_defaults(is_new_install, *, generation=None):
    """Choose a baseline once; never rewrite individual saved preferences."""
    if not isinstance(is_new_install, bool):
        raise ValueError('Invalid overlay installation state')
    if generation is None:
        generation = 'v2' if is_new_install else 'legacy'
    if generation not in (('current', 'v2') if is_new_install else ('legacy',)):
        raise ValueError('Invalid overlay defaults generation')
    with closing(sqlite3.connect(database_setting, timeout=10)) as con, con:
        con.execute('CREATE TABLE IF NOT EXISTS overlay_defaults_version '
                    '(id INTEGER PRIMARY KEY CHECK(id=1), version TEXT NOT NULL)')
        con.execute('INSERT OR IGNORE INTO overlay_defaults_version(id,version) VALUES(1,?)',
                    (generation,))

def _valid_option(key, value):
    if key == 'position':
        return isinstance(value, str) and value in ('top_left', 'top_right', 'bottom_left', 'bottom_right')
    if key == 'visibility_mode':
        return isinstance(value, str) and value in ('capture', 'game_visible', 'always')
    if key in _BOOL_OPTIONS:
        return isinstance(value, bool)
    if key in _INT_OPTIONS:
        low, high = _INT_OPTIONS[key]
        return type(value) is int and low <= value <= high
    if key in _COLOR_OPTIONS:
        return isinstance(value, str) and re.fullmatch(r'#[0-9a-fA-F]{6}', value) is not None
    return False


def options():
    """Read options without creating or changing any existing preference."""
    result = dict(DEFAULT_OPTIONS)
    with closing(sqlite3.connect(database_setting, timeout=10)) as con:
        version_table = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='overlay_defaults_version'").fetchone()
        version = con.execute('SELECT version FROM overlay_defaults_version WHERE id=1').fetchone() if version_table else None
        if version and version[0] in ('legacy', 'current'):
            result.update(CURRENT_V1_DEFAULT_OPTIONS)
            if version[0] == 'legacy':
                result.update(LEGACY_DEFAULT_OPTIONS)
        exists = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='overlay_options'").fetchone()
        rows = con.execute('SELECT name, value FROM overlay_options').fetchall() if exists else ()
    for key, raw in rows:
        try:
            value = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if _valid_option(key, value):
            result[key] = value.lower() if key in _COLOR_OPTIONS else value
    return result


def set_options(values):
    """Validate the complete patch before writing any value."""
    if not isinstance(values, dict) or not values or any(not _valid_option(key, value) for key, value in values.items()):
        raise ValueError('Invalid overlay options')
    with closing(sqlite3.connect(database_setting, timeout=10)) as con, con:
        con.execute('CREATE TABLE IF NOT EXISTS overlay_options (name TEXT PRIMARY KEY, value TEXT NOT NULL)')
        con.executemany('INSERT INTO overlay_options(name,value) VALUES(?,?) ON CONFLICT(name) DO UPDATE SET value=excluded.value',
                        [(key, json.dumps(value.lower() if key in _COLOR_OPTIONS else value))
                         for key, value in values.items()])


def enabled():
    with closing(sqlite3.connect(database_setting, timeout=10)) as con:
        exists = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='overlay_setting'").fetchone()
        row = con.execute('SELECT enabled FROM overlay_setting WHERE id=1').fetchone() if exists else None
    return bool(row[0]) if row else True


def set_enabled(value):
    if not isinstance(value, bool):
        raise ValueError('Invalid overlay setting')
    with closing(sqlite3.connect(database_setting, timeout=10)) as con, con:
        con.execute('CREATE TABLE IF NOT EXISTS overlay_setting (id INTEGER PRIMARY KEY CHECK(id=1), enabled INTEGER NOT NULL CHECK(enabled IN (0,1)))')
        con.execute('INSERT INTO overlay_setting(id,enabled) VALUES(1,?) ON CONFLICT(id) DO UPDATE SET enabled=excluded.enabled', (int(value),))
