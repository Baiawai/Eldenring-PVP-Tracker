from flask import Flask, jsonify, request
import sqlite3
import re
import os
import base64
import ast
from cryptography.fernet import Fernet
from __main__ import app


key_str = '_Elden_ring_Pvp_' * 2
key_bytes = key_str.encode('utf-8')
key = base64.urlsafe_b64encode(key_bytes)
key = key.ljust(32, b'=')
   

def app_name():
    global key
    return key

def app_insert(donnees_a_chiffrer):
    fernet = Fernet(app_name())
    donnees_chiffrees = fernet.encrypt(str(donnees_a_chiffrer).encode('utf-8'))
    return donnees_chiffrees

def app_get(donnees_chiffrees):
    fernet = Fernet(app_name())
    donnees_dechiffrees = fernet.decrypt(donnees_chiffrees)
    return donnees_dechiffrees


def clean_decrypted(decoded):
    if decoded.startswith(("b'", 'b"')):
        try:
            value = ast.literal_eval(decoded)
            if isinstance(value, bytes):
                return value.decode('utf-8')
        except (ValueError, SyntaxError, UnicodeDecodeError):
            pass
    return decoded


def renderArray(Array):
    new_array = []
    for ligne in Array:
        if isinstance(ligne, (int, str)):
           
            if str(ligne).isdigit():
                new_array.append(1)
            else:
                if isinstance(ligne, float) == False and len(str(ligne)) > 10:
                    decoded = app_get(ligne).decode('utf-8')
                    cleaned = clean_decrypted(decoded)
                else:
                    cleaned = ligne
                new_array.append(cleaned)
        else:
       
            new_ligne = []
            count = 0
            for element in ligne:
                if count == 0:
                    element_decrypt = element
                else:
              
                    if element != "":
                        if isinstance(element, float) == False and len(str(element)) > 10:
                            decoded = app_get(element).decode('utf-8')
                            cleaned = clean_decrypted(decoded)
                        else:
                            cleaned = element
                        # print(cleaned)
                        element_decrypt = cleaned
                new_ligne.append(element_decrypt)
                count += 1
            new_array.append(new_ligne)
    # print(new_array)
    return new_array




