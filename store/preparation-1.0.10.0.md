# Préparation Microsoft Store — 1.0.10.0

État : **préparation de la mise à jour**, sans soumission pour certification ni publication. Ce numéro a été choisi pour poursuivre la numérotation du projet.

## État constaté dans Partner Center

- Le package actuellement publié est `EldenRingTracker_1.0.9.0_x64.msix`. La nouvelle version `1.0.10.0` lui est supérieure.
- L'identité vérifiée est `Baiawai.EldenRingPvPTracker`, avec le sujet `CN=7C9E2690-6D7E-4D7B-91ED-3ED1041287BE` et le nom d'éditeur `Baiawai`.
- La soumission **9**, à l'état de brouillon, contient `EldenRingTracker_1.0.10.0_x64.msix`, indiqué comme validé dans Partner Center. Le remplacement de l'ancien package concerne le brouillon ; la version publiée reste la `1.0.9.0`.
- Les 15 fiches correspondant aux langues du package précédent sont complètes ; des fiches supplémentaires en français de France et en anglais des États-Unis existent également. Conserver leurs champs et vérifier les correspondances entre codes génériques et régionaux avant tout import.

## Paquet et contrôles

- Le candidat MSIX non signé `1.0.10.0` est dans `dist/store-1.0.10.0-preparation/`. Son SHA-256 est `8e755998bc8c621352d19ee5c711b58a30fde69e0b044220366305f07467dc0c`. Le candidat antérieur `1.1.0.0` ne correspond plus au numéro choisi.
- `store/verify_release_artifact.py` a vérifié la version et l'identité du manifeste et de l'exécutable, les 30 ressources de langue, les 14 modèles OCR partagés par les 15 langues du jeu, le lecteur Steam et l'absence des fichiers locaux sensibles recherchés. Le smoke test de l'exécutable en environnement isolé a réussi.
- La suite complète a réussi après renumérotation : **381 tests**.
- Le Windows App Certification Kit n'a pas été trouvé dans les emplacements examinés. Son contrôle, l'installation de test, la mise à jour depuis une ancienne installation sur une copie de données, l'OCR et l'overlay en jeu restent à vérifier avant certification.
- La version Store utilise le ping Steam lorsqu'il est disponible sans demander d'élévation pour cette mesure. La mesure avancée et son éventuelle élévation concernent la version de développement. L'activation du journal Steam est une fonction distincte.

## Langues et fiches

- L'interface prend en charge **30 langues** ; la reconnaissance des notifications du jeu couvre **15 langues**. Les notes et descriptions de `1.0.10.0` sont préparées pour les 30 langues et doivent être relues avant utilisation.
- Les 120 captures localisées du candidat `1.0.10.0` utilisent un profil de démonstration vide ; elles ne proviennent pas d'un MSIX installé.
- Un dossier d'import a été préparé depuis l'export réel de la soumission : il conserve les noms, captures existantes et champs non concernés, et ajoute les captures manquantes aux nouvelles fiches. Contrôler dans Partner Center le résultat de l'import avant certification.
- Les notes GitHub sont préparées localement en 30 langues. La version `1.0.10.0` ne doit pas être publiée depuis une référence pointant encore vers l'ancien code.

## Avant certification

Vérifier la politique de confidentialité et les flux effectivement déployés, les marchés, l'évaluation d'âge, les notes pour les testeurs et le calendrier de publication. Vérifier les conditions d'installation, de mise à jour et d'utilisation en jeu sans écraser les données réelles. Soumettre uniquement après examen du candidat, des fiches et des résultats des contrôles ; la création d'un brouillon ne lance aucune certification.

Références : [numérotation des packages Microsoft](https://learn.microsoft.com/en-us/windows/apps/publish/publish-your-app/package-version-numbering), [fiches MSIX](https://learn.microsoft.com/en-us/windows/apps/publish/publish-your-app/msix/add-and-edit-store-listing-info), [captures Store](https://learn.microsoft.com/en-us/windows/apps/publish/publish-your-app/screenshots-and-images), [import et export des fiches](https://learn.microsoft.com/en-us/windows/apps/publish/publish-your-app/import-and-export-store-listings?pivots=store-installer-msix).
