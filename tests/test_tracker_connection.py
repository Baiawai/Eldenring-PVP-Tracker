import shutil
import subprocess
import unittest
from pathlib import Path


class TrackerConnectionTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node is not installed')
    def test_disconnection_and_restart_reuse_the_existing_tab(self):
        root = Path(__file__).resolve().parents[1]
        subprocess.run(['node', 'tests/test_tracker_connection.js'], cwd=root,
                       check=True, capture_output=True, text=True)
