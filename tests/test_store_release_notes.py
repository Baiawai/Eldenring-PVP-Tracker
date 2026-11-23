"""Check completeness and Store field size for the prepared release notes."""
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOTES = ROOT / 'store' / 'notes-de-version-1.0.10.0.md'
DESCRIPTIONS = ROOT / 'store' / 'descriptions-fiche-1.0.10.0.md'

# Map the app's codes to the regional listing labels used in the notes. A
# Partner Center listing may use additional market-specific locale variants.
LOCALES = {
    'fra': 'fr-FR', 'eng': 'en-US', 'deu': 'de-DE', 'ita': 'it-IT',
    'por': 'pt-BR', 'pol': 'pl-PL', 'rus': 'ru-RU', 'jap': 'ja-JP',
    'kor': 'ko-KR', 'chi': 'zh-CN', 'zht': 'zh-TW', 'tha': 'th-TH',
    'ara': 'ar-SA', 'spaes': 'es-ES', 'spaar': 'es-419', 'nld': 'nl-NL',
    'tur': 'tr-TR', 'ukr': 'uk-UA', 'ces': 'cs-CZ', 'ron': 'ro-RO',
    'hun': 'hu-HU', 'ell': 'el-GR', 'ind': 'id-ID', 'vie': 'vi-VN',
    'hin': 'hi-IN', 'swe': 'sv-SE', 'dan': 'da-DK', 'nor': 'nb-NO',
    'fin': 'fi-FI', 'ptpt': 'pt-PT',
}


class StoreReleaseNotesTests(unittest.TestCase):
    def test_every_interface_language_has_one_nonempty_store_note_within_limit(self):
        packs = json.loads((ROOT / 'application/locales/ui_packs.json').read_text(encoding='utf-8'))
        self.assertEqual(set(LOCALES), set(packs) | {'fra'})
        content = NOTES.read_text(encoding='utf-8')
        sections = re.split(r'^## [^\n]* \(([^()\n]+)\)\s*$', content, flags=re.MULTILINE)
        self.assertEqual(len(sections) % 2, 1)
        entries = list(zip(sections[1::2], sections[2::2]))
        self.assertEqual(len(entries), len(LOCALES))
        self.assertEqual({locale for locale, _ in entries}, set(LOCALES.values()))
        for locale, text in entries:
            with self.subTest(locale=locale):
                lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
                self.assertEqual(len(lines), 3)
                self.assertTrue(all(line.startswith('- ') and len(line) > 15 for line in lines))
                # UTF-16 code units are a conservative bound for supplementary characters.
                self.assertLessEqual(len('\n'.join(lines).encode('utf-16-le')) // 2, 1500)
                self.assertNotRegex(text, r'\{[^{}]+\}|<\?[^>]+\?>')

    def test_every_interface_language_has_a_store_description_within_limit(self):
        game_languages = json.loads((ROOT / 'application/locales/network_messages.json').read_text(encoding='utf-8'))
        self.assertEqual(len(LOCALES), 30)
        self.assertEqual(len(game_languages), 15)
        content = DESCRIPTIONS.read_text(encoding='utf-8')
        sections = re.split(r'^## [^\n]* \(([^()\n]+)\)\s*$', content, flags=re.MULTILINE)
        entries = list(zip(sections[1::2], sections[2::2]))
        self.assertEqual(len(entries), len(LOCALES))
        self.assertEqual({locale for locale, _ in entries}, set(LOCALES.values()))
        for locale, text in entries:
            with self.subTest(locale=locale):
                paragraphs = [paragraph.strip() for paragraph in text.strip().split('\n\n') if paragraph.strip()]
                self.assertEqual(len(paragraphs), 3)
                self.assertIn('Elden Ring PvP Tracker', paragraphs[0])
                self.assertIn('OCR', paragraphs[0])
                self.assertIn('Steam', paragraphs[1])
                self.assertRegex(paragraphs[2], r'(?<!\d)30(?!\d)')
                self.assertRegex(paragraphs[2], r'(?<!\d)15(?!\d)')
                self.assertLessEqual(len(text.strip().encode('utf-16-le')) // 2, 10000)
                self.assertNotRegex(text, r'\{[^{}]+\}|<\?[^>]+\?>')


if __name__ == '__main__':
    unittest.main()
