import threading
from flask import Flask, abort, jsonify, redirect, render_template, request
import webbrowser
import os
import socket
import secrets
import pystray
from PIL import Image
from application.runtime_paths import tesseract_path, RESOURCE_DIR, STORE_BUILD, accessible_data_directories
from application.version import APP_VERSION
from application.local_security import is_allowed_request
from application import store_update
import threading
from waitress import serve, create_server
import sys
import traceback

os.environ['TESSDATA_PREFIX'] = str(RESOURCE_DIR / 'locales' / 'tessdata')



print("=====================================")
print(" ELDEN PVP TRACKER ")
print("=====================================")
print(f"version: {APP_VERSION}")
print("-------------")
print("Date : 26/02/2023")
print("Dev by : Baiawai")
print("Official web site : https://www.eldenring-tracker.com/")
print("=====================================")
# Creation de l'app 
app = Flask(__name__)
# Local commands contain only small forms and JSON, never uploaded images.
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024
app.config['TRACKER_INSTANCE_ID'] = secrets.token_urlsafe(18)
_LOCAL_SESSION = secrets.token_urlsafe(32)
_LOCAL_COOKIE = 'tracker_session'

@app.before_request
def restrict_local_requests():
    if request.path == '/preference-migration':
        if (request.method != 'GET' or request.host.lower() != 'localhost:5000' or
                request.headers.get('Sec-Fetch-Dest') != 'iframe'):
            abort(403)
        return None
    if not is_allowed_request(request.host, request.headers.get('Origin'),
                              request.headers.get('Referer'), request.headers.get('Sec-Fetch-Site')):
        abort(403)
    if (request.method == 'GET' and request.path == '/' and request.host.lower() == 'localhost:5000'
            and globals().get('interface_url', '').startswith('http://elden-tracker.localhost')):
        return redirect(interface_url, code=302)
    if request.path not in ('/', '/monitor-status') and not request.path.startswith('/static/'):
        supplied = request.cookies.get(_LOCAL_COOKIE, '')
        if not supplied.isascii() or not secrets.compare_digest(supplied, _LOCAL_SESSION):
            abort(403)
    # Flask automatically supplies HEAD for GET routes, including these
    # historical endpoints that change state. A probe must not start or stop
    # tracking, consume an event, or terminate the application.
    if request.method == 'HEAD' and request.path in ('/start', '/stop', '/exit', '/interval', '/capture', '/nextCaptures'):
        abort(405)
    return store_update.gate_response(request, get_selected_language, packs)


