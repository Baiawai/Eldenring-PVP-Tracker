"""Integration checks in a subprocess with a private APPDATA and no listener."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class IsolatedApplicationTests(unittest.TestCase):
    def test_routes_initialize_and_preserve_mode_settings(self):
        with tempfile.TemporaryDirectory(prefix='tracker-isolated-test-') as directory:
            environment = os.environ.copy()
            environment['APPDATA'] = directory
            result = subprocess.run([sys.executable, str(ROOT / 'tests' / 'support' / 'exercise_app.py')],
                                    cwd=ROOT, env=environment, capture_output=True, text=True,
                                    encoding='utf-8', errors='replace', timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

