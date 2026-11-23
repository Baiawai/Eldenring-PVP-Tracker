"""Keep the French GitHub notes consistent with the French Store draft."""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class GithubReleaseNotesTests(unittest.TestCase):
    def test_github_contains_only_the_french_store_notes(self):
        store = (ROOT / 'store/notes-de-version-1.0.10.0.md').read_text(encoding='utf-8')
        github = (ROOT / 'release/github-notes-1.0.10.0.md').read_text(encoding='utf-8')
        section = re.compile(r'^## ([^\n]+)\n\n([\s\S]*?)(?=^## |\Z)', re.MULTILINE)
        expected = [(match.group(1), match.group(2).strip()) for match in section.finditer(store)]
        self.assertEqual(len(expected), 30)
        self.assertEqual(len({title for title, _ in expected}), 30)
        self.assertTrue(github.startswith('# Elden PVP Tracker 1.0.10.0\n'))
        title, body = expected[0]
        self.assertEqual(title, 'Français (fr-FR)')
        self.assertEqual(github.strip(), '# Elden PVP Tracker 1.0.10.0\n\n## ' + title + '\n\n' + body)


if __name__ == '__main__':
    unittest.main()
