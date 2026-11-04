from flask import Flask, jsonify, request
import sqlite3
import re
import os
import wmi
import pythoncom
import ctypes
import platform
from __main__ import app
from application.secur import app_insert, app_get, renderArray




appdata_path = os.getenv("APPDATA")
elden_counter_dir_name = "hid_el_cou"
elden_counter_dir_path = os.path.join(appdata_path, elden_counter_dir_name)
if not os.path.exists(elden_counter_dir_path):
    os.makedirs(elden_counter_dir_path)
    
database_user = os.path.join(elden_counter_dir_path, "database_user.db")
database_capture = os.path.join(elden_counter_dir_path, "database_capture.db")
database_multi = os.path.join(elden_counter_dir_path, "database_multi.db")
database_setting = os.path.join(elden_counter_dir_path, "database_setting.db")





def verifyIdentity():
    system_info = platform.uname()
    pythoncom.CoInitialize()
    try:
        c = wmi.WMI()
        adapter = c.Win32_NetworkAdapterConfiguration(IPEnabled=True)[0]
        mac_address = adapter.MACAddress
    finally:
        pythoncom.CoUninitialize()
    macId = app_insert(".".join([mac_address, system_info.node])).decode("utf-8")
    
    con = sqlite3.connect(database_user) 
    cursor = con.cursor()
    cursor.execute("SELECT * FROM tabel_user")
    result = cursor.fetchall()
    delet_file = False
    
    if str(result) != "[]":  
        user =  checkUser()[0]
        user_macID = user[8]
       
        if app_get(macId).decode("utf-8") != user_macID: 
            delet_file = True
    else:
            delet_file = True   
    
    if delet_file == True:
            base_dir = os.path.dirname(os.path.abspath(__file__))
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






def con_user():
    return sqlite3.connect(database_user)

def con_captures():
    return sqlite3.connect(database_capture)

def con_multi():
    return sqlite3.connect(database_multi)

def con_setting():
    return sqlite3.connect(database_setting)

def creat_table():
    cursor = con_user().cursor()
    cursor.execute("CREATE TABLE tabel_user (id INTEGER PRIMARY KEY, name TEXT, victory TEXT, defeat TEXT, egality TEXT, language TEXT, base64 TEXT, ratio TEXT, macId TEXT, combats TEXT, noResult TEXT, fight_exit TEXT, abandon TEXT, maxVictory TEXT, maxDefeat TEXT, ratioTime TEXT, score TEXT, connexionError TEXT, gameExit TEXT, userLevel TEXT)")
    con_user().commit()
    con_user().close()
    
    cursor = con_captures().cursor()
    cursor.execute("CREATE TABLE tabel_captures (id INTEGER PRIMARY KEY, name TEXT, victory BOOL, defeat BOOL, egality BOOL, time TEXT, date TEXT, mode TEXT, base64 TEXT)")
    con_captures().commit()
    con_captures().close()
    
    cursor = con_multi().cursor()
    cursor.execute("CREATE TABLE table_multi (id INTEGER PRIMARY KEY, number TEXT, name TEXT, victory TEXT, defeat TEXT, egality TEXT, language TEXT, ratio TEXT, base64 TEXT, macId TEXT, combats TEXT, noResult TEXT, fight_exit TEXT, abandon TEXT, maxVictory TEXT, maxDefeat TEXT, ratioTime TEXT, score NUMBER, userLevel TEXT, connexionError TEXT, gameExit TEXT)")
    con_multi().commit()
    con_multi().close()
    
    cursor = con_setting().cursor()
    cursor.execute("CREATE TABLE table_setting (id INTEGER PRIMARY KEY, resolutionHeight TEXT, resolutionWidth TEXT, scale TEXT, topCustom TEXT, bottomCustom TEXT, autoStart BOOL, apiLink TEXT, apiDont TEXT)")
    con_multi().commit()
    con_multi().close()


con = sqlite3.connect(database_user)
cursor = con.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tabel_user'")
tables = cursor.fetchall()

if not any(table[0] == 'tabel_user' for table in tables):
    creat_table()


