from flask import Flask, session, jsonify, request
from datetime import date, datetime
from screeninfo import get_monitors
from PIL import Image
from pytesseract import pytesseract
from base64 import b64encode
import cv2
import numpy as np
import time
import os
import math
import time
import pygetwindow
import pyautogui
import ctypes
import base64
import unicodedata
import re
import html
import threading
import traceback
import sqlite3
from io import BytesIO


from __main__ import app


from application.init import load_user, load_settings, initialize_display_settings, update_settings, verify_identity, get_selected_language, update_language, apply_score as add_arena_score, add_capture, get_capture_page, get_ratio, update_user_image, update_user_level
from application.mode_stats import mode_user, add_mode_score, correct_invasion_no_result
from application.player_sightings import SightingTracker, record_sighting
from application.detection_history import record_detection, update_detection, message_text, read_steam_history
from application.locale_catalog import tracker_notifications, classify
from application import game_language, capture_speed, notification_region, peer_tracking, steam_history, steam_overlay, profile_legend
from application.session_summary import SessionSummary
from application.browser_language import browser_language
from application.ui_localization import packs as ui_packs, localize_counter
from application.runtime_paths import image_dir, RESOURCE_DIR, tesseract_path, data_dir
from application import usage_metrics
from application import auto_tracking
from application import capture_display, profile_capture, notification_sample
from application import retention
from application import tracker_notifications
from application import steam_log_auto
from application.invasion_search import SearchVisibility
from application.multi import sync_leaderboard_data
from application.secur import encrypt_value, decrypt_value, decrypt_rows
#  _   __   _   _   _____  
# | | |  \ | | | | |_   _| 
# | | |   \| | | |   | |   
# | | | |\   | | |   | |   
# | | | | \  | | |   | |   
# |_| |_|  \_| |_|   |_|   

user = load_user()[0]
settings = load_settings()[0]


# Keep the database unset until the first browser request supplies its language.
language_default = not str(user[5]).strip()
langue_select = 'eng' if language_default else get_selected_language()
first_language_lock = threading.Lock()
game_locale = game_language.UI_TO_GAME.get(langue_select, 'engus')
# Freeze the existing game language before the UI language can be changed.
game_language.save(game_locale)
capture_interval_seconds = capture_speed.load()
_legacy_preview = os.path.join(image_dir(), 'template_notif.jpg')
try:
    with Image.open(_legacy_preview) as _legacy_image:
        _legacy_height = _legacy_image.height
except (OSError, ValueError):
    _legacy_height = None
notification_bounds = notification_region.load((settings[4], settings[5]), _legacy_height)
notification_manual_mode = notification_region.manual_mode()
notification_locked_bounds = notification_region.load_locked_bounds()
game_detected = True
game_running = None  # Unknown until the monitor checks the game window.
steam_overlay_open = False
mode_select = "Arena"
mode_detected = False
invasion_phase = None
invasion_search_extent = None
invasion_search_history_id = None
invasion_search_visibility = SearchVisibility()
invasion_return_pending = None
recent_invasion_no_result = None
opponent_name = ''
monitor_lock = threading.Lock()
run_monitor = False
monitor_ready = False
monitor_error = False
sighting_tracker = SightingTracker()
ally_summoning_last_seen = None
ally_summon_failure_last_seen = None
inventory_warning_seen = {}
sightings_revision = 0
def _observe_steam_peers(status, peers):
    global sightings_revision
    mode = mode_select if mode_detected and run_monitor else 'Unknown'
    if steam_history.observe(status, peers, mode):
        sightings_revision += 1


peer_tracking.set_observer(_observe_steam_peers)
cout_total = 0
count = 0
count_limit = 20
cout_max_limit = 10000
fighter_find = False
fight = False
wait_fighter = False
cant_fight = False
fighters_exit = False
fighter_exit = False
victory = user[2]
defeat = user[3]
egality = user[4]
error = False
want_annul = False
connexion_error = False
mod_launch = 0
stape = 0
captur_send = 1
monitor_user_img = False
monitor_user_lvl = False
time_start = time.time()
time_end = time.time()
time_result = time_end - time_start

tampo_text = ""
capture = ""
capture_revision = 0
notification_event_sample = None
notification_sample_revision = 0
preview_condition = threading.Condition()
try:
    _saved_notification_sample = notification_sample.load()
    if _saved_notification_sample and (_saved_notification_sample.get('lines') or 0) >= 2:
        notification_sample_revision = 1
        notification_event_sample = dict(_saved_notification_sample, identity=None, id=notification_sample_revision)
except Exception:
    app.logger.exception('Unable to load notification example')
preview_wait_slots = threading.BoundedSemaphore(2)
captures = []
captures_stats = []
array_stats = {
    "run":False,
    "text":"",
    "mode":{},
    "victory":victory,
    "defeat":defeat,
    "egality":egality
}


def _latest_saved_capture():
    from application.init import database_capture
    try:
        with sqlite3.connect(database_capture) as con:
            row = con.execute('SELECT id,name,victory,defeat,egality,mode FROM tabel_captures ORDER BY id DESC LIMIT 1').fetchone()
        if not row:
            return None
        _, name, victory, defeat, draw, mode = decrypt_rows([row])[0]
        result = 'victory' if str(victory) in ('1', 'True') else 'defeat' if str(defeat) in ('1', 'True') else 'draw' if str(draw) in ('1', 'True') else None
        return {'mode':mode if mode in ('Arena', 'Invasion', 'Defense') else 'Arena', 'opponent':name, 'result':result} if result else None
    except (sqlite3.Error, ValueError, TypeError):
        app.logger.exception('Unable to read latest combat')
        return None

session_summary = SessionSummary(_latest_saved_capture())

def apply_score(*args):
    result = add_arena_score(*args) if mode_select == 'Arena' else add_mode_score(mode_select, *args)
    if args[3]:
        session_summary.combat_started(mode_select, opponent_name if mode_select != 'Arena' else '')
    elif args[0] or args[1] or args[2] or args[4] or args[5] or args[7] or args[8]:
        outcome = ('victory' if args[0] else 'defeat' if args[1] else 'draw' if args[2]
                   else 'connection_error' if args[7] else 'no_result')
        steam_name = steam_history.arena_opponent_name() if mode_select == 'Arena' else ''
        session_summary.combat_finished(outcome, steam_name)
    return result
correspondly_en = ["The combatant has left combat <br> Leaving combat ",
                   "All combatants have left combat <br> Leaving combat ",
                   "Echec du matchmaking <br> Failed to join session",
                   "A connection error occurred <br> Leaving combat ",
                   "waiting for player(s)",
                   "Matchmaking canceled",
                   "Matchmaking failed",
                   "Cancel matchmaking ? ",
                   "All combatants have assembled",
                   "Commencing combat",
                   "Combat ends in your victory ! ",
                   "Error of stape",
                   "Combat ends in your loss ",
                   "Leaving combat <br> Sorry we couldn't capture the end of the fight ",
                   "2 combatants",
                   "Prohibited",
                   "All players",
                   "No preference",
                   "Royal Colosseum",
                   "to Desktop",
                   "Le combat s\'achève par une égalité",
                   "Fin du combat <br> Le jeu c'est fermé pendant le combat",
                   "Quitter la partie"
                   ]

correspondly_fr = ["Le combattant à quittés le combat <br> Fin du combat ",
                   "Tous les combattants ont quittés le combat <br> Fin du combat ",
                   "Echec du matchmaking <br> Impossible de rejoindre la session",
                   "Une erreur de connexion est survenue <br> Fin du combat ",
                   "En attente de joueur(s)",
                   "Le matchmaking à été annulé",
                   "Matchmaking annulé",
                   "Vous voulez annuler le duel ? ",
                   "Tous les combattants sont rassemblés",
                   "Début du combat",
                   "Vous remportez la victoire ! ",
                   "Erreur de stape",
                   "Vous avez perdu ",
                   "Fin du combat <br> Désoler nous n'avons pas pu captuer la fin du combat ",
                   "2 combattants",
                   "Interdit",
                   "Tous les joueurs",
                   "Aucune préférence",
                   "Colysé royal",
                   "sur le bureau",
                   "Le combat s\'achève par une égalité",
                   "Fin du combat <br> Le jeu c'est fermé pendant le combat",
                   "Quitter la partie"
                   ]

detect_mod_fr = ['Duel', '2 combattants', 'Interdit', 'Tous les joueurs', 'Aucune pr', 'royal']
detect_mod_en = ['Duel', '2 combatants', 'Prohibited', 'AII players', 'No preference', 'Royal Colosseum']









detect_text_fr = ['but du combat', 'la victoire', 'Vous remportez', 'Tous les combattants sont', 'Annuler le matchmaking', 'Matchmaking annul','Le matchmaking a', 'Veuillez attendre que tous les combattants soient','Une erreur de connexion est survenue', 'Vous avez perdu', 'chec du matchmaking', 'Tous les combattants ont quitt', 'a quitt', 'COMMENCER', 'avez perdu','Le combat s\'achève par une égalité','Fin du combat']
detect_text_en = ['Commencing combat', 'Combat ends in your victory', 'in your victory', 'All combatants have assembled', 'Cancel matchmaking', 'Matchmaking failed', 'Matchmaking canceled', 'Please wait until all combatants are assembled','A connection error occurred', 'Combat ends in your loss', 'Failed to join', 'All combatants have left combat', 'has left combat','cing combat', 'in your loss', 'Le combat s\'achève par une égalité','Fin du combat']

detect_mod_active = ['']
detect_text_active = ['']
correspondly_active = ['']
if langue_select == "eng":
        detect_mod_active = detect_mod_en
        detect_text_active = detect_text_en
        correspondly_active = ui_packs()['eng']['backend']
        langue_select = "eng"
if langue_select == "fra":
        detect_mod_active = detect_mod_fr
        detect_text_active = detect_text_fr
        correspondly_active = correspondly_fr
        langue_select = "fra"
if langue_select not in ('fra', 'eng') and langue_select in ui_packs():
        correspondly_active = ui_packs()[langue_select]['backend']

# Arena matching follows the language of the game, not the UI language.
# Other languages are adapted to the internal French event vocabulary.
if game_locale == 'engus':
    detect_mod_active, detect_text_active = detect_mod_en, detect_text_en
else:
    detect_mod_active, detect_text_active = detect_mod_fr, detect_text_fr
     

base_dir = str(image_dir())
path_finish_fight = os.path.join(base_dir, 'finish_.jpg')   
path_start_fight = os.path.join(base_dir, 'start_.jpg')          
        
