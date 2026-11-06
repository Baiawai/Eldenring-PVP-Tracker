import importlib.util
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

    def test_store_never_queues_or_launches_elevation(self):
        p = self.peers
        p.FROZEN = True
        p._started = True
        process = Mock()
        p._process = process
        with patch.object(p, 'enabled', return_value=True), patch.object(p.shell, 'ShellExecuteEx') as launch:
            self.assertTrue(p.request_auto_ping())
            self.assertFalse(p.activate_ping())
            self.assertFalse(p._ask_elevation)
            self.assertEqual(p.snapshot()['ping_mode'], 'steam_only')
            with self.assertRaises(RuntimeError):
                p._elevated_stream('unused')
            process.terminate.assert_not_called()
            launch.assert_not_called()

    def test_source_run_keeps_advanced_ping(self):
        p = self.peers
        p.FROZEN = False
        p._started = True
        with patch.object(p, 'enabled', return_value=True):
            self.assertTrue(p.request_auto_ping())
            self.assertTrue(p._ask_elevation)
            self.assertNotEqual(p.snapshot()['ping_mode'], 'steam_only')

