"""Language codes and OCR models used for recognition of game messages."""
import sqlite3
from contextlib import closing
from application.init import database_setting

LANGUAGES = {
    'frafr': ('Français', 'fra'), 'engus': ('English', 'eng'),
    'deude': ('Deutsch', 'deu'), 'itait': ('Italiano', 'ita'),
    'spaes': ('Español (España)', 'spa'), 'spaar': ('Español (Latinoamérica)', 'spa'),
    'porbr': ('Português (Brasil)', 'por'), 'polpl': ('Polski', 'pol'),
    'rusru': ('Русский', 'rus'), 'jpnjp': ('日本語', 'jpn'),
    'korkr': ('한국어', 'kor'), 'zhocn': ('简体中文', 'chi_sim'),
    'zhotw': ('繁體中文', 'chi_tra'), 'thath': ('ไทย', 'tha'),
    'araae': ('العربية', 'ara'),
}


UI_TO_GAME = {
    'fra':'frafr', 'eng':'engus', 'deu':'deude', 'ita':'itait',
    'spaes':'spaes', 'spaar':'spaar', 'por':'porbr', 'pol':'polpl',
    'rus':'rusru', 'jap':'jpnjp', 'kor':'korkr', 'chi':'zhocn',
    'zht':'zhotw', 'tha':'thath', 'ara':'araae',
}


def selected(interface_language):
    with closing(sqlite3.connect(database_setting, timeout=10)) as con:
        con.execute('CREATE TABLE IF NOT EXISTS game_language (id INTEGER PRIMARY KEY CHECK (id=1), locale TEXT NOT NULL)')
        row = con.execute('SELECT locale FROM game_language WHERE id=1').fetchone()
        con.commit()
    return row[0] if row and row[0] in LANGUAGES else UI_TO_GAME.get(interface_language, 'engus')


def initialize(interface_language, first_run=False):
    """Keep existing choices; detect Steam only for a new tracker profile.

    Older profiles have one shared language, which is migrated to the game
    setting. If Steam cannot identify the game language, use English until the
    user selects another one. Detection is never repeated on later starts.
    """
    from application.steam_game_language import detect
    with closing(sqlite3.connect(database_setting, timeout=10)) as con:
        con.execute('CREATE TABLE IF NOT EXISTS game_language (id INTEGER PRIMARY KEY CHECK (id=1), locale TEXT NOT NULL)')
        row = con.execute('SELECT locale FROM game_language WHERE id=1').fetchone()
        if row and row[0] in LANGUAGES:
            return row[0]
        locale = (detect() or 'engus') if first_run else UI_TO_GAME.get(interface_language, 'engus')
        con.execute('INSERT INTO game_language(id,locale) VALUES(1,?) ON CONFLICT(id) DO UPDATE SET locale=excluded.locale', (locale,))
        con.commit()
        return locale


def save(locale):
    if locale not in LANGUAGES:
        raise ValueError('Invalid game language')
    with closing(sqlite3.connect(database_setting, timeout=10)) as con:
        con.execute('CREATE TABLE IF NOT EXISTS game_language (id INTEGER PRIMARY KEY CHECK (id=1), locale TEXT NOT NULL)')
        con.execute('INSERT INTO game_language(id,locale) VALUES(1,?) ON CONFLICT(id) DO UPDATE SET locale=excluded.locale', (locale,))
        con.commit()