@app.route("/languages", methods={"POST"})
def languages(requested_language=None):
    global detect_mod_active
    global detect_text_active
    global langue_select
    global detect_mod_fr
    global detect_mod_en
    global detect_text_fr
    global detect_text_en
    global correspondly_active
    global language_default
    requested_language = requested_language or request.form.get("language")
    if requested_language != 'fra' and requested_language not in ui_packs():
        return jsonify({'request':'error', 'reason':'invalid_language'}), 400
    global game_locale, mode_detected, invasion_phase
    locale = game_language.UI_TO_GAME[requested_language]
    if fight:
        return jsonify({'request':'error', 'reason':'combat_active'}), 409
    model = game_language.LANGUAGES[locale][1]
    path = os.path.join(RESOURCE_DIR, 'locales', 'tessdata', model + '.traineddata')
    if not os.path.isfile(path):
        return jsonify({'request':'error', 'reason':'model_missing'}), 503
    game_language.save(locale)
    if locale != game_locale:
        mode_detected = False
        invasion_phase = None
        sighting_tracker.pending.clear()
    game_locale = locale
    langue_select = requested_language
   
    if langue_select == "eng":
        detect_mod_active = detect_mod_en
        detect_text_active = detect_text_en
        correspondly_active = ui_packs()['eng']['backend']
        langue_select = "eng"
        language_default = False 
    elif langue_select == "fra":
        detect_mod_active = detect_mod_fr
        detect_text_active = detect_text_fr
        correspondly_active = correspondly_fr
        langue_select = "fra"
        language_default = False
    else:
        correspondly_active = ui_packs()[langue_select]['backend']
        language_default = False
    # elif langue_select == "spa":
    #     detect_mod_active = detect_mod_es
    #     detect_text_active = detect_text_es
    #     correspondly_active = correspondly_es
    #     langue_select = "spa"
    #     language_default = False
    # elif langue_select == "ita":
    #     detect_mod_active = detect_mod_it
    #     detect_text_active = detect_text_it
    #     correspondly_active = correspondly_it
    #     langue_select = "ita"
    #     language_default = False
    # elif langue_select == "deu":
    #     detect_mod_active = detect_mod_de
    #     detect_text_active = detect_text_de
    #     correspondly_active = correspondly_de
    #     langue_select = "deu"
    #     language_default = False
    # elif langue_select == "rus":
    #     detect_mod_active = detect_mod_ru
    #     detect_text_active = detect_text_ru
    #     correspondly_active = correspondly_ru
    #     langue_select = "rus"
    #     language_default = False
    # elif langue_select == "jap":
    #     detect_mod_active = detect_mod_ja
    #     detect_text_active = detect_text_ja
    #     correspondly_active = correspondly_ja
    #     langue_select = "jap"
    #     language_default = False
    # elif langue_select == "chi":
    #     detect_mod_active = detect_mod_zh
    #     detect_text_active = detect_text_zh
    #     correspondly_active = correspondly_zh
    #     langue_select = "chi"
    #     language_default = False
    # elif langue_select == "por":
    #     detect_mod_active = detect_mod_pt
    #     detect_text_active = detect_text_pt
    #     correspondly_active = correspondly_pt
    #     langue_select = "por"
    #     language_default = False
    # elif langue_select == "nld":
    #     detect_mod_active = detect_mod_nl
    #     detect_text_active = detect_text_nl
    #     correspondly_active = correspondly_nl
    #     langue_select = "nld"
    #     language_default = False
    # elif langue_select == "swe":
    #     detect_mod_active = detect_mod_sv
    #     detect_text_active = detect_text_sv
    #     correspondly_active = correspondly_sv
    #     langue_select = "swe"
    #     language_default = False
    # elif langue_select == "nor":
    #     detect_mod_active = detect_mod_no
    #     detect_text_active = detect_text_no
    #     correspondly_active = correspondly_no
    #     langue_select = "nor"
    #     language_default = False
    # elif langue_select == "fin":
    #     detect_mod_active = detect_mod_fi
    #     detect_text_active = detect_text_fi
    #     correspondly_active = correspondly_fi
    #     langue_select = "fin"
    #     language_default = False
    # elif langue_select == "dan":
    #     detect_mod_active = detect_mod_da
    #     detect_text_active = detect_text_da
    #     correspondly_active = correspondly_da
    #     langue_select = "dan"
    #     language_default = False
    # elif langue_select == "tur":
    #     detect_mod_active = detect_mod_tr
    #     detect_text_active = detect_text_tr
    #     correspondly_active = correspondly_tr
    #     langue_select = "tur"
    #     language_default = False
    # elif langue_select == "tur":
    #     detect_mod_active = detect_mod_tr
    #     detect_text_active = detect_text_tr
    #     correspondly_active = correspondly_tr
    #     langue_select = "tur"
    #     language_default = False 
    # elif langue_select == "kor":
    #     detect_mod_active = detect_mod_ko
    #     detect_text_active = detect_text_ko
    #     correspondly_active = correspondly_ko
    #     langue_select = "kor"
    #     language_default = False 
    # elif langue_select == "ell":
    #     detect_mod_active = detect_mod_el
    #     detect_text_active = detect_text_el
    #     correspondly_active = correspondly_el
    #     langue_select = "ell"
    #     language_default = False 
    # elif langue_select == "pol":
    #     detect_mod_active = detect_mod_pl
    #     detect_text_active = detect_text_pl
    #     correspondly_active = correspondly_pl
    #     langue_select = "pol"
    #     language_default = False 
    # elif langue_select == "ces":
    #     detect_mod_active = detect_mod_cs
    #     detect_text_active = detect_text_cs
    #     correspondly_active = correspondly_cs
    #     langue_select = "ces"
    #     language_default = False 
    # elif langue_select == "hun":
    #     detect_mod_active = detect_mod_hu
    #     detect_text_active = detect_text_hu
    #     correspondly_active = correspondly_hu
    #     langue_select = "hun"
    #     language_default = False 
    # elif langue_select == "ron":
    #     detect_mod_active = detect_mod_ro
    #     detect_text_active = detect_text_ro
    #     correspondly_active = correspondly_ro
    #     langue_select = "ron"
    #     language_default = False 
    # elif langue_select == "ara":
    #     detect_mod_active = detect_mod_ar
    #     detect_text_active = detect_text_ar
    #     correspondly_active = correspondly_ar
    #     langue_select = "ara"
    #     language_default = False 
    # elif langue_select == "heb":
    #     detect_mod_active = detect_mod_he
    #     detect_text_active = detect_text_he
    #     correspondly_active = correspondly_he
    #     langue_select = "heb"
    #     language_default = False 

  
    update_language(langue_select)
    if game_locale == 'engus':
        detect_mod_active, detect_text_active = detect_mod_en, detect_text_en
    else:
        detect_mod_active, detect_text_active = detect_mod_fr, detect_text_fr
    return jsonify({"request": "success", "language":langue_select, "game_language":game_locale})


@app.before_request
def configure_first_browser_language():
    # Only the first page/init request may establish the shared preference.
    if request.method != 'GET' or request.path not in ('/', '/init') or not language_default:
        return None
    with first_language_lock:
        if not language_default:
            return None
        selected = browser_language(request.accept_languages)
        response = languages(selected)
        if isinstance(response, tuple) and response[1] == 503 and selected != 'eng':
            languages('eng')
    return None


@app.route('/steam-peers', methods={'GET', 'POST'})
def steam_peers():
    if request.method == 'POST':
        value = request.form.get('enabled')
        if value not in ('true', 'false'):
            return jsonify({'request':'error', 'reason':'invalid_setting'}), 400
        peer_tracking.set_enabled(value == 'true')
    return jsonify(peer_tracking.snapshot())


@app.route('/steam-log-auto', methods={'GET', 'POST'})
def steam_log_auto_setting():
    if request.method == 'POST':
        value = request.form.get('enabled')
        if value not in ('true', 'false'):
            return jsonify({'request': 'error', 'reason': 'invalid_setting'}), 400
        steam_log_auto.set_enabled(value == 'true')
    return jsonify({'request': 'success', 'enabled': steam_log_auto.get_enabled()})


@app.route('/steam-profile', methods={'POST'})
def steam_profile_open():
    steam_id = request.form.get('steam_id', '')
    if peer_tracking.open_profile(steam_id):
        return jsonify({'request':'success'})
    # Only allow historical IDs that really belong to a recorded Steam profile.
    if len(steam_id) == 17 and steam_id.isascii() and steam_id.isdigit():
        if any(str(event['steam'].get('id', '')) == steam_id for event in read_steam_history()):
            if peer_tracking.open_profile(steam_id, allow_historical=True):
                return jsonify({'request':'success'})
    return jsonify({'request':'error'}), 409


@app.route('/steam-ping', methods={'POST'})
def steam_ping_activate():
    if not peer_tracking.activate_ping():
        return jsonify({'request':'error', 'reason':'game_closed_or_disabled'}), 409
    return jsonify({'request':'success'})


_notification_save_condition = threading.Condition()
_pending_notification_save = None
_notification_save_started = False
_notification_save_busy = False


def _notification_sample_writer():
    global _pending_notification_save, _notification_save_busy
    while True:
        with _notification_save_condition:
            _notification_save_condition.wait_for(lambda: _pending_notification_save is not None)
            example = _pending_notification_save
            _pending_notification_save = None
            _notification_save_busy = True
        try:
            notification_sample.save(*example)
        except Exception:
            app.logger.exception('Unable to save notification example')
        finally:
            with _notification_save_condition:
                _notification_save_busy = False
                _notification_save_condition.notify_all()


def _queue_notification_sample(image, language, bounds, lines):
    global _pending_notification_save, _notification_save_started
    with _notification_save_condition:
        _pending_notification_save = (image, language, bounds, lines)
        if not _notification_save_started:
            threading.Thread(target=_notification_sample_writer, name='notification-example-writer', daemon=True).start()
            _notification_save_started = True
        _notification_save_condition.notify()


def flush_notification_sample(timeout=2):
    """Allow the queued example to finish before normal application exit."""
    with _notification_save_condition:
        return _notification_save_condition.wait_for(
            lambda: _pending_notification_save is None and not _notification_save_busy, timeout=timeout)


def _remember_notification_event(image_b64, text, language, bounds=None, lines=0):
    """Keep a real game frame only when its OCR contains a known game event."""
    global notification_event_sample, notification_sample_revision
    if not image_b64 or not text or lines < 2:
        return False
    events = classify(text, language)
    if not events:
        return False
    identity = (language, bounds is not None, tuple(sorted({(item['event'], tuple(sorted(item['values'].items()))) for item in events})))
    with preview_condition:
        if notification_event_sample and notification_event_sample['identity'] == identity:
            return False
        notification_sample_revision += 1
        notification_event_sample = {'image':image_b64, 'language':language,
                                     'identity':identity, 'id':notification_sample_revision, 'bounds':bounds, 'lines':lines}
    try:
        _queue_notification_sample(image_b64, language, bounds, lines)
    except Exception:
        # Failure to preserve an example must not interrupt a combat.
        app.logger.exception('Unable to queue notification example')
    return True