@app.after_request
def secure_local_response(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    if request.path == '/preference-migration':
        response.headers['Content-Security-Policy'] = "default-src 'none'; script-src 'unsafe-inline'; frame-ancestors http://elden-tracker.localhost http://elden-tracker.localhost:5000"
    else:
        response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'same-origin'
    if not request.path.startswith('/static/'):
        response.headers['Cache-Control'] = 'no-store'
    if request.path == '/' and request.method == 'GET' and response.status_code == 200:
        response.set_cookie(_LOCAL_COOKIE, _LOCAL_SESSION, httponly=True, samesite='Strict', path='/')
    if request.path in ('/', '/languages') and response.status_code == 200:
        tray = globals().get('icon')
        if tray is not None and tray.visible:
            try:
                tray.update_menu()
            except Exception:
                app.logger.exception('Unable to refresh the notification-area menu')
    return response



from application import first_run
try:
    first_run.begin()
    from application import init
    from application import overlay_settings
    overlay_settings.initialize_defaults(first_run.uses_new_overlay_defaults(),
                                         generation=first_run.overlay_defaults_generation())
    from application import functions
    from application import multi
    from application import online_leaderboard
    from application import secur
    from application import players
    from application import metrics_routes
    from application import usage_metrics
    from application import auto_tracking
    from application import retention
    from application import steam_log_auto, peer_tracking
    from application import history_archives
    from application import tray_controls
    from application import interface_mode
    from application.tray_navigation import Navigation
    from application.init import get_selected_language
    from application.ui_localization import packs
except Exception:
    first_run.report_fatal(traceback.format_exc())
    raise


# Report uncaught local request failures without transmitting requests or messages.
from flask import got_request_exception
from application import error_reports

def _report_local_exception(sender, exception, **extra):
    error_reports.report('application', 'other', exception)

got_request_exception.connect(_report_local_exception, app, weak=False)


# POUR LE NO CONSOLE 
# sys.stdout = sys.stderr = open(os.devnull, 'w') 
server = None

current_folder = os.path.dirname(os.path.abspath(__file__))
static_folder = os.path.join(current_folder, "static")
icon_path = os.path.join(static_folder, "tracker-eye-ornament.ico")
image = Image.open(icon_path)
interface_url = 'http://localhost:5000/'
tray_navigation = Navigation(lambda url: interface_mode.open_interface(url), base_url=lambda: interface_url)


@app.route('/preference-migration')
def preference_migration():
    return '''<!doctype html><script>
    addEventListener('message', function(e) {
      if (!['http://elden-tracker.localhost', 'http://elden-tracker.localhost:5000'].includes(e.origin) || e.source !== parent || e.data !== 'tracker-preferences-request') return;
      const result = {};
      for (const key of ['trackerDisplayPreferences', 'trackerSteamDisplayPreferences', 'trackerProfileSidebarOpen']) {
        try { const value = localStorage.getItem(key); if (value !== null && value.length < 4096) result[key] = value; } catch (_) {}
      }
      parent.postMessage({type:'tracker-preferences-response', values:result}, e.origin);
    });</script>'''


@app.route('/interface-mode', methods=['GET', 'POST'])
def change_interface_mode():
    if request.method == 'POST':
        mode = request.form.get('mode')
        if mode not in ('browser', 'window'):
            abort(400)
        previous = interface_mode.get_mode()
        try:
            if mode != previous:
                interface_mode.set_mode(mode)
                try:
                    interface_mode.open_interface(interface_url, mode)
                except (OSError, RuntimeError):
                    interface_mode.set_mode(previous)
                    raise
                icon.update_menu()
        except (OSError, RuntimeError):
            return jsonify(request='error'), 503
    return jsonify(request='success', mode=interface_mode.get_mode())


def tray_mode(mode):
    def action(icon, item):
        previous = interface_mode.get_mode()
        try:
            interface_mode.set_mode(mode)
            try:
                interface_mode.open_interface(interface_url, mode)
            except (OSError, RuntimeError):
                interface_mode.set_mode(previous)
                raise
            icon.update_menu()
        except (OSError, RuntimeError):
            icon.notify(tray_modern('interface_mode_error', 'Impossible d’ouvrir cette fenêtre.'))
    return action



 
def tray_text(index, fallback):
    def label(item):
        language = get_selected_language()
        legacy = packs().get(language, {}).get('legacy', [])
        return legacy[index] if len(legacy) > index else fallback
    return label


def open_tracker(icon, item):
    tray_navigation.open('home')


def open_statistics(icon, item):
    tray_navigation.open('statistics')


def open_settings(icon, item):
    tray_navigation.open('settings')


def open_captures(icon, item):
    tray_navigation.open('captures')


def open_history(icon, item):
    tray_navigation.open('history')


def tray_modern(key, fallback):
    return tray_controls.text(packs(), get_selected_language(), key, fallback)


def tray_start_label(item):
    return tray_modern('tray_start_tracking', 'Démarrer le suivi')


def tray_stop_label(item):
    return tray_modern('tray_stop_tracking', 'Arrêter le suivi')


def start_tracking(icon, item):
    tray_controls.change_tracking(app, functions, store_update, icon, True, tray_modern)


def stop_tracking(icon, item):
    tray_controls.change_tracking(app, functions, store_update, icon, False, tray_modern)


def open_data_folder(icon, item):
    for directory in accessible_data_directories():
        os.startfile(directory)


def data_folder_label(item):
    language = get_selected_language()
    return packs().get(language, {}).get('modern', {}).get('environment_data_path', 'Dossier des données')


def quit_tracker(icon, item):
    stop_flask(icon)


icon = pystray.Icon("EldenRingPvPTracker", image, "Elden PVP Tracker", menu=pystray.Menu(
    pystray.MenuItem("Elden PVP Tracker", open_tracker, default=True),
    pystray.MenuItem(tray_start_label, start_tracking),
    pystray.MenuItem(tray_stop_label, stop_tracking),
    pystray.MenuItem(lambda item: tray_modern('interface_mode', 'Mode d’ouverture'), pystray.Menu(
        pystray.MenuItem(lambda item: tray_modern('interface_browser', 'Navigateur'), tray_mode('browser'), checked=lambda item: interface_mode.get_mode() == 'browser', radio=True),
        pystray.MenuItem(lambda item: tray_modern('interface_window', 'Fenêtre dédiée'), tray_mode('window'), checked=lambda item: interface_mode.get_mode() == 'window', radio=True))),
    pystray.Menu.SEPARATOR,
    pystray.MenuItem(tray_text(3, 'Captures'), open_captures),
    pystray.MenuItem(tray_text(83, 'Statistiques'), open_statistics),
    pystray.MenuItem(lambda item: tray_modern('menu_history', 'Historique'), open_history),
    pystray.MenuItem(tray_text(4, 'Configurations'), open_settings),
    pystray.MenuItem(data_folder_label, open_data_folder),
    pystray.Menu.SEPARATOR,
    pystray.MenuItem(tray_text(62, 'Quitter le tracker'), quit_tracker)
))
 
def start_pystray():
    icon.run()


@app.route('/tray-navigation', methods={'POST'})
def poll_tray_navigation():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400)
    try:
        command = tray_navigation.poll(data.get('tab'), data.get('visible'),
                                       data.get('focused'), data.get('ack'))
    except ValueError:
        abort(400)
    return jsonify(command=command)


