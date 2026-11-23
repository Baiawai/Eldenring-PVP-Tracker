"""Private categories and favourites for locally observed players."""
import sqlite3
import re
import threading
import unicodedata
import uuid
from contextlib import closing

from application.init import database_setting
from application.secur import decrypt_value, encrypt_value

DEFAULTS = ('steam_friend', 'friend', 'rival')
DEFAULT_COLOURS = {'steam_friend':'#3b8db7', 'friend':'#69c37b', 'rival':'#dc6a6a'}
CUSTOM_COLOUR = '#c9a96b'
_revision = 0
_revision_lock = threading.Lock()


def revision():
    with _revision_lock:
        return _revision


def _changed():
    global _revision
    with _revision_lock:
        _revision += 1


def _connect():
    con = sqlite3.connect(database_setting, timeout=10)
    con.execute('PRAGMA foreign_keys=ON')
    con.execute('CREATE TABLE IF NOT EXISTS player_categories (id TEXT PRIMARY KEY, name BLOB NOT NULL)')
    con.execute('CREATE TABLE IF NOT EXISTS player_hidden_categories (id TEXT PRIMARY KEY)')
    con.execute('CREATE TABLE IF NOT EXISTS player_category_colours (category_id TEXT PRIMARY KEY, colour TEXT NOT NULL)')
    con.execute('CREATE TABLE IF NOT EXISTS player_preferences (id INTEGER PRIMARY KEY, identity BLOB NOT NULL, category TEXT, favourite INTEGER NOT NULL DEFAULT 0)')
    con.execute('''CREATE TABLE IF NOT EXISTS player_preference_categories (
        preference_id INTEGER NOT NULL REFERENCES player_preferences(id) ON DELETE CASCADE,
        category TEXT NOT NULL, PRIMARY KEY(preference_id,category))''')
    return con


def identity(source, value):
    if not isinstance(value, str) or not isinstance(source, str):
        raise ValueError('invalid_player')
    value = unicodedata.normalize('NFKC', value).strip()
    if source == 'steam':
        if len(value) != 17 or not value.isascii() or not value.isdigit():
            raise ValueError('invalid_player')
    elif source == 'game':
        if not value or len(value) > 128 or not any(c.isalnum() for c in value):
            raise ValueError('invalid_player')
        value = value.casefold()
    else:
        raise ValueError('invalid_player')
    return source + ':' + value


def player_identity(player):
    steam = player.get('steam')
    return identity('steam', str(steam['id'])) if steam else identity('game', player['name'])


def _categories(con):
    # Keep existing Partner assignments accessible, without creating that
    # category for new users or losing their personal classification.
    legacy_partner = con.execute("SELECT 1 FROM player_preferences WHERE category='partner' UNION ALL SELECT 1 FROM player_preference_categories WHERE category='partner' LIMIT 1").fetchone()
    legacy = [{'id':'partner', 'name':'Partenaire', 'builtin':False, 'former_default':True, 'color':'#d4af37'}] if legacy_partner else []
    return [{'id': key, 'builtin': True, 'automatic':key == 'steam_friend', 'color': DEFAULT_COLOURS[key]} for key in DEFAULTS] + legacy + [
        {'id': row[0], 'name': decrypt_value(row[1]).decode('utf-8'), 'builtin': False,
         'color': row[2] or CUSTOM_COLOUR}
        for row in con.execute('SELECT c.id,c.name,col.colour FROM player_categories c LEFT JOIN player_category_colours col ON col.category_id=c.id ORDER BY c.rowid')]


def categories():
    with closing(_connect()) as con:
        return _categories(con)


