# Instructions pour travailler sur Elden Ring PvP Tracker

## Contexte

Application Windows locale : Flask/Waitress et Python côté serveur, interface HTML/CSS/jQuery côté navigateur, capture d’écran et OCR Tesseract. Le point d’entrée est `ELDENRING_Tracker.py` ; `Lancer le tracker.bat` utilise `.venv\Scripts\pythonw.exe`. Le serveur écoute sur `127.0.0.1:5000`.

Lire [README.md](README.md) avant une modification importante. Ne pas supposer que le classement distant, Steam, le jeu ou les autorisations administrateur sont disponibles.

La version affichée est définie dans `application/version.py`. La version de développement et la version Store ne sont pas interchangeables : consulter [store/README.md](store/README.md) avant de modifier ou construire le package. Vérifier explicitement la version passée au script Store et les différences concernant le ping. Le classement distant est actuellement désactivé dans les deux versions ; ne pas rétablir les appels à l’ancien serveur.

## Données et partie en cours

- Les données réelles se trouvent dans `%APPDATA%\Elden Ring PvP Tracker\`. Ne pas effacer ni modifier les statistiques, captures, historiques ou paramètres pour tester, sauf demande explicite.
- Les fichiers `application/simple_*.jpg`, `application/simple_notif_*.jpg`, `application/steam.jpg`, `application/template_notif.jpg`, `application/start_.jpg`, `application/finish_.jpg`, `application/user.jpg` et `application/user_panel.jpg` sont des images générées par le suivi ; ne pas les publier comme ressources du projet. En version compilée, les images temporaires utilisent `runtime_images` dans le dossier de données.
- Avant de redémarrer le serveur ou d’interrompre le suivi, vérifier si un combat est en cours. S’il y en a un, attendre sa fin avec l’utilisateur. Une recherche d’invasion seule n’est pas un combat commencé. `/monitor-status` indique si le suivi tourne sans consommer d’événement, mais ne dit pas si un combat est en cours. `/interval` expose `fight` et consomme des messages en attente : si nécessaire, ne le consulter qu’une fois, sans afficher les données personnelles de la réponse. Si l’état reste incertain, le vérifier avec l’utilisateur.
- Le redémarrage du tracker réinitialise la session en mémoire. Préférer un simple rafraîchissement pour les changements CSS/JS lorsqu’il suffit.
- Pour des tests qui écrivent, utiliser des copies isolées des bases et un `APPDATA` de test ; ne pas faire jouer les fixtures sur les données réelles. En développement, `application.runtime_paths.image_dir()` pointe néanmoins vers `application/` : un `APPDATA` isolé ne suffit pas pour les tests qui créent ou suppriment des images. Rediriger aussi ces chemins vers un répertoire temporaire ou utiliser une copie isolée du projet.
- Des écarts de visibilité des fichiers ont été observés entre l’Explorateur de l’utilisateur et un tracker lancé depuis l’environnement de l’agent, malgré un chemin affiché identique. Si les données ou le dossier observés divergent, vérifier le processus qui écoute sur le port 5000 et le contexte de lancement avant de conclure qu’une suppression a réussi ou que des données ont été restaurées. Pour retrouver la session habituelle de l’utilisateur, privilégier un lancement de `Lancer le tracker.bat` depuis son Explorateur ; ne pas lancer une seconde instance sur le même port.
- Certains réglages d’affichage sont aussi conservés dans le stockage local du navigateur ; `localhost` et `127.0.0.1` sont des origines distinctes. Ne pas effacer les données du navigateur ou celles d’autres sites pour tester.

## Fonctionnement à préserver

- Les modes internes sont `Arena`, `Invasion` et `Defense` ; leurs libellés utilisateur peuvent être traduits. Les statistiques restent séparées et les égalités concernent l’arène uniquement.
- L’arène, les invasions et les défenses utilisent `application/functions.py`, `mode_stats.py` et les modules de reconnaissance. Vérifier les transitions, les cas sans résultat et les doublons avant de toucher au suivi.
- L’OCR repose sur la langue sélectionnée et les textes de `application/locales/network_messages.json`. Ne pas inventer de texte de jeu : vérifier le catalogue et les relevés OCR disponibles. Les noms et rôles Steam/jeu ne sont pas nécessairement reliés.
- Dans Configuration → Capture, la détection automatique est le mode par défaut. Préserver le réglage manuel, le verrouillage de la zone et l’exemple persistant chiffré : une notification à deux lignes sert de référence et la zone doit rester suffisamment haute pour ces messages. L’écran du jeu est détecté automatiquement.
- La capture du profil récupère ensemble pseudo, niveau et image depuis l’écran « Quitter la partie ». Préserver la vérification avant enregistrement, l’annulation et la notification unique du volet droit lorsque l’une des données manque.
- Les événements de suivi sont classés `System` dans l’historique ; conserver le filtrage, les anciens événements et leurs migrations.
- Dans l’historique, l’archivage retire les événements de la liste active mais les conserve dans la base ; la restauration ajoute les événements absents sans doublons et conserve l’archive. La purge et l’archivage exigent l’arrêt du suivi. Préserver les captures et les statistiques cumulées ; les rencontres Steam font partie de l’historique actif. Tester ces opérations uniquement sur des données isolées.
- La détection Steam peut demander l’activation automatique de son journal si l’option P2P correspondante est active. Ne pas supposer que le ping, une adresse IP ou la correspondance entre joueur et profil Steam sont disponibles. En développement, la mesure avancée du ping peut demander une élévation ; la version Store utilise le ping Steam disponible sans cette élévation.
- Le panneau des captures utilise `.capture-toolbar` pour les commandes et `.capture-scroll` pour le défilement. Préserver les filtres, la pagination et la visionneuse.
- L’interface utilise Agmena pour les textes et Mantinia pour le menu, via `static/app-typography.css`. Les textes doivent rester lisibles, normalement au moins 18 px, et les mises en page doivent s’adapter à leur contenu.
- Dans Configuration, conserver l’alignement des libellés à gauche, l’alignement vertical des lignes et la cohérence des commandes, des espacements et des infobulles. Préserver la présentation particulière de Quitter, notamment le pseudo centré. Les choix Oui/Non utilisent les commandes et chevrons communs.
- Les textes de l’interface doivent être couverts dans toutes les langues. Maintenir `application/locales/ui_packs.json` et `static/ui-packs.js` synchronisés, en plus des textes français de repli. Ne pas modifier la langue ou les préférences existantes sans demande.
- Au premier lancement, la langue du navigateur est utilisée si elle est prise en charge, avec repli en anglais ; un choix déjà enregistré doit être conservé. La langue choisie détermine aussi la reconnaissance des messages du jeu.
- Les changements de CSS/JS peuvent être servis sans redémarrer le backend ; les modifications Python ou du modèle HTML mis en cache nécessitent généralement un redémarrage. `static/ui-i18n.js` et certains scripts adaptent les anciens modèles en cache : préserver ces compatibilités lorsqu’une modification doit être visible après un simple rafraîchissement. Ne pas redémarrer pendant un combat.
- L’icône du navigateur, celle de la zone de notification et les icônes du package Store doivent rester cohérentes. Une modification du fichier source peut nécessiter un rafraîchissement du navigateur, un redémarrage du tracker ou une reconstruction du package selon le cas ; ne pas prétendre qu’une version Store installée est mise à jour sans la reconstruire et l’installer.

## Vérification

Depuis la racine :

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Pour du JavaScript modifié, `node --check static/nom-du-fichier.js` permet de contrôler sa syntaxe si Node est installé. Compléter par une vérification ciblée : interface et états responsive pour le CSS, données isolées pour les routes et migrations, et essais en jeu pour les messages OCR lorsque c’est nécessaire. Signaler clairement ce qui n’a pas pu être vérifié.

Ne pas publier de bases SQLite, captures personnelles, journaux, environnements virtuels, secrets ou données réseau réelles. Conserver les ressources et licences nécessaires au fonctionnement du projet.