def _notification_preview():
    with preview_condition:
        return dict(notification_event_sample) if notification_event_sample else None


def _usable_sample_bounds(sample):
    bounds = (sample or {}).get('bounds')
    return bool(bounds and notification_region.valid(*bounds) and bounds[1] - bounds[0] < .95)


@app.route('/notification-region', methods={'GET', 'POST'})
def notification_region_setting():
    global notification_bounds, notification_manual_mode, notification_locked_bounds
    if request.method == 'POST':
        manual = request.form.get('manual')
        lock = request.form.get('locked')
        if manual is not None:
            if manual not in ('true', 'false') or lock is not None:
                return jsonify(request='error', reason='invalid_mode'), 400
            notification_region.set_manual_mode(manual == 'true')
            notification_manual_mode = manual == 'true'
        elif lock is not None:
            if lock not in ('true', 'false'):
                return jsonify(request='error', reason='invalid_mode'), 400
            if notification_manual_mode:
                return jsonify(request='error', reason='manual_mode'), 409
            if lock == 'true':
                sample = _notification_preview()
                if not _usable_sample_bounds(sample):
                    return jsonify(request='error', reason='no_lockable_preview'), 409
                if request.form.get('preview_id') != str(sample['id']):
                    return jsonify(request='error', reason='preview_changed'), 409
                next_bounds = tuple(sample['bounds'])
            else:
                next_bounds = None
            notification_region.set_locked_bounds(next_bounds)
            notification_locked_bounds = next_bounds
        else:
            if not notification_manual_mode:
                return jsonify(request='error', reason='automatic_mode'), 409
            try:
                top = float(request.form.get('top', ''))
                bottom = float(request.form.get('bottom', ''))
                if not notification_region.valid(top, bottom):
                    raise ValueError('invalid region')
            except (TypeError, ValueError):
                return jsonify({'request':'error', 'reason':'invalid_region'}), 400
            notification_region.save(top, bottom)
            notification_bounds = (top, bottom)
    sample = _notification_preview()
    effective = notification_bounds if notification_manual_mode else (notification_locked_bounds or (sample or {}).get('bounds') or (0.0, 1.0))
    return jsonify({'request':'success', 'top':effective[0], 'bottom':effective[1],
                    'manual':notification_manual_mode, 'locked':notification_locked_bounds is not None,
                    'can_lock':_usable_sample_bounds(sample), 'preview':sample['image'] if sample else '',
                    'preview_id':sample['id'] if sample else None})


@app.route('/notification-ocr-test', methods={'POST'})
def notification_ocr_test():
    # The test uses the same event image displayed by the settings page and
    # never sends its result to the tracking state machine.
    sample = _notification_preview()
    bounds = notification_bounds if notification_manual_mode else (notification_locked_bounds or (sample or {}).get('bounds') or (0.0, 1.0))
    if not sample:
        return jsonify(request='error', reason='no_preview'), 409
    if request.form.get('preview_id') != str(sample['id']):
        return jsonify(request='error', reason='preview_changed'), 409
    try:
        raw = base64.b64decode(sample['image'], validate=True)
        with Image.open(BytesIO(raw)) as image:
            image.load()
            region = image.crop(notification_region.crop_box(*image.size, bounds)).convert('RGB')
        grey = cv2.cvtColor(np.array(region), cv2.COLOR_RGB2GRAY)
        model = game_language.LANGUAGES[sample['language']][1]
        text = pytesseract.image_to_string(grey, lang=model, config='--psm 6 --oem 1' + game_ocr_data_config())
        matched = bool(classify(text, sample['language']))
    except Exception:
        app.logger.exception('Notification OCR test failed')
        return jsonify(request='error', reason='ocr_error'), 503
    return jsonify(request='success', text=text, matched=matched)


@app.route('/auto-game-start', methods={'GET', 'POST'})
def auto_game_start_setting():
    if request.method == 'POST':
        value = request.form.get('enabled')
        if value not in ('true', 'false'):
            return jsonify(request='error', reason='invalid_setting'), 400
        auto_tracking.save(value == 'true')
    return jsonify(request='success', enabled=auto_tracking.enabled())


@app.route('/tracking-notifications', methods={'GET', 'POST'})
def tracking_notifications_setting():
    if request.method == 'POST':
        value = request.form.get('enabled')
        if value not in ('true', 'false'):
            return jsonify(request='error', reason='invalid_setting'), 400
        try:
            tracker_notifications.save(request.form.get('kind', ''), value == 'true')
        except ValueError:
            return jsonify(request='error', reason='invalid_setting'), 400
    return jsonify(request='success', settings=tracker_notifications.load())


@app.route('/monitor-status', methods={'GET'})
def monitor_status():
    # Unlike /interval, this does not consume pending tracker events.
    return jsonify(request='success', running=run_monitor)


@app.route('/retention-settings', methods={'GET', 'POST'})
def retention_settings():
    if request.method == 'POST':
        if not monitor_lock.acquire(blocking=False):
            return jsonify(request='error', reason='monitor_active'), 409
        try:
            if run_monitor or fight:
                return jsonify(request='error', reason='monitor_active'), 409
            try:
                days = int(request.form.get('days', ''))
                retention.save(request.form.get('kind', ''), days)
            except (TypeError, ValueError):
                return jsonify(request='error', reason='invalid_setting'), 400
        finally:
            monitor_lock.release()
    return jsonify(request='success', settings=retention.load())


@app.route('/capture-speed', methods={'GET', 'POST'})
def capture_speed_setting():
    global capture_interval_seconds
    if request.method == 'POST':
        try:
            interval = float(request.form.get('interval', ''))
        except (TypeError, ValueError):
            return jsonify({'request': 'error', 'reason': 'invalid_interval'}), 400
        if interval not in capture_speed.ALLOWED_INTERVALS:
            return jsonify({'request': 'error', 'reason': 'invalid_interval'}), 400
        capture_speed.save(interval)
        capture_interval_seconds = interval
    return jsonify({'request': 'success', 'interval': capture_interval_seconds,
                    'intervals': capture_speed.ALLOWED_INTERVALS})


@app.route('/game-language', methods={'GET', 'POST'})
def game_language_setting():
    global game_locale, detect_mod_active, detect_text_active, mode_detected, invasion_phase
    if request.method == 'POST':
        locale = request.form.get('language', '')
        ui_language = next((key for key, value in game_language.UI_TO_GAME.items() if value == locale), None)
        if ui_language is None:
            return jsonify({'request':'error', 'reason':'invalid_language'}), 400
        result = languages(ui_language)
        if isinstance(result, tuple):
            return result
    return jsonify({'request':'success', 'language':game_locale,
                    'languages':[{'id':key,'name':value[0]} for key,value in game_language.LANGUAGES.items()]})



def reset_monitor_state():
    global mode_select, mode_detected
    global invasion_phase, invasion_search_extent, invasion_search_history_id, invasion_return_pending, recent_invasion_no_result, opponent_name, ally_summoning_last_seen, ally_summon_failure_last_seen, inventory_warning_seen
    recent_invasion_no_result = None
    invasion_search_history_id = None
    invasion_search_visibility.reset()
    steam_history.cancel_arena()
    mode_select = 'Arena'
    mode_detected = False
    invasion_phase = None
    invasion_search_extent = None
    invasion_return_pending = None
    opponent_name = ''
    sighting_tracker.pending.clear()
    ally_summoning_last_seen = None
    ally_summon_failure_last_seen = None
    inventory_warning_seen.clear()
    global array_stats
    global error
    global want_annul
    global fighter_find
    global fight
    global cant_fight
    global mod_launch
    global wait_fighter
    global stape
    global fighters_exit
    global fighter_exit
    global tampo_text
    global run_monitor
    global game_detected
    global captur_send
    game_detected = True
    run_monitor = False
    fighter_find = False
    fight = False
    wait_fighter = False
    cant_fight = False
    fighters_exit = False
    fighter_exit = False
    error = False
    want_annul = False
    mod_launch = 0
    stape = 0
    array_stats["text"] = ""
    tampo_text = ""
    captur_send = 1


@app.route("/init", methods={"GET"})
def init():
    global captur_send
    global language_default
    # Opening or reloading another browser tab must not stop an active monitor.
    if not run_monitor and not monitor_lock.locked():
        reset_monitor_state()
    captur_send = 1
    verifiy = verify_identity()
    user = mode_user(load_user()[0], mode_select)
    captures = get_capture_page(50 , captur_send)
    settings = initialize_display_settings()
    langue_select = get_selected_language()
    apply_score(0, 0, 0, 0, 0, 0, 0, 0, 0)
    
    
    sync_leaderboard_data()



    path_exemple_template = os.path.join(base_dir, 'template_notif.jpg') 
    if os.path.exists(path_exemple_template):
         
        image_notif = cv2.imread(path_exemple_template)
       
        # Récupérez la taille de l'image
        (h, w) = image_notif.shape[:2]
        left = 0
        top = 0
        right = int(w)
        bottom = int(h)
        size_notification = [left, top, right, bottom, h, w]
        notif_base64 = base64.b64encode(cv2.imencode('.jpg', image_notif)[1]).decode()
        

        return jsonify({"request": "success", "captures":captures, "user":user, "notif": notif_base64, "size_notification":size_notification, "settings":settings, "language_default": language_default})
    else:                  
        notif_base64 = ""               
        return jsonify({"request": "success", "captures":captures, "user":user, "notif": notif_base64, "settings":settings, "language_default": language_default})

@app.route("/nextCaptures", endpoint="nextCaptures", methods={"GET"})
def next_captures():
    global captur_send
    captur_send = captur_send +1 
    captures = get_capture_page(50, captur_send)
    
    return jsonify({"request": "success", "captures":captures})



class _CaptureStopped(Exception):
    """The user stopped tracking while Windows temporarily blocked capture."""


def screenshot_with_retry(*args, **kwargs):
    # The secure desktop used by UAC temporarily prevents ImageGrab from
    # accessing the screen. Retry only this known transient failure.
    while run_monitor:
        try:
            if active_capture_display is None:
                return pyautogui.screenshot(*args, **kwargs)
            filename = args[0] if args else None
            return capture_display.capture(active_capture_display, filename=filename, region=kwargs.get('region'))
        except OSError as exc:
            if 'screen grab failed' not in str(exc).lower():
                raise
            time.sleep(0.25)
    raise _CaptureStopped()


def update_game_display():
    """Refresh capture geometry when the game window has a usable monitor."""
    global active_capture_display, width_screen, height_screen
    detected_display = capture_display.game_display()
    if detected_display is not None:
        active_capture_display = detected_display
        width_screen, height_screen = detected_display['width'], detected_display['height']


