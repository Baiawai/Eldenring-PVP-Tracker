from flask import Flask, jsonify, request
import sqlite3
from __main__ import app
import os
import json
import requests


import base64
from application.init import checkUser, checkSetting
from application.secur import app_insert, app_get, renderArray

appdata_path = os.getenv("APPDATA")
elden_counter_dir_name = "hid_el_cou"
elden_counter_dir_path = os.path.join(appdata_path, elden_counter_dir_name)


database_multi = os.path.join(elden_counter_dir_path, "database_multi.db")



def checkMulti():
        setting = checkSetting()[0]
        url = app_get(setting[7]).decode("utf-8")
        con = sqlite3.connect(database_multi)
        cur = con.cursor()
        cur.execute("SELECT * FROM table_multi WHERE macId != ''")
        payload = cur.fetchall()
        payload = renderArray(payload)
       
        # if len(payload) > 0:
        #     payload = payload[0]
        # En-tête contenant le token
        # headers = {
        #     'toto': app_get(setting[8]).decode("utf-8")
        # }
        headers = {
            'toto': 'ELDENRINGTRACKER'
        }
      
      
        result = ""
      
        # Envoi de la requête POST avec la charge utile JSON et l'en-tête
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=3)
            response.raise_for_status()
        except requests.RequestException as exc:
            app.logger.warning("Multiplayer synchronization unavailable: %s", exc)
            return False
   
        if response.status_code == 200:
            if response.content.decode("utf-8") != "" and response.content.decode("utf-8") != "[]":
               
                data = response.json()
            
                con = sqlite3.connect(database_multi) 
                cursor = con.cursor()
                cursor.execute("DELETE FROM table_multi WHERE macId = ''")
                con.commit()
    
                
           
                # Boucler sur chaque élément du tableau
                if str(data) != "[[]]" and str(data) != "[]":
                    count = 0
                    for item in data:
                          
                            number_position = app_insert(1)
                            user_name = app_insert(item["user_name"])
                            victory = app_insert(item["victory"])
                            defeat = app_insert(item["defeat"])
                            egality = app_insert(item["egality"])
                            language = app_insert(item["language"])
                            ratio = app_insert(item["ratio"])
                            base64 = app_insert(item["base64"])
                            combats = app_insert(item["combats"])
                            noResult = app_insert(item["noResult"])
                            fightExit = app_insert(item["fightExit"])
                            abandon = app_insert(item["abandon"])
                            maxVictory = app_insert(item["maxVictory"])
                            maxDefeat = app_insert(item["maxDefeat"])
                            ratioTime = app_insert(item["ratioTime"])
                            score = float(item["score"])
                            connexionError = app_insert(str(item["connexionError"]))
                            gameExit = app_insert(str(item["gameExit"]))
                            
                            userLevel = app_insert(item["userLevel"])

                            sql = "INSERT INTO table_multi ( number, name, victory, defeat, egality, language, base64, ratio, macId, combats , noResult , fight_exit , abandon , maxVictory , maxDefeat , ratioTime , score, userLevel, connexionError, gameExit) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                            val = (number_position, user_name, victory, defeat, egality, language, base64, ratio, "", combats ,noResult ,fightExit ,abandon ,maxVictory ,maxDefeat ,ratioTime ,score, userLevel, connexionError, gameExit)
                            con = sqlite3.connect(database_multi)
                            cur = con.cursor()
                            cur.execute(sql, val)
                            con.commit()
                            count = count +1   
        con = sqlite3.connect(database_multi)
        cur = con.cursor()
        cur.execute("SELECT * FROM table_multi")
        result = cur.fetchall()
        
        return True
   

