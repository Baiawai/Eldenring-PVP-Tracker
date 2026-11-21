"""Keep the reviewable GitHub notes consistent with all Store languages."""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class GithubReleaseNotesTests(unittest.TestCase):
    def test_all_thirty_languages_match_the_reviewed_store_notes(self):
        store = (ROOT / 'store/notes-de-version-1.0.10.0.md').read_text(encoding='utf-8')
        github = (ROOT / 'release/github-notes-1.0.10.0.md').read_text(encoding='utf-8')
        section = re.compile(r'^## ([^\n]+)\n\n([\s\S]*?)(?=^## |\Z)', re.MULTILINE)
        expected = [(match.group(1), match.group(2).strip()) for match in section.finditer(store)]
        self.assertEqual(len(expected), 30)
        self.assertEqual(len({title for title, _ in expected}), 30)
        self.assertTrue(github.startswith('# Elden PVP Tracker 1.0.10.0\n'))
        for title, body in expected[:2]:
            self.assertEqual(github.count('## ' + title + '\n'), 1, title)
            self.assertIn('## ' + title + '\n\n' + body, github)
        for title, body in expected[2:]:
            self.assertEqual(github.count('<summary>' + title + '</summary>'), 1, title)
            self.assertIn('<summary>' + title + '</summary>\n\n' + body + '\n\n</details>', github)
        self.assertEqual(github.count('<details>'), 28)
        self.assertEqual(github.count('</details>'), 28)


if __name__ == '__main__':
    unittest.main()
