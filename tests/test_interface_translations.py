"""Keep the interface translation catalog in sync with its consumers."""
import json
import re
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class InterfaceTranslationTests(unittest.TestCase):
    def test_main_template_accessible_labels_have_translations(self):
        class Labels(HTMLParser):
            missing = []

            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                for attribute, key in (('aria-label', 'data-i18n-aria'),
                                       ('placeholder', 'data-i18n-placeholder')):
                    if attrs.get(attribute) and not attrs.get(key):
                        self.missing.append((self.getpos()[0], attribute))

        parser = Labels()
        parser.feed((ROOT / 'templates/index.html').read_text(encoding='utf-8'))
        self.assertEqual(parser.missing, [])

    def test_korean_basic_controls_are_not_corrupted(self):
        packs = json.loads((ROOT / 'application/locales/ui_packs.json').read_text(encoding='utf-8'))
        korean = packs['kor']
        self.assertEqual(korean['legacy'][44:46], ['아니요', '예'])
        self.assertEqual([korean['counter'][i] for i in (0, 2, 4)],
                         ['시작', '중지', '불러오는 중...'])

    def test_all_interface_keys_exist_for_every_non_french_language(self):
        packs = json.loads((ROOT / 'application/locales/ui_packs.json').read_text(encoding='utf-8'))
        keys = set()
        for file in (ROOT / 'static').glob('*.js'):
            if file.name in ('jquery.js', 'ui-packs.js') or file.name.endswith('.min.js'):
                continue
            source = file.read_text(encoding='utf-8')
            keys.update(re.findall(r"\b(?:t|tr|appT|uiT)\(\s*['\"]([\w-]+)['\"]", source))
            keys.update(re.findall(r'data-online=["\']([\w-]+)["\']', source))
        html = (ROOT / 'templates/index.html').read_text(encoding='utf-8')
        keys.update(re.findall(r'data-i18n(?:-aria|-placeholder|-title)?="([\w-]+)"', html))
        self.assertEqual(len(packs), 14)
        for language, pack in packs.items():
            with self.subTest(language=language):
                self.assertFalse(keys - set(pack['modern']))
                self.assertTrue(all(pack['modern'][key] for key in keys))
                self.assertGreaterEqual(len(pack['legacy']), 89)
                self.assertGreaterEqual(len(pack['counter']), 14)

    def test_every_catalog_contains_all_modern_keys(self):
        packs = json.loads((ROOT / 'application/locales/ui_packs.json').read_text(encoding='utf-8'))
        english_keys = set(packs['eng']['modern'])
        for language, pack in packs.items():
            with self.subTest(language=language):
                self.assertEqual(set(pack['modern']), english_keys)
                self.assertTrue(all(pack['modern'].values()))

    def test_modern_translation_placeholders_match_english(self):
        packs = json.loads((ROOT / 'application/locales/ui_packs.json').read_text(encoding='utf-8'))
        placeholders = lambda text: sorted(re.findall(r'\{\w+\}|%[sd]', text))
        for language, pack in packs.items():
            for key, english in packs['eng']['modern'].items():
                if key in pack['modern']:
                    with self.subTest(language=language, key=key):
                        self.assertEqual(placeholders(pack['modern'][key]), placeholders(english))

    def test_arabic_consent_preserves_pvp_acronym(self):
        packs = json.loads((ROOT / 'application/locales/ui_packs.json').read_text(encoding='utf-8'))
        self.assertIn('PvP', packs['ara']['modern']['online_consent_text'])

    def test_browser_and_backend_use_identical_packs(self):
        backend = json.loads((ROOT / 'application/locales/ui_packs.json').read_text(encoding='utf-8'))
        source = (ROOT / 'static/ui-packs.js').read_text(encoding='utf-8').strip()
        prefix = 'window.ELDEN_UI_PACKS = '
        self.assertTrue(source.startswith(prefix) and source.endswith(';'))
        self.assertEqual(backend, json.loads(source[len(prefix):-1]))

if __name__ == '__main__':
    unittest.main()
