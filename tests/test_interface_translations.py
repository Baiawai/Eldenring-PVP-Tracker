"""Keep the interface translation catalog in sync with its consumers."""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class InterfaceTranslationTests(unittest.TestCase):
    def test_all_interface_keys_exist_for_every_non_french_language(self):
        packs = json.loads((ROOT / 'application/locales/ui_packs.json').read_text(encoding='utf-8'))
        keys = set()
        for file in (ROOT / 'static').glob('*.js'):
            if file.name in ('jquery.js', 'ui-packs.js') or file.name.endswith('.min.js'):
                continue
            source = file.read_text(encoding='utf-8')
            keys.update(re.findall(r"\b(?:tr|appT|uiT)\(\s*['\"]([\w-]+)['\"]", source))
        html = (ROOT / 'templates/index.html').read_text(encoding='utf-8')
        keys.update(re.findall(r'data-i18n(?:-aria|-placeholder)?="([\w-]+)"', html))
        self.assertEqual(len(packs), 14)
        for language, pack in packs.items():
            with self.subTest(language=language):
                self.assertFalse(keys - set(pack['modern']))
                self.assertTrue(all(pack['modern'][key] for key in keys))
                self.assertGreaterEqual(len(pack['legacy']), 89)
                self.assertGreaterEqual(len(pack['counter']), 14)

    def test_browser_and_backend_use_identical_packs(self):
        backend = json.loads((ROOT / 'application/locales/ui_packs.json').read_text(encoding='utf-8'))
        source = (ROOT / 'static/ui-packs.js').read_text(encoding='utf-8').strip()
        prefix = 'window.ELDEN_UI_PACKS = '
        self.assertTrue(source.startswith(prefix) and source.endswith(';'))
        self.assertEqual(backend, json.loads(source[len(prefix):-1]))

if __name__ == '__main__':
    unittest.main()
