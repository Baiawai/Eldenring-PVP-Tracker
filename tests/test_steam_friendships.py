import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SteamFriendshipTests(unittest.TestCase):
    def test_local_friendships_and_automatic_category(self):
        with tempfile.TemporaryDirectory(prefix='tracker-friend-test-') as folder:
            env = dict(os.environ, APPDATA=folder, LOCALAPPDATA=folder, PYTHONPATH=str(ROOT))
            result = subprocess.run([sys.executable, str(ROOT / 'tests/support/exercise_steam_friendships.py')],
                                    cwd=ROOT, env=env, capture_output=True, text=True, encoding='utf-8', timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
