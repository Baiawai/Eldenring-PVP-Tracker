# Instructions pour travailler sur Elden Ring PvP Tracker

## Contexte

Application Windows locale : Flask/Waitress et Python côté serveur, interface HTML/CSS/jQuery côté navigateur, capture d’écran et OCR Tesseract. Le point d’entrée est `ELDENRING_Tracker.py` ; `Lancer le tracker.bat` utilise `.venv\Scripts\pythonw.exe`. Le serveur écoute sur `127.0.0.1:5000`.

Lire [README.md](README.md) avant une modification importante. Ne pas supposer que le classement distant, Steam, le jeu ou les autorisations administrateur sont disponibles.

## Données et partie en cours

- Les données réelles se trouvent dans `%APPDATA%\Elden Ring PvP Tracker\`. Ne pas effacer ni modifier les statistiques, captures, historiques ou paramètres pour tester, sauf demande explicite.
- Les fichiers `application/simple_*.jpg`, `simple_notif_*.jpg`, `steam.jpg`, `template_notif.jpg`, `start_.jpg`, `finish_.jpg`, `user.jpg` et `user_panel.jpg` sont des images générées par le suivi ; ne pas les publier comme ressources du projet.
- Avant de redémarrer le serveur ou d’interrompre le suivi, vérifier si un combat est en cours. S’il y en a un, attendre sa fin avec l’utilisateur. Une recherche d’invasion seule n’est pas un combat commencé. Attention : la lecture de `/interval` consomme des messages en attente ; éviter les interrogations répétées pendant une partie.
- Le redémarrage du tracker réinitialise la session en mémoire. Préférer un simple rafraîchissement pour les changements CSS/JS lorsqu’il suffit.
- Pour des tests qui écrivent, utiliser des copies isolées des bases et un `APPDATA` de test ; ne pas faire jouer les fixtures sur les données réelles.

## Fonctionnement à préserver

- Les modes internes sont `Arena`, `Invasion` et `Defense` ; leurs libellés utilisateur peuvent être traduits. Les statistiques restent séparées et les égalités concernent l’arène uniquement.
- L’arène, les invasions et les défenses utilisent `application/functions.py`, `mode_stats.py` et les modules de reconnaissance. Vérifier les transitions, les cas sans résultat et les doublons avant de toucher au suivi.
- L’OCR repose sur la langue sélectionnée et les textes de `application/locales/network_messages.json`. Ne pas inventer de texte de jeu : vérifier le catalogue et les relevés OCR disponibles. Les noms et rôles Steam/jeu ne sont pas nécessairement reliés.
- Les événements de suivi sont classés `System` dans l’historique ; conserver le filtrage, les anciens événements et leurs migrations.
- Le panneau des captures utilise `.capture-toolbar` pour les commandes et `.capture-scroll` pour le défilement. Préserver les filtres, la pagination et la visionneuse.
- L’interface utilise Agmena pour les textes et Mantinia pour le menu, via `static/app-typography.css`. Les textes doivent rester lisibles, normalement au moins 18 px, et les mises en page doivent s’adapter à leur contenu.
- Les textes de l’interface doivent être couverts dans toutes les langues. Maintenir `application/locales/ui_packs.json` et `static/ui-packs.js` synchronisés, en plus des textes français de repli. Ne pas modifier la langue ou les préférences existantes sans demande.
- Les changements de CSS/JS peuvent être servis sans redémarrer le backend ; les modifications Python ou du modèle HTML mis en cache nécessitent généralement un redémarrage. Ne pas redémarrer pendant un combat.

## Vérification

Depuis la racine :

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Pour du JavaScript modifié, `node --check static/nom-du-fichier.js` permet de contrôler sa syntaxe si Node est installé. Compléter par une vérification ciblée : interface et états responsive pour le CSS, données isolées pour les routes et migrations, et essais en jeu pour les messages OCR lorsque c’est nécessaire. Signaler clairement ce qui n’a pas pu être vérifié.

Ne pas publier de bases SQLite, captures personnelles, journaux, environnements virtuels, secrets ou données réseau réelles. Conserver les ressources et licences nécessaires au fonctionnement du projet.