def updateSetting(resolutionHeight, resolutionWidth, scale, topCustom, bottomCustom, autoStart):
    
    con = sqlite3.connect(database_setting) 
    cursor = con.cursor()
    cursor.execute("SELECT * FROM table_setting")
    result = cursor.fetchall()
        
    sql = "UPDATE table_setting SET resolutionHeight = ?, resolutionWidth = ?, scale = ?, topCustom = ?, bottomCustom = ?, autoStart = ? WHERE id = ?"
    val = (resolutionHeight, resolutionWidth, scale, topCustom, bottomCustom, autoStart, 1)
    con = sqlite3.connect(database_setting)
    cur = con.cursor()
    cur.execute(sql, val)
    con.commit()
    
    
    return "ok"
def checkSetting():
    con = sqlite3.connect(database_setting) 
    cursor = con.cursor()
    cursor.execute("SELECT * FROM table_setting")
    result = cursor.fetchall()
   
    
    if str(result) == "[]":
        resolutionHeight = 0
        resolutionWidth = 0
        scale = 0
        topCustom = 0
        bottomCustom = 0
        autoStart = False
        # print(app_insert('ⓔ ⒺDontTOucheMePLs♇'))
        apiLink = "gAAAAABj8NV_fo5djmUw14TXgQfaKmYdMAkZea7OVq3MVKQJ9xNISzwwb61c64RmrFEq1enXhij3RDra3ucmnA6j0J8xdnnw-6_oP02Ue7VZ0USI003ASJIfMkNG_FDxg35BksVz3GwR3cn4nCzP45k7XT5bCpCdfogLtLlmCWtki2UlCUstQjI="
        apiDont = "gAAAAABj8WSZN4uMMDsOI6Mt_7IXReqSXoAp3jF_Vpr4voHsSmjdM_iF73O0z5A_WSemQIGpjQlhM8CQBAD5FsD2WNgOgPDxGgw_B6QP7nj1-uDRWdiLQV0="
        sql = "INSERT INTO table_setting (id, resolutionHeight, resolutionWidth, scale, topCustom, bottomCustom, autoStart, apiLink, apiDont) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
        val = (1, resolutionHeight, resolutionWidth, scale, topCustom, bottomCustom, autoStart, apiLink, apiDont)
        con = sqlite3.connect(database_setting)
        cur = con.cursor()
        cur.execute(sql, val)
        con.commit()
    
    con = sqlite3.connect(database_setting)
    cur = con.cursor()
    cur.execute("SELECT * FROM table_setting")
    resulta = cur.fetchall()
    
    return resulta

def checkUser():
    
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
        val = ( app_insert(name), app_insert(victory), app_insert(defeat), app_insert(egality), app_insert(language), app_insert(base64), app_insert(ratio), app_insert(macId), app_insert(combats), app_insert(noResult), app_insert(fight_exit), app_insert(abandon), app_insert(maxVictory), app_insert(maxDefeat), app_insert(ratioTime), app_insert(score), app_insert(connexionError), app_insert(gameExit), app_insert(userLevel))
        con = sqlite3.connect(database_user)
        cur = con.cursor()
        cur.execute(sql, val)
        con.commit()
        base_dir = os.path.dirname(os.path.abspath(__file__))
        path_exemple_template = os.path.join(base_dir, 'template_notif.jpg') 
       
        if os.path.exists(path_exemple_template) == True:
            os.remove(path_exemple_template)
   
    con = sqlite3.connect(database_user)
    cur = con.cursor()
    cur.execute("SELECT * FROM tabel_user")
    result = cur.fetchall()
    
    return renderArray(result)


def langue_selected():
    con = sqlite3.connect(database_user)
    cur = con.cursor()
    cur.execute("SELECT * FROM tabel_user")
    result = cur.fetchall()
    
    if str(result) != "[]":
        return app_get(result[0][5]).decode("utf-8")
    else:
        return 0
    
def update_language(language_selected):
    sql = "UPDATE tabel_user SET language = ? WHERE id = ?"
    val = (app_insert(language_selected), 1)
    con = sqlite3.connect(database_user)
    cur = con.cursor()
    cur.execute(sql, val)
    con.commit()



