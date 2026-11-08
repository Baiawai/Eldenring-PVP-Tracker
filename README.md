# Elden Ring PvP Tracker

Elden Ring PvP Tracker est une application Windows locale qui suit les combats PvP à partir des notifications affichées dans le jeu. Son interface s'ouvre dans le navigateur et les données sont conservées sur le PC. Version actuelle : **1.0.3.0**.

## Fonctionnalités

- Suivi séparé de l'arène 1v1, des invasions et des défenses lorsque votre monde est envahi. Les égalités concernent uniquement l'arène.
- Statistiques, captures de résultat, historique des événements et liste des joueurs rencontrés.
- Profil de personnage avec pseudo, niveau, image et légende ; volet de session et dernier combat.
- Détection des joueurs et informations réseau disponibles via Steam, avec accès aux profils Steam lorsque ceux-ci sont identifiés.
- Interface et reconnaissance des messages dans les langues prises en charge par le jeu.

La reconnaissance utilise l'OCR et ne peut lire que les notifications visibles. Un texte ou un nom peut être mal reconnu ; un personnage et un compte Steam ne sont pas nécessairement associés. Le classement en ligne est facultatif et sa disponibilité ne conditionne pas les statistiques locales.

## Installation de la version de développement

### Prérequis

- Windows, Elden Ring et Steam pour le suivi en jeu.
- Python 3.15 64 bits pour lancer le projet depuis ses sources.
- Tesseract OCR installé dans `C:\Program Files\Tesseract-OCR\tesseract.exe`. Les modèles OCR utilisés par le projet se trouvent dans `application/locales/tessdata/`.

Depuis PowerShell, à la racine du projet :

```powershell
py -3.15 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\Lancer le tracker.bat
```