def _run_monitor():
    global run_monitor, monitor_ready, monitor_error, steam_overlay_open
    try:
        monitor()
    except _CaptureStopped:
        pass
    except Exception:
        monitor_error = True
        usage_metrics.record_monitor_error()
        details = traceback.format_exc()
        app.logger.error('Capture monitor failed: %s', details)
        try:
            directory = str(data_dir())
            os.makedirs(directory, exist_ok=True)
            with open(os.path.join(directory, 'tracker-errors.log'), 'a', encoding='utf-8') as log:
                log.write(datetime.now().isoformat(timespec='seconds') + ' - capture monitor\n' + details + '\n')
        except OSError:
            app.logger.exception('Unable to save capture error log')
    finally:
        run_monitor = False
        monitor_ready = False
        steam_overlay_open = False
        tracker_notifications.notify('monitor_error' if monitor_error else 'monitor_stop')
        try:
            kind = 'monitor_error' if monitor_error else 'monitor_stop'
            message = 'Suivi arrêté à cause d’une erreur' if monitor_error else 'Suivi arrêté'
            record_detection(message, 'System', kind)
        except Exception:
            app.logger.exception('Unable to record tracking stop in history')
        with preview_condition:
            preview_condition.notify_all()
        monitor_lock.release()


@app.route("/start", methods={"GET"})
def start():
    global run_monitor, monitor_ready, monitor_error, capture, capture_revision, game_running
    global active_capture_display, width_screen, height_screen
    if not monitor_lock.acquire(blocking=False):
        if run_monitor:
            return jsonify({"request": "already_running"})
        return jsonify({"request": "error", "reason": "stopping"}), 409
    try:
        active_capture_display = None
        width_screen, height_screen = legacy_screen_size
        session_summary.start()
        game_running = None
        run_monitor = True
        monitor_ready = False
        monitor_error = False
        with preview_condition:
            capture = ""
            capture_revision += 1
            preview_condition.notify_all()
        try:
            peer_tracking.request_auto_ping()
        except Exception:
            app.logger.exception('Unable to start Steam peer detection')
        threading.Thread(target=_run_monitor, name='capture-monitor', daemon=True).start()
    except Exception:
        run_monitor = False
        monitor_lock.release()
        raise
    return jsonify({"request": "success"})


@app.route("/stop", methods={"GET"})
def stop():

    global run_monitor
    global tampo_text
    tampo_text = ""
    run_monitor = False
    peer_tracking.cancel_auto_ping()
    reset_monitor_state()
    return jsonify({"request": "success"})

@app.route("/autoStart", endpoint="autoStart", methods={"POST"})
def set_auto_start():
    
    auto_start = request.form.get("auto_start")
    settings = load_settings()[0]
    update_settings(settings[1], settings[2], settings[3], settings[4], settings[5], auto_start)
    return jsonify({"request": "success"})

@app.route("/capture", methods={"GET"})
def capture_select():
    global captures
    user = load_user()[0]
    victory = user[2]
    defeat = user[3]
    egality = user[4]
    ratio = user[7]
    global captures_stats
    sync_leaderboard_data()
    
    last = captures_stats[-1]
    if len(last) > 5:
        image = last[5]
    else:
        with open(path_start_fight, "rb") as f:
            image = b64encode(f.read()).decode("utf-8")
    captures.append(image)
        
    
   
    return jsonify({"request": "success", "datas":image, "victory":victory, "defeat":defeat, "egality":egality, "date":last[2], "mode": last[3] if len(last) > 3 else 'Arena', "opponent": last[4] if len(last) > 4 else '', "ratio": ratio})

@app.route('/live-preview', methods={'GET'})
def live_preview():
    try:
        last_revision = int(request.args.get('after', '-1'))
    except ValueError:
        return jsonify({'request':'error'}), 400
    previous_detected = request.args.get('detected')
    wants_wait = request.args.get('wait') == '1' and last_revision >= 0
    acquired = preview_wait_slots.acquire(blocking=False) if wants_wait else False
    try:
        with preview_condition:
            if acquired:
                preview_condition.wait_for(
                    lambda: capture_revision != last_revision or
                    (previous_detected in ('0', '1') and game_detected != (previous_detected == '1')),
                    timeout=1.0)
            revision = capture_revision
            return jsonify({'revision': revision, 'gameDetected': game_detected,
                            'capture': capture if revision != last_revision else None,
                            'retryAfter': 250 if wants_wait and not acquired else 0})
    finally:
        if acquired:
            preview_wait_slots.release()


@app.route("/interval", methods={"GET"})
def interval():
    # Affichage du bandeau, vérification via COOKIE
    global array_stats
    global tampo_text
    global capture
    global time_start
    global fight
    global game_detected
    user = mode_user(load_user()[0], mode_select)
    time_actuel = time.time() - time_start
    array_tampo = array_stats.copy()
    if tampo_text == array_tampo["text"]:
        array_tampo["text"] = ""
  
    if array_tampo["text"] != "":
        if array_tampo["text"] == tampo_text:
            array_stats["text"] = ""
            array_tampo["text"] = ""
            tampo_text = ""
        else:
            tampo_text = array_stats["text"]
            array_stats["text"] = ""
    
    
 
    notif_base64 = ""
    size_notification = 0
    path_exemple_template = os.path.join(base_dir, 'template_notif.jpg') 
    if os.path.exists(path_exemple_template):
            
            image_notif = cv2.imread(path_exemple_template)
             # Récupérez la taille de l'image
            (h, w) = image_notif.shape[:2]
            left = 0
            top = 0
            right = int(w)
            bottom = int(h)
            size_notification = [left, top, right, bottom, h, w]
            notif_base64 = base64.b64encode(cv2.imencode('.jpg', image_notif)[1]).decode()
    
    return jsonify({"request": "success", "datas":array_tampo, "capture":capture, "gameDetected": game_detected, "game_running": game_running, "steamOverlay": steam_overlay_open, "time_actuel": time_actuel, "fight":fight, "mode": mode_select, "mode_detected": mode_detected, "sightings_revision": sightings_revision, "monitor_running": run_monitor, "monitor_ready": monitor_ready, "monitor_error": monitor_error, "session_summary": session_summary.snapshot(), "user": user, "notif_base64": notif_base64, "size_notification": size_notification})


@app.route('/profile-legend', methods={'GET', 'POST'})
def profile_legend_view():
    if request.method == 'GET':
        return jsonify({'request':'success', 'legend':profile_legend.load(), 'session':session_summary.snapshot()})
    try:
        value = profile_legend.save((request.get_json(silent=True) or {}).get('legend'))
    except ValueError:
        return jsonify({'request':'error'}), 400
    return jsonify({'request':'success', 'legend':value})

@app.route('/modeStats', methods={'GET'})
def mode_stats_view():
    selected = request.args.get('mode', 'Arena')
    if selected not in ('Arena', 'Invasion', 'Defense'):
        return jsonify({'request': 'error'}), 400
    return jsonify({'request': 'success', 'mode': selected,
                    'user': mode_user(load_user()[0], selected)})


#Define path to tessaract.exe
path_to_tesseract = tesseract_path()
#Point tessaract_cmd to tessaract.exe
pytesseract.tesseract_cmd = path_to_tesseract




user32 = ctypes.windll.user32
scaling = user32.GetSystemMetrics(0x1000) / 100.0



height_screen = 0
width_screen = 0

for m in get_monitors():
    if str(scaling) != "0.0":
          
            height_screen = m.height / scaling
            width_screen = m.width / scaling
    else:
        height_screen = m.height
        width_screen = m.width
legacy_screen_size = (width_screen, height_screen)
active_capture_display = None
        

def emit_tracking_event(text):
    global array_stats, invasion_search_history_id
    marker = ''
    for candidate in ('<!--search-start-->', '<!--search-update-->', '<!--invasion-no-result-->', '<!--connection-correction-->'):
        if text.startswith(candidate):
            marker, text = candidate, text[len(candidate):]
            break
    # The frontend uses commas as message separators. Preserve literal commas
    # inside translated strings and leave the queue delimiter unambiguous.
    text = marker + localize_counter(text, langue_select).replace(',', '&#44;')
 
    if(len(array_stats["text"].split(",")[0]) == "Lets go !" and text == "Lets go !"):
        array_stats["text"] = array_stats["text"]
    else:
        if array_stats["text"] == "":
            array_stats["text"] = text
        else:
            array_stats["text"] = array_stats["text"] + ", "+text
        event_id = None
        try:
            if marker == '<!--connection-correction-->':
                pass
            elif marker == '<!--search-update-->' and update_detection(invasion_search_history_id, text):
                pass
            else:
                event_id = record_detection(text, mode_select if mode_detected else 'Unknown')
                if marker in ('<!--search-start-->', '<!--search-update-->'):
                    invasion_search_history_id = event_id
        except Exception:
            app.logger.exception('Unable to record detection history')
        return event_id
            
            
            
            
# Detection du premier plan            
def get_foreground_window():
    hwnd = ctypes.windll.user32.GetForegroundWindow()
    return hwnd

def get_window_text(hwnd):
    length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
    buff = ctypes.create_unicode_buffer(length + 1)
    ctypes.windll.user32.GetWindowTextW(hwnd, buff, length + 1)
    return buff.value

def get_foreground_app():
    hwnd = get_foreground_window()
    encryption_key = get_window_text(hwnd)
    return encryption_key


def get_zoom_level():
    # Ouvre un handle vers l'écran
    hdc = ctypes.windll.user32.GetDC(0)

    # Récupère la valeur de la constante LOGPIXELSX
    log_pixels_x = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)

    # Libère l'handle
    ctypes.windll.user32.ReleaseDC(0, hdc)

    # Calcule et retourne le niveau de zoom en pourcentage
    return 100 * 96 / log_pixels_x 


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long)
    ]

def get_window_resolution(window_name: str) -> tuple:
    # Récupère le handle de la fenêtre du jeu Elden Ring
    window_handle = ctypes.windll.user32.FindWindowA(None, window_name)
    # Crée un objet RECT pour stocker les dimensions de la fenêtre
    rect = RECT()
    # Récupère les dimensions de la fenêtre du jeu
    ctypes.windll.user32.GetWindowRect(window_handle, ctypes.byref(rect))
    # Récupère les dimensions de la fenêtre à partir de l'objet RECT
    width, height = rect.right - rect.left, rect.bottom - rect.top
    # Retourne les dimensions sous forme de tuple (largeur, hauteur)
    return width, height


