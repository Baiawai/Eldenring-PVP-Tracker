import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SteamDiagnosticTranslationTests(unittest.TestCase):
    def test_every_diagnostic_message_has_a_french_fallback_and_all_packs(self):
        source = (ROOT / 'static/steam-peers.js').read_text(encoding='utf-8')
        messages = dict(re.findall(r"['\"](steam_diag_[a-z_]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]", source))
        expected = {
            'steam_diag_log_label', 'steam_diag_log_unknown', 'steam_diag_log_missing',
            'steam_diag_log_unreadable', 'steam_diag_log_waiting', 'steam_diag_log_receiving',
        }
        self.assertEqual(set(messages), expected)
        self.assertTrue(all(value.strip() for value in messages.values()))
        packs = json.loads((ROOT / 'application/locales/ui_packs.json').read_text(encoding='utf-8'))
        script = (ROOT / 'static/ui-packs.js').read_text(encoding='utf-8')
        self.assertEqual(packs, json.loads(script.removeprefix('window.ELDEN_UI_PACKS = ').strip().removesuffix(';')))
        self.assertEqual(len(packs), 29)  # French uses the explicit fallbacks above.
        for language, pack in packs.items():
            for key in expected:
                with self.subTest(language=language, key=key):
                    self.assertIsInstance(pack['modern'].get(key), str)
                    self.assertTrue(pack['modern'][key].strip())


if __name__ == '__main__':
    unittest.main()
