import threading
from flask import Flask, render_template, request
import webbrowser
import os
import ctypes
import socket
import pystray
from PIL import Image
import threading
from waitress import serve
import sys




print("=====================================")
print(" ELDENRING TRACKER ")
print("=====================================")
print("version: BETA")
print("-------------")
print("Date : 26/02/2023")
print("Dev by : Baiawai")
print("Official web site : https://www.eldenring-tracker.com/")
print("=====================================")
# Creation de l'app 
app = Flask(__name__)



from application import init
from application import functions
from application import multi
from application import secur
from application import players

from application.init import langue_selected


# POUR LE NO CONSOLE 
# sys.stdout = sys.stderr = open(os.devnull, 'w') 
server = None

current_folder = os.path.dirname(os.path.abspath(__file__))
static_folder = os.path.join(current_folder, "static")
icon_path = os.path.join(static_folder, "baia.ico")  
image = Image.open(icon_path)



 
def after_click(icon, query):
    if str(query) == "Open Website":
        app_started = True
        url = 'http://localhost:5000/'
        webbrowser.open_new(url)
        print("app ready")
    elif str(query) == "Exit":
        stop_flask(icon)
       
icon = pystray.Icon("GFG", image, "EldenRing PvP Counteur", menu=pystray.Menu(
    pystray.MenuItem("Open Website", after_click),
    pystray.MenuItem("Exit", after_click)
    ))
 
def start_pystray():
    icon.run()


path_to_tesseract = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
    
@app.route("/")
def index():
    autor = False
    if os.path.exists(path_to_tesseract):
            autor = True
    else:
            autor = False
    if autor:
        langue_select = langue_selected()
        if langue_select == "fra":
            langue_select= "fr"
        if langue_select == "eng":
            langue_select= "en"
        elif langue_select != "fr":
            from application.ui_localization import packs
            langue_select = packs().get(langue_select, {}).get('html_lang', 'en')
        return render_template("index.html", lang = langue_select)
    else:
        url = 'https://github.com/UB-Mannheim/tesseract/wiki'
        version = ctypes.sizeof(ctypes.c_voidp) 
        if version == 8:
            version = "64bits"
        if version == 4:
            version = "32bits"
        return render_template("tesseract_error.html", version = version, url = url)


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
    icon.stop()
    os._exit(0)
    
@app.route("/exit", methods={"GET"})
def exit():
    global icon
    stop_flask(icon)

    
flask_thread = threading.Thread(target=start_flask)     
if __name__ == '__main__' and app_started == True:
    flask_thread.start()
    start_pystray()



# Version : 1.0.0.0
# CompanyName: Baiawai Dev
# FileDescription: EldenRing game tracker
# InternalName: Eldenring tracker
# LegalCopyright: © Baiawai Dev. All rights reserved.
# OriginalFilename: EldenRingTracker.exe
# ProductName: EldenRing Tracker