#  _____   _____   _____    _____    _____   _____   _____   _____   __   _   _____   _      __    __ 
# /  ___| /  _  \ |  _  \  |  _  \  | ____| /  ___/ |  _  \ /  _  \ |  \ | | |  _  \ | |     \ \  / / 
# | |     | | | | | |_| |  | |_| |  | |__   | |___  | |_| | | | | | |   \| | | | | | | |      \ \/ /  
# | |     | | | | |  _  /  |  _  /  |  __|  \___  \ |  ___/ | | | | | |\   | | | | | | |       \  /   
# | |___  | |_| | | | \ \  | | \ \  | |___   ___| | | |     | |_| | | | \  | | |_| | | |___    / /    
# \_____| \_____/ |_|  \_\ |_|  \_\ |_____| /_____/ |_|     \_____/ |_|  \_| |_____/ |_____|  /_/     

def kmp_search(pattern, text):
  
    n = len(text)
    m = len(pattern)
    
    # Preprocessing
    lsp = [0] * m
    j = 0
    for i in range(1, m):
        while j > 0 and pattern[i] != pattern[j]:
            j = lsp[j - 1]
        if pattern[i] == pattern[j]:
            j += 1
        lsp[i] = j
    
    # Searching
    j = 0
    for i in range(n):
        while j > 0 and text[i] != pattern[j]:
            j = lsp[j - 1]
        if text[i] == pattern[j]:
            j += 1
        if j == m:
            return i - m + 1
    return -1

def measured_game_ocr(*args, **kwargs):
    started = time.monotonic()
    failed = False
    try:
        return pytesseract.image_to_string(*args, **kwargs)
    except Exception:
        failed = True
        raise
    finally:
        usage_metrics.record_ocr(time.monotonic() - started, failed)


def game_ocr_data_config():
    # TESSDATA_PREFIX is configured at startup. Passing a quoted path through
    # pytesseract on Windows leaves literal quotes in the subprocess argument.
    return ''


def normalise_ocr(text):
    return ' '.join(''.join(c for c in unicodedata.normalize('NFKD', text.casefold())
                            if not unicodedata.combining(c)).replace('’', "'").replace('‘', "'").split())


def handle_invasion(text, path_video_simple, original_grey):
    global fight, mode_select, mode_detected, stape, time_start, time_end, time_result
    global fighter_find, fighters_exit, fighter_exit, error, want_annul
    global wait_fighter, connexion_error, mod_launch
    global invasion_phase, invasion_search_extent, invasion_return_pending, recent_invasion_no_result, opponent_name

    original_text = text
    text = normalise_ocr(text)
    connection_problem = ('erreur de connexion' in text or 'a connection error occurred' in text)
    error_message = 'Une erreur de connexion est survenue.<br>Retour dans votre monde…'
    if not fight and mode_select == 'Invasion' and connection_problem and recent_invasion_no_result:
        previous = recent_invasion_no_result
        if time.monotonic() <= previous['deadline']:
            expected = message_text(localize_counter('Retour dans votre monde · Combat sans résultat', langue_select))
            replacement = message_text(localize_counter(error_message, langue_select))
            if correct_invasion_no_result(previous['id'], expected, replacement):
                session_summary.correct_connection_error()
                recent_invasion_no_result = None
                emit_tracking_event('<!--connection-correction-->' + error_message)
                return True
        else:
            recent_invasion_no_result = None
    host_start = re.search(r'le\s+doigt\s+(?:sanglant|r[ée]fractaire)\s+(.{1,80}?)\s+a\s+envahi\s+votre\s+monde', original_text, re.IGNORECASE | re.DOTALL)
    if not fight and host_start:
        fight = True
        mode_select = 'Defense'
        mode_detected = True
        stape = 1
        invasion_phase = 'fight'
        opponent_name = ' '.join(host_start.group(1).split())
        time_start = time.time()
        fighter_find = fighters_exit = fighter_exit = error = want_annul = False
        wait_fighter = connexion_error = False
        mod_launch = 0
        original_image = cv2.imread(path_video_simple)
        height, width = original_image.shape[:2]
        cv2.imwrite(path_start_fight, original_image[0:int(height / 3), int(width / 4):int(width - width / 4)])
        apply_score(0, 0, 0, 1, 0, 0, 1, 0, 0)
        safe_name = html.escape(opponent_name.replace(',', ' '))
        emit_tracking_event('Monde envahi : combat contre ' + safe_name)
        return True
    if not fight and "vous tentez d'envahir un autre monde" in text:
        mode_select = 'Invasion'
        mode_detected = True
        is_menu = "selectionnez l'etendue" in text
        extent = None
        if not is_menu:
            extent_match = re.search(r'etend(?:ue)?\s*:\s*proches\s*(uniquement|[/,]\s*distants|et\s+distants)', text)
            if extent_match:
                extent = 'proches uniquement' if extent_match.group(1) == 'uniquement' else 'proches et distants'
        if invasion_phase != 'search':
            invasion_phase = 'search'
            recent_invasion_no_result = None
            invasion_search_extent = extent
            message = "Vous tentez d'envahir un autre monde"
            if extent:
                message += " · Étendue : " + extent
            emit_tracking_event('<!--search-start-->' + message)
        elif extent and extent != invasion_search_extent:
            invasion_search_extent = extent
            emit_tracking_event("<!--search-update-->Vous tentez d'envahir un autre monde · Étendue : " + extent)
        return True
    if not fight and "invasion d'un autre monde" in text and 'terrassez' not in text:
        mode_select = 'Invasion'
        mode_detected = True
        if invasion_phase != 'loading':
            invasion_phase = 'loading'
            emit_tracking_event("Invasion d'un autre monde…")
        return True
    if not fight and "invasion d'un autre monde" in text and 'terrassez' in text and 'hote des doigts' in text:
        fight = True
        mode_select = 'Invasion'
        mode_detected = True
        stape = 1
        invasion_phase = 'fight'
        invasion_return_pending = None
        match = re.search(r'terrassez\s+(.{1,80}?)\s*,\s*h[oô]te\s+des\s+doigts', original_text, re.IGNORECASE | re.DOTALL)
        opponent_name = ' '.join(match.group(1).split()) if match else ''
        time_start = time.time()
        fighter_find = fighters_exit = fighter_exit = error = want_annul = False
        wait_fighter = connexion_error = False
        mod_launch = 0
        original_image = cv2.imread(path_video_simple)
        height, width = original_image.shape[:2]
        cv2.imwrite(path_start_fight, original_image[0:int(height / 3), int(width / 4):int(width - width / 4)])
        apply_score(0, 0, 0, 1, 0, 0, 1, 0, 0)
        safe_name = html.escape(opponent_name.replace(',', ' '))
        emit_tracking_event(('Vous avez envahi le monde de ' + safe_name) if safe_name else 'Vous avez envahi un autre monde')
        return True

    if not fight or mode_select not in ('Invasion', 'Defense'):
        return False
    if mode_select == 'Invasion':
        victory = 'hote des doigts vaincu' in text and 'retour dans votre monde' in text
        defeat = 'vous avez peri' in text and 'retour dans votre monde' in text
    else:
        name = ''.join(c for c in normalise_ocr(opponent_name) if c.isalnum())
        victory = False
        for line in original_text.splitlines():
            result = re.search(r'\bdoigt\s+(?:sanglant|refractaire)\s+(.+?)\s+est\s+mort\b', normalise_ocr(line))
            if result and name and ''.join(c for c in result.group(1) if c.isalnum()) == name:
                victory = True
                break
        defeat = 'vous avez peri' in text
    if connection_problem and not (victory or defeat):
        apply_score(0, 0, 0, 0, 0, 0, 0, 1, 0)
        fight = False
        stape = 0
        connexion_error = True
        invasion_phase = 'finished'
        invasion_return_pending = None
        recent_invasion_no_result = None
        emit_tracking_event(error_message)
        return True
    if mode_select == 'Invasion' and not (victory or defeat):
        if 'retour dans votre monde' in text and invasion_return_pending is None:
            invasion_return_pending = time.monotonic()
        # Leave time for the result to appear in the next OCR readings.
        if invasion_return_pending is not None and time.monotonic() - invasion_return_pending >= 4:
            time_end = time.time()
            time_result = time_end - time_start
            apply_score(0, 0, 0, 0, 1, 0, 0, 0, 0)
            fight = False
            stape = 0
            invasion_phase = 'finished'
            invasion_return_pending = None
            event_id = emit_tracking_event('<!--invasion-no-result-->Retour dans votre monde · Combat sans résultat')
            recent_invasion_no_result = {'id':event_id, 'deadline':time.monotonic() + 30} if event_id else None
            return True
    if victory or defeat:
        invasion_return_pending = None
        time_end = time.time()
        time_result = time_end - time_start
        with open(path_video_simple, 'rb') as image_file:
            image = b64encode(image_file.read()).decode('utf-8')
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        add_capture(opponent_name, int(victory), int(defeat), 0, str(math.ceil(time_result)), now, mode_select, image)
        apply_score(int(victory), int(defeat), 0, 0, 0, 0, 0, 0, 0)
        captures_stats.append([victory, str(math.ceil(time_result)), now, mode_select, opponent_name, image])
        cv2.imwrite(path_finish_fight, original_grey)
        fight = False
        stape = 0
        invasion_phase = 'finished'
        emit_tracking_event(correspondly_active[10 if victory else 12] + '<br> Time: ' + str(math.ceil(time_result)) + ' s')
    return True


def inventory_limit_item(text):
    """Read the item named in the game's inventory limit notification."""
    text = unicodedata.normalize('NFKC', text or '')
    match = re.search(r"impossible\s+d['’]acqu[ée]rir\s+([^\r\n.]{1,100})", text, re.IGNORECASE)
    if not match:
        return None
    item = ' '.join(match.group(1).split()).strip(' :;!…')
    return item if any(c.isalnum() for c in item) else None


