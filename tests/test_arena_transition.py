"""Exercise mode transitions in a separate profile with private runtime images."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ArenaTransitionTests(unittest.TestCase):
    def test_transition_from_defense_and_secondary_ocr(self):
        with tempfile.TemporaryDirectory(prefix='tracker-arena-transition-') as temp:
            env = os.environ.copy()
            env.update(APPDATA=temp, LOCALAPPDATA=temp)
            result = subprocess.run(
                [sys.executable, str(ROOT / 'tests' / 'support' / 'exercise_arena_transition.py')],
                cwd=ROOT, env=env, capture_output=True, text=True, encoding='utf-8',
                errors='replace', timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
