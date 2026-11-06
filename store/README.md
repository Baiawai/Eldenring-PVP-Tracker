# Construction et examen Store

La préparation actuelle ne constitue pas une version prête à soumettre. Dans la version compilée, le classement en ligne et ses appels réseau sont désactivés. La mesure avec élévation est désactivée : seul le ping disponible auprès de Steam est affiché ; il peut être indisponible. La version lancée depuis les sources conserve son comportement. Vérifier les droits sur les ressources du jeu, les images, polices, données et toutes les licences des dépendances redistribuées, notamment les DLL Tesseract.

Sur Windows x64, installer Python 3.12, créer `.venv`, installer `requirements.txt` puis `pyinstaller==6.16.0`. Installer le SDK Windows avec MakeAppx et fournir une distribution Tesseract x64 complète avec ses licences dans `C:\Program Files\Tesseract-OCR` (ou utiliser `-TesseractDir`). Les modèles OCR du projet sont embarqués. La compilation n'inclut pas les captures personnelles présentes dans `application`.

Après réservation du nom dans Partner Center, reprendre exactement le nom d'identité du package, le sujet Publisher et le nom d'éditeur communiqués par Partner Center :

```powershell
.\store\build.ps1 -Identity 'IDENTITE_PARTNER_CENTER' -Publisher 'CN=SUJET_PARTNER_CENTER' -PublisherDisplay 'NOM_EDITEUR' -Version '1.0.2.0'
```

Le fichier MSIX non signé est créé dans `dist/store/`. `-ExecutableOnly` construit uniquement l'exécutable et ses ressources. Une signature de test et un certificat approuvé sont nécessaires pour tester l'installation sur une machine ordinaire ; Microsoft signe le package publié après certification. Tester l'installation, le démarrage, les mises à jour, la désinstallation, les modes de suivi et la capture en plein écran avec Steam et le jeu avant la soumission. Ne pas lancer l'exécutable parallèlement à un tracker actif, car les deux utilisent le port 5000.

Le contrôle `.\.venv\Scripts\python.exe store\smoke_test.py` utilise un APPDATA temporaire et interroge l'interface sans ouvrir de port. Il nécessite l'accès à WMI ; il ne remplace pas un essai de capture en jeu ou du package installé.

Renseigner la fiche Store, ses captures et une URL publique de politique de confidentialité. Celle-ci doit décrire les captures d'écran, les données conservées localement (dont historique Steam et adresses IP éventuelles), l'identifiant construit à partir de l'adresse MAC et du nom de machine, et les données réellement transmises au service de classement lorsqu'il est utilisé. Vérifier ses destinataires et durées de conservation. L'application utilise un serveur HTTP sur localhost et possède des routes de modification : examiner leur protection contre les requêtes non sollicitées d'autres pages locales ou sites web avant publication. L'installation MSIX peut isoler ou rediriger les données existantes : tester la migration et la désinstallation sur une copie, sans toucher aux données réelles.

Sources Microsoft : [préparation d'une application de bureau](https://learn.microsoft.com/en-us/windows/uwp/porting/desktop-to-uwp-prepare), [envoi du package](https://learn.microsoft.com/en-us/windows/apps/publish/publish-your-app/msix/upload-app-packages), [test d'un package](https://learn.microsoft.com/en-us/windows/msix/desktop/desktop-to-uwp-debug).