def process_game_text(text_simple, path_video_simple, original_grey, notification_text=None):
    global array_stats
    global detect_text_active
    global error
    global want_annul
    global fighter_find
    global fight
    global cant_fight
    global victory
    global defeat
    global egality
    global mod_launch
    global wait_fighter
    global stape
    global time_start
    global time_end
    global time_result
    global fighters_exit
    global fighter_exit
    global mode_select, mode_detected, invasion_phase, invasion_search_extent, invasion_search_history_id
    global sightings_revision, ally_summoning_last_seen, ally_summon_failure_last_seen, inventory_warning_seen
    global connexion_error
    # The original invasion/player detectors understand French notifications.
    # Preserve the source OCR as well: arena and on-screen capture logic still
    # consume the original language, while translated IDs supply PvP events.
    summon_failed = any(event['event'] == 'ally_summon_failed'
                        for text in (text_simple, notification_text) if text
                        for event in classify(text, game_locale))
    if game_locale != 'frafr':
        first = tracker_notifications(text_simple or '', game_locale)
        second = tracker_notifications(notification_text or '', game_locale)
        if first:
            text_simple = (text_simple or '') + '\n' + '\n'.join(first)
        if second:
            notification_text = (notification_text or '') + '\n' + '\n'.join(second)
    item = inventory_limit_item(notification_text) or inventory_limit_item(text_simple)
    if item:
        key = normalise_ocr(item)
        now = time.monotonic()
        if key not in inventory_warning_seen or now - inventory_warning_seen[key] > 12:
            safe_item = html.escape(item.replace(',', ' '))
            emit_tracking_event('Impossible d’acquérir ' + safe_item + '.<br><span class="inventory-warning">Pensez à retirer une partie de cet objet de votre inventaire ou de votre stockage pour ne pas gêner la détection.</span>')
        inventory_warning_seen[key] = now
    combined_ocr = normalise_ocr((text_simple or "") + "\n" + (notification_text or "")).replace("’", "'")
    search_visible = "vous tentez d'envahir un autre monde" in combined_ocr
    if invasion_search_visibility.observe(invasion_phase == 'search' and not fight, search_visible, time.monotonic()):
        invasion_phase = None
        invasion_search_extent = None
        invasion_search_history_id = None
    if summon_failed:
        now = time.monotonic()
        if ally_summon_failure_last_seen is None or now - ally_summon_failure_last_seen > 8:
            emit_tracking_event("Impossible d'invoquer l'allié.")
        ally_summon_failure_last_seen = now
    if "invocation de l'allie" in combined_ocr and not (fight and mode_select in ("Invasion", "Arena")):
        now = time.monotonic()
        if ally_summoning_last_seen is None or now - ally_summoning_last_seen > 8:
            if not fight:
                mode_select = "Defense"
                mode_detected = True
            emit_tracking_event("Invocation de l’allié…")
        ally_summoning_last_seen = now
    for sighting in sighting_tracker.observe(text_simple, notification_text, mode_select, mode_detected, in_combat=fight):
        try:
            if sighting['role'] == 'ally' and not fight:
                mode_select = 'Defense'
                mode_detected = True
            if record_sighting(sighting):
                sightings_revision += 1
                role = {'ally': 'Allié', 'cooperator': 'Allié adverse',
                        'hunter': 'Chasseur', 'invader': 'Envahisseur'}[sighting['role']]
                if sighting['role'] == 'invader' and sighting['relation'] == 'coinvader':
                    role = 'Autre envahisseur'
                role += {'joined': ' arrivé', 'summoning': ' en cours d’invocation',
                         'left': ' reparti', 'dismissed': ' renvoyé dans son monde', 'died': ' mort', 'invaded': ' arrivé'}.get(sighting['event'], ' observé')
                emit_tracking_event(role + ' : ' + html.escape(sighting['name'].replace(',', ' ')))
        except Exception:
            app.logger.exception('Unable to record player sighting')
    if fight and mode_select == 'Invasion':
        # Check both OCR readings together before interpreting a return.
        handle_invasion((text_simple or '') + '\n' + (notification_text or ''), path_video_simple, original_grey)
        return
    if notification_text and handle_invasion(notification_text, path_video_simple, original_grey):
        if fight and mode_select in ('Invasion', 'Defense'):
            handle_invasion(text_simple, path_video_simple, original_grey)
        return
    if handle_invasion(text_simple, path_video_simple, original_grey):
        return
    if not fight and (any(kmp_search(detect_text_active[i], text_simple) != -1 for i in (0, 3, 7, 13)) or
                      (kmp_search(detect_mod_active[0], text_simple) != -1 and kmp_search(detect_mod_active[1], text_simple) != -1)):
        mode_select = 'Arena'
        mode_detected = True
    
    startReady = True
    if kmp_search(detect_text_active[13], text_simple) != -1 and ( kmp_search(detect_text_active[9], text_simple) != -1 and (kmp_search(detect_text_active[1], text_simple) != -1 or kmp_search(detect_text_active[2], text_simple) != -1)):
        startReady = False
        
    if kmp_search(detect_mod_active[0], text_simple) != -1 and kmp_search(detect_text_active[13], text_simple) != -1 and kmp_search(detect_text_active[3], text_simple) != -1:
       startReady = False

    if startReady == True:
      
        
        if kmp_search(detect_text_active[11], text_simple) != -1 and fighters_exit == False and fighter_exit == False and fight == True:
            # TOUS LES COMBATANTS ONT QUIT
            fighters_exit = True
            cant_fight = False
            fight = False
            wait_fighter = False
            want_annul = False
            stape = 0
            mod_launch = 0
            time_end = time.time()
            time_result = time_end - time_start
            apply_score(0, 0, 0, 0, 0, 1, 0, 0, 0)
            emit_tracking_event(correspondly_active[1]+"<br> Time: "+ str(math.ceil(time_result - 5))+" s")
        
        if kmp_search(detect_text_active[10], text_simple) != -1 and cant_fight == False:
            cant_fight = True
            fight = False
            wait_fighter = False
            want_annul = False
            stape = 0
            mod_launch = 0
            emit_tracking_event(correspondly_active[2])
        
        if kmp_search(detect_text_active[8], text_simple) != -1 and connexion_error == False and time.time() - time_start >= 8 and fight == True:
            # ERROR DE CONNEXION
            time_end = time.time()
            time_result = time_end - time_start
            connexion_error = True
            wait_fighter = False
            want_annul = False
            mod_launch = 0
            fight = False
            stape = 0
            apply_score(0, 0, 0, 0, 0, 0, 0, 1, 0)
            emit_tracking_event(correspondly_active[3]+"<br> Time: "+ str(math.ceil(time_result - 5))+" s")
        
        if kmp_search(detect_text_active[7], text_simple) != -1 and wait_fighter == False:
            # EN ATTENTE DE JOUEURS
            if fight == False:
                emit_tracking_event(correspondly_active[4])
                fighter_exit = False
                fighters_exit = False
                wait_fighter = True
                want_annul = False
                mod_launch = 1
                stape += 1
                
                path_exemple_template = os.path.join(base_dir, 'template_notif.jpg') 
                original_image = cv2.imread(path_video_simple)
                exemple_template = cv2.imwrite(path_exemple_template, original_image)
            else:
                fight = False
                mod_launch = 0
                connexion_error = True
                wait_fighter = False
                want_annul = False
                fight = False
                stape = 0
                apply_score(0, 0, 0, 0, 1, 0, 0, 0, 0)
                emit_tracking_event(correspondly_active[13])
        if kmp_search(detect_text_active[6], text_simple) != -1 and error == False:
            emit_tracking_event(correspondly_active[5])
            error = True
            mod_launch = 0
            wait_fighter = False
            stape = 0
        if kmp_search(detect_text_active[5], text_simple) != -1 and error == False:
            emit_tracking_event(correspondly_active[6])
            error = True
            mod_launch = 0
            wait_fighter = False
            stape = 0
            fighter_exit = False
            fighters_exit = False
        if kmp_search(detect_text_active[4], text_simple) != -1 and want_annul == False:
            emit_tracking_event(correspondly_active[7])
            want_annul = True
            error = False
            mod_launch = 1
            fighter_exit = False
            fighters_exit = False
        if kmp_search(detect_text_active[3], text_simple) != -1 and fighter_find == False:
            if fight == False:
                emit_tracking_event(correspondly_active[8])
                fighter_exit = False
                fighter_find = True
                error = False
                want_annul = False
                mod_launch = 1
                wait_fighter = False
                stape += 1
            else:
                fight = False
                mod_launch = 0
                connexion_error = True
                wait_fighter = False
                want_annul = False
                fight = False
                stape = 0
                apply_score(0, 0, 0, 0, 1, 0, 0, 0, 0)
                emit_tracking_event(correspondly_active[13])
        if (kmp_search(detect_text_active[0], text_simple) != -1 or kmp_search(detect_text_active[13], text_simple) != -1) and fight == False:
        #    début du combat
            fight = True
            fighter_find = False
            fighters_exit = False
            fighter_exit = False
            error = False
            want_annul = False
            wait_fighter = False
            connexion_error = False
            mod_launch = 0
            stape += 1
            time_start = time.time()
            try:
                steam_history.begin_arena()
            except Exception:
                app.logger.exception('Unable to associate arena Steam participants')
            original_image = cv2.imread(path_video_simple)
            height, width, channels = original_image.shape
            left = int(width / 4)
            top = 0
            right = int(width - (width / 4))
            bottom = int(height / 3)
            apply_score(0, 0, 0, 1, 0, 0, 1, 0, 0)
         
            croppedImage = original_image[top:bottom, left:right]
            start_fight = cv2.imwrite(path_start_fight, croppedImage)
            emit_tracking_event(correspondly_active[9])
 
        elif (kmp_search(detect_text_active[1], text_simple) != -1 or kmp_search(detect_text_active[2], text_simple) != -1) and fight == True and time.time() - time_start >= 8 :
            # VICTORY
            mod_launch = 0
            fight = False
            error = False
            wait_fighter = False
            time_end = time.time()
            time_result = time_end - time_start
           
            if stape >= 1:
                now = datetime.now()
                # 
                
                with open(path_start_fight, "rb") as f:
                    image_binary = f.read()
                    image = b64encode(image_binary).decode("utf-8")
                    add_capture("", 1, 0, 0, str(math.ceil(time_result - 5)), str(now.strftime("%Y-%m-%d %H:%M:%S")), mode_select, image)
                apply_score(1, 0, 0, 0, 0, 0, 0, 0, 0)
                try:
                    if steam_history.finish_arena('victory', now.strftime('%Y-%m-%d %H:%M:%S')):
                        sightings_revision += 1
                except Exception:
                    app.logger.exception('Unable to save arena Steam result')
                stape = 0
                captures_stats.append([True, str(math.ceil(time_result - 5)), str(now.strftime("%Y-%m-%d %H:%M:%S"))])
                
                
                finish_fight = cv2.imwrite(path_finish_fight, original_grey)
                emit_tracking_event(correspondly_active[10]+"<br> Time: "+ str(math.ceil(time_result - 5))+" s")
            else:
                
                emit_tracking_event(correspondly_active[11]+"<br> Time: "+ str(math.ceil(time_result - 5))+" s")
            time_start = time.time()
            time_end = time.time()
        
            
        
        elif (kmp_search(detect_text_active[9], text_simple) != -1 or kmp_search(detect_text_active[14], text_simple) != -1) and fight == True and time.time() - time_start >= 8 :
            # DEFEAT
            mod_launch = 0
            fight = False
            error = False
            wait_fighter = False
            time_end = time.time()
            time_result = time_end - time_start
          
            if stape >= 2:
                now = datetime.now()
                
                
                with open(path_start_fight, "rb") as f:
                    image_binary = f.read()
                    image = b64encode(image_binary).decode("utf-8")
                    add_capture("", 0, 1, 0, str(math.ceil(time_result - 5)), str(now.strftime("%Y-%m-%d %H:%M:%S")), mode_select, image)
                apply_score(0, 1, 0, 0, 0, 0, 0, 0, 0)
                try:
                    if steam_history.finish_arena('defeat', now.strftime('%Y-%m-%d %H:%M:%S')):
                        sightings_revision += 1
                except Exception:
                    app.logger.exception('Unable to save arena Steam result')
                stape = 0
                captures_stats.append([False, str(math.ceil(time_result - 5)), str(now.strftime("%Y-%m-%d %H:%M:%S"))])
                
            
                finish_fight = cv2.imwrite(path_finish_fight, original_grey)
                emit_tracking_event(correspondly_active[12]+"<br> Time: "+ str(math.ceil(time_result - 5))+" s")
            time_start = time.time()
            time_end = time.time()
        elif kmp_search(detect_text_active[15], text_simple) != -1  and fight == True :    
            # elif (kmp_search(detect_text_active[15], text_simple) != -1 or kmp_search(detect_text_active[16], text_simple) != -1) and fight == True :
            # EGALITY
            mod_launch = 0
            fight = False
            error = False
            wait_fighter = False
            time_end = time.time()
            time_result = time_end - time_start
      
            if stape >= 2:
                now = datetime.now()
                
                
                with open(path_start_fight, "rb") as f:
                    image_binary = f.read()
                    image = b64encode(image_binary).decode("utf-8")
                    add_capture("", 0, 0, 1, str(math.ceil(time_result - 5)), str(now.strftime("%Y-%m-%d %H:%M:%S")), mode_select, image)
                apply_score(0, 0, 1, 0, 0, 0, 0, 0, 0)
                try:
                    if steam_history.finish_arena('draw', now.strftime('%Y-%m-%d %H:%M:%S')):
                        sightings_revision += 1
                except Exception:
                    app.logger.exception('Unable to save arena Steam result')
                stape = 0
                captures_stats.append([None, str(math.ceil(time_result - 5)), str(now.strftime("%Y-%m-%d %H:%M:%S"))])
                
            
                finish_fight = cv2.imwrite(path_finish_fight, original_grey)
                emit_tracking_event(correspondly_active[20]+"<br> Time: "+ str(math.ceil(time_result - 5))+" s")
            time_start = time.time()
            time_end = time.time()
        if kmp_search(detect_text_active[12], text_simple) != -1 and fighter_exit == False and fight == True:
            # LE COMBATANT X A QUITTER LA PARTIE
            fighter_exit = True
            cant_fight = False
            fight = False
            wait_fighter = False
            want_annul = False
            stape = 0
            mod_launch = 0
            time_end = time.time()
            time_result = time_end - time_start
            apply_score(0, 0, 0, 0, 0, 1, 0, 0, 0)
            emit_tracking_event(correspondly_active[0]+"<br> Time: "+ str(math.ceil(time_result - 5))+" s")
            
        if kmp_search(detect_mod_active[0], text_simple) != -1 and mod_launch == 0:
            if kmp_search(detect_mod_active[1], text_simple) != -1 and mod_launch == 0:
                
                
                text_mod = "MODE : DUEL - "
                text_mod = text_mod + correspondly_active[14]+" - "
                if kmp_search(detect_mod_active[2], text_simple) != -1 and mod_launch == 0:
                    text_mod = text_mod + correspondly_active[15]+" - "
                if kmp_search(detect_mod_active[3], text_simple) != -1 and mod_launch == 0:
                    text_mod = text_mod + correspondly_active[16]+" - "
                if kmp_search(detect_mod_active[4], text_simple) != -1 and mod_launch == 0:
                    text_mod = text_mod + correspondly_active[17]+" - "
                if kmp_search(detect_mod_active[5], text_simple) != -1 and mod_launch == 0:
                    text_mod = text_mod + correspondly_active[18]
                
                if fight == True :
                    fight = False
                    mod_launch = 0
                    connexion_error = True
                    wait_fighter = False
                    want_annul = False
                    fight = False
                    stape = 0
                    apply_score(0, 0, 0, 0, 1, 0, 0, 0, 0)
                    emit_tracking_event(correspondly_active[13])
                else:
                    emit_tracking_event(text_mod)
                    mod_launch = 1
                    



