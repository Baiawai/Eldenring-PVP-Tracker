import threading
from flask import Flask, abort, render_template, request
import webbrowser
import os
import ctypes
import socket
import pystray
from PIL import Image
from application.runtime_paths import tesseract_path, RESOURCE_DIR, FROZEN
from application.version import APP_VERSION
from application.local_security import is_allowed_request
import threading
from waitress import serve
import sys

os.environ['TESSDATA_PREFIX'] = str(RESOURCE_DIR / 'locales' / 'tessdata')



print("=====================================")
print(" ELDENRING TRACKER ")
print("=====================================")
print(f"version: {APP_VERSION}")
print("-------------")
print("Date : 26/02/2023")
print("Dev by : Baiawai")
print("Official web site : https://www.eldenring-tracker.com/")
print("=====================================")
# Creation de l'app 
app = Flask(__name__)

@app.before_request
def restrict_local_requests():
    if not is_allowed_request(request.host, request.headers.get('Origin'),
                              request.headers.get('Referer'), request.headers.get('Sec-Fetch-Site')):
        abort(403)



from application import init
from application import functions
from application import multi
from application import secur
from application import players
from application import metrics_routes
from application import usage_metrics
from application import auto_tracking
from application import retention
from application import steam_log_auto, peer_tracking
from application import history_archives

from application.init import get_selected_language, elden_counter_dir_path
from application.ui_localization import packs


# POUR LE NO CONSOLE 
# sys.stdout = sys.stderr = open(os.devnull, 'w') 
server = None

current_folder = os.path.dirname(os.path.abspath(__file__))
static_folder = os.path.join(current_folder, "static")
icon_path = os.path.join(static_folder, "tracker-eye.ico")  
image = Image.open(icon_path)



 
def tray_text(index, fallback):
    def label(item):
        language = get_selected_language()
        legacy = packs().get(language, {}).get('legacy', [])
        return legacy[index] if len(legacy) > index else fallback
    return label


def open_tracker(icon, item):
    webbrowser.open_new('http://localhost:5000/')


def open_statistics(icon, item):
    webbrowser.open_new('http://localhost:5000/#statistics')


def open_settings(icon, item):
    webbrowser.open_new('http://localhost:5000/#settings')


def open_data_folder(icon, item):
    os.startfile(elden_counter_dir_path)


def data_folder_label(item):
    language = get_selected_language()
    return packs().get(language, {}).get('modern', {}).get('environment_data_path', 'Dossier des données')


def quit_tracker(icon, item):
    stop_flask(icon)


icon = pystray.Icon("EldenRingPvPTracker", image, "Elden Ring PvP Tracker", menu=pystray.Menu(
    pystray.MenuItem("Elden Ring PvP Tracker", open_tracker, default=True),
    pystray.MenuItem(tray_text(83, 'Statistiques'), open_statistics),
    pystray.MenuItem(tray_text(4, 'Paramètres'), open_settings),
    pystray.MenuItem(data_folder_label, open_data_folder),
    pystray.Menu.SEPARATOR,
    pystray.MenuItem(tray_text(62, 'Quitter le tracker'), quit_tracker)
))
 
def start_pystray():
    icon.run()


path_to_tesseract = tesseract_path()
    
@app.route("/")
def index():
    autor = False
    if os.path.exists(path_to_tesseract):
            autor = True
    else:
            autor = False
    if autor:
        langue_select = get_selected_language()
        if langue_select == "fra":
            langue_select= "fr"
        if langue_select == "eng":
            langue_select= "en"
        elif langue_select != "fr":
            from application.ui_localization import packs
            langue_select = packs().get(langue_select, {}).get('html_lang', 'en')
        return render_template("index.html", lang = langue_select, store_build=FROZEN, app_version=APP_VERSION)
    else:
        url = 'https://github.com/UB-Mannheim/tesseract/wiki'
        version = ctypes.sizeof(ctypes.c_voidp) 
        if version == 8:
            version = "64bits"
        if version == 4:
            version = "32bits"
        return render_template("tesseract_error.html", version = version, url = url)


# Packaging smoke test: no web browser, listening socket, tray or game tracking.
if getattr(sys, 'frozen', False) and len(sys.argv) == 3 and sys.argv[1] == '--distribution-smoke-test':
    import json
    with app.test_client() as client:
        response = client.get('/')
        result = {'status': response.status_code, 'tesseract': os.path.isfile(path_to_tesseract),
                  'interface': b'tesseract_error' not in response.data and response.status_code == 200,
                  'store_mode': b'data-store-build="true"' in response.data,
                  'leaderboard_disabled': client.get('/syncMulti').status_code == 404}
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
    webbrowser.open_new(url)
    print("app ready")


def start_flask():
    print("start serveur")
    # POUR PASSER EN MODE DEV
    # app.run(debug=False)

    # POUR PASSER SUR UN SERVEUR WSGI
    serve(app, _quiet=True, listen='127.0.0.1:5000')
    


def stop_flask(icon):
    print("Exit")
    functions.flush_notification_sample()
    icon.stop()
    os._exit(0)
    
@app.route("/exit", methods={"GET"})
def exit():
    global icon
    stop_flask(icon)

    
flask_thread = threading.Thread(target=start_flask)     
if __name__ == '__main__' and app_started == True:
    try:
        retention.cleanup(init.database_capture, retention.load(), secur.decrypt_value)
        functions.session_summary = functions.SessionSummary(functions._latest_saved_capture())
    except Exception:
        app.logger.exception('Unable to apply retention settings')
    try:
        usage_metrics.start()
    except Exception:
        app.logger.exception('Unable to start local usage metrics')
    auto_tracking.start_worker(app, functions)
    steam_log_auto.start_worker(peer_tracking.enabled)
    flask_thread.start()
    start_pystray()



# Version : 1.0.0.0
# CompanyName: Baiawai Dev
# FileDescription: EldenRing game tracker
# InternalName: Eldenring tracker
# LegalCopyright: © Baiawai Dev. All rights reserved.
# OriginalFilename: EldenRingTracker.exe
# ProductName: EldenRing Tracker