def create_category(name, color=CUSTOM_COLOUR):
    if not isinstance(name, str):
        raise ValueError('invalid_category')
    name = unicodedata.normalize('NFKC', name).strip()
    if not name or len(name) > 50 or any(unicodedata.category(c).startswith('C') for c in name):
        raise ValueError('invalid_category')
    if not isinstance(color, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
        raise ValueError('invalid_color')
    with closing(_connect()) as con, con:
        con.execute('BEGIN IMMEDIATE')
        existing = _categories(con)
        if len(existing) >= 103 or any(not c['builtin'] and c['name'].casefold() == name.casefold() for c in existing):
            raise ValueError('invalid_category')
        category = {'id': uuid.uuid4().hex, 'name': name, 'builtin': False, 'color':color.lower()}
        con.execute('INSERT INTO player_categories(id,name) VALUES(?,?)', (category['id'], encrypt_value(name)))
        con.execute('INSERT INTO player_category_colours(category_id,colour) VALUES(?,?)', (category['id'], category['color']))
        con.commit()
        _changed()
        return category


def delete_category(category_id):
    """Remove the category and its assignments, keeping independent favourites."""
    if category_id in DEFAULTS:
        raise ValueError('default_category')
    with closing(_connect()) as con:
        con.execute('BEGIN IMMEDIATE')
        if category_id not in {category['id'] for category in _categories(con)}:
            return False
        con.execute('DELETE FROM player_preference_categories WHERE category=?', (category_id,))
        con.execute('''UPDATE player_preferences SET category=(
            SELECT category FROM player_preference_categories WHERE preference_id=player_preferences.id ORDER BY rowid LIMIT 1)
            WHERE category=?''', (category_id,))
        con.execute('''DELETE FROM player_preferences WHERE category IS NULL AND favourite=0 AND NOT EXISTS
            (SELECT 1 FROM player_preference_categories WHERE preference_id=player_preferences.id)''')
        con.execute('DELETE FROM player_categories WHERE id=?', (category_id,))
        con.execute('DELETE FROM player_category_colours WHERE category_id=?', (category_id,))
        con.commit()
        _changed()
        return True


def read_preferences():
    with closing(_connect()) as con:
        # Read the assignments and preference rows from the same snapshot.
        con.execute('BEGIN')
        by_id = {}
        for pref_id, category in con.execute('SELECT preference_id,category FROM player_preference_categories ORDER BY rowid'):
            by_id.setdefault(pref_id, []).append(category)
        result = {}
        for pref_id, key, category, favourite in con.execute('SELECT id,identity,category,favourite FROM player_preferences'):
            values = by_id.get(pref_id, [category] if category else [])
            result[decrypt_value(key).decode('utf-8')] = {'category':values[0] if values else None,
                'categories':values, 'favourite':bool(favourite)}
        return result


def category_counts():
    """Count assigned identities, including those absent from active history."""
    counts = {}
    for preference in read_preferences().values():
        for category in preference['categories']:
            counts[category] = counts.get(category, 0) + 1
    return counts


def set_preference(source, value, category, favourite, *, legacy=False):
    key = identity(source, value)
    if legacy:
        if category is not None and not isinstance(category, str):
            raise ValueError('invalid_category')
        values = [category] if category else []
    elif not isinstance(category, list) or len(category) > 103 or any(not isinstance(c, str) or not c for c in category):
        raise ValueError('invalid_category')
    else:
        values = list(dict.fromkeys(category))
    if not isinstance(favourite, bool):
        raise ValueError('invalid_favourite')
    with closing(_connect()) as con:
        con.execute('BEGIN IMMEDIATE')
        if set(values) - {c['id'] for c in _categories(con) if not c.get('automatic')}:
            raise ValueError('invalid_category')
        existing = next(((rowid, primary, bool(old_favourite)) for rowid, encrypted, primary, old_favourite in con.execute('SELECT id,identity,category,favourite FROM player_preferences')
                         if decrypt_value(encrypted).decode('utf-8') == key), None)
        previous = ([row[0] for row in con.execute('SELECT category FROM player_preference_categories WHERE preference_id=? ORDER BY rowid', (existing[0],))] if existing else [])
        if existing and not previous and existing[1]:
            previous = [existing[1]]
        previous_favourite = existing[2] if existing else False
        if legacy and existing and values == ([existing[1]] if existing[1] else []):
            # An older client toggling a favourite must not erase extra tags.
            values = previous
        if existing is None:
            if values or favourite:
                cursor = con.execute('INSERT INTO player_preferences(identity,category,favourite) VALUES(?,?,?)',
                                     (encrypt_value(key), values[0] if values else None, int(favourite)))
                existing = (cursor.lastrowid, None)
        elif not values and not favourite:
            con.execute('DELETE FROM player_preferences WHERE id=?', (existing[0],))
            existing = None
        else:
            con.execute('UPDATE player_preferences SET category=?,favourite=? WHERE id=?', (values[0] if values else None, int(favourite), existing[0]))
        if existing is not None:
            con.execute('DELETE FROM player_preference_categories WHERE preference_id=?', (existing[0],))
            con.executemany('INSERT INTO player_preference_categories(preference_id,category) VALUES(?,?)',
                            [(existing[0], item) for item in values])
        con.commit()
        _changed()
        return {'categories':values, 'favourite':favourite,
                'previous_categories':previous, 'category_changed':set(previous) != set(values),
                'favourite_changed':previous_favourite != favourite}


def annotate(players):
    preferences = read_preferences()
    result = []
    for player in players:
        try:
            preference = preferences.get(player_identity(player), {})
        except (KeyError, TypeError, ValueError):
            preference = {}
        automatic = ['steam_friend'] if player.get('steam') and player.get('steam_friend') is True else []
        result.append({**player, 'category': preference.get('category'), 'categories':automatic + preference.get('categories', []),
                       'favourite': bool(preference.get('favourite'))})
    return result
