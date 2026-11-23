import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from application.steam_log_diagnostics import LogProbe


class SteamLogDiagnosticsTests(unittest.TestCase):
    def test_missing_readable_change_and_silence_do_not_read_contents(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'ipc_SteamClient.log'
            now = [10.0]
            probe = LogProbe(lambda: now[0])
            self.assertEqual(probe.observe(path), 'missing')
            path.write_bytes(b'synthetic log')
            self.assertEqual(probe.observe(path), 'waiting')
            path.write_bytes(b'synthetic log with a new line\n')
            now[0] += 1
            self.assertEqual(probe.observe(path), 'receiving')
            now[0] += 179
            self.assertEqual(probe.observe(path), 'receiving')
            now[0] += 1
            self.assertEqual(probe.observe(path), 'waiting')
            self.assertEqual(probe.observe(None), 'unknown')

    def test_access_denied_is_not_reported_as_missing(self):
        with patch.object(Path, 'open', side_effect=PermissionError('denied')):
            self.assertEqual(LogProbe().observe(Path('fake.log')), 'unreadable')

    def test_different_file_does_not_inherit_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            first, second = Path(directory) / 'one', Path(directory) / 'two'
            first.write_bytes(b'1')
            second.write_bytes(b'2')
            probe = LogProbe()
            self.assertEqual(probe.observe(first), 'waiting')
            first.write_bytes(b'11')
            self.assertEqual(probe.observe(first), 'receiving')
            self.assertEqual(probe.observe(second), 'waiting')


if __name__ == '__main__':
    unittest.main()