#      ___  ___   _____   __   _   _   _____   _____   _____   
#     /   |/   | /  _  \ |  \ | | | | |_   _| /  _  \ |  _  \  
#    / /|   /| | | | | | |   \| | | |   | |   | | | | | |_| |  
#   / / |__/ | | | | | | | |\   | | |   | |   | | | | |  _  /  
#  / /       | | | |_| | | | \  | | |   | |   | |_| | | | \ \  
# /_/        |_| \_____/ |_|  \_| |_|   |_|   \_____/ |_|  \_\ 





def monitor():
   

    now = datetime.now()
    emit_tracking_event("Let's gooo ! [ "+str(now.strftime("%Y-%m-%d %H:%M:%S"))+" ]")
    global count
    global count_limit
    global cout_total
    global cout_max_limit
    global newpath_folder
    global run_monitor, monitor_ready
    global capture, capture_revision
    global game_detected, game_running, steam_overlay_open
    global langue_select
    global mod_launch
    global mode_select
    global connexion_error
    global wait_fighter
    global want_annul
    global stape
    global fight
    global monitor_user_img
    global monitor_user_lvl
    base_dir = str(image_dir())
    path_steam = os.path.join(base_dir, 'steam.jpg')        
    path_logo_steam = os.path.join(RESOURCE_DIR, 'steam_logo.png')
    logo = cv2.imread(path_logo_steam, cv2.IMREAD_GRAYSCALE)
    monitor_ready = bool(run_monitor)
    
    # path__runes = os.path.join(base_dir, 'runes.jpg') 
    # path_icon_runes = os.path.join(base_dir, 'icon_runes.png')  
    # icon_runes = cv2.imread(path_icon_runes, cv2.IMREAD_GRAYSCALE)
     
    last_capture_cycle = None
    ever_game_visible = False
    overlay_detector = steam_overlay.OverlayDetector()
    while(True):
        if count < count_limit and run_monitor == True:
            # Limit the start rate, including processing time; check the setting
            # repeatedly so stopping or changing speed remains responsive.
            if last_capture_cycle is not None:
                remaining = capture_interval_seconds - (time.monotonic() - last_capture_cycle)
                if remaining > 0:
                    time.sleep(min(remaining, 0.1))
                    continue
            last_capture_cycle = time.monotonic()   
            
            # A game can appear or move after tracking starts. Keep the last
            # usable screen while it is minimized or temporarily unavailable.
            update_game_display()

            # Confirm the screen is available before declaring the game closed:
            # Windows may be showing its secure administrator prompt.
            img_steam = screenshot_with_retry(path_steam, region=(
                0, int((height_screen - (height_screen / 2)) + (height_screen / 2.5)),
                int(width_screen / 3.2), 100))

            windows = pygetwindow.getAllWindows()
            window_titles = [(window, window.title) for window in windows]
            elden_find = any("ELDEN RING™" in title for _, title in window_titles)
            game_running = elden_find
                 
            
                 
            if (fight == True and mode_select == 'Arena' and (time.time() - time_start) - 1 >= 190) or (fight == True and elden_find == False):
                    fight = False
                    mod_launch = 0
                    connexion_error = True
                    wait_fighter = False
                    want_annul = False
                    fight = False
                    stape = 0
                    if elden_find == False: 
                        apply_score(0, 0, 0, 0, 0, 0, 0, 0, 1)
                        emit_tracking_event(correspondly_active[21])
                        mode_select = 'Arena'
                    else:
                        apply_score(0, 0, 0, 0, 1, 0, 0, 0, 0)
                        emit_tracking_event(correspondly_active[13])
            
            text_steam = pytesseract.image_to_string(img_steam)
            try:
                image_steam = cv2.imread(path_steam, cv2.IMREAD_GRAYSCALE)
                result_steam = cv2.matchTemplate(image_steam, logo, cv2.TM_CCOEFF_NORMED)
                min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result_steam)
            except:
                max_val = 1
            # pyautogui.screenshot(path__runes, region=((width_screen - 300,(height_screen - (height_screen / 2 )) + (height_screen / 2.5),200,100)))
            # image_runes = cv2.imread(path__runes, cv2.IMREAD_GRAYSCALE)
            # result_runes = cv2.matchTemplate(image_runes, icon_runes, cv2.TM_CCOEFF_NORMED)
            # min_val_runes, max_val_runes, min_loc_runes, max_loc_runes = cv2.minMaxLoc(result_runes)
                    
            # if monitor_user_img == True or monitor_user_lvl == True:       
            #     max_val_runes = 1
            
            game_windows = [(window, title) for window, title in window_titles if 'ELDEN RING' in title.upper()]
            foreground_hwnd = get_foreground_window()
            game_in_foreground = bool(game_windows) and get_window_text(foreground_hwnd) == "ELDEN RING™"
            game_hwnd = next((window._hWnd for window, title in game_windows if title == "ELDEN RING™"), None)
            overlay_window = bool(game_hwnd and not game_in_foreground and
                                  steam_overlay.is_steam_overlay_window(foreground_hwnd, game_hwnd))
            steam_overlay_open = overlay_detector.update(foreground_hwnd if game_in_foreground else None,
                                                         overlay_window=overlay_window)
            if game_in_foreground and not steam_overlay_open and text_steam.find("STEAM") == -1 and max_val < 0.8: 
                ever_game_visible = True
        
                if game_detected == False:
                    with preview_condition:
                        game_detected = True
                        preview_condition.notify_all()
                    time.sleep(1)
                else:
                   
                    
                    if monitor_user_img == True or monitor_user_lvl == True:
                        sub_monitor()
                    
             
            
            
                    path_video_simple = os.path.join(base_dir, 'simple_'+str(count)+'.jpg') 
                    path_notif_simple = os.path.join(base_dir, 'simple_notif_'+str(count)+'.jpg')       
                  
                    width_crop_left = 3.2
                    width_crop_right = 3.2
                    height_crop_top = 5
                    height_crop_bottom = 20
                   
                   
                    screenshot_with_retry(path_video_simple)
                    # NORMAL SCREEN
                    img = Image.open(path_video_simple)
                    # Work in actual captured pixels; the notification region is
                    # stored as proportions of this central image, independent of DPI.
                    image_width, image_height = img.size
                    left_capt = int(image_width / width_crop_left)
                    top_capt = int(image_height / height_crop_top)
                    right_capt = int(image_width - (image_width / width_crop_right))
                    bottom_capt = int(image_height - (image_height / height_crop_bottom))
                    img_simple = img.crop((left_capt, top_capt, right_capt, bottom_capt))
                    img_simple.save(path_video_simple, 'JPEG', optimize=True, quality=95)
                    original_grey = cv2.imread(path_video_simple, cv2.IMREAD_GRAYSCALE)
                    with open(path_video_simple, "rb") as f:
                        image_binary = f.read()
                        image_b64 = b64encode(image_binary).decode("utf-8")
                        with preview_condition:
                            capture = image_b64
                            capture_revision += 1
                            preview_condition.notify_all()
                

                    
                    #Extract text from image
                    game_model = game_language.LANGUAGES[game_locale][1]
                    ocr_data = game_ocr_data_config()
                    text_simple = measured_game_ocr(original_grey, lang=game_model, config="--psm 12 --oem 1" + ocr_data)
                    frame_manual = notification_manual_mode
                    frame_locked = None if frame_manual else notification_locked_bounds
                    # If unlocked, full-image OCR remains the safe fallback.
                    frame_bounds = notification_bounds if frame_manual else (frame_locked or (0.0, 1.0))
                    notification_image = img_simple.crop(notification_region.crop_box(*img_simple.size, frame_bounds))
                    notification_grey = cv2.cvtColor(np.array(notification_image.convert('RGB')), cv2.COLOR_RGB2GRAY)
                    notification_text = measured_game_ocr(notification_grey, lang=game_model, config="--psm 6 --oem 1" + ocr_data)
                    if fight and mode_select == 'Defense':
                        frame = cv2.imread(path_video_simple)
                        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
                        death_mask = cv2.inRange(hsv, (0, 70, 40), (12, 255, 255)) | cv2.inRange(hsv, (165, 70, 40), (179, 255, 255))
                        death_text = measured_game_ocr(death_mask, lang=game_model, config='--psm 6' + ocr_data)
                        if 'vous avez peri' in normalise_ocr(death_text):
                            text_simple += '\n' + death_text
                    try:
                        combined = text_simple + '\n' + notification_text
                        if classify(combined, game_locale):
                            positioned = pytesseract.image_to_data(original_grey, lang=game_model,
                                config="--psm 6 --oem 1" + ocr_data, output_type=pytesseract.Output.DICT)
                            located = notification_region.analyze_notification(positioned, img_simple.height, game_locale, original_grey)
                            if located:
                                if not frame_manual and frame_locked is None:
                                    crop = img_simple.crop(notification_region.crop_box(*img_simple.size, located['bounds'])).convert('RGB')
                                    crop_grey = cv2.cvtColor(np.array(crop), cv2.COLOR_RGB2GRAY)
                                    crop_text = measured_game_ocr(crop_grey, lang=game_model, config="--psm 6 --oem 1" + ocr_data)
                                    # Never replace a recognized full-image message with an
                                    # unreadable crop: preserve the broad fallback.
                                    if classify(crop_text, game_locale):
                                        notification_text = crop_text
                                _remember_notification_event(image_b64, combined, game_locale, located['bounds'], located['lines'])
                    except Exception:
                        # The optional automatic zone and preview must not interrupt tracking.
                        app.logger.exception('Unable to prepare notification event preview')
                    process_game_text(text_simple, path_video_simple, original_grey, notification_text)
                
                # try:
                #     # Result(text_simple, "")
                #         correspondly(text_simple, originalImage)              
                        
                
                # except:
                #     prunt("/!\ ERROR ! Merci de vous arreter /!\\")
                #     print("/!\ ERROR! Please stop ! ERROR ! Merci de vous arreter /!\\")
                        
                       
                
                if cv2.waitKey(25) & 0xFF == ord('q'):
                    cv2.destroyAllWindows()
                    break
                if count == count_limit:
                    cv2.destroyAllWindows()
                    break
            else:
                notify_hidden = False
                with preview_condition:
                    if game_detected:
                        game_detected = False
                        preview_condition.notify_all()
                        notify_hidden = bool(ever_game_visible and game_running and not steam_overlay_open)
                if notify_hidden:
                    tracker_notifications.notify('game_hidden')
                
                
        else:
            cv2.destroyAllWindows()
            break
        if count == count_limit - 1 :
            count = 0 
        count+=1
        cout_total+=1
    
    



