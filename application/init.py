from flask import Flask, jsonify, request
import sqlite3
import re
import os
import wmi
import pythoncom
import ctypes
import platform
from contextlib import closing
from __main__ import app
from application.secur import encrypt_value, decrypt_value, decrypt_rows
from application.runtime_paths import image_dir, initialize_data_dir




elden_counter_dir_path = str(initialize_data_dir())

database_user = os.path.join(elden_counter_dir_path, 'database_user.db')
database_capture = os.path.join(elden_counter_dir_path, 'database_capture.db')
database_multi = os.path.join(elden_counter_dir_path, "database_multi.db")
database_setting = os.path.join(elden_counter_dir_path, "database_setting.db")





def verify_identity():
    system_info = platform.uname()
    pythoncom.CoInitialize()
    try:
        c = wmi.WMI()
        adapter = c.Win32_NetworkAdapterConfiguration(IPEnabled=True)[0]
        mac_address = adapter.MACAddress
    finally:
        pythoncom.CoUninitialize()
    identity = ".".join([mac_address, system_info.node])
    macId = encrypt_value(identity).decode("utf-8")
    
    con = sqlite3.connect(database_user) 
    cursor = con.cursor()
    cursor.execute("SELECT * FROM tabel_user")
    result = cursor.fetchall()
    delet_file = False
    
    if str(result) != "[]":  
        user =  load_user()[0]
        user_macID = user[8]
       
        if decrypt_value(macId).decode("utf-8") != user_macID:
            delet_file = True
    else:
            delet_file = True   
    
    if delet_file == True:
            base_dir = str(image_dir())
            path_user_img = os.path.join(base_dir, 'user.jpg')
            path_notif_template = os.path.join(base_dir, 'template_notif.jpg') 
            path_user_panel = os.path.join(base_dir, 'user_panel.jpg')  
            path_steam = os.path.join(base_dir, 'steam.jpg')  
            path_finish_fight = os.path.join(base_dir, 'finish_.jpg')   
            path_start_fight = os.path.join(base_dir, 'start_.jpg') 
            if os.path.exists(path_finish_fight):
                os.remove(path_finish_fight)
            if os.path.exists(path_start_fight):
                os.remove(path_start_fight)
            if os.path.exists(path_steam):
                os.remove(path_steam) 
            if os.path.exists(path_notif_template):
                os.remove(path_notif_template)
            if os.path.exists(path_user_img):
                os.remove(path_user_img)
            if os.path.exists(path_user_panel):
                os.remove(path_user_panel)  
        
        
        
          
    return delet_file






def connect_user():
    return sqlite3.connect(database_user)

def connect_captures():
    return sqlite3.connect(database_capture)

def connect_multiplayer():
    return sqlite3.connect(database_multi)

def connect_settings():
    return sqlite3.connect(database_setting)

def create_tables():
    """Create missing base tables without replacing existing user data."""
    schemas = (
        (database_user, "CREATE TABLE IF NOT EXISTS tabel_user (id INTEGER PRIMARY KEY, name TEXT, victory TEXT, defeat TEXT, egality TEXT, language TEXT, base64 TEXT, ratio TEXT, macId TEXT, combats TEXT, noResult TEXT, fight_exit TEXT, abandon TEXT, maxVictory TEXT, maxDefeat TEXT, ratioTime TEXT, score TEXT, connexionError TEXT, gameExit TEXT, userLevel TEXT)"),
        (database_capture, "CREATE TABLE IF NOT EXISTS tabel_captures (id INTEGER PRIMARY KEY, name TEXT, victory BOOL, defeat BOOL, egality BOOL, time TEXT, date TEXT, mode TEXT, base64 TEXT)"),
        (database_multi, "CREATE TABLE IF NOT EXISTS table_multi (id INTEGER PRIMARY KEY, number TEXT, name TEXT, victory TEXT, defeat TEXT, egality TEXT, language TEXT, ratio TEXT, base64 TEXT, macId TEXT, combats TEXT, noResult TEXT, fight_exit TEXT, abandon TEXT, maxVictory TEXT, maxDefeat TEXT, ratioTime TEXT, score NUMBER, userLevel TEXT, connexionError TEXT, gameExit TEXT)"),
        (database_setting, "CREATE TABLE IF NOT EXISTS table_setting (id INTEGER PRIMARY KEY, resolutionHeight TEXT, resolutionWidth TEXT, scale TEXT, topCustom TEXT, bottomCustom TEXT, autoStart BOOL, apiLink TEXT, apiDont TEXT)"),
    )
    for path, sql in schemas:
        with closing(sqlite3.connect(path, timeout=10)) as con:
            with con:
                con.execute(sql)


