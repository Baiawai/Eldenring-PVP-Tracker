"""Settings tab labels must exist in every language and match the frontend packs."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class SettingsTabTranslationTests(unittest.TestCase):
    def test_labels_are_complete_and_frontend_packs_match(self):
        backend = json.loads((ROOT / 'application/locales/ui_packs.json').read_text(encoding='utf-8'))
        script = (ROOT / 'static/ui-packs.js').read_text(encoding='utf-8').strip()
        prefix = 'window.ELDEN_UI_PACKS = '
        self.assertTrue(script.startswith(prefix) and script.endswith(';'))
        frontend = json.loads(script[len(prefix):-1])
        self.assertEqual(frontend, backend)
        keys = ('settings_tab_general', 'settings_tab_display', 'settings_tab_capture',
                'settings_tab_profile', 'settings_tab_p2p', 'settings_tab_diagnostics', 'settings_tab_exit')
        for language, pack in backend.items():
            for key in keys:
                with self.subTest(language=language, key=key):
                    self.assertTrue(pack['modern'].get(key))


if __name__ == '__main__':
    unittest.main()
