"""Exercise Store candidate verification using only synthetic ZIP archives."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zipfile

from store import verify_release_artifact as verifier


class ReleaseArtifactTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='tracker-artifact-test-')
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.package = self.root / 'synthetic.msix'
        self.version = '1.2.3.0'
        self.identity = 'Example.Tracker'
        self.publisher = 'CN=Example Publisher'
        self.catalog = {
            'eng': {'html_lang': 'en', 'modern': {'mode': 'Mode'}},
            'deu': {'html_lang': 'de', 'modern': {'mode': 'Modus'}},
        }
        self.locales = self.root / 'application' / 'locales'
        self.locales.mkdir(parents=True)
        (self.locales / 'ui_packs.json').write_text(
            json.dumps(self.catalog), encoding='utf-8')
        self.game_catalog = {'frafr': {'2610304': 'Test'}, 'engus': {'2610304': 'Test'}}
        (self.locales / 'network_messages.json').write_text(
            json.dumps(self.game_catalog), encoding='utf-8')
        self.models = self.locales / 'tessdata'
        self.models.mkdir()
        for model in verifier.GAME_OCR_MODELS:
            (self.models / (model + '.traineddata')).write_bytes(('synthetic ' + model).encode('ascii'))
        self.helper = self.root / 'application' / 'steam_peers' / 'TrackerSteamPeersV6.exe'
        self.helper.parent.mkdir(parents=True)
        self.helper.write_bytes(b'synthetic Steam helper binary')
        root = patch.object(verifier, 'ROOT', self.root)
        version = patch.object(verifier, 'APP_VERSION', self.version)
        root.start()
        version.start()
        self.addCleanup(root.stop)
        self.addCleanup(version.stop)
        self.files = {name: b'synthetic fixture' for name in verifier.REQUIRED}
        self.files['AppxManifest.xml'] = self.manifest()
        catalog = json.dumps(self.catalog, ensure_ascii=False).encode('utf-8')
        self.files['_internal/application/locales/ui_packs.json'] = catalog
        self.files['_internal/application/locales/network_messages.json'] = json.dumps(self.game_catalog).encode('utf-8')
        self.files['_internal/static/ui-packs.js'] = b'window.ELDEN_UI_PACKS = ' + catalog + b';\n'
        self.files['_internal/application/steam_peers/TrackerSteamPeersV6.exe'] = self.helper.read_bytes()
        for model in verifier.GAME_OCR_MODELS:
            self.files['_internal/application/locales/tessdata/' + model + '.traineddata'] = (
                self.models / (model + '.traineddata')).read_bytes()

    def manifest(self, *, version=None, name=None, publisher=None, languages=('fr', 'en', 'de')):
        namespace = verifier.NS['m']
        root = ET.Element('{' + namespace + '}Package')
        ET.SubElement(root, '{' + namespace + '}Identity', {
            'Name': name if name is not None else self.identity,
            'Publisher': publisher if publisher is not None else self.publisher,
            'Version': version if version is not None else self.version,
        })
        resources = ET.SubElement(root, '{' + namespace + '}Resources')
        for language in languages:
            ET.SubElement(resources, '{' + namespace + '}Resource', {'Language': language})
        return ET.tostring(root, encoding='utf-8', xml_declaration=True)

    def write_package(self, updates=None, remove=()):
        files = dict(self.files)
        files.update(updates or {})
        for name in remove:
            files.pop(name, None)
        with zipfile.ZipFile(self.package, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for name, content in files.items():
                archive.writestr(name, content)

    def test_valid_candidate_reports_version_identity_languages_and_digest(self):
        self.write_package()
        result = verifier.verify(self.package, self.identity, self.publisher)
        self.assertEqual(result, {
            'version': self.version, 'identity': self.identity, 'publisher': self.publisher,
            'languages': 3, 'sha256': hashlib.sha256(self.package.read_bytes()).hexdigest(),
        })

    def test_rejects_incorrect_version_and_incorrect_or_missing_identity(self):
        cases = [
            (self.manifest(version='1.2.2.0'), self.identity, self.publisher, 'version'),
            (self.manifest(name='Example.Other'), self.identity, self.publisher, 'identity'),
            (self.manifest(publisher='CN=Other'), self.identity, self.publisher, 'publisher'),
            (self.manifest(name=''), self.identity, self.publisher, 'identity'),
        ]
        for manifest, name, publisher, message in cases:
            with self.subTest(message=message, manifest=manifest):
                self.write_package({'AppxManifest.xml': manifest})
                with self.assertRaisesRegex(ValueError, message):
                    verifier.verify(self.package, name, publisher)

    def test_rejects_private_data_and_generated_tracker_images(self):
        for path in ('_internal/application/database_capture.db', 'nested/User.SQLITE3',
                     'logs/tracker.log', 'keys/certificate.PFX', 'nested/runtime_images/user.png',
                     '_internal/application/user.jpg', '_internal/application/simple_notif_2.jpg'):
            with self.subTest(path=path):
                self.write_package({path: b'synthetic private data'})
                with self.assertRaisesRegex(ValueError, 'Unexpected local-data files'):
                    verifier.verify(self.package)

    def test_rejects_missing_required_files(self):
        for path in verifier.REQUIRED:
            with self.subTest(path=path):
                self.write_package(remove=(path,))
                with self.assertRaisesRegex(ValueError, 'Missing required package files'):
                    verifier.verify(self.package)

    def test_rejects_missing_or_extra_manifest_languages(self):
        for languages in (('fr', 'en'), ('fr', 'en', 'de', 'it')):
            with self.subTest(languages=languages):
                self.write_package({'AppxManifest.xml': self.manifest(languages=languages)})
                with self.assertRaisesRegex(ValueError, 'Manifest language resources'):
                    verifier.verify(self.package)

    def test_rejects_stale_and_unsynchronized_interface_catalogs(self):
        backend = '_internal/application/locales/ui_packs.json'
        frontend = '_internal/static/ui-packs.js'
        cases = [
            {backend: b'{}'},
            {frontend: b'window.ELDEN_UI_PACKS = {};'},
            {frontend: b'not a valid catalog'},
        ]
        for updates in cases:
            with self.subTest(updates=updates):
                self.write_package(updates)
                with self.assertRaisesRegex(ValueError, 'language catalogs'):
                    verifier.verify(self.package)

    def test_rejects_unexpected_steam_helper_binary(self):
        self.write_package({'_internal/application/steam_peers/TrackerSteamPeersV6.exe': b'other helper'})
        with self.assertRaisesRegex(ValueError, 'Steam helper differs'):
            verifier.verify(self.package)

    def test_rejects_changed_game_message_catalog(self):
        self.write_package({'_internal/application/locales/network_messages.json': b'{}'})
        with self.assertRaisesRegex(ValueError, 'game-message catalog'):
            verifier.verify(self.package)

    def test_rejects_each_missing_or_modified_ocr_model(self):
        for model in verifier.GAME_OCR_MODELS:
            path = '_internal/application/locales/tessdata/' + model + '.traineddata'
            for is_missing in (True, False):
                with self.subTest(model=model, missing=is_missing):
                    self.write_package(remove=(path,) if is_missing else (),
                                       updates={} if is_missing else {path: b'wrong model'})
                    with self.assertRaisesRegex(ValueError, 'OCR model is missing or differs'):
                        verifier.verify(self.package)


if __name__ == '__main__':
    unittest.main()
