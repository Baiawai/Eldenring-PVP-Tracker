import pystray
from PIL import Image
import os
import webbrowser

base_dir = os.path.dirname(os.path.abspath(__file__))
path_icon = os.path.join(base_dir, 'baia.ico')        
image = Image.open(path_icon)
 
def after_click(icon, query):
    if str(query) == "Open Website":
        app_started = True
        url = 'http://localhost:5000/'
        webbrowser.open(url)
        print("app ready")
    elif str(query) == "Exit":
        icon.stop()
 
 
icon = pystray.Icon("GFG", image, "EldenRing PvP Counteur",
                    menu=pystray.Menu(
    pystray.MenuItem("Open Website",
                     after_click),
    pystray.MenuItem("Exit", after_click)))
 
def start_pystray():
    icon.run()