create_tables()


def update_settings(resolutionHeight, resolutionWidth, scale, topCustom, bottomCustom, autoStart):
    sql = "UPDATE table_setting SET resolutionHeight = ?, resolutionWidth = ?, scale = ?, topCustom = ?, bottomCustom = ?, autoStart = ? WHERE id = ?"
    val = (resolutionHeight, resolutionWidth, scale, topCustom, bottomCustom, autoStart, 1)
    with closing(sqlite3.connect(database_setting)) as con:
        with con:
            con.execute(sql, val)
    return "ok"
def load_settings():
    with closing(sqlite3.connect(database_setting)) as con:
        result = con.execute("SELECT * FROM table_setting").fetchall()
   
    
    if str(result) == "[]":
        resolutionHeight = 0
        resolutionWidth = 0
        scale = 0
        topCustom = 0
        bottomCustom = 0
        autoStart = False
        # print(app_insert('ⓔ ⒺDontTOucheMePLs♇'))
        apiLink = ""
        apiDont = ""
        sql = "INSERT INTO table_setting (id, resolutionHeight, resolutionWidth, scale, topCustom, bottomCustom, autoStart, apiLink, apiDont) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
        val = (1, resolutionHeight, resolutionWidth, scale, topCustom, bottomCustom, autoStart, apiLink, apiDont)
        with closing(sqlite3.connect(database_setting)) as con:
            with con:
                con.execute(sql, val)
    
    with closing(sqlite3.connect(database_setting)) as con:
        resulta = con.execute("SELECT * FROM table_setting").fetchall()
    
    return resulta

def load_user():
    
    con = sqlite3.connect(database_user) 
    cursor = con.cursor()
    cursor.execute("SELECT * FROM tabel_user")
    result = cursor.fetchall()
   
    if str(result) == "[]":
        
        system_info = platform.uname()
        c = wmi.WMI()
        adapter = c.Win32_NetworkAdapterConfiguration(IPEnabled=True)[0]
        mac_address = adapter.MACAddress
        macId = ".".join([mac_address, system_info.node])
        
    
    
        
        name = ""
        victory = 0
        defeat = 0
        egality = 0
        ratio = 0
        language = " "
        base64 = ""
        combats = 0
        noResult = 0
        fight_exit = 0
        abandon = 0
        maxVictory = 0
        maxDefeat = 0
        ratioTime = 0
        score = 0
        connexionError = 0
        gameExit = 0
        userLevel = 0
        sql = "INSERT INTO tabel_user ( name, victory, defeat, egality, language, base64, ratio, macId, combats, noResult, fight_exit, abandon, maxVictory, maxDefeat, ratioTime, score, connexionError, gameExit, userLevel ) VALUES ( ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        val = ( encrypt_value(name), encrypt_value(victory), encrypt_value(defeat), encrypt_value(egality), encrypt_value(language), encrypt_value(base64), encrypt_value(ratio), encrypt_value(macId), encrypt_value(combats), encrypt_value(noResult), encrypt_value(fight_exit), encrypt_value(abandon), encrypt_value(maxVictory), encrypt_value(maxDefeat), encrypt_value(ratioTime), encrypt_value(score), encrypt_value(connexionError), encrypt_value(gameExit), encrypt_value(userLevel))
        con = sqlite3.connect(database_user)
        cur = con.cursor()
        cur.execute(sql, val)
        con.commit()
        base_dir = str(image_dir())
        path_exemple_template = os.path.join(base_dir, 'template_notif.jpg') 
       
        if os.path.exists(path_exemple_template) == True:
            os.remove(path_exemple_template)
   
    con = sqlite3.connect(database_user)
    cur = con.cursor()
    cur.execute("SELECT * FROM tabel_user")
    result = cur.fetchall()
    
    return decrypt_rows(result)


def get_selected_language():
    con = sqlite3.connect(database_user)
    cur = con.cursor()
    cur.execute("SELECT * FROM tabel_user")
    result = cur.fetchall()
    
    if str(result) != "[]":
        return decrypt_value(result[0][5]).decode("utf-8")
    else:
        return 0
    
