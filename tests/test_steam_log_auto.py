import importlib.util
import ctypes
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

    def test_elevated_steam_uses_windows_consent_and_fixed_command(self):
        p = self.module
        handle = Mock()
        with patch.object(p.subprocess, 'Popen', side_effect=ctypes.WinError(740)), \
             patch.object(p.shell, 'ShellExecuteEx', return_value={'hProcess': handle}) as launch, \
             patch.object(p.win32event, 'WaitForSingleObject', return_value=p.win32event.WAIT_OBJECT_0), \
             patch.object(p.win32process, 'GetExitCodeProcess', return_value=0):
            self.assertIs(p.activate(Path('steam.exe')), True)
        self.assertEqual(launch.call_args.kwargs['lpVerb'], 'runas')
        self.assertEqual(launch.call_args.kwargs['lpParameters'],
                         p.subprocess.list2cmdline(['-console', '+log_ipc', p.COMMAND_FILTER]))
        self.assertEqual(launch.call_args.kwargs['nShow'], p.win32con.SW_HIDE)
        handle.Close.assert_called_once()

    def test_refused_elevation_does_not_prompt_again_for_same_session(self):
        p = self.module
        with patch.object(p.subprocess, 'Popen', side_effect=ctypes.WinError(740)), \
             patch.object(p.shell, 'ShellExecuteEx', side_effect=p.pywintypes.error(1223, 'ShellExecuteEx', 'cancelled')):
            self.assertIsNone(p.activate(Path('steam.exe')))
        session = (1, 'first', Path('steam.exe'))
        with patch.object(p, 'get_enabled', return_value=True), \
             patch.object(p, 'steam_session', return_value=session), \
             patch.object(p, 'activate', return_value=None) as activate, \
             patch.object(p._wake, 'wait', side_effect=[None, StopIteration]), \
             patch.object(p._wake, 'clear'):
            with self.assertRaises(StopIteration):
                p._worker(lambda: True)
        activate.assert_called_once()

    def test_refusal_survives_transient_process_lookup_failure(self):
        p = self.module
        session = (1, 'first', Path('steam.exe'))
        with patch.object(p, 'get_enabled', return_value=True), \
             patch.object(p, 'steam_session', side_effect=[session, None, session]), \
             patch.object(p, 'activate', return_value=None) as activate, \
             patch.object(p._wake, 'wait', side_effect=[None, None, StopIteration]), \
             patch.object(p._wake, 'clear'):
            with self.assertRaises(StopIteration):
                p._worker(lambda: True)
        activate.assert_called_once_with(session[2])
        self.assertEqual(p.status(), 'refused')

    def test_refusal_survives_disable_and_reenable(self):
        p = self.module
        session = (1, 'first', Path('steam.exe'))
        with patch.object(p, 'get_enabled', side_effect=[True, False, True]), \
             patch.object(p, 'steam_session', return_value=session), \
             patch.object(p, 'activate', return_value=None) as activate, \
             patch.object(p._wake, 'wait', side_effect=[None, None, StopIteration]), \
             patch.object(p._wake, 'clear'):
            with self.assertRaises(StopIteration):
                p._worker(lambda: True)
        activate.assert_called_once_with(session[2])
        self.assertEqual(p.status(), 'refused')

    def test_request_survives_peer_detection_pause(self):
        p = self.module
        session = (1, 'first', Path('steam.exe'))
        enabled = Mock(side_effect=[True, False, True])
        with patch.object(p, 'get_enabled', return_value=True), \
             patch.object(p, 'steam_session', return_value=session), \
             patch.object(p, 'activate', return_value=True) as activate, \
             patch.object(p._wake, 'wait', side_effect=[None, None, StopIteration]), \
             patch.object(p._wake, 'clear'):
            with self.assertRaises(StopIteration):
                p._worker(enabled)
        activate.assert_called_once_with(session[2])
        self.assertEqual(p.status(), 'requested')

    def test_elevated_request_timeout_is_not_reported_as_success(self):
        p = self.module
        handle = Mock()
        with patch.object(p.shell, 'ShellExecuteEx', return_value={'hProcess': handle}), \
             patch.object(p.win32event, 'WaitForSingleObject', return_value=p.win32event.WAIT_TIMEOUT), \
             patch.object(p.win32process, 'GetExitCodeProcess') as get_exit:
            self.assertFalse(p._activate_elevated(Path('steam.exe')))
        get_exit.assert_not_called()
        handle.Close.assert_called_once()

    def test_only_failure_before_process_creation_is_definitely_not_started(self):
        p = self.module
        with patch.object(p.subprocess, 'Popen', side_effect=FileNotFoundError('missing')), \
             patch.object(p.logging, 'getLogger'):
            self.assertIs(p.activate(Path('steam.exe')), p._NOT_STARTED)
        process = Mock()
        process.wait.side_effect = OSError('wait failed')
        with patch.object(p.subprocess, 'Popen', return_value=process), \
             patch.object(p.logging, 'getLogger'):
            self.assertIs(p.activate(Path('steam.exe')), False)

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

    def test_explicit_retry_is_coalesced_and_respects_cooldown(self):
        p = self.module
        with patch.object(p, '_started', True), patch.object(p, '_state', 'requested'), \
             patch.object(p, '_last_attempt', 100.0), patch.object(p, '_retry_pending', False), \
             patch.object(p, 'get_enabled', return_value=True), \
             patch.object(p.time, 'monotonic', return_value=150.0), patch.object(p._wake, 'set') as wake:
            result = p.request_retry(lambda: True)
            self.assertEqual(result['state'], 'cooldown')
            self.assertEqual(result['retry_after_seconds'], 70)
            wake.assert_not_called()
        with patch.object(p, '_started', True), patch.object(p, '_state', 'requested'), \
             patch.object(p, '_last_attempt', 100.0), patch.object(p, '_retry_pending', False), \
             patch.object(p, 'get_enabled', return_value=True), \
             patch.object(p.time, 'monotonic', return_value=220.0), patch.object(p._wake, 'set') as wake:
            self.assertEqual(p.request_retry(lambda: True)['state'], 'queued')
            self.assertEqual(p.request_retry(lambda: True)['state'], 'cooldown')
            wake.assert_called_once()

    def test_failed_request_is_not_repeated_for_the_same_steam_session(self):
        p = self.module
        session = (1, 'same-session', Path('steam.exe'))
        with patch.object(p, 'get_enabled', return_value=True), \
             patch.object(p, 'steam_session', return_value=session), \
             patch.object(p, 'activate', return_value=False) as activate, \
             patch.object(p.time, 'monotonic', side_effect=[0, 120, 240, 360]), \
             patch.object(p._wake, 'wait', side_effect=[None, None, None, StopIteration]), \
             patch.object(p._wake, 'clear'):
            with self.assertRaises(StopIteration):
                p._worker(lambda: True)
        activate.assert_called_once_with(session[2])
        self.assertEqual(p.status(), 'failed')

    def test_prelaunch_failures_retry_at_most_twice_without_another_uac(self):
        p = self.module
        session = (1, 'same-session', Path('steam.exe'))
        with patch.object(p, 'get_enabled', return_value=True), \
             patch.object(p, 'steam_session', return_value=session), \
             patch.object(p, 'activate', return_value=p._NOT_STARTED) as activate, \
             patch.object(p.time, 'monotonic', side_effect=[0, 120, 240, 360]), \
             patch.object(p._wake, 'wait', side_effect=[None, None, None, StopIteration]), \
             patch.object(p._wake, 'clear'):
            with self.assertRaises(StopIteration):
                p._worker(lambda: True)
        self.assertEqual(activate.call_count, 3)
        self.assertEqual(activate.call_args_list[0].kwargs, {})
        self.assertEqual(activate.call_args_list[1].kwargs, {'allow_elevation': False})
        self.assertEqual(activate.call_args_list[2].kwargs, {'allow_elevation': False})
        self.assertEqual(p.status(), 'failed')

    def test_new_steam_session_gets_one_request_after_previous_failure(self):
        p = self.module
        exe = Path('steam.exe')
        sessions = [(1, 'first', exe), (1, 'first', exe), (2, 'second', exe)]
        with patch.object(p, 'get_enabled', return_value=True), \
             patch.object(p, 'steam_session', side_effect=sessions), \
             patch.object(p, 'activate', return_value=False) as activate, \
             patch.object(p._wake, 'wait', side_effect=[None, None, StopIteration]), \
             patch.object(p._wake, 'clear'):
            with self.assertRaises(StopIteration):
                p._worker(lambda: True)
        self.assertEqual(activate.call_count, 2)

    def test_retry_never_queues_if_auto_or_peer_detection_disabled(self):
        p = self.module
        with patch.object(p, 'get_enabled', return_value=False), patch.object(p._wake, 'set') as wake:
            self.assertEqual(p.request_retry(lambda: True)['state'], 'disabled')
            wake.assert_not_called()
        with patch.object(p, 'get_enabled', return_value=True), patch.object(p._wake, 'set') as wake:
            self.assertEqual(p.request_retry(lambda: False)['state'], 'disabled')
            wake.assert_not_called()

    def test_explicit_retry_can_request_again_after_refusal(self):
        p = self.module
        session = (1, 'same-session', Path('steam.exe'))
        def wait_again(_seconds):
            if p.status() == 'refused':
                p._retry_pending = True  # Equivalent to an accepted user click.
                return None
            raise StopIteration
        with patch.object(p, 'get_enabled', return_value=True), \
             patch.object(p, 'steam_session', return_value=session), \
             patch.object(p, 'activate', side_effect=[None, True]) as activate, \
             patch.object(p.time, 'monotonic', side_effect=[100, 220]), \
             patch.object(p._wake, 'wait', side_effect=wait_again), \
             patch.object(p._wake, 'clear'):
            with self.assertRaises(StopIteration):
                p._worker(lambda: True)
        self.assertEqual(activate.call_count, 2)
        self.assertEqual(p.status(), 'requested')

    def test_unexpected_activation_error_does_not_repeat_request(self):
        p = self.module
        session = (1, 'same-session', Path('steam.exe'))
        with patch.object(p, 'get_enabled', return_value=True), \
             patch.object(p, 'steam_session', return_value=session), \
             patch.object(p, 'activate', side_effect=RuntimeError('failure')) as activate, \
             patch.object(p.time, 'monotonic', side_effect=[0, 120]), \
             patch.object(p.logging, 'getLogger'), \
             patch.object(p._wake, 'wait', side_effect=[None, StopIteration]), \
             patch.object(p._wake, 'clear'):
            with self.assertRaises(StopIteration):
                p._worker(lambda: True)
        activate.assert_called_once_with(session[2])
