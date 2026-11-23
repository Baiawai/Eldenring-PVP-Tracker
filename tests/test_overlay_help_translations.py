"""Overlay setting help stays available in every supported UI language."""
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class OverlayHelpTranslationTests(unittest.TestCase):
    def test_every_overlay_setting_has_localized_help(self):
        source = (ROOT / 'static/overlay-settings.js').read_text(encoding='utf-8')
        definitions = re.search(r'const definitions = \[(.*?)\n\s*\];', source, re.S)
        self.assertIsNotNone(definitions)
        options = re.findall(r"^\s*\['([a-z_]+)'", definitions.group(1), re.M)
        self.assertEqual(len(options), len(set(options)))
        self.assertIn('visibility_mode', options)
        self.assertIn('show_tracker_user', options)
        help_keys = {'overlay_info_' + option for option in options}
        help_keys.remove('overlay_info_visibility_mode')
        help_keys.update(('overlay_visibility_help', 'tracker_member_privacy', 'game_overlay_help'))

        packs = json.loads((ROOT / 'application/locales/ui_packs.json').read_text(encoding='utf-8'))
        self.assertEqual(len(packs), 29)  # French is supplied by the UI fallback.
        for language, pack in packs.items():
            for key in help_keys:
                with self.subTest(language=language, key=key):
                    value = pack['modern'].get(key)
                    self.assertIsInstance(value, str)
                    self.assertTrue(value.strip())

    def test_browser_catalog_matches_json(self):
        packs = json.loads((ROOT / 'application/locales/ui_packs.json').read_text(encoding='utf-8'))
        script = (ROOT / 'static/ui-packs.js').read_text(encoding='utf-8').strip()
        prefix = 'window.ELDEN_UI_PACKS = '
        self.assertTrue(script.startswith(prefix) and script.endswith(';'))
        self.assertEqual(json.loads(script[len(prefix):-1]), packs)


if __name__ == '__main__':
    unittest.main()