@app.route("/syncMulti", methods={"GET"})
def syncMulti():
    user = checkUser()[0]
    con = sqlite3.connect(database_multi) 
    cursor = con.cursor()
    cursor.execute("SELECT macId FROM table_multi WHERE macId != ''")
    result = cursor.fetchall()
    
    
    if user[1] != "" and user[6] != " ":
        if str(result) == "[]":
          
            # id , name , victory , defeat , egality , language , base64 , ratio , macId , combats , noResult , fight_exit , abandon , maxVictory , maxDefeat , ratioTime , score 
            name = app_insert(user[1]).decode("utf-8")
            victory = app_insert(user[2]).decode("utf-8")
            defeat = app_insert(user[3]).decode("utf-8")
            egality = app_insert(user[4]).decode("utf-8")
            language = app_insert(user[5]).decode("utf-8")
            base64 = app_insert(user[6]).decode("utf-8")
            ratio = app_insert(user[7]).decode("utf-8")
            macId = app_insert(user[8]).decode("utf-8")
            combats = app_insert(user[9]).decode("utf-8")
            noResult = app_insert(user[10]).decode("utf-8")
            fight_exit = app_insert(user[11]).decode("utf-8")
            abandon = app_insert(user[12]).decode("utf-8")
            maxVictory = app_insert(user[13]).decode("utf-8")
            maxDefeat = app_insert(user[14]).decode("utf-8")
            ratioTime = app_insert(user[15]).decode("utf-8")
            score = float(user[16])
            connexionError = app_insert(user[17]).decode("utf-8")
            gameExit = app_insert(user[18]).decode("utf-8")
            userLevel = app_insert(user[19]).decode("utf-8")
            sql = "INSERT INTO table_multi ( number, name, victory, defeat, egality, language, base64, ratio, macId, combats , noResult , fight_exit , abandon , maxVictory , maxDefeat , ratioTime , score, userLevel, connexionError, gameExit) VALUES ( ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            val = ( app_insert(1).decode("utf-8"), name, victory, defeat, egality, language, base64, ratio, macId, combats ,noResult ,fight_exit ,abandon ,maxVictory ,maxDefeat ,ratioTime ,score, userLevel, connexionError, gameExit)
            con = sqlite3.connect(database_multi)
            cur = con.cursor()
            cur.execute(sql, val)
            con.commit()
        else:
            name = app_insert(user[1]).decode("utf-8")
            victory = app_insert(user[2]).decode("utf-8")
            defeat = app_insert(user[3]).decode("utf-8")
            egality = app_insert(user[4]).decode("utf-8")
            language = app_insert(user[5]).decode("utf-8")
            base64 = app_insert(user[6]).decode("utf-8")
            ratio = app_insert(user[7]).decode("utf-8")
            combats = app_insert(user[9]).decode("utf-8")
            noResult = app_insert(user[10]).decode("utf-8")
            fight_exit = app_insert(user[11]).decode("utf-8")
            abandon = app_insert(user[12]).decode("utf-8")
            maxVictory = app_insert(user[13]).decode("utf-8")
            maxDefeat = app_insert(user[14]).decode("utf-8")
            ratioTime = app_insert(user[15]).decode("utf-8")
            score = float(user[16])
            connexionError = app_insert(user[17]).decode("utf-8")
            gameExit = app_insert(user[18]).decode("utf-8")
            userLevel = app_insert(user[19]).decode("utf-8")
            
          
        
            sql = "UPDATE table_multi SET name = ?, victory = ?, defeat = ?, egality = ?, ratio = ?, language = ?, base64 = ?, combats = ?, noResult = ?, fight_exit = ?, abandon = ?, maxVictory = ?, maxDefeat = ?, ratioTime = ?, score = ?, userLevel = ?, connexionError = ?, gameExit = ?  WHERE macId = ?"
            val = (name, victory, defeat, egality, ratio, language, base64, combats, noResult, fight_exit, abandon, maxVictory, maxDefeat, ratioTime, score, userLevel, connexionError, gameExit, result[0][0])
            con = sqlite3.connect(database_multi)
            cur = con.cursor()
            cur.execute(sql, val)
            con.commit()
            
        online = checkMulti()
        con = sqlite3.connect(database_multi) 
        cursor = con.cursor()
        cursor.execute("SELECT * FROM table_multi ORDER BY score DESC")
        
        result = cursor.fetchall()
  

        return jsonify({"request": "success", "datas": renderArray(result), "online": online})
    else :
        return jsonify({"request": "error"})