def update_language(language_selected):
    sql = "UPDATE tabel_user SET language = ? WHERE id = ?"
    val = (encrypt_value(language_selected), 1)
    con = sqlite3.connect(database_user)
    cur = con.cursor()
    cur.execute(sql, val)
    con.commit()



def apply_score(victory, defeat, egality, combats, noResult, fight_exit, abandon, connexionError, gameExit):
    con = sqlite3.connect(database_user) 
    cursor = con.cursor()
    cursor.execute("SELECT * FROM tabel_user")
    result = cursor.fetchall()
    result = decrypt_rows(result)[0]
    new_victory = int(result[2]) + victory
    new_defeat = int(result[3]) + defeat
    new_egality = int(result[4]) + egality
    new_combats = int(result[9]) + combats
    if new_victory != 0 or new_defeat != 0:
        
        if new_victory != 0 or new_defeat != 0:
            if new_combats > 5000:
                new_ration = str(round(((new_victory / (new_victory + new_defeat + new_egality)) * 100), 4))
            elif new_combats > 1000:
                new_ration = str(round(((new_victory / (new_victory + new_defeat + new_egality)) * 100), 3))
            else:
                new_ration = str(round(((new_victory / (new_victory + new_defeat + new_egality)) * 100), 2))

    else:
        new_ration = int(result[7])
 
    new_noResult = int(result[10]) + noResult
    new_fight_exit = int(result[11]) + fight_exit
    new_connexionError = int(result[17]) + connexionError
    new_gameExit = int(result[18]) + gameExit
    new_abandon = new_combats - (new_victory + new_defeat + new_egality) - (new_noResult + abandon + new_fight_exit + new_connexionError + new_gameExit)
    
    if victory != 0 or defeat != 0 or egality != 0:
        new_maxVictory = 0
        if victory != 0:
            new_maxVictory = 1
            if int(result[13]) != 0:
                new_maxVictory = int(result[13]) + new_maxVictory
                
        new_maxDefeat = 0
        if defeat != 0:
            new_maxDefeat = 1
            if int(result[14]) != 0:
                new_maxDefeat = int(result[14]) + new_maxDefeat
    else:
        new_maxVictory = int(result[13])
        new_maxDefeat = int(result[14])
        
    victory_points = 3 
    defeat_points = -2 
    egality_points = 1 
    fight_exit_points = 0.5 
    abandon_points = -4 
    noResult_points = -1
    connexionError_points = 0
    gameExit_points = -1
    new_score = round((((new_victory * victory_points) + (new_defeat * defeat_points) + (new_egality * egality_points) + (new_fight_exit * fight_exit_points) + (new_abandon * abandon_points) + (new_noResult * noResult_points) + (new_gameExit * gameExit_points)) / 3) / 10, 2)
        
    sql = "UPDATE tabel_user SET victory = ?, defeat = ?, egality = ?, ratio = ?, combats = ?, noResult = ?, fight_exit = ?, abandon = ?, maxVictory = ?, maxDefeat = ?, score = ?, connexionError = ? , gameExit = ? WHERE id = ?"
    val = (encrypt_value(new_victory), encrypt_value(new_defeat), encrypt_value(new_egality), encrypt_value(new_ration), encrypt_value(new_combats), encrypt_value(new_noResult), encrypt_value(new_fight_exit), encrypt_value(new_abandon), encrypt_value(new_maxVictory), encrypt_value(new_maxDefeat), encrypt_value(new_score), encrypt_value(new_connexionError), encrypt_value(new_gameExit), 1)
    con = sqlite3.connect(database_user)
    cur = con.cursor()
    cur.execute(sql, val)
    try:
        from application.leaderboard_events import record_delta
        record_delta(con, 'Arena', (victory, defeat, egality, combats, noResult, fight_exit, abandon, connexionError, gameExit), database_setting)
    except Exception:
        app.logger.exception('Unable to queue leaderboard event')
    con.commit()
    con.close()
    
def _load_captures(selected_mode, include_images):
    """Filter encrypted modes before decrypting the potentially large images."""
    columns = '*' if include_images else 'id, name, victory, defeat, egality, time, date, mode'
    filter_mode = selected_mode in ('Arena', 'Invasion', 'Defense')
    captures = []
    with closing(sqlite3.connect(database_capture, timeout=10)) as con:
        for row in con.execute('SELECT ' + columns + ' FROM tabel_captures'):
            if filter_mode and decrypt_rows([(0, row[7])])[0][1] != selected_mode:
                continue
            captures.append(decrypt_rows([row])[0])
    return captures


