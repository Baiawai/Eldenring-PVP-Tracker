# Elden PVP Tracker 1.0.11.0

## Français (fr-FR)

- Lors de cette mise à jour, les anciens réglages de l’overlay en jeu sont réinitialisés une seule fois aux nouveaux paramètres par défaut. L’activation ou la désactivation de l’overlay reste inchangée. Les modifications effectuées ensuite sont conservées.
- Le tracker vérifie périodiquement les mises à jour Microsoft Store. L’écran apparaît après le combat en cours et indique la version installée ainsi que la nouvelle version lorsqu’elle est disponible.
- Le bouton ouvre le Store et ferme le tracker : installez la mise à jour, puis relancez-le.
- Les participants au classement peuvent reconnaître les autres participants ayant un SteamID vérifié, même si leur lien de profil n’est pas partagé. L’identification, activée par défaut, peut être désactivée ; le partage public du profil reste facultatif.

- L’overlay en jeu affiche l’état du suivi, le mode, le dernier événement et les joueurs Steam détectés. Sa position, ses dimensions, ses couleurs, sa transparence, ses bordures et les éléments affichés sont personnalisables. Les informations indisponibles restent indiquées comme telles.
- Les cartes de joueurs Steam présentent les avatars disponibles, le ping, la durée de connexion et le nombre de rencontres enregistrées. Les amis Steam identifiés reçoivent un tag distinct des catégories manuelles.
- La page Joueurs permet de retrouver les rencontres, de gérer les favoris et les catégories personnalisées, et de consulter les captures associées aux joueurs lorsque cette association est disponible.
- La langue de l’interface et celle du jeu peuvent être choisies séparément. Le tracker tente de détecter la langue du jeu dans la configuration Steam, sans modifier celle-ci ; des langues supplémentaires sont disponibles pour l’interface.
- Le guide de récupération du profil détaille les étapes dans le menu du jeu et présente les éléments de l’interface à utiliser avant la vérification et l’enregistrement du personnage.
- La détection des événements de combat et des participants a été revue pour les transitions entre arène, invasion et défense, notamment lorsque certaines notifications intermédiaires ont été manquées.
- La capture dédiée à la recherche du logo Steam a été retirée de la boucle normale. La détection de l’overlay Steam reste active et l’accès à l’écran est vérifié avant de conclure à la fermeture du jeu pendant un combat.
- Les messages du suivi disposent d’une lecture indépendante pour chaque fenêtre du tracker : un onglet ne retire plus les nouveaux événements destinés aux autres, et deux événements identiques successifs peuvent être affichés.
- La section **Configuration → Données du tracker** regroupe les réglages de conservation des captures et de l’historique Steam, ainsi que les commandes d’archivage, de restauration et de purge de l’historique. Une archive peut être supprimée individuellement après confirmation ; ces opérations exigent l’arrêt du suivi.
- La navigation de Configuration a été harmonisée : les sections utilisent des boutons accessibles au clavier et le classement en ligne se trouve à côté du profil.
- Les diagnostics Steam distinguent la demande d’activation du journal et l’observation du fichier, afin de faciliter l’identification des problèmes de détection des joueurs et du ping.
- Le suivi reprend les joueurs déjà connectés lorsque les événements nécessaires sont disponibles dans le journal Steam, et peut récupérer progressivement les avatars historiques disponibles.
- Les informations de classement et les badges disponibles sont actualisés sans bloquer l’interface ; la participation et le partage du profil Steam restent contrôlés par les réglages du joueur.
