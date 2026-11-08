import importlib.util
import sqlite3
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


def load_module(database):
    init = types.ModuleType('application.init')
    init.database_setting = str(database)
    path = Path(__file__).resolve().parents[1] / 'application' / 'steam_log_auto.py'
    spec = importlib.util.spec_from_file_location('application._steam_log_auto_test', path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {'application.init': init}):
        spec.loader.exec_module(module)
    return module


class SteamLogAutoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.module = load_module(Path(self.temp.name) / 'settings.db')

    def test_setting_defaults_to_yes_and_persists(self):
        p = self.module
        self.assertTrue(p.get_enabled())
        p.set_enabled(False)
        self.assertFalse(load_module(p.database_setting).get_enabled())
        p.set_enabled(True)
        self.assertTrue(load_module(p.database_setting).get_enabled())

    def test_command_uses_fixed_filter_without_shell(self):
        p = self.module
        process = Mock(returncode=0)
        with patch.object(p.subprocess, 'Popen', return_value=process) as popen:
            self.assertTrue(p.activate(Path('steam.exe')))
        self.assertEqual(popen.call_args.args[0], ['steam.exe', '-console', '+log_ipc', p.COMMAND_FILTER])
        self.assertNotIn('shell', popen.call_args.kwargs)
        process.wait.assert_called_once_with(timeout=15)

    def test_only_once_per_steam_session_then_on_restart(self):
        p = self.module
        exe = Path('steam.exe')
        sessions = [(1, 'first', exe), (1, 'first', exe), (2, 'second', exe)]
        with patch.object(p, 'get_enabled', return_value=True), \
             patch.object(p, 'steam_session', side_effect=sessions), \
             patch.object(p, 'activate', return_value=True) as activate, \
             patch.object(p._wake, 'wait', side_effect=[None, None, StopIteration]), \
             patch.object(p._wake, 'clear'):
            with self.assertRaises(StopIteration):
                p._worker(lambda: True)
        self.assertEqual(activate.call_count, 2)

    def test_disabled_option_does_not_launch_steam(self):
        p = self.module
        with patch.object(p, 'get_enabled', return_value=False), \
             patch.object(p, 'steam_session') as session, \
             patch.object(p, 'activate') as activate, \
             patch.object(p._wake, 'wait', side_effect=StopIteration):
            with self.assertRaises(StopIteration):
                p._worker(lambda: True)
        session.assert_not_called()
        activate.assert_not_called()
