import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ProfileGuideTranslationTests(unittest.TestCase):
    def test_guide_has_complete_localized_labels_in_every_pack(self):
        packs = json.loads((ROOT / 'application/locales/ui_packs.json').read_text(encoding='utf-8'))
        keys = ('profile_guide_title', 'profile_guide_visual_label',
                'profile_guide_menu_visual_label', 'profile_guide_profile_visual_label',
                *(f'profile_guide_step_{number}' for number in range(1, 6)))
        self.assertEqual(len(packs), 29)  # French uses the interface's built-in fallback.
        english = packs['eng']['modern']
        for code, pack in packs.items():
            for key in keys:
                with self.subTest(language=code, key=key):
                    value = pack['modern'].get(key)
                    self.assertIsInstance(value, str)
                    self.assertTrue(value.strip())
                    if code != 'eng':
                        self.assertNotEqual(value, english[key], 'Guide text fell back to English')


if __name__ == '__main__':
    unittest.main()
