# Langues du jeu et de l’interface

Le catalogue `network_messages.json` rassemble 58 messages par langue pour les 15 langues du jeu : réseau, Colisée, mort et limite d’inventaire. Ils proviennent de [HigorFr/Elden-Ring-Unpacked-msg](https://github.com/HigorFr/Elden-Ring-Unpacked-msg), dérivé de [elden-ring-data/msg](https://github.com/elden-ring-data/msg). Les champs entre chevrons sont des valeurs variables du jeu.

Un seul sélecteur règle à la fois la langue de l’interface et celle utilisée pour la reconnaissance du jeu. Les modèles OCR locaux proviennent du dépôt officiel [tessdata_fast](https://github.com/tesseract-ocr/tessdata_fast). Les deux variantes espagnoles partagent un modèle. Toutes les langues, y compris le français et l’anglais, utilisent les modèles locaux du projet.

`ui_packs.json` et `static/ui-packs.js` contiennent les traductions hors ligne de l’interface. Les traductions ont été générées automatiquement avec des modèles Argos Translate, puis les principaux libellés ont été corrigés ; elles ne sont pas toutes révisées par des locuteurs natifs. Les textes de victoire, défaite et égalité proviennent du jeu.

Les tests vérifient les 870 textes du catalogue et les transitions pour les 15 langues. Un essai OCR sur des images synthétiques reconnaît 167 messages sur 180 ; certains textes, particulièrement en arabe et dans les écritures est-asiatiques, nécessitent encore une validation et des ajustements sur des captures réelles. Les messages identiques d’invocation et d’arrivée d’un chasseur restent volontairement ambigus.
