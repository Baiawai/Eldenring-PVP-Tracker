from flask import Flask, jsonify, request
import sqlite3
from __main__ import app
import os
import json
import requests
import time
from application import usage_metrics


import base64
from application.init import load_user, load_settings
from application.secur import encrypt_value, decrypt_value, decrypt_rows
from application.runtime_paths import FROZEN, data_dir

database_multi = str(data_dir() / "database_multi.db")



def _sync_leaderboard_data():
        if FROZEN:
            return False
        setting = load_settings()[0]
        url = decrypt_value(setting[7]).decode("utf-8")
        con = sqlite3.connect(database_multi)
        cur = con.cursor()
        cur.execute("SELECT * FROM table_multi WHERE macId != ''")
        payload = cur.fetchall()
        payload = decrypt_rows(payload)
       
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
                          
                            number_position = encrypt_value(1)
                            user_name = encrypt_value(item["user_name"])
                            victory = encrypt_value(item["victory"])
                            defeat = encrypt_value(item["defeat"])
                            egality = encrypt_value(item["egality"])
                            language = encrypt_value(item["language"])
                            ratio = encrypt_value(item["ratio"])
                            base64 = encrypt_value(item["base64"])
                            combats = encrypt_value(item["combats"])
                            noResult = encrypt_value(item["noResult"])
                            fightExit = encrypt_value(item["fightExit"])
                            abandon = encrypt_value(item["abandon"])
                            maxVictory = encrypt_value(item["maxVictory"])
                            maxDefeat = encrypt_value(item["maxDefeat"])
                            ratioTime = encrypt_value(item["ratioTime"])
                            score = float(item["score"])
                            connexionError = encrypt_value(str(item["connexionError"]))
                            gameExit = encrypt_value(str(item["gameExit"]))
                            
                            userLevel = encrypt_value(item["userLevel"])

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
   

def sync_leaderboard_data():
    if FROZEN:
        return False
    started = time.monotonic()
    success = False
    try:
        success = _sync_leaderboard_data()
        return success
    finally:
        usage_metrics.record_sync(time.monotonic() - started, bool(success))


@app.route("/syncMulti", endpoint="syncMulti", methods={"GET"})
def sync_leaderboard():
    if FROZEN:
        return jsonify({'request': 'error', 'reason': 'leaderboard_unavailable'}), 404
    user = load_user()[0]
    con = sqlite3.connect(database_multi) 
    cursor = con.cursor()
    cursor.execute("SELECT macId FROM table_multi WHERE macId != ''")
    result = cursor.fetchall()
    
    
    if user[1] != "" and user[6] != " ":
        if str(result) == "[]":
          
            # id , name , victory , defeat , egality , language , base64 , ratio , macId , combats , noResult , fight_exit , abandon , maxVictory , maxDefeat , ratioTime , score 
            name = encrypt_value(user[1]).decode("utf-8")
            victory = encrypt_value(user[2]).decode("utf-8")
            defeat = encrypt_value(user[3]).decode("utf-8")
            egality = encrypt_value(user[4]).decode("utf-8")
            language = encrypt_value(user[5]).decode("utf-8")
            base64 = encrypt_value(user[6]).decode("utf-8")
            ratio = encrypt_value(user[7]).decode("utf-8")
            macId = encrypt_value(user[8]).decode("utf-8")
            combats = encrypt_value(user[9]).decode("utf-8")
            noResult = encrypt_value(user[10]).decode("utf-8")
            fight_exit = encrypt_value(user[11]).decode("utf-8")
            abandon = encrypt_value(user[12]).decode("utf-8")
            maxVictory = encrypt_value(user[13]).decode("utf-8")
            maxDefeat = encrypt_value(user[14]).decode("utf-8")
            ratioTime = encrypt_value(user[15]).decode("utf-8")
            score = float(user[16])
            connexionError = encrypt_value(user[17]).decode("utf-8")
            gameExit = encrypt_value(user[18]).decode("utf-8")
            userLevel = encrypt_value(user[19]).decode("utf-8")
            sql = "INSERT INTO table_multi ( number, name, victory, defeat, egality, language, base64, ratio, macId, combats , noResult , fight_exit , abandon , maxVictory , maxDefeat , ratioTime , score, userLevel, connexionError, gameExit) VALUES ( ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            val = ( encrypt_value(1).decode("utf-8"), name, victory, defeat, egality, language, base64, ratio, macId, combats ,noResult ,fight_exit ,abandon ,maxVictory ,maxDefeat ,ratioTime ,score, userLevel, connexionError, gameExit)
            con = sqlite3.connect(database_multi)
            cur = con.cursor()
            cur.execute(sql, val)
            con.commit()
        else:
            name = encrypt_value(user[1]).decode("utf-8")
            victory = encrypt_value(user[2]).decode("utf-8")
            defeat = encrypt_value(user[3]).decode("utf-8")
            egality = encrypt_value(user[4]).decode("utf-8")
            language = encrypt_value(user[5]).decode("utf-8")
            base64 = encrypt_value(user[6]).decode("utf-8")
            ratio = encrypt_value(user[7]).decode("utf-8")
            combats = encrypt_value(user[9]).decode("utf-8")
            noResult = encrypt_value(user[10]).decode("utf-8")
            fight_exit = encrypt_value(user[11]).decode("utf-8")
            abandon = encrypt_value(user[12]).decode("utf-8")
            maxVictory = encrypt_value(user[13]).decode("utf-8")
            maxDefeat = encrypt_value(user[14]).decode("utf-8")
            ratioTime = encrypt_value(user[15]).decode("utf-8")
            score = float(user[16])
            connexionError = encrypt_value(user[17]).decode("utf-8")
            gameExit = encrypt_value(user[18]).decode("utf-8")
            userLevel = encrypt_value(user[19]).decode("utf-8")
            
          
        
            sql = "UPDATE table_multi SET name = ?, victory = ?, defeat = ?, egality = ?, ratio = ?, language = ?, base64 = ?, combats = ?, noResult = ?, fight_exit = ?, abandon = ?, maxVictory = ?, maxDefeat = ?, ratioTime = ?, score = ?, userLevel = ?, connexionError = ?, gameExit = ?  WHERE macId = ?"
            val = (name, victory, defeat, egality, ratio, language, base64, combats, noResult, fight_exit, abandon, maxVictory, maxDefeat, ratioTime, score, userLevel, connexionError, gameExit, result[0][0])
            con = sqlite3.connect(database_multi)
            cur = con.cursor()
            cur.execute(sql, val)
            con.commit()
            
        online = sync_leaderboard_data()
        con = sqlite3.connect(database_multi) 
        cursor = con.cursor()
        cursor.execute("SELECT * FROM table_multi ORDER BY score DESC")
        
        result = cursor.fetchall()
  

        return jsonify({"request": "success", "datas": decrypt_rows(result), "online": online})
    else :
        return jsonify({"request": "error"})





