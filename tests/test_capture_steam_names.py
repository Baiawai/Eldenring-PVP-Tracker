"""Run capture metadata checks without touching the user's tracker data."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CaptureSteamNamesTests(unittest.TestCase):
    def test_database_and_routes_in_isolated_profile(self):
        with tempfile.TemporaryDirectory(prefix='tracker-steam-captures-') as directory:
            environment = os.environ.copy()
            environment['APPDATA'] = directory
            result = subprocess.run(
                [sys.executable, str(ROOT / 'tests' / 'support' / 'exercise_capture_steam_names.py')],
                cwd=ROOT, env=environment, capture_output=True, text=True,
                encoding='utf-8', errors='replace', timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
