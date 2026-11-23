# Préparation Microsoft Store — 1.0.11.0

État au 23 novembre 2026 : candidat local reconstruit ; aucune nouvelle soumission Partner Center n’a été vérifiée. Le fichier MSIX est non signé et n’est pas une installation Microsoft Store.

- Package : `dist/store-1.0.11.0-candidate-20261123/EldenRingTracker_1.0.11.0_x64.msix`.
- SHA-256 : `442935608c6cd21eefec0d460e4239d46469170830ed062ed69b91826d721350`.
- L’identité, la version, les 30 langues et le contenu ont été contrôlés avec `store/verify_release_artifact.py`.
- Le smoke test isolé vérifie notamment le démarrage, Tesseract, le mode Store, la version, le ping Steam sans élévation et la configuration du classement de production. Il ne teste pas un jeu réel ni une installation Store.
- Les descriptions et notes sont préparées pour 30 langues dans `store/descriptions-fiche-1.0.11.0.md` et `store/notes-de-version-1.0.11.0.md`. Une relecture linguistique reste nécessaire pour les nouvelles traductions.
- `dist/PartnerListing_1_0_11_0-preparation-v2.csv` est généré à partir de l’export 1.0.10.0 du 21 novembre. Il faut le comparer avec un export actuel de Partner Center avant import ; il ne prouve pas l’état actuel des fiches ni des captures.
- La mise à jour d’une installation Store existante et de ses données, les captures en jeu, l’overlay, Steam, la détection de mise à jour et le résultat de certification doivent encore être contrôlés. Vérifier dans Partner Center le numéro publié, la politique de confidentialité, les champs et captures avant soumission.
