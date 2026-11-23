"""Check a built Store candidate without installing it or accessing user data."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from application.version import APP_VERSION

NS = {'m': 'http://schemas.microsoft.com/appx/manifest/foundation/windows10'}
REQUIRED = (
    'EldenRingTracker.exe', 'AppxManifest.xml', 'tesseract/tesseract.exe',
    'tesseract/doc/LICENSE', '_internal/application/store-build.marker',
    '_internal/application/locales/ui_packs.json', '_internal/application/locales/network_messages.json',
    '_internal/application/steam_peers/TrackerSteamPeersV9.exe',
    '_internal/application/steam_peers/LICENSE-SteamP2PInfo.txt',
    '_internal/static/ui-packs.js', '_internal/static/overlay-settings.js',
    '_internal/static/overlay-country-flags.png', '_internal/templates/index.html',
)
PRIVATE_SUFFIXES = ('.db', '.sqlite', '.sqlite3', '.log', '.pfx', '.p12', '.key')
RUNTIME_IMAGE_NAMES = {
    'steam.jpg', 'template_notif.jpg', 'start_.jpg', 'finish_.jpg', 'user.jpg', 'user_panel.jpg',
}
# Two Spanish game locales share one OCR model.
GAME_OCR_MODELS = ('ara', 'chi_sim', 'chi_tra', 'deu', 'eng', 'fra', 'ita',
                   'jpn', 'kor', 'pol', 'por', 'rus', 'spa', 'tha')


def verify(path, expected_identity=None, expected_publisher=None):
    with zipfile.ZipFile(path) as package:
        names = set(package.namelist())
        missing = sorted(set(REQUIRED) - names)
        if missing:
            raise ValueError('Missing required package files: ' + ', '.join(missing))
        private = []
        for name in names:
            lower = name.lower()
            filename = lower.rsplit('/', 1)[-1]
            if (lower.endswith(PRIVATE_SUFFIXES) or '/runtime_images/' in lower or
                    (lower.startswith('_internal/application/') and
                     (filename in RUNTIME_IMAGE_NAMES or filename.startswith(('simple_', 'simple_notif_')) and filename.endswith('.jpg')))):
                private.append(name)
        if private:
            raise ValueError('Unexpected local-data files in package: ' + ', '.join(sorted(private)))
        if package.testzip() is not None:
            raise ValueError('Package contains a corrupted ZIP entry')
        root = ET.fromstring(package.read('AppxManifest.xml'))
        identity = root.find('m:Identity', NS)
        if identity is None or identity.get('Version') != APP_VERSION:
            raise ValueError('Manifest version does not match application/version.py')
        if expected_identity and identity.get('Name') != expected_identity:
            raise ValueError('Manifest package identity does not match the expected identity')
        if expected_publisher and identity.get('Publisher') != expected_publisher:
            raise ValueError('Manifest publisher does not match the expected publisher')
        packed = json.loads(package.read('_internal/application/locales/ui_packs.json'))
        source = json.loads((ROOT / 'application/locales/ui_packs.json').read_text(encoding='utf-8'))
        js = package.read('_internal/static/ui-packs.js').decode('utf-8').strip()
        prefix = 'window.ELDEN_UI_PACKS = '
        if packed != source or not js.startswith(prefix) or not js.endswith(';') or json.loads(js[len(prefix):-1]) != source:
            raise ValueError('Package language catalogs are missing, stale or out of sync')
        expected_languages = {'fr', *(pack['html_lang'] for pack in source.values())}
        declared = {element.get('Language') for element in root.findall('m:Resources/m:Resource', NS)}
        if declared != expected_languages:
            raise ValueError('Manifest language resources do not match the interface languages')
        catalog = '_internal/application/locales/network_messages.json'
        source_catalog = ROOT / 'application/locales/network_messages.json'
        if json.loads(package.read(catalog)) != json.loads(source_catalog.read_text(encoding='utf-8')):
            raise ValueError('Package game-message catalog differs from the checked source')
        for model in GAME_OCR_MODELS:
            relative = 'application/locales/tessdata/' + model + '.traineddata'
            name = '_internal/' + relative
            if name not in names or hashlib.sha256(package.read(name)).digest() != hashlib.sha256((ROOT / relative).read_bytes()).digest():
                raise ValueError('Package OCR model is missing or differs from source: ' + model)
        helper = '_internal/application/steam_peers/TrackerSteamPeersV9.exe'
        if package.read(helper) != (ROOT / 'application/steam_peers/TrackerSteamPeersV9.exe').read_bytes():
            raise ValueError('Package Steam helper differs from the checked source artifact')
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return {'version': APP_VERSION, 'languages': len(expected_languages),
            'identity': identity.get('Name'), 'publisher': identity.get('Publisher'),
            'sha256': digest.hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    parser.add_argument('--identity')
    parser.add_argument('--publisher')
    args = parser.parse_args()
    try:
        result = verify(args.package, args.identity, args.publisher)
    except (OSError, ValueError, ET.ParseError, zipfile.BadZipFile) as exc:
        parser.exit(1, 'Release verification failed: ' + str(exc) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