user_img_tampo = ""
def sub_monitor():
                    
                        global user_img_tampo
                        global monitor_user_img
                        global monitor_user_lvl
                        
                    
                        user_img_tampo = ""
                        base_dir = str(image_dir())
                        path_user_img = os.path.join(base_dir, 'user.jpg')  
                        path_user_lvl = os.path.join(base_dir, 'user_lvl.jpg')  
                        path_user_img_panel = os.path.join(base_dir, 'user_panel.jpg')  
                        # path_user_img = '/Video/user.jpg'
                        
                        width_crop_left = 3
                        width_crop_right = 4
                        height_crop_top = 2
                        height_crop_bottom = 4
                    
                        screenshot_with_retry(path_user_img_panel)
                        img_user_panel = Image.open(path_user_img_panel)
                        left = int(width_screen / width_crop_left )
                        top = int(height_screen / height_crop_top)
                        right = int(width_screen)
                        bottom = int(height_screen - (height_screen / 4))
                        img_user_panel = img_user_panel.crop((left, top, right, bottom))
                        img_user_panel.save(path_user_img_panel, 'JPEG', optimize=True, quality=100)   
                        
                        text_user = pytesseract.image_to_string(img_user_panel, lang=game_language.LANGUAGES[game_locale][1], config=game_ocr_data_config())
                     
                        if (text_user.find(correspondly_active[19]) != -1 or text_user.find(correspondly_active[22]) != -1) and monitor_user_img == True:
                            
                                width_crop_left = 2
                                width_crop_right = 4.5
                                height_crop_top = 3
                                height_crop_bottom = 2.5

                                
                                screenshot_with_retry(path_user_img)
                                img_user = Image.open(path_user_img)
                                left = int(width_screen / width_crop_left)
                                top = int(height_screen / height_crop_top)
                                right = int(width_screen - (width_screen / width_crop_right))
                                bottom = int(height_screen - (height_screen / height_crop_bottom))
                                img_user = img_user.crop((left, top, right, bottom))
                                img_user.save(path_user_img, 'JPEG', optimize=True, quality=100)  
                                
                            
                                user = load_user()[0]
                                tampo_base64 = user[6]
                                with open(path_user_img, "rb") as f:
                                    image_binary_bis = f.read()
                                    image_b64_bis = b64encode(image_binary_bis).decode("utf-8")
                                    if tampo_base64 != image_b64_bis and image_b64_bis != "":
                                
                                        user_img_tampo = image_b64_bis
                                        monitor_user_img = False
                                        
                        if (text_user.find(correspondly_active[19]) != -1 or text_user.find(correspondly_active[22]) != -1) and monitor_user_lvl == True:
                        
                            width_crop_left = 5
                            height_crop_top = 2.5
                            width_crop_right = 2.4
                            height_crop_bottom = 2.1
                            
                            screenshot_with_retry(path_user_lvl)
                            img_lvl = Image.open(path_user_lvl)
                            left = int(width_screen / width_crop_left)
                            top = int(height_screen / height_crop_top)
                            right = int(width_screen / width_crop_right)
                            bottom = int(height_screen / height_crop_bottom)
                            img_lvl = img_lvl.crop((left, top, right, bottom))
                            img_lvl.save(path_user_lvl, 'JPEG', optimize=True, quality=100)
                            
                            text_lvl = pytesseract.image_to_string(img_lvl, lang=game_language.LANGUAGES[game_locale][1], config=game_ocr_data_config())
                            number = ""
                            for char in text_lvl:
                                if char.isdigit():
                                    number += char
                            number = int(number)
                           
                            if number < 714 and number > 0:
                                user_img_tampo = str(number)
                                monitor_user_lvl = False
                      
                          
                                
                                     
                                
_profile_candidate_lock = threading.Lock()
_profile_candidate = None


@app.route('/profile-capture', methods={'POST'})
def capture_profile():
    global _profile_candidate
    import secrets
    import win32gui
    from application import init
    action = request.form.get('action')
    if action == 'read':
        hwnd = win32gui.FindWindow(None, 'ELDEN RING™')
        if not hwnd or hwnd != win32gui.GetForegroundWindow() or win32gui.IsIconic(hwnd):
            return jsonify(request='waiting')
        display = capture_display.game_display()
        if not display:
            return jsonify(request='waiting')
        try:
            image = capture_display.capture(display)
            candidate = profile_capture.read(image, game_language.LANGUAGES[game_locale][1])
        except (OSError, pytesseract.TesseractError):
            app.logger.exception('Unable to read character profile')
            return jsonify(request='error'), 503
        if not candidate:
            return jsonify(request='waiting')
        token = secrets.token_urlsafe(32)
        with _profile_candidate_lock:
            _profile_candidate = (token, time.monotonic(), candidate)
        return jsonify(request='success', token=token, profile=candidate)
    if action == 'save':
        token = request.form.get('token', '')
        with _profile_candidate_lock:
            candidate = _profile_candidate
            if not candidate or not token.isascii() or len(token) > 100 or time.monotonic() - candidate[1] > 300 or not secrets.compare_digest(token, candidate[0]):
                return jsonify(request='error'), 400
            profile = candidate[2]
            with sqlite3.connect(init.database_user, timeout=10) as db:
                db.execute('UPDATE tabel_user SET name=?, base64=?, userLevel=? WHERE id=1',
                           (encrypt_value(profile['name']), encrypt_value(profile['avatar']), encrypt_value(profile['level'])))
            _profile_candidate = None
        return jsonify(request='success', profile=profile)
    return jsonify(request='error'), 400


@app.route("/monitor_user", methods={"POST"})
def monitor_user():
    
    global monitor_user_img
    global user_img_tampo
    global monitor_user_lvl
    mod_select = request.form.get("mode")
    if mod_select == "img_avatar":
        if monitor_user_img == False and user_img_tampo == "":
            monitor_user_img = True
        user = load_user()[0]
        tampo_base64 = user[6]
        if tampo_base64 != user_img_tampo and user_img_tampo != "":
            update_user_image(user_img_tampo)
            result = user_img_tampo
            user_img_tampo = ""
            return jsonify({"request": "success", "interval":result}) 
        else:
            return jsonify({"request": "success", "interval":""}) 
    elif mod_select == "img_lvl": 
        if monitor_user_lvl == False and user_img_tampo == "":
            monitor_user_lvl = True
        if user_img_tampo != "":
            monitor_user_lvl = False
            update_user_level(user_img_tampo)
            result = user_img_tampo
            user_img_tampo = ""
            return jsonify({"request": "success", "interval":result}) 
        else:
            return jsonify({"request": "success", "interval":""}) 
           
 
                                   
                                
@app.route("/updateNotify", endpoint="updateNotify", methods={"POST"})
def update_notification_region():
    top = request.form.get("top")
    bottom = request.form.get("bottom")
    settings = load_settings()[0]
   
    update_settings(settings[1], settings[2], settings[3], str(top), str(bottom), settings[6])
    return jsonify({"request": "success", "settings": settings})
