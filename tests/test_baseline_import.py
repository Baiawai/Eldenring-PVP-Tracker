import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class BaselineImportTests(unittest.TestCase):
    def test_snapshot_and_retry_use_only_isolated_data(self):
        with tempfile.TemporaryDirectory(prefix='baseline-fixture-') as directory:
            env = os.environ.copy()
            env.update(APPDATA=directory, PYTHONPATH=str(ROOT))
            result = subprocess.run([sys.executable, str(ROOT / 'tests/support/exercise_baseline.py')], cwd=ROOT, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=40)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
