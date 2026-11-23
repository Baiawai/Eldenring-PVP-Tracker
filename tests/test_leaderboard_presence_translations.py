import json
import unittest
from pathlib import Path


class LeaderboardPresenceTranslationTests(unittest.TestCase):
    def test_presence_labels_cover_all_language_packs(self):
        root = Path(__file__).resolve().parents[1]
        packs = json.loads((root / 'application/locales/ui_packs.json').read_text(encoding='utf-8'))
        self.assertEqual(len(packs), 29)  # French is provided by the built-in fallback.
        for language, pack in packs.items():
            for key in ('leaderboard_tracker_active', 'online_presence_notice'):
                with self.subTest(language=language, key=key):
                    self.assertIsInstance(pack['modern'].get(key), str)
                    self.assertTrue(pack['modern'][key].strip())


if __name__ == '__main__':
    unittest.main()
