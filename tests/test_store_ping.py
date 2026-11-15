import importlib.util
import io
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


def load_peer_tracking():
    init = types.ModuleType('application.init')
    init.database_setting = 'unused.db'
    path = Path(__file__).resolve().parents[1] / 'application' / 'peer_tracking.py'
    spec = importlib.util.spec_from_file_location('application._peer_tracking_test', path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {'application.init': init}):
        spec.loader.exec_module(module)
    return module


class StorePingTests(unittest.TestCase):
    def setUp(self):
        self.peers = load_peer_tracking()

    def test_start_requests_elevation_for_packaged_build_too(self):
        p = self.peers
        p._started = True
        process = Mock()
        process.poll.return_value = None
        p._process = process
        with patch.object(p, 'enabled', return_value=True):
            self.assertTrue(p.request_auto_ping())
            self.assertTrue(p._ask_elevation)
            self.assertTrue(p._auto_ping_pending)
            process.terminate.assert_called_once()

    def test_manual_request_is_available_and_can_retry(self):
        p = self.peers
        p._last_elevation_failure = 'denied'
        with patch.object(p, 'enabled', return_value=True), \
             patch.object(p.ctypes.windll.user32, 'FindWindowW', return_value=1):
            self.assertTrue(p.activate_ping())
        self.assertTrue(p._ask_elevation)
        self.assertIsNone(p._last_elevation_failure)

    def test_refusal_falls_back_to_steam_and_retains_denied_status(self):
        p = self.peers
        p._ask_elevation = True
        denied = p.pywintypes.error(1223, 'ShellExecuteEx', 'cancelled')
        stream = io.StringIO('{"status":"active","ping_mode":"admin_required","peers":[]}\n')
        process = Mock()
        process.stdout = stream
        process.poll.return_value = 0
        with patch.object(p, 'enabled', return_value=True), \
             patch.object(p.ctypes.windll.user32, 'FindWindowW', return_value=1), \
             patch.object(p, '_steam_path', return_value=Path('.')), \
             patch.object(p, '_elevated_stream', side_effect=denied) as elevated, \
             patch.object(p.subprocess, 'Popen', return_value=process) as fallback, \
             patch.object(p.time, 'sleep', side_effect=[None, StopIteration]):
            with self.assertRaises(StopIteration):
                p._worker()
        elevated.assert_called_once()
        fallback.assert_called_once()
        self.assertEqual(p._snapshot['status'], 'active')
        self.assertEqual(p._snapshot['ping_mode'], 'denied')
        self.assertFalse(p._ask_elevation)

    def test_approved_helper_publishes_advanced_ping(self):
        p = self.peers
        p._ask_elevation = True
        stream = io.StringIO('{"status":"active","ping_mode":"active","peers":[{"id":"76561198000000001","name":"Test","ping":42}]}\n')
        handle, commands = Mock(), Mock()
        with patch.object(p, 'enabled', return_value=True), \
             patch.object(p.ctypes.windll.user32, 'FindWindowW', return_value=1), \
             patch.object(p, '_steam_path', return_value=Path('.')), \
             patch.object(p, '_elevated_stream', return_value=(stream, handle, commands)), \
             patch.object(p, 'country_code', return_value=None), \
             patch.object(p.time, 'sleep', side_effect=StopIteration):
            with self.assertRaises(StopIteration):
                p._worker()
        self.assertEqual(p._snapshot['status'], 'active')
        self.assertEqual(p._snapshot['ping_mode'], 'active')
        self.assertEqual(p._snapshot['peers'][0]['ping'], 42)
        commands.Close.assert_called_once()
        handle.Close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
