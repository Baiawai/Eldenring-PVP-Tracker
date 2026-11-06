import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class StoreManifestTests(unittest.TestCase):
    def test_publisher_display_name_is_plain_xml_text(self):
        with tempfile.TemporaryDirectory() as directory:
            subprocess.run([sys.executable, str(ROOT / 'store/create_manifest.py'),
                            '--package-dir', directory, '--identity', 'Example.Tracker',
                            '--publisher', 'CN=Example', '--publisher-display', 'A & B',
                            '--version', '1.0.0.0', '--icon', str(ROOT / 'baia.ico')],
                           check=True)
            root = ET.parse(Path(directory) / 'AppxManifest.xml').getroot()
            ns = {'f': 'http://schemas.microsoft.com/appx/manifest/foundation/windows10'}
            self.assertEqual(root.findtext('f:Properties/f:PublisherDisplayName', namespaces=ns), 'A & B')
            declared = {r.attrib['Language'] for r in root.findall('f:Resources/f:Resource', ns)}
            packs = json.loads((ROOT / 'application/locales/ui_packs.json').read_text(encoding='utf-8'))
            self.assertEqual(declared, {'fr', *(pack['html_lang'] for pack in packs.values())})
