# Préparation Microsoft Store — 1.0.10.0

État au 21 novembre 2026 : **soumise pour certification**, avec blocage de la publication jusqu'à l'action « Publier maintenant ». Ce numéro a été choisi pour poursuivre la numérotation du projet.

## État constaté dans Partner Center

- Le package actuellement publié est `EldenRingTracker_1.0.9.0_x64.msix`. La nouvelle version `1.0.10.0` lui est supérieure.
- L'identité vérifiée est `Baiawai.EldenRingPvPTracker`, avec le sujet `CN=7C9E2690-6D7E-4D7B-91ED-3ED1041287BE` et le nom d'éditeur `Baiawai`.
- La soumission **9** contient `EldenRingTracker_1.0.10.0_x64.msix`, indiqué comme validé dans Partner Center. Elle a été envoyée en certification ; sa publication est bloquée jusqu'à une action manuelle. La version publiée reste la `1.0.9.0` en attendant.
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
- L'import des fiches est terminé et Partner Center indiquait « Mise à jour terminée » avant soumission. Un nouvel export confirme pour les 32 fiches (30 langues et deux variantes régionales) les descriptions et notes attendues, un titre et quatre captures par fiche ; les captures et autres champs préexistants ont été conservés.
- Les notes GitHub sont préparées localement en 30 langues. La version `1.0.10.0` ne doit pas être publiée depuis une référence pointant encore vers l'ancien code.

## Avant certification

L'utilisateur a confirmé que le nouveau classement distant est en ligne. La participation est désactivée par défaut et l'envoi des événements exige les autorisations correspondantes. Le module de présence tente au démarrage d'envoyer au site un identifiant aléatoire persistant et l'état actif ; la politique de confidentialité enregistrée dans Partner Center décrit ce signal, les diagnostics et le classement. Le service distant n'a pas été contacté pendant cet audit et sa disponibilité n'a pas été vérifiée.

La publication doit rester bloquée jusqu'à l'examen du résultat de certification et des contrôles restants, notamment l'installation et la mise à jour sur une copie de données, ainsi que l'utilisation en jeu sans écraser les données réelles. Les notes pour les testeurs ont été corrigées pour préciser que le package Store ne demande pas d'élévation pour la mesure du ping.

Références : [numérotation des packages Microsoft](https://learn.microsoft.com/en-us/windows/apps/publish/publish-your-app/package-version-numbering), [fiches MSIX](https://learn.microsoft.com/en-us/windows/apps/publish/publish-your-app/msix/add-and-edit-store-listing-info), [captures Store](https://learn.microsoft.com/en-us/windows/apps/publish/publish-your-app/screenshots-and-images), [import et export des fiches](https://learn.microsoft.com/en-us/windows/apps/publish/publish-your-app/import-and-export-store-listings?pivots=store-installer-msix).
