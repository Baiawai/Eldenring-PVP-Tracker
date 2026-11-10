import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class OnlineLeaderboardTests(unittest.TestCase):
    def test_consent_and_deletion_retry_in_isolated_data_directory(self):
        with tempfile.TemporaryDirectory(prefix='leaderboard-test-') as directory:
            env = os.environ.copy()
            env['APPDATA'] = directory
            env['PYTHONPATH'] = str(ROOT)
            result = subprocess.run([sys.executable, str(ROOT / 'tests' / 'support' / 'exercise_online_leaderboard.py')], cwd=ROOT, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=40)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
