# Langues du jeu et de l’interface

Le catalogue `network_messages.json` rassemble 64 messages par langue pour les 15 langues du jeu : réseau, Colisée, mort et limite d’inventaire. Ils proviennent de [HigorFr/Elden-Ring-Unpacked-msg](https://github.com/HigorFr/Elden-Ring-Unpacked-msg), dérivé de [elden-ring-data/msg](https://github.com/elden-ring-data/msg). Les champs entre chevrons sont des valeurs variables du jeu.

Une comparaison ponctuelle avec le dépôt HigorFr au commit `4c9b6171e1820af9d3a75a740fd8a9ebe1e806ff` a retrouvé les 960 textes locaux à l’identique dans les fichiers XML correspondants. Le dépôt n’indique pas de version précise du jeu pour cette extraction ; cette comparaison ne garantit donc pas la couverture de toutes les mises à jour du jeu.

Un seul sélecteur règle à la fois la langue de l’interface et celle utilisée pour la reconnaissance du jeu. Les modèles OCR locaux proviennent du dépôt officiel [tessdata_fast](https://github.com/tesseract-ocr/tessdata_fast). Les deux variantes espagnoles partagent un modèle. Toutes les langues, y compris le français et l’anglais, utilisent les modèles locaux du projet.

`ui_packs.json` et `static/ui-packs.js` contiennent les traductions hors ligne de l’interface. Les traductions ont été générées automatiquement avec des modèles Argos Translate, puis les principaux libellés ont été corrigés ; elles ne sont pas toutes révisées par des locuteurs natifs. Les textes de victoire, défaite et égalité proviennent du jeu.

Les tests vérifient la classification des 960 textes du catalogue et des transitions simulées pour les 15 langues. Le test OCR automatisé vérifie des messages de victoire synthétiques en français et en anglais ; un ancien essai exploratoire sur images synthétiques avait reconnu 167 messages sur 180, sans constituer un test permanent. La lecture et le suivi nécessitent encore une validation sur des captures réelles, notamment en arabe et dans les écritures est-asiatiques. Les messages identiques d’invocation et d’arrivée d’un chasseur restent volontairement ambigus.
