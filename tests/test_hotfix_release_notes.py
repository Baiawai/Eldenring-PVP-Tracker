"""Validate localized 1.0.11.0 notes before preparing Store listings."""
import re
import unittest
from pathlib import Path

from store.prepare_listing_csv import LOCALES, _load_drafts


ROOT = Path(__file__).resolve().parents[1]


class HotfixReleaseNotesTests(unittest.TestCase):
    def test_store_and_github_cover_the_same_30_locales(self):
        notes = _load_drafts(ROOT / 'store/notes-de-version-1.0.11.0.md', 1500)
        github = (ROOT / 'release/github-notes-1.0.11.0.md').read_text(encoding='utf-8')
        self.assertEqual(set(notes), {locale.casefold() for locale in LOCALES})
        self.assertTrue(github.startswith('# Elden PVP Tracker 1.0.11.0\n'))
        self.assertEqual(github.count('<details>'), 28)
        self.assertEqual(github.count('</details>'), 28)
        for locale, note in notes.items():
            with self.subTest(locale=locale):
                self.assertTrue(note.startswith('- '))
                self.assertGreater(len(note), 50)
                bullets = [line for line in note.splitlines() if line.strip()]
                self.assertEqual(len(bullets), 4)
                self.assertTrue(all(line.startswith('- ') for line in bullets))
                self.assertIn('Microsoft Store', bullets[1])
                self.assertIn('SteamID', bullets[3])
                self.assertEqual(github.count(note), 1)
                self.assertNotRegex(note, r'\{[^{}]+\}|<\?[^>]+\?>')


if __name__ == '__main__':
    unittest.main()
