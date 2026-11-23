"""Test bounded historical avatar scheduling without contacting Steam."""
import os
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSC = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'


@unittest.skipUnless(os.name == 'nt' and CSC.is_file(), 'Requires Windows .NET Framework compiler')
class SteamAvatarRequestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='tracker-historical-avatar-test-')
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.harness = Path(cls.temporary.name) / 'avatar-requests.exe'
        result = subprocess.run([str(CSC), '/nologo', '/target:exe', '/out:' + str(cls.harness),
                                 str(ROOT / 'application/steam_peers/SteamAvatarRequests.cs'),
                                 str(ROOT / 'tests/support/steam_avatar_requests_harness.cs')],
                                capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise AssertionError('Cannot compile avatar test: ' + result.stdout + result.stderr)

    def check(self, scenario):
        result = subprocess.run([str(self.harness), scenario], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_duplicate_ids_share_one_result(self):
        self.check('dedupe')

    def test_avatar_commands_are_distinct_from_profile_commands(self):
        self.check('protocol')

    def test_queue_is_bounded_and_frees_slots(self):
        self.check('bounds')

    def test_rate_limit_and_parallel_timeout(self):
        self.check('cadence')

    def test_unavailable_can_retry_after_timeout(self):
        self.check('retry')

    def test_built_helper_is_present_and_rejects_invalid_invocation(self):
        helper = ROOT / 'application/steam_peers/TrackerSteamPeersV9.exe'
        self.assertTrue(helper.is_file(), 'Build the V9 helper before testing')
        result = subprocess.run([str(helper)], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout.lstrip('\ufeff')), {'status': 'log_missing'})


if __name__ == '__main__':
    unittest.main()
