# Elden Ring PvP Tracker

Elden Ring PvP Tracker est une application Windows locale qui suit les combats PvP à partir des notifications affichées dans le jeu. Son interface s'ouvre dans le navigateur et les données sont conservées sur le PC. Version en préparation : **1.0.10.0**.

## Fonctionnalités

- Suivi séparé de l'arène 1v1, des invasions et des défenses lorsque votre monde est envahi. Les égalités concernent uniquement l'arène.
- Statistiques, captures de résultat, historique des événements et liste des joueurs rencontrés.
- Profil de personnage avec pseudo, niveau, image et légende ; volet de session et dernier combat.
- Détection des joueurs et informations réseau disponibles via Steam, avec accès aux profils Steam lorsque ceux-ci sont identifiés.
- Langues de l’interface et du jeu réglables séparément. Au premier lancement, l’interface utilise la langue du navigateur si elle est disponible, sinon l’anglais. Le tracker tente de lire la langue du jeu dans la configuration Steam, sans modifier ces fichiers ; si elle est introuvable, il choisit l’anglais. Vérifiez ce réglage avant le suivi. L’interface propose aussi des langues supplémentaires qui ne changent pas la reconnaissance des messages du jeu.

La reconnaissance utilise l'OCR et ne peut lire que les notifications visibles. Un texte ou un nom peut être mal reconnu ; un personnage et un compte Steam ne sont pas nécessairement associés. L'ancien classement distant est désactivé. Le nouveau classement utilise par défaut le site `https://eldenringpvp.com` : la participation nécessite une autorisation explicite et une connexion Steam vérifiée. Dans l'application, les profils des autres joueurs sont affichés après l'acceptation des conditions. Les statistiques locales restent disponibles hors ligne.

Lorsqu'une version de développement participe au classement, le pseudo publié porte le suffixe ` (dev)`. Le profil de personnage local n'est pas modifié. Les packages préparés pour le Microsoft Store ne reçoivent pas automatiquement ce suffixe.

## Installation de la version de développement

### Prérequis

- Windows, Elden Ring et Steam pour le suivi en jeu.
- Python 3.15 64 bits pour lancer le projet depuis ses sources.
- Tesseract OCR : préparez la version 5.5.4 locale avec `.\.venv\Scripts\python.exe store\prepare_tesseract.py`. À défaut, l'application utilise `C:\Program Files\Tesseract-OCR\tesseract.exe`. Les modèles OCR se trouvent dans `application/locales/tessdata/`.

Depuis PowerShell, à la racine du projet :

```powershell
py -3.15 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\Lancer le tracker.bat
```