def addScore(victory, defeat, egality, combats, noResult, fight_exit, abandon, connexionError, gameExit):
    con = sqlite3.connect(database_user) 
    cursor = con.cursor()
    cursor.execute("SELECT * FROM tabel_user")
    result = cursor.fetchall()
    result = renderArray(result)[0]
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
    val = (app_insert(new_victory), app_insert(new_defeat), app_insert(new_egality), app_insert(new_ration), app_insert(new_combats), app_insert(new_noResult), app_insert(new_fight_exit), app_insert(new_abandon), app_insert(new_maxVictory), app_insert(new_maxDefeat), app_insert(new_score), app_insert(new_connexionError), app_insert(new_gameExit), 1)
    con = sqlite3.connect(database_user)
    cur = con.cursor()
    cur.execute(sql, val)
    con.commit()
    
@app.route("/allCapturesChart", methods={"GET"})
def allCapturesChart():

    con = sqlite3.connect(database_capture)
    cur = con.cursor()
    cur.execute("SELECT id, name, victory, defeat, egality, time, date, mode FROM tabel_captures")
    result = cur.fetchall()
    
    captures = renderArray(result)
    selected_mode = request.args.get('mode')
    if selected_mode in ('Arena', 'Invasion', 'Defense'):
        captures = [capture for capture in captures if capture[7] == selected_mode]
    return jsonify({"request": "success", "captures": captures})    
    
@app.route("/allCaptures", methods={"GET"})
def allCaptures():

    con = sqlite3.connect(database_capture)
    cur = con.cursor()
    cur.execute("SELECT * FROM tabel_captures")
    result = cur.fetchall()
   
    captures = renderArray(result)
    selected_mode = request.args.get('mode')
    if selected_mode in ('Arena', 'Invasion', 'Defense'):
        captures = [capture for capture in captures if capture[7] == selected_mode]
    return jsonify({"request": "success", "captures": captures})

def checkCaptures(space, captur_send):

    con = sqlite3.connect(database_capture)
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM tabel_captures")
    count = cur.fetchone()
   
    space_ligne = space
    actual_offset = count[0] - (space * captur_send)
 
    if actual_offset < 0:
        actual_offset = 0
        space_ligne = count[0] - (space * (captur_send - 1))
    con = sqlite3.connect(database_capture)
    cur = con.cursor()
    cur.execute("SELECT * FROM tabel_captures LIMIT "+str(space_ligne)+" OFFSET "+str(actual_offset))
    result = cur.fetchall()
    
    
    return [renderArray(result), space, count]

 
def addCapture(name, victory, defeat, egality, time, date, mode, base64):
    
    sql = "INSERT INTO tabel_captures (name, victory, defeat, egality, time, date, mode, base64) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
    val = (app_insert(name), app_insert(victory), app_insert(defeat), app_insert(egality), app_insert(time), app_insert(date), app_insert(mode), app_insert(base64))
    con = sqlite3.connect(database_capture)
    cur = con.cursor()
    cur.execute(sql, val)
    con.commit()
    
    return "ok"



@app.route("/addUser", methods={"POST"})
def addUser():
    pseudo_select = request.form.get("pseudo")
    if len(pseudo_select) >= 3 and len(pseudo_select) <= 21 and bool(re.match('^[a-zA-Z0-9]+$', pseudo_select)):
        

            sql = "UPDATE tabel_user SET name = ? WHERE id = ?"
            val = (app_insert(pseudo_select), 1)
            con = sqlite3.connect(database_user)
            cur = con.cursor()
            cur.execute(sql, val)
            con.commit()

            return jsonify({"request": "success", "pseudo": pseudo_select})
    else:  
        return jsonify({"request": "error"})
      
   
  

def addImgUser(img_b64):
    
            sql = "UPDATE tabel_user SET base64 = ? WHERE id = ?"
            val = (app_insert(img_b64), 1)
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

            
def addLVLUser(img_b64):
    
            sql = "UPDATE tabel_user SET userLevel = ? WHERE id = ?"
            val = (app_insert(img_b64), 1)
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
        
    return app_get(result[0][7]) 


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




def initSetting():

    settings = checkSetting()[0]
  
    
    user32 = ctypes.windll.user32
    width = user32.GetSystemMetrics(0)
    height = user32.GetSystemMetrics(1)
    updateSetting(height, width, get_zoom_level(), settings[4], settings[5], settings[6])
    settings = checkSetting()[0]
    
        
    return settings


