import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class FrontendLanguageTableTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node is not installed')
    def test_tracker_actions_support_running_previous_backend(self):
        result = subprocess.run(['node', 'tests/test_tracker_action.js'], cwd=ROOT,
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    @unittest.skipUnless(shutil.which('node'), 'Node is not installed')
    def test_translation_requests_do_not_restore_stale_languages(self):
        result = subprocess.run(['node', 'tests/test_table_language.js'], cwd=ROOT,
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