@app.route('/initialization-notice', methods={'POST'})
def initialization_notice():
    return jsonify(notice=first_run.claim())


@app.route('/initialization-error-log', methods={'POST'})
def initialization_error_log():
    try:
        return jsonify(opened=first_run.open_log())
    except OSError:
        return jsonify(opened=False), 500


path_to_tesseract = tesseract_path()
    
@app.route("/")
def index():
    langue_select = get_selected_language()
    if langue_select == "fra":
        langue_select = "fr"
    elif langue_select == "eng":
        langue_select = "en"
    else:
        from application.ui_localization import packs
        langue_select = packs().get(langue_select, {}).get('html_lang', 'en')
    return render_template("index.html", lang=langue_select, store_build=STORE_BUILD, app_version=APP_VERSION)


# Packaging smoke test: no web browser, listening socket, tray or game tracking.
if getattr(sys, 'frozen', False) and len(sys.argv) == 3 and sys.argv[1] == '--distribution-smoke-test':
    import json
    import tempfile
    from pathlib import Path
    from unittest.mock import patch
    from PIL import ImageDraw, ImageFont
    from application import online_leaderboard, ocr_runner, store_smoke
    with app.test_client() as client:
        response = client.get('/')
        result = {'status': response.status_code, 'application_version': APP_VERSION,
                  'version_matches_interface': APP_VERSION.encode('utf-8') in response.data,
                  'steam_ping_store_no_elevation': store_smoke.ping_without_elevation(peer_tracking),
                  'tesseract': os.path.isfile(path_to_tesseract),
                  'interface': b'id="game_language"' in response.data and response.status_code == 200,
                  'store_mode': b'data-store-build="true"' in response.data,
                  'legacy_leaderboard_disabled': client.get('/syncMulti').status_code == 404,
                  'steam_login_route': client.post('/online-leaderboard/steam-login').status_code == 503,
                  'production_leaderboard': online_leaderboard._base_url() == 'https://eldenringpvp.com',
                  'store_distribution_marker': online_leaderboard.STORE_BUILD}
        # Exercise the bundled OCR subprocess and its positioned-text output on
        # a synthetic image, without capturing the screen or using game data.
        try:
            sample = Image.new('RGB', (300, 90), 'white')
            ImageDraw.Draw(sample).text((15, 15), 'TEST', fill='black', font=ImageFont.load_default(size=42))
            text = ocr_runner.image_to_string(sample, lang='eng', config='--psm 6 --oem 1')
            positions = ocr_runner.image_to_data(sample, lang='eng', config='--psm 6 --oem 1')
            result['optimized_ocr'] = 'TEST' in text and 'TEST' in positions.get('text', [])
        except Exception:
            result['optimized_ocr'] = False
        with patch.object(online_leaderboard, '_call', return_value={'entries': []}) as leaderboard_call:
            leaderboard_response = client.get('/online-leaderboard/entries?mode=Arena')
        result['leaderboard_route'] = leaderboard_response.status_code == 200 and leaderboard_call.called
        # A Store package must ignore legacy development configuration and
        # never attach credentials to another origin. The fixture is isolated.
        with tempfile.TemporaryDirectory(prefix='tracker-store-routing-') as directory:
            (Path(directory) / 'leaderboard-config.json').write_text(
                json.dumps({'environment': 'development', 'urls': {'development': 'http://127.0.0.1:8000'}}),
                encoding='utf-8')
            with patch.object(online_leaderboard, 'data_dir', return_value=Path(directory)):
                result['production_ignores_local_config'] = online_leaderboard._base_url() == 'https://eldenringpvp.com'
                with patch.object(online_leaderboard, 'build_opener') as opener:
                    try:
                        online_leaderboard._call('GET', '/api/v1/leaderboards', root='http://127.0.0.1:8000')
                    except RuntimeError as error:
                        result['other_origin_blocked'] = str(error) == 'server_not_allowed' and not opener.called
                    else:
                        result['other_origin_blocked'] = False
    with open(sys.argv[2], 'w', encoding='utf-8') as output:
        json.dump(result, output)
    sys.exit(0 if all(result.values()) else 1)