@app.route("/allCapturesChart", endpoint="allCapturesChart", methods={"GET"})
def all_captures_chart():
    return jsonify({"request": "success", "captures": _load_captures(request.args.get('mode'), False)})


@app.route("/allCaptures", endpoint="allCaptures", methods={"GET"})
def all_captures():
    return jsonify({"request": "success", "captures": _load_captures(request.args.get('mode'), True)})

def get_capture_page(space, captur_send):
    with closing(sqlite3.connect(database_capture, timeout=10)) as con:
        count = con.execute("SELECT COUNT(*) FROM tabel_captures").fetchone()
        space_ligne = space
        actual_offset = count[0] - (space * captur_send)
        if actual_offset < 0:
            actual_offset = 0
            space_ligne = count[0] - (space * (captur_send - 1))
        result = con.execute("SELECT * FROM tabel_captures LIMIT ? OFFSET ?", (space_ligne, actual_offset)).fetchall()
    return [decrypt_rows(result), space, count]

 
def add_capture(name, victory, defeat, egality, time, date, mode, base64):
    
    sql = "INSERT INTO tabel_captures (name, victory, defeat, egality, time, date, mode, base64) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
    val = (encrypt_value(name), encrypt_value(victory), encrypt_value(defeat), encrypt_value(egality), encrypt_value(time), encrypt_value(date), encrypt_value(mode), encrypt_value(base64))
    with closing(sqlite3.connect(database_capture, timeout=10)) as con:
        with con:
            con.execute(sql, val)
    
    return "ok"



@app.route("/addUser", endpoint="addUser", methods={"POST"})
def update_user_name():
    pseudo_select = request.form.get("pseudo")
    if len(pseudo_select) >= 3 and len(pseudo_select) <= 21 and bool(re.match('^[a-zA-Z0-9]+$', pseudo_select)):
        

            sql = "UPDATE tabel_user SET name = ? WHERE id = ?"
            val = (encrypt_value(pseudo_select), 1)
            con = sqlite3.connect(database_user)
            cur = con.cursor()
            cur.execute(sql, val)
            con.commit()

            return jsonify({"request": "success", "pseudo": pseudo_select})
    else:  
        return jsonify({"request": "error"})
      
   
  

def update_user_image(img_b64):
    
            sql = "UPDATE tabel_user SET base64 = ? WHERE id = ?"
            val = (encrypt_value(img_b64), 1)
            con = sqlite3.connect(database_user)
            cur = con.cursor()
            cur.execute(sql, val)
            con.commit()
            
            sql = "UPDATE table_multi SET base64 = ? WHERE macId = ?"
            val = (img_b64, 1)
            con = sqlite3.connect(database_multi)
            cur = con.cursor()
            cur.execute(sql, val)
            con.commit()

            
def update_user_level(img_b64):
    
            sql = "UPDATE tabel_user SET userLevel = ? WHERE id = ?"
            val = (encrypt_value(img_b64), 1)
            con = sqlite3.connect(database_user)
            cur = con.cursor()
            cur.execute(sql, val)
            con.commit()
            
            sql = "UPDATE table_multi SET userLevel = ? WHERE macId = ?"
            val = (img_b64, 1)
            con = sqlite3.connect(database_multi)
            cur = con.cursor()
            cur.execute(sql, val)
            con.commit()



def get_ratio():
    con = sqlite3.connect(database_user)
    cur = con.cursor()
    cur.execute("SELECT * FROM tabel_user")
    result = cur.fetchall()
        
    return decrypt_value(result[0][7])


def get_zoom_level():
 
    hdc = ctypes.windll.user32.GetDC(0)
    log_pixels_x = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)
    ctypes.windll.user32.ReleaseDC(0, hdc)
    value = log_pixels_x + 5
    if value > 99 and value < 105:
       value = 100 
    if value > 119 and value < 130:
       value = 125 
    if value > 140 and value < 159:
       value = 150 
    if value > 160 and value < 179:
       value = 175 
    if value > 190 and value < 210:
       value = 200 
    if value > 240 and value < 260:
       value = 250 
    if value > 290 and value < 310:
       value = 300 
    return value




def initialize_display_settings():

    settings = load_settings()[0]
  
    
    user32 = ctypes.windll.user32
    width = user32.GetSystemMetrics(0)
    height = user32.GetSystemMetrics(1)
    update_settings(height, width, get_zoom_level(), settings[4], settings[5], settings[6])
    settings = load_settings()[0]
    
        
    return settings


