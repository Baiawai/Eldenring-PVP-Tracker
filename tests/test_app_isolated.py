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
            restored = subprocess.run([sys.executable, '-c',
                "from flask import Flask; app=Flask(__name__); from application.notification_sample import load; from application.notification_region import load_locked_bounds,manual_mode; sample=load(); assert sample and sample['language']=='frafr' and sample['lines']==2 and sample['image']; assert load_locked_bounds()==(.1,.9) and manual_mode() is False"],
                cwd=ROOT, env=environment, capture_output=True, text=True,
                encoding='utf-8', errors='replace', timeout=60)
            self.assertEqual(restored.returncode, 0, restored.stdout + restored.stderr)
