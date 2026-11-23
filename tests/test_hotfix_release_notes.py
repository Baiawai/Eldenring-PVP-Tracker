"""Validate localized 1.0.11.0 notes before preparing Store listings."""
import re
import unittest
from pathlib import Path

from store.prepare_listing_csv import LOCALES, _load_drafts


ROOT = Path(__file__).resolve().parents[1]


class HotfixReleaseNotesTests(unittest.TestCase):
    def test_store_covers_all_locales_and_github_is_french_only(self):
        notes = _load_drafts(ROOT / 'store/notes-de-version-1.0.11.0.md', 1500)
        github = (ROOT / 'release/github-notes-1.0.11.0.md').read_text(encoding='utf-8')
        self.assertEqual(set(notes), {locale.casefold() for locale in LOCALES})
        self.assertTrue(github.startswith('# Elden PVP Tracker 1.0.11.0\n'))
        self.assertNotIn('## English', github)
        self.assertNotIn('<details>', github)
        for locale, note in notes.items():
            with self.subTest(locale=locale):
                self.assertTrue(note.startswith('- '))
                self.assertGreater(len(note), 50)
                bullets = [line for line in note.splitlines() if line.strip()]
                self.assertGreaterEqual(len(bullets), 10)
                self.assertTrue(all(line.startswith('- ') for line in bullets))
                self.assertIn('Microsoft Store', bullets[1])
                self.assertIn('SteamID', bullets[3])
                self.assertNotRegex(note, r'\{[^{}]+\}|<\?[^>]+\?>')
        for bullet in notes['fr-fr'].splitlines()[:4]:
            self.assertIn(bullet, github)

    def test_previous_github_release_is_french_only(self):
        notes = (ROOT / 'release/github-notes-1.0.10.0.md').read_text(encoding='utf-8')
        self.assertIn('## Français (fr-FR)', notes)
        self.assertNotIn('## English', notes)
        self.assertNotIn('<details>', notes)


if __name__ == '__main__':
    unittest.main()
