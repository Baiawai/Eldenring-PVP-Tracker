"""Separate PvP statistics while keeping the original arena profile intact."""
import os
import sqlite3
from contextlib import closing
from application.init import database_user, database_setting

DATABASE = database_user
MODES = ('Arena', 'Invasion', 'Defense')
FIELDS = ('victory', 'defeat', 'egality', 'combats', 'noResult', 'fight_exit',
          'abandon', 'maxVictory', 'maxDefeat', 'ratioTime', 'score',
          'connexionError', 'gameExit', 'ratio')
INDEXES = (2, 3, 4, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 7)


def _connect():
    con = sqlite3.connect(DATABASE, timeout=10)
    con.execute('CREATE TABLE IF NOT EXISTS mode_stats (mode TEXT PRIMARY KEY, ' +
                ', '.join(name + ' REAL NOT NULL DEFAULT 0' for name in FIELDS) + ')')
    return con


def mode_user(profile, mode):
    user = list(profile)
    if mode not in ('Invasion', 'Defense'):
        return user
    with closing(_connect()) as con:
        row = con.execute('SELECT ' + ', '.join(FIELDS) + ' FROM mode_stats WHERE mode=?', (mode,)).fetchone()
    if row is None:
        row = [0] * len(FIELDS)
    for index, value in zip(INDEXES, row):
        user[index] = str(int(value)) if float(value).is_integer() else str(value)
    return user


def add_mode_score(mode, victory, defeat, egality, combats, no_result, fight_exit,
                   abandon, connexion_error, game_exit):
    if mode not in ('Invasion', 'Defense'):
        raise ValueError('Unknown mode')
    with closing(_connect()) as con:
        con.execute('BEGIN IMMEDIATE')
        con.execute('INSERT OR IGNORE INTO mode_stats (mode) VALUES (?)', (mode,))
        row = con.execute('SELECT ' + ', '.join(FIELDS) + ' FROM mode_stats WHERE mode=?', (mode,)).fetchone()
        s = dict(zip(FIELDS, row))
        for key, delta in (('victory', victory), ('defeat', defeat), ('egality', egality),
                           ('combats', combats), ('noResult', no_result), ('fight_exit', fight_exit),
                           ('connexionError', connexion_error), ('gameExit', game_exit)):
            s[key] += delta
        s['abandon'] = max(0, s['combats'] - s['victory'] - s['defeat'] - s['egality'] -
                           s['noResult'] - s['fight_exit'] - s['connexionError'] - s['gameExit'] - abandon)
        if victory or defeat or egality:
            s['maxVictory'] = s['maxVictory'] + 1 if victory else 0
            s['maxDefeat'] = s['maxDefeat'] + 1 if defeat else 0
        total = s['victory'] + s['defeat'] + s['egality']
        s['ratio'] = round(s['victory'] / total * 100, 2) if total else 0
        s['score'] = round((s['victory'] * 3 - s['defeat'] * 2 + s['egality'] +
                            s['fight_exit'] * .5 - s['abandon'] * 4 - s['noResult'] - s['gameExit']) / 30, 2)
        con.execute('UPDATE mode_stats SET ' + ', '.join(name + '=?' for name in FIELDS) + ' WHERE mode=?',
                    [s[name] for name in FIELDS] + [mode])
        try:
            from application.leaderboard_events import record_delta
            record_delta(con, mode, (victory, defeat, egality, combats, no_result, fight_exit, abandon, connexion_error, game_exit), database_setting)
        except Exception:
            from __main__ import app
            app.logger.exception('Unable to queue leaderboard event')
        con.commit()


def correct_invasion_no_result(event_id, expected_text, replacement_text):
    """Atomically reclassify one known history entry and its mode totals."""
    from application.init import database_capture
    from application.secur import decrypt_value, encrypt_value
    with closing(sqlite3.connect(DATABASE, timeout=10)) as con:
        con.execute('ATTACH DATABASE ? AS capture_db', (database_capture,))
        con.execute('BEGIN IMMEDIATE')
        event = con.execute('SELECT mode,message FROM capture_db.detection_history WHERE id=?', (event_id,)).fetchone()
        row = con.execute('SELECT victory,defeat,egality,noResult,fight_exit,abandon,connexionError,gameExit FROM mode_stats WHERE mode=?', ('Invasion',)).fetchone()
        if not event or event[0] != 'Invasion' or decrypt_value(event[1]).decode('utf-8') != expected_text or not row or row[3] < 1:
            con.rollback()
            return False
        victory, defeat, draw, no_result, fight_exit, abandon, connection_error, game_exit = row
        no_result -= 1
        connection_error += 1
        score = round((victory * 3 - defeat * 2 + draw + fight_exit * .5 - abandon * 4 - no_result - game_exit) / 30, 2)
        con.execute('UPDATE mode_stats SET noResult=?, connexionError=?, score=? WHERE mode=?',
                    (no_result, connection_error, score, 'Invasion'))
        con.execute('UPDATE capture_db.detection_history SET message=? WHERE id=?',
                    (encrypt_value(replacement_text), event_id))
        try:
            from application.leaderboard_events import record_correction
            record_correction(con, 'Invasion', database_setting)
        except Exception:
            from __main__ import app
            app.logger.exception('Unable to queue leaderboard correction')
        con.commit()
        return True
