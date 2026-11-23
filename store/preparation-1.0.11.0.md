# Préparation Microsoft Store — 1.0.11.0

État : cette fiche décrit un candidat construit auparavant. Depuis, des modifications ont été apportées au code et aux notes : le package et les résultats ci-dessous ne représentent donc pas nécessairement l'état actuel. Reconstruire et vérifier un nouveau candidat avant toute soumission.

Le correctif applique une fois le préréglage actuel d'overlay aux anciens profils, conserve l'activation ou la désactivation de l'overlay, puis respecte les personnalisations ultérieures. Les profils ayant déjà reçu ce préréglage ne sont pas réinitialisés. Il ajoute aussi un badge pour les participants au classement dont le compte Steam est vérifié, même lorsque le lien de leur profil n'est pas publié ; la recherche et le badge sont désactivables dans les réglages.

La version Store vérifie également les mises à jour au démarrage puis toutes les dix minutes. Les limites et le cache de Microsoft peuvent retarder la détection effective. Lorsque le Store confirme une mise à jour pendant un combat, le tracker attend que le traitement du combat soit terminé avant de s'arrêter et d'afficher l'écran obligatoire. Le bouton ouvre le Store et ferme le tracker tout en laissant l'onglet ouvert. Lorsque le numéro exact n'est pas disponible, la dernière version publiée peut être demandée à un fournisseur facultatif et indiquée comme telle ; cette information ne déclenche pas le blocage.

- Package : `dist/store-1.0.11.0-peer-badge-auth/EldenRingTracker_1.0.11.0_x64.msix`.
- SHA-256 : `8a0c5ff37878fe45ffe95ad8a0528b2b3d7c9488c71727bc9cda96794fc2ea40`.
- Identité et version, 30 langues et contenu de l'archive vérifiés ; adaptateurs privés de version et de badge présents dans l'exécutable compilé.
- 425 tests automatisés réussis, tests navigateur isolés et smoke test de l'exécutable réussis.
- Le service authentifié nécessaire au badge est déployé sur le site (commit `78aca135`) ; l'ancien service de rang/statistiques préparé séparément n'a pas été déployé. L'accueil répond HTTP 200 et le nouveau service refuse les requêtes non authentifiées (401). La politique de confidentialité révisée se trouve dans `store/politique-confidentialite-1.0.11.0.txt` et devra être examinée dans Partner Center avant toute publication.
- La détection WinRT d'une vraie mise à jour, l'ouverture du Store et la mise à niveau sur une installation réelle restent à vérifier. Les réponses Store et fournisseur sont simulées dans les tests automatisés ; les notes de version traduites n'ont pas toutes été relues par des locuteurs natifs.

Les anciens packages sont conservés séparément. Ne pas envoyer ni publier ce candidat avant demande de l'utilisateur.