Le lanceur utilise `.venv` et ouvre normalement [elden-tracker.localhost](http://elden-tracker.localhost/). Le serveur écoute uniquement sur ce PC : le port 5000 reste disponible pour les anciens onglets et le port 80 est utilisé pour l’adresse courte. Si le port 80 est occupé, l’adresse devient `http://elden-tracker.localhost:5000/`. Dans Configuration → Graphismes ou depuis l’icône de notification, choisissez le navigateur ou une fenêtre dédiée utilisant Chrome ou Edge installé. Si le tracker tourne déjà, utilisez sa page existante ou l’icône dans la zone de notification. Pour afficher les messages du programme dans une console :

```powershell
.\.venv\Scripts\python.exe ELDENRING_Tracker.py
```

Un environnement virtuel dépend de l'installation Python et de son chemin : recréez `.venv` après avoir déplacé le projet sur un autre PC.

## Démarrer le suivi

1. Lancez le tracker et Elden Ring.
2. Dans **Configuration → Général**, vérifiez la langue utilisée dans le jeu pour la reconnaissance et choisissez séparément la langue de l’interface. Ces réglages ne modifient pas la langue du jeu.
3. Cliquez sur **Start** et gardez le jeu visible au premier plan pour que les notifications puissent être capturées. **Stop** arrête le suivi.
4. Consultez les captures, les statistiques, les joueurs et l'historique depuis le menu. La session affichée dans le volet repart de zéro au prochain démarrage du suivi.

Dans **Configuration → Overlay en jeu**, l'overlay facultatif affiche le statut du suivi avec un indicateur de capture, le mode détecté, les joueurs Steam actuellement détectés avec leur ping disponible et le dernier événement du suivi. Par défaut, il reste affiché lorsque la fenêtre du jeu est visible et non réduite, même hors du premier plan. Les réglages permettent aussi de l'afficher uniquement pendant la capture, ou tant que le tracker est ouvert. Le point indique en vert que la capture fonctionne et en rouge qu'elle est inactive. Il est activé par défaut et peut être désactivé dans les réglages ; il ne prend pas le focus et laisse passer les clics. La fenêtre est externe au jeu et ne modifie pas celui-ci. Utilisez le jeu en mode fenêtré ou sans bordure : le plein écran exclusif peut masquer l'overlay. Les joueurs Steam ne sont pas nécessairement les personnages identifiés par l'OCR.

Cette section permet de choisir la position dans l’un des quatre coins de l’écran du jeu, la largeur de l'overlay, la transparence et la couleur du fond, la transparence, la couleur et la taille du texte, l'arrondi et la couleur des bordures, ainsi que les informations à afficher. Le contour extérieur peut aussi être masqué. Elle permet aussi de régler les avatars, les dimensions et l'espacement des cartes et les couleurs du ping. La transparence du fond et celle du texte sont indépendantes. Les réglages sont conservés localement et appliqués pendant le fonctionnement du tracker. Les avatars des joueurs détectés sont récupérés par Steamworks, mis en cache en mémoire et remplacés par une silhouette s'ils sont indisponibles. La durée de connexion commence à la première observation par le tracker ; elle repart si la détection est interrompue. Lorsque leur affichage est activé, la qualité de connexion et le nombre de rencontres indiquent si les données sont indisponibles.

Les options « Informations des joueurs » s'appliquent aux cartes de l'overlay et de l'application. Les préférences d'affichage propres à l'application continuent également de s'appliquer. Dans l'overlay, le rôle reconnu peut être affiché sur chaque carte : les envahisseurs sont teintés de rouge et les chasseurs de bleu. L'association utilise les notifications confirmées et un nom correspondant sans ambiguïté parmi les joueurs Steam connectés ; elle reste probable, car un nom de personnage peut différer d'un pseudo Steam ou lui correspondre par hasard. En duel d'arène, l'unique participant Steam observé et encore connecté est présenté comme duelliste si aucun autre pair n'a rendu la rencontre ambiguë. Les cartes dont le rôle est inconnu gardent leur couleur neutre. Le rôle peut être masqué dans les réglages. La ligne facultative avec le drapeau et le nom du pays indique le pays estimé à partir de l'adresse réseau si elle est disponible, et non la langue du joueur ; elle peut manquer ou être inexacte, notamment en cas de relais ou de VPN.

Le nombre de rencontres est calculé localement à partir des observations de connexions Steam enregistrées dans l'historique actif et ses archives. Une rencontre restaurée n'est comptée qu'une fois ; la connexion actuelle peut être incluse. Une reconnexion peut constituer une nouvelle observation, qui ne correspond pas nécessairement à un combat. Aucun appel au classement n'est nécessaire pour ce compteur.

Pour éviter de perturber les captures, l'overlay reste masqué si Windows ne confirme pas son exclusion des captures ; cette fonction nécessite Windows 10 version 2004 ou ultérieure. Le rendu, l'exclusion avec le système de capture du tracker, la compatibilité avec l'anti-triche et celle du package Store doivent encore être vérifiés en jeu et sur une installation Store réelle.

### Capture et reconnaissance

Les messages du jeu utilisés pour la reconnaissance proviennent du dépôt [HigorFr/Elden-Ring-Unpacked-msg](https://github.com/HigorFr/Elden-Ring-Unpacked-msg), dérivé de [elden-ring-data/msg](https://github.com/elden-ring-data/msg). Le tracker utilise une sélection de 66 messages pour chacune des 15 langues ; la provenance et les limites de vérification sont détaillées dans [application/locales/README.md](application/locales/README.md).

Dans **Configuration → Capture**, la détection automatique de la zone de notification est active par défaut. Elle cherche les messages reconnus et prévoit une hauteur suffisante pour deux lignes ; si elle ne peut pas situer le message, elle analyse la zone centrale de l'image. Après reconnaissance d’une notification sur deux lignes, elle fixe automatiquement la zone. Si la fenêtre ou l’écran change, la détection reprend. Vous pouvez aussi désactiver le mode automatique pour définir les limites manuellement.

L'aperçu et le test OCR utilisent une notification reconnue sur deux lignes. Si aucun exemple n'est disponible, démarrez le suivi et attendez une notification de ce type. Le test ne modifie pas les statistiques. Le dernier exemple est chiffré et conservé localement après le redémarrage.

L'écran contenant la fenêtre du jeu est détecté automatiquement. La reconnaissance dépend aussi de la langue sélectionnée et de la visibilité des notifications.

### Profil et connexions Steam

Dans **Configuration → Profil**, la capture du profil permet de récupérer le pseudo, le niveau et l'image en une étape. Dans Elden Ring, ouvrez le menu, puis **Configuration → Quitter la partie**, sans confirmer la sortie. Vérifiez les éléments reconnus avant de les enregistrer : l'OCR peut se tromper.

Dans **Configuration → P2P**, l'activation automatique du journal Steam est proposée par défaut. Lorsque la détection P2P est active, le tracker demande au client Steam d'activer son journal au démarrage ou après un redémarrage de Steam. Désactivez cette option pour utiliser la configuration manuelle ; la commande reste disponible dans la section P2P.

Si des joueurs sont déjà connectés au lancement du tracker, le lecteur examine les événements récents du journal Steam et vérifie leur connexion actuelle auprès de Steam avant de les afficher. Cette reprise dépend du journal : si leur arrivée n'y a pas été enregistrée ou ne figure plus dans les 8 Mo les plus récents, elle ne peut pas les retrouver avant une nouvelle connexion.

Pour participer au classement, accepte les conditions dans **Configuration → Classement en ligne** et connecte-toi à Steam. La connexion est confirmée automatiquement lorsque le navigateur le permet ; sinon, saisis le code temporaire affiché par le site. Ne partage pas ce code. Le partage du lien vers le profil Steam est facultatif ; son activation ou son retrait est appliqué à la prochaine synchronisation réussie, au démarrage, automatiquement après dix minutes ou lors d’une demande depuis le classement.

Après accord, les statistiques locales existantes sont reprises une fois pour chaque mode. Les débuts et résultats détectés ensuite, leur mode et leur date sont conservés localement en attente puis transmis au serveur, qui calcule les scores. Les envois sont réessayés sans être comptés deux fois après une interruption. Si les compteurs du serveur dépassent les données locales, la reprise s'arrête pour éviter d'écraser les données. Ces contrôles ne prouvent pas qu'un combat envoyé par un client modifié a réellement eu lieu.

Si l'accès à une ancienne installation est perdu, active la participation puis utilise **Récupérer une installation** dans cette même section. Confirme à nouveau le compte Steam avec le code affiché et choisis l'installation publiée à récupérer. Son ancien jeton sera révoqué, son score sera conservé et les combats en attente seront envoyés à la prochaine synchronisation.

Dans la version de développement, la mesure avancée du ping peut demander une autorisation administrateur Windows. La version Store utilise le ping Steam disponible sans élévation pour le ping. Le ping Steam est utilisé lorsqu'il est disponible ; certaines connexions ne fournissent aucune mesure. Une adresse affichée peut être celle d'un relais et sa géolocalisation est indicative.

### Historique et archives

En bas de la page **Historique**, la taille correspond à l'espace alloué aux événements actifs et à leurs index lorsque SQLite fournit cette mesure ; sinon, elle est estimée à partir des données enregistrées.

Arrêtez le suivi avant de purger ou d'archiver l'historique actif. L'archivage retire les événements de la liste active et les conserve chiffrés dans la même base locale, y compris les rencontres Steam. La restauration ajoute les événements absents sans écraser les événements déjà présents et conserve l'archive.

La purge retire également les rencontres Steam de la liste active des joueurs, mais ne supprime ni les archives, ni les captures, ni les statistiques cumulées. SQLite peut réutiliser l'espace libéré sans réduire immédiatement la taille du fichier.

Les durées de conservation des captures et de l'historique Steam sont désactivées par défaut. Si vous en activez une, les anciennes données sont supprimées au démarrage. La suppression des captures peut modifier les graphiques et certaines rencontres, sans modifier les statistiques cumulées.

## Mesure du nombre d’installations

Le tracker transmet à `https://eldenringpvp.com` un identifiant aléatoire créé localement au démarrage, puis un signal d’activité au moins toutes les 10 minutes tant que l’interface est ouverte ou que le suivi fonctionne, indépendamment de la participation au classement. Le serveur conserve une empreinte de cet identifiant ainsi que la première et la dernière réception ainsi que la dernière activité afin de compter les installations et d’estimer celles qui sont actives. Ce compteur ne permet pas de connaître le nombre exact de personnes, ni les installations antérieures qui ne se sont pas encore signalées. Les données de combat et le profil ne sont pas inclus dans cette requête. Une nouvelle installation ou la suppression des données locales peut produire un nouvel identifiant. Les journaux techniques de l’hébergement peuvent contenir des données de connexion telles que l’adresse IP.

## Données locales et sauvegarde

En développement, les bases SQLite de profil, configuration, captures, historique et statistiques se trouvent dans `%APPDATA%\Elden Ring PvP Tracker\`. La version Store peut utiliser des fichiers privés au package sous `%LOCALAPPDATA%\Packages\<famille-du-package>\LocalCache\Roaming\Elden Ring PvP Tracker\`. Le tracker affiche les emplacements des bases dans Information → Dossier des données et peut les ouvrir depuis son icône de notification. Des images temporaires générées pendant le suivi peuvent aussi apparaître dans `application/` en développement. Ces fichiers personnels, les journaux et les environnements virtuels sont exclus du dépôt.

Pour une base déjà présente, la version Store peut utiliser son chemin privé s'il est le seul accessible ou s'il désigne le même fichier que le chemin habituel. Si deux copies différentes ou des fichiers SQLite associés incompatibles existent, elle conserve le chemin habituel : aucune copie n'est automatiquement remplacée ou fusionnée.

Pour sauvegarder vos données, consultez d'abord les emplacements affichés, arrêtez le tracker puis copiez chacun des dossiers indiqués. Les captures et historiques peuvent contenir des pseudos et des adresses réseau : protégez vos sauvegardes avant de les partager.

Une migration de chiffrement peut être préparée sur une **copie distincte**, sans modifier les données originales :

```powershell
.\.venv\Scripts\python.exe -m application.data_protection prepare "$env:APPDATA\Elden Ring PvP Tracker" "$env:USERPROFILE\Desktop\Tracker-copie-securisee"
```

Arrête d'abord le tracker. Le programme demande un mot de passe d'au moins 12 caractères et le confirme. Conserve-le séparément : il protège le fichier `data-key-recovery.json` qui accompagne la copie. Pour utiliser cette copie sur un autre PC, il faut y disposer du projet et de son environnement Python, puis exécuter `python -m application.data_protection restore-key "CHEMIN_DE_LA_COPIE"` et saisir le mot de passe. La clé d'accès au classement dépend de l'utilisateur Windows ; une reconnexion Steam ou la récupération d'installation peut être nécessaire.

**Ne remplace pas encore le dossier habituel par cette copie** si tu utilises une version Store ou une ancienne version du tracker : elles ne savent pas lire le nouveau format. La copie préparée nécessite une version reconstruite intégrant cette modification. L'original et les anciennes sauvegardes restent protégés par l'ancien chiffrement. Cette migration concerne les champs déjà chiffrés ; certaines données locales et certains fichiers restent lisibles en clair, donc protège aussi le PC et les sauvegardes.

Les statistiques d'utilisation sont enregistrées localement dans `usage_metrics.db`. Une session mesure la durée de fonctionnement du tracker, y compris en attente, et est mise à jour environ toutes les 30 secondes. Le diagnostic présente aussi des mesures temporaires du processus courant ; les erreurs OCR techniques ne représentent pas un taux de reconnaissance.

## Version Microsoft Store

La construction et les vérifications du package sont décrites dans [store/README.md](store/README.md). L'ancien classement distant reste désactivé. Dans le code Store en préparation, le nouveau classement utilise exclusivement `https://eldenringpvp.com`, même si un ancien fichier de configuration contient une autre adresse ; la participation nécessite un consentement et une connexion Steam vérifiée. Les profils du classement s'affichent dans l'application après acceptation des conditions. Les packages Store existants et le tag GitHub `v1.0.3.0` peuvent différer de ce code : vérifier le contenu du package soumis avant d'en décrire les fonctionnalités. La version Store utilise le ping Steam disponible sans demander d’élévation pour la mesure du ping. Les données et l'installation du package doivent être testées séparément de la version de développement.

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

### Configuration du classement en ligne (développement)

La participation au classement est facultative et désactivée par défaut : aucun profil ni événement de combat ne sont transmis tant que la participation et les conditions associées n’ont pas été acceptées dans Configuration → Classement en ligne. Dans l'application, les profils des autres joueurs sont affichés après cet accord. Le texte de consentement actuel est provisoire et doit être validé avant la mise en production. L’application continue à fonctionner sans connexion.

En développement, en l’absence de fichier de configuration, le serveur utilisé est `https://eldenringpvp.com`. Pour utiliser un autre serveur, copier `leaderboard-config.example.json` vers `%APPDATA%\Elden Ring PvP Tracker\leaderboard-config.json`, puis choisir `development` ou `production` dans `environment` et renseigner l’URL correspondante dans `urls`. Une configuration existante reste prioritaire en développement, même si elle est vide ou invalide. L’adresse distante doit utiliser HTTPS ; HTTP est accepté uniquement pour une adresse locale de test. Ne pas placer la configuration dans `.venv`. Une demande de retrait ou d’annulation déjà en attente peut être réessayée auprès du serveur précédemment associé à l’installation. Le code Store en préparation ignore ce fichier et refuse les requêtes vers toute autre adresse ; une demande déjà en attente sur un ancien serveur reste conservée, mais ne peut pas y être envoyée par la version Store.

Lorsque la participation est activée et Steam vérifié, la synchronisation transmet les événements de combat en attente ainsi que le pseudo, le niveau et l’avatar, au lancement du tracker, automatiquement dix minutes après la dernière synchronisation terminée, et à l’ouverture ou à l’actualisation du classement. La synchronisation automatique fonctionne tant que le tracker est lancé, même sans onglet ouvert. Le serveur calcule les scores à partir des événements ; les totaux des statistiques locales ne sont pas envoyés comme résultats. Les synchronisations ordinaires partagent un délai d’au moins 10 secondes après la fin de la précédente ; les retraits de consentement restent prioritaires et les délais plus longs demandés par le serveur sont respectés. La langue de jeu sélectionnée peut aussi être transmise dans le cadre de la participation ; elle apparaît avec un drapeau qui représente la langue, pas la nationalité. Un rechargement de la page ne déclenche pas de nouvelle synchronisation. Une installation est identifiée par un UUID et un jeton protégé par Windows pour l’utilisateur courant. Ce mécanisme ne prouve pas l’authenticité des résultats transmis. La désactivation propose de conserver les données publiées ou de les retirer : si le serveur est indisponible, le retrait reste en attente et est retenté au prochain lancement. Les statistiques locales ne sont pas supprimées.

La participation nécessite de connecter un compte Steam dans le navigateur. Après l'acceptation, la fenêtre de participation guide la connexion et indique son résultat ; l'état du compte apparaît aussi dans Configuration → Classement en ligne sans recharger la page. En cas de fermeture ou de blocage de la fenêtre Steam, la même fenêtre permet de réessayer ou d'annuler. Le site vérifie la réponse auprès de Steam : le tracker ne reçoit pas le mot de passe. L'identifiant Steam vérifié est conservé sur le serveur pour identifier l'installation ; la publication d'un lien vers le profil reste distincte et désactivée par défaut. Ce lien peut être retiré dans Configuration → Classement en ligne ; si le serveur est indisponible, le retrait est réessayé au prochain démarrage. Les anciens profils doivent reconnecter leur compte avant de réapparaître. La connexion Steam vérifie le contrôle du compte, pas l'authenticité des résultats de jeu déclarés par le tracker.
