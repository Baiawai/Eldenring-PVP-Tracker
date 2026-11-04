# Elden Ring PvP Tracker

Application Windows locale qui suit les combats PvP d’Elden Ring à partir des messages affichés à l’écran. L’interface s’ouvre dans un navigateur et les statistiques sont conservées sur le PC.

## Fonctions

- Suivi distinct de l’**Arène 1v1**, des **invasions** et des combats lorsque votre **monde est envahi**. Seule l’arène possède des égalités.
- Statistiques par mode, captures de résultat, historique des détections et joueurs rencontrés, y compris les alliés et chasseurs reconnus.
- Profil personnalisable, légende, informations de session et dernier combat dans le volet latéral.
- Détection des joueurs Steam et informations réseau disponibles, avec accès aux profils Steam. Les noms, rôles et pings ne sont affichés que lorsqu’ils peuvent être identifiés.
- Interface et reconnaissance des messages dans les langues prises en charge par le jeu. Au premier lancement, la langue du navigateur est utilisée si elle est disponible ; elle reste modifiable dans les paramètres.

La reconnaissance dépend de l’OCR et des notifications réellement visibles. Certains textes, langues ou noms peuvent être mal lus ou masqués ; les profils Steam ne sont pas automatiquement assimilés à des personnages lorsque leur correspondance n’est pas certaine. Le classement en ligne est facultatif : les statistiques locales restent utilisables si le serveur de classement est indisponible.

## Prérequis

- Windows, avec Elden Ring et Steam pour l’utilisation en jeu.
- Python 3.12 64 bits pour exécuter le projet depuis ses sources.
- Tesseract OCR installé à l’emplacement actuellement attendu par l’application : `C:\Program Files\Tesseract-OCR\tesseract.exe`. Les modèles de reconnaissance supplémentaires sont dans `application/locales/tessdata/`.

La mesure de ping utilise les composants Steam/P2P du projet et peut demander une autorisation administrateur Windows. Une adresse affichée peut être celle d’un relais ; sa géolocalisation est indicative.

## Installation et lancement

Depuis PowerShell, à la racine du projet :

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\Lancer le tracker.bat
```

Le script de lancement utilise `.venv` et ouvre normalement `http://localhost:5000/` dans le navigateur. Si le tracker tourne déjà, utilisez sa page existante ou l’icône dans la zone de notification. Pour voir les messages de diagnostic dans une console :

```powershell
.\.venv\Scripts\python.exe ELDENRING_Tracker.py
```

L’environnement virtuel existant est lié à son installation Python et à son chemin Windows : recréez-le après une copie sur un autre PC. Les bibliothèques et modèles nécessaires au code de l’application sont suivis dans le projet ; Tesseract lui-même doit être installé séparément.

## Utilisation

1. Lancez le tracker, puis Elden Ring.
2. Dans les paramètres, vérifiez que la langue choisie correspond à celle du jeu. Ce réglage adapte l’interface et l’OCR ; il ne change pas la langue d’Elden Ring.
3. Cliquez sur **Start** et gardez le jeu au premier plan pendant la détection. Configurez si nécessaire la zone des notifications et l’intervalle de capture.
4. Consultez les captures, les statistiques, les joueurs rencontrés ou l’historique dans le menu. **Stop** arrête le suivi. La session affichée dans le volet repart de zéro au prochain démarrage du suivi.

## Données locales

Les bases SQLite de profil, paramètres, captures, historique et statistiques se trouvent dans `%APPDATA%\hid_el_cou\`. Les captures temporaires et images générées pendant le suivi peuvent aussi apparaître dans `application/`. Ces fichiers personnels et les environnements virtuels sont exclus du dépôt par `.gitignore`.

Pour conserver vos données, sauvegardez le dossier `%APPDATA%\hid_el_cou\` lorsque le tracker est arrêté. Les adresses IP et informations Steam détectées peuvent faire partie de l’historique : protégez vos sauvegardes en conséquence.

## Structure du projet

- `ELDENRING_Tracker.py` : lancement du serveur Flask/Waitress et icône de notification.
- `application/functions.py` : suivi, OCR, routes et orchestration des combats.
- `application/mode_stats.py`, `session_summary.py` : statistiques par mode et session courante.
- `application/detection_history.py`, `player_sightings.py`, `players.py` : historique et rencontres.
- `application/peer_tracking.py`, `steam_history.py`, `steam_overlay.py`, `steam_peers/` : informations Steam et réseau.
- `application/locales/` : messages du jeu, traductions de l’interface et modèles OCR ; voir son [README](application/locales/README.md).
- `templates/index.html` et `static/` : interface, styles et scripts du navigateur.
- `tests/` : tests automatisés du projet.

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Pour les changements visuels ou de détection, complétez les tests automatisés par une vérification dans l’interface ou sur une partie adaptée. Les instructions de travail pour les assistants figurent dans [AGENTS.md](AGENTS.md).