Le lanceur utilise `.venv` et ouvre normalement [localhost:5000](http://localhost:5000/). Le serveur écoute uniquement sur `127.0.0.1:5000`. Si le tracker tourne déjà, utilisez sa page existante ou l'icône dans la zone de notification. Pour afficher les messages du programme dans une console :

```powershell
.\.venv\Scripts\python.exe ELDENRING_Tracker.py
```

Un environnement virtuel dépend de l'installation Python et de son chemin : recréez `.venv` après avoir déplacé le projet sur un autre PC.

## Démarrer le suivi

1. Lancez le tracker et Elden Ring.
2. Dans **Configuration**, choisissez la langue utilisée dans le jeu. Elle adapte l'interface et la reconnaissance, sans modifier la langue du jeu.
3. Cliquez sur **Start** et gardez le jeu visible au premier plan pour que les notifications puissent être capturées. **Stop** arrête le suivi.
4. Consultez les captures, les statistiques, les joueurs et l'historique depuis le menu. La session affichée dans le volet repart de zéro au prochain démarrage du suivi.

### Capture et reconnaissance

Dans **Configuration → Capture**, la détection automatique de la zone de notification est active par défaut. Elle cherche les messages reconnus et prévoit une hauteur suffisante pour deux lignes ; si elle ne peut pas situer le message, elle analyse la zone centrale de l'image. Vous pouvez verrouiller une zone vérifiée, puis la déverrouiller pour reprendre la détection, ou désactiver le mode automatique pour définir les limites manuellement.

L'aperçu et le test OCR utilisent une notification reconnue sur deux lignes. Si aucun exemple n'est disponible, démarrez le suivi et attendez une notification de ce type. Le test ne modifie pas les statistiques. Le dernier exemple est chiffré et conservé localement après le redémarrage.

L'écran contenant la fenêtre du jeu est détecté automatiquement. La reconnaissance dépend aussi de la langue sélectionnée et de la visibilité des notifications.

### Profil et connexions Steam

Dans **Configuration → Profil**, la capture du profil permet de récupérer le pseudo, le niveau et l'image en une étape. Dans Elden Ring, ouvrez le menu, puis **Configuration → Quitter la partie**, sans confirmer la sortie. Vérifiez les éléments reconnus avant de les enregistrer : l'OCR peut se tromper.

Dans **Configuration → P2P**, l'activation automatique du journal Steam est proposée par défaut. Lorsque la détection P2P est active, le tracker demande au client Steam d'activer son journal au démarrage ou après un redémarrage de Steam. Désactivez cette option pour utiliser la configuration manuelle ; la commande reste disponible dans la section P2P.

En développement, la mesure avancée du ping peut demander une autorisation administrateur Windows. Le ping Steam est utilisé lorsqu'il est disponible ; certaines connexions ne fournissent aucune mesure. Une adresse affichée peut être celle d'un relais et sa géolocalisation est indicative.

### Historique et archives

En bas de la page **Historique**, la taille correspond à l'espace alloué aux événements actifs et à leurs index lorsque SQLite fournit cette mesure ; sinon, elle est estimée à partir des données enregistrées.

Arrêtez le suivi avant de purger ou d'archiver l'historique actif. L'archivage retire les événements de la liste active et les conserve chiffrés dans la même base locale, y compris les rencontres Steam. La restauration ajoute les événements absents sans écraser les événements déjà présents et conserve l'archive.

La purge retire également les rencontres Steam de la liste active des joueurs, mais ne supprime ni les archives, ni les captures, ni les statistiques cumulées. SQLite peut réutiliser l'espace libéré sans réduire immédiatement la taille du fichier.

Les durées de conservation des captures et de l'historique Steam sont désactivées par défaut. Si vous en activez une, les anciennes données sont supprimées au démarrage. La suppression des captures peut modifier les graphiques et certaines rencontres, sans modifier les statistiques cumulées.

## Données locales et sauvegarde

Les bases SQLite de profil, configuration, captures, historique et statistiques se trouvent dans `%APPDATA%\Elden Ring PvP Tracker\`. Des images temporaires générées pendant le suivi peuvent aussi apparaître dans `application/`. Ces fichiers personnels, les journaux et les environnements virtuels sont exclus du dépôt.

Pour sauvegarder vos données, arrêtez le tracker puis copiez le dossier `%APPDATA%\Elden Ring PvP Tracker\`. Les captures et historiques peuvent contenir des pseudos et des adresses réseau : protégez vos sauvegardes avant de les partager.

Les statistiques d'utilisation sont enregistrées localement dans `usage_metrics.db`. Une session mesure la durée de fonctionnement du tracker, y compris en attente, et est mise à jour environ toutes les 30 secondes. Le diagnostic présente aussi des mesures temporaires du processus courant ; les erreurs OCR techniques ne représentent pas un taux de reconnaissance.

## Version Microsoft Store

La construction et les vérifications du package sont décrites dans [store/README.md](store/README.md). La version compilée désactive le classement distant et la mesure du ping nécessitant une élévation ; elle affiche le ping Steam lorsqu'il est disponible. Les données et l'installation du package doivent être testées séparément de la version de développement.

## Structure du projet

- `ELDENRING_Tracker.py` : serveur Flask/Waitress et icône de notification.
- `application/functions.py` : orchestration du suivi et des combats.
- `application/mode_stats.py`, `session_summary.py` : statistiques par mode et session.
- `application/detection_history.py`, `history_archives.py`, `player_sightings.py`, `players.py` : événements, archives et rencontres.
- `application/notification_region.py`, `notification_sample.py`, `profile_capture.py` : zone OCR, exemple de notification et capture du profil.
- `application/peer_tracking.py`, `steam_history.py`, `steam_overlay.py`, `steam_peers/` : informations Steam et réseau.
- `application/locales/` : messages du jeu, traductions et modèles OCR ; voir son [README](application/locales/README.md).
- `templates/index.html` et `static/` : interface et ressources.
- `tests/` : tests automatisés.

## Vérification

Depuis la racine :

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Pour un fichier JavaScript modifié, `node --check static/nom-du-fichier.js` vérifie sa syntaxe si Node est installé. Complétez par des essais de l'interface et, pour l'OCR, par une partie adaptée. Les tests qui écrivent doivent utiliser des données et un `APPDATA` isolés.

Les consignes de travail figurent dans [AGENTS.md](AGENTS.md), et les résultats et limites de l'audit dans [AUDIT.md](AUDIT.md).
