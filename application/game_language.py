"""Language codes and OCR models used by the shared language setting."""
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


def save(locale):
    if locale not in LANGUAGES:
        raise ValueError('Invalid game language')
    with closing(sqlite3.connect(database_setting, timeout=10)) as con:
        con.execute('CREATE TABLE IF NOT EXISTS game_language (id INTEGER PRIMARY KEY CHECK (id=1), locale TEXT NOT NULL)')
        con.execute('INSERT INTO game_language(id,locale) VALUES(1,?) ON CONFLICT(id) DO UPDATE SET locale=excluded.locale', (locale,))
        con.commit()
