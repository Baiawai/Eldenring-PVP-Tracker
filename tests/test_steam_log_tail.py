"""Test the real C# Steam log tail with synthetic files, no Steam required."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
CSC = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'


@unittest.skipUnless(os.name == 'nt' and CSC.is_file(), 'Requires the Windows .NET Framework C# compiler')
class SteamLogTailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='tracker-steam-log-test-')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.harness = Path(cls.temp.name) / 'SteamLogTailHarness.exe'
        result = subprocess.run(
            [str(CSC), '/nologo', '/target:exe', '/out:' + str(cls.harness),
             str(ROOT / 'application/steam_peers/SteamLogTail.cs'),
             str(ROOT / 'tests/support/steam_log_tail_harness.cs')],
            capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise AssertionError('Cannot compile isolated log test: ' + result.stdout + result.stderr)

    def run_scenario(self, scenario):
        result = subprocess.run([str(self.harness), scenario], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_existing_connections_and_ordered_events(self):
        self.run_scenario('startup')

    def test_incomplete_final_line_waits_for_completion(self):
        self.run_scenario('partial')

    def test_replaced_log_of_identical_length_is_detected(self):
        self.run_scenario('rotation')

    def test_truncation_discards_prior_candidates(self):
        self.run_scenario('truncation')

    def test_only_recent_history_is_replayed(self):
        self.run_scenario('history')

    def test_log_created_after_startup_is_replayed(self):
        self.run_scenario('missing')


if __name__ == '__main__':
    unittest.main()
