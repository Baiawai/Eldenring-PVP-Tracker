import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SettingsHelpTests(unittest.TestCase):
    def test_specific_descriptions_are_present_in_all_packs(self):
        source = (ROOT / 'static/settings-yes-no.js').read_text(encoding='utf-8')
        keys = set(re.findall(r"\['(help_[a-z_]+)', '[^']+'\]", source)) | {'help_steam_detection'}
        keys.update(re.findall(r"fieldInfo\('[^']+', '(help_[a-z_]+)', '[^']+'", source))
        self.assertGreaterEqual(len(keys), 40)
        packs = json.loads((ROOT / 'application/locales/ui_packs.json').read_text(encoding='utf-8'))
        for language, pack in packs.items():
            for key in keys:
                with self.subTest(language=language, key=key):
                    self.assertTrue(pack['modern'].get(key, '').strip())

    def test_web_pack_matches_server_pack(self):
        packs = json.loads((ROOT / 'application/locales/ui_packs.json').read_text(encoding='utf-8'))
        source = (ROOT / 'static/ui-packs.js').read_text(encoding='utf-8')
        self.assertTrue(source.startswith('window.ELDEN_UI_PACKS = '))
        self.assertEqual(packs, json.loads(source.removeprefix('window.ELDEN_UI_PACKS = ').strip().removesuffix(';')))
