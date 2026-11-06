# Audit de la version de développement

Audit et corrections effectués le 4 novembre 2026. Ils concernent le code de développement local ; le paquet Store déjà soumis n’a pas été remplacé.

## Points corrigés

- Flask, Werkzeug, NumPy et OpenCV ont été mis à jour dans `requirements.txt` et dans l’environnement de développement. `pip check` passe et `pip-audit` ne signale aucune vulnérabilité connue pour les versions Python déclarées à la date de l’audit. Cet outil ne couvre pas tous les risques de sécurité de l’application ou des composants natifs.
- jQuery et DataTables ont été mis à jour dans leurs branches compatibles respectives. DataTables 1 est en fin de vie ; sa migration vers une version majeure plus récente reste à préparer et tester. Chart.js reste en version 3 : son passage en version 4 comporte des changements de compatibilité.
- Le serveur local filtre les requêtes de sites tiers et les noms d’hôtes non locaux. Cette protection ne remplace pas l’isolation contre un programme malveillant exécuté sur le même PC.
- La création des tables est idempotente, les connexions SQLite des captures et des paramètres sont mieux fermées, et des tests utilisent des données temporaires isolées.
- Le chargement des langues de tableau évite les réponses asynchrones obsolètes ; la navigation et le volet latéral ont été adaptés aux petites fenêtres.
- Tesseract utilise les modèles de langue du projet même lorsque son chemin contient des espaces. Cela permet d’utiliser les modèles fournis pour toutes les langues, y compris en français et en anglais.

## Limites et points à suivre

- Les 15 variantes de l’interface correspondent aux catalogues de messages et modèles OCR fournis. Les messages sont issus du dépôt de textes du jeu indiqué dans `application/locales/README.md`. Les tests couvrent les entrées du catalogue et une lecture OCR synthétique en français et en anglais ; ils ne prouvent pas la reconnaissance de chaque message dans une partie réelle. Le français utilise aussi des détecteurs historiques.
- NumPy et OpenCV ont changé de version majeure. Des comparaisons synthétiques et les tests automatisés passent, mais les captures automatiques, la reconnaissance des résultats et le plein écran d’Elden Ring doivent encore être vérifiés en jeu sur les modes utilisés.
- La version de développement conserve le classement distant existant. Le serveur et ses pratiques de conservation ou de suppression des données ne sont pas administrés ni vérifiables ici. La désactivation antérieure concerne la version Store compilée. Il faut clarifier la gestion des données avant de réutiliser ce service pour une distribution.
- Les améliorations SQLite sont ciblées : d’autres fonctions historiques restent à simplifier progressivement, avec des tests de migration et de suivi adaptés.
- Le filtre des captures évite de déchiffrer les images des autres modes, mais l’API historique renvoie encore toutes les images du mode sélectionné : une pagination côté serveur sera nécessaire pour les très grosses bibliothèques. Les modes sont chiffrés en base et ne peuvent pas être filtrés par un index SQLite sans migration du format.

Les essais automatisés exécutés comprennent `unittest discover`, `pip check`, l’analyse `pip-audit` des dépendances Python déclarées, la vérification syntaxique JavaScript et une visite de l’interface en 15 langues sur trois tailles de fenêtre, avec données temporaires.
