import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PlayerCaptureTests(unittest.TestCase):
    def test_player_capture_associations_in_isolated_data(self):
        with tempfile.TemporaryDirectory(prefix='tracker-player-captures-', ignore_cleanup_errors=True) as folder:
            env = dict(os.environ, APPDATA=folder, LOCALAPPDATA=folder, PYTHONPATH=str(ROOT))
            result = subprocess.run([sys.executable, str(ROOT / 'tests/support/exercise_player_captures.py')],
                                    cwd=ROOT, env=env, capture_output=True, text=True, encoding='utf-8', timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
