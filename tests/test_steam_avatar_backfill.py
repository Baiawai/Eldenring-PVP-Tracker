import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SteamAvatarBackfillTests(unittest.TestCase):
    def test_recovery_in_isolated_data_directory(self):
        with tempfile.TemporaryDirectory(prefix='tracker-avatar-backfill-') as folder:
            env = dict(os.environ, APPDATA=folder, LOCALAPPDATA=folder, PYTHONPATH=str(ROOT))
            result = subprocess.run([sys.executable, str(ROOT / 'tests/support/exercise_avatar_backfill.py')],
                                    cwd=ROOT, env=env, capture_output=True, text=True, encoding='utf-8', timeout=45)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
