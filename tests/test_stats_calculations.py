"""Run the pure chart and counter calculation checks when Node is available."""
import shutil
import subprocess
import unittest
from pathlib import Path


class StatisticsCalculationTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node is not installed')
    def test_chart_periods_and_win_rate(self):
        subprocess.run(['node', str(Path(__file__).with_suffix('.js'))], check=True, capture_output=True, text=True)