# Vérifier si le port 5000 est déjà utilisé
def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

app_started = False
print("Initialization. . .")
if is_port_in_use(5000):
    print("app already launched")
    url = 'http://localhost:5000/'
    webbrowser.open_new(url)
    app_started = False
else: 
    app_started = True
    url = 'http://localhost:5000/'
    if __name__ == '__main__':
        store_update.check_at_start()
    print("app ready")


def start_flask():
    print("start serveur")
    # POUR PASSER EN MODE DEV
    # app.run(debug=False)

    # POUR PASSER SUR UN SERVEUR WSGI
    serve(app, _quiet=True, listen='127.0.0.1:5000', max_request_body_size=2 * 1024 * 1024)


def open_initial_browser():
    # A previously open tab can reconnect once the server is listening.
    if not tray_navigation.wait_for_tab(6):
        interface_mode.open_interface(interface_url)
    


def stop_flask(icon):
    print("Exit")
    functions.flush_notification_sample()
    icon.stop()
    os._exit(0)
    
@app.route("/exit", methods={"POST"})
def exit():
    global icon
    stop_flask(icon)

    
flask_thread = threading.Thread(target=start_flask)     
if __name__ == '__main__' and app_started == True:
    alias_socket = None
    try:
        alias_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        alias_socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        alias_socket.bind(('127.0.0.1', 80))
        alias_socket.listen(128)
        alias_server = create_server(app, map={}, sockets=[alias_socket], max_request_body_size=2 * 1024 * 1024)
        interface_url = 'http://elden-tracker.localhost/'
        threading.Thread(target=alias_server.run, name='local-alias-server', daemon=True).start()
    except OSError:
        if alias_socket is not None:
            alias_socket.close()
        interface_url = 'http://elden-tracker.localhost:5000/'
    if not store_update.is_required():
        try:
            from contextlib import closing
            from application import detection_history
            with closing(detection_history._connect()):
                pass  # Apply history privacy migrations before serving requests.
        except Exception:
            app.logger.exception('Unable to migrate Steam history privacy')
        try:
            retention.cleanup(init.database_capture, retention.load(), secur.decrypt_value)
            functions.session_summary = functions.SessionSummary(functions._latest_saved_capture())
        except Exception:
            app.logger.exception('Unable to apply retention settings')
        try:
            usage_metrics.start()
        except Exception:
            app.logger.exception('Unable to start local usage metrics')
        try:
            first_run.finish()
        except Exception:
            first_run.report_fatal(traceback.format_exc())
        from application import tracker_presence
        tracker_presence.start(lambda: bool(functions.run_monitor))
        from application import error_reports
        error_reports.start()
        online_leaderboard.start_sync()
        online_leaderboard.start_periodic_sync()
        auto_tracking.start_worker(app, functions)
        steam_log_auto.start_worker(peer_tracking.enabled)
        try:
            from application import tracker_overlay
            tracker_overlay.start(functions)
        except Exception:
            app.logger.exception('Unable to start tracker overlay')
    flask_thread.start()
    threading.Thread(target=open_initial_browser, name='initial-browser', daemon=True).start()
    start_pystray()



# Version : 1.0.0.0
# CompanyName: Baiawai Dev
# FileDescription: EldenRing game tracker
# InternalName: Eldenring tracker
# LegalCopyright: © Baiawai Dev. All rights reserved.
# OriginalFilename: EldenRingTracker.exe
# ProductName: EldenRing Tracker
