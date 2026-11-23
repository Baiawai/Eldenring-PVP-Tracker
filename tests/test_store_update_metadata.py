"""Optional version metadata must never contact a real server during tests."""
import sys
import threading
import time
import types
import unittest
from unittest.mock import Mock, patch

from application import store_update


class InlineThread:
    def __init__(self, *, target, **_kwargs):
        self.target = target

    def start(self):
        self.target()


class StoreUpdateMetadataTests(unittest.TestCase):
    def setUp(self):
        names = ('_REQUIRED', '_PENDING', '_AVAILABLE_VERSION', '_AVAILABLE_VERSION_SOURCE',
                 '_METADATA_STARTED', '_METADATA_LOOKUP_PENDING')
        self.original = {name: getattr(store_update, name) for name in names}
        for name, value in zip(names, (False, False, None, None, False, False)):
            setattr(store_update, name, value)
        app_version = patch.object(store_update, 'APP_VERSION', '1.0.11.0')
        app_version.start()
        self.addCleanup(app_version.stop)

    def tearDown(self):
        for name, value in self.original.items():
            setattr(store_update, name, value)

    @staticmethod
    def provider(fetch):
        module = types.ModuleType('application._private_store_version')
        module.fetch_version = fetch
        return module

    def test_no_lookup_without_a_confirmed_store_update(self):
        fetch = Mock(return_value='1.0.12.0')
        with patch.dict(sys.modules, {'application._private_store_version': self.provider(fetch)}), \
                patch.object(store_update.threading, 'Thread', InlineThread):
            self.assertFalse(store_update._start_indicative_version_lookup())
        fetch.assert_not_called()
        self.assertIsNone(store_update.get_version_status()['available_version'])

    def test_startup_and_periodic_errors_do_not_query_provider(self):
        fetch = Mock(return_value='1.0.12.0')
        with patch.object(store_update, 'FROZEN', True), \
                patch.object(store_update, '_query_store_update', return_value=False), \
                patch.dict(sys.modules, {'application._private_store_version': self.provider(fetch)}), \
                patch.object(store_update.threading, 'Thread', InlineThread):
            self.assertFalse(store_update.check_at_start())
            self.assertFalse(store_update._check_periodic_once())
        fetch.assert_not_called()

    def test_confirmed_update_without_store_version_triggers_provider(self):
        for check in ('startup', 'periodic'):
            with self.subTest(check=check):
                store_update._REQUIRED = False
                store_update._PENDING = False
                store_update._AVAILABLE_VERSION = None
                store_update._AVAILABLE_VERSION_SOURCE = None
                store_update._METADATA_STARTED = False
                fetch = Mock(return_value='1.0.12.0')
                with patch.object(store_update, 'FROZEN', True), \
                        patch.object(store_update, '_query_store_update', return_value=True), \
                        patch.dict(sys.modules, {'application._private_store_version': self.provider(fetch)}), \
                        patch.object(store_update.threading, 'Thread', InlineThread):
                    (store_update.check_at_start if check == 'startup' else store_update._check_periodic_once)()
                fetch.assert_called_once_with('1.0.11.0', timeout=3.0)
                self.assertTrue(store_update.is_required() or store_update.is_pending())
                self.assertEqual(store_update.get_version_status()['version_source'], 'site')

    def test_confirmed_update_launches_only_one_lookup(self):
        fetch = Mock(return_value='1.0.12.0')
        store_update._PENDING = True
        with patch.dict(sys.modules, {'application._private_store_version': self.provider(fetch)}), \
                patch.object(store_update.threading, 'Thread', InlineThread):
            self.assertTrue(store_update._start_indicative_version_lookup())
            self.assertFalse(store_update._start_indicative_version_lookup())
        fetch.assert_called_once_with('1.0.11.0', timeout=3.0)
        self.assertEqual(store_update.get_version_status(), {
            'available_version': '1.0.12.0', 'version_source': 'site', 'lookup_pending': False})

    def test_missing_provider_keeps_confirmed_update_and_unknown_version(self):
        store_update._REQUIRED = True
        with patch.dict(sys.modules, {'application._private_store_version': None}), \
                patch.object(store_update.threading, 'Thread', InlineThread):
            self.assertTrue(store_update._start_indicative_version_lookup())
        self.assertTrue(store_update.is_required())
        self.assertEqual(store_update.get_version_status(), {
            'available_version': None, 'version_source': None, 'lookup_pending': False})

    def test_provider_error_or_old_invalid_version_never_removes_gate(self):
        for answer in ('1.0.10.0', '1.0.11.0', 'v1.0.12.0', None, OSError('offline')):
            with self.subTest(answer=answer):
                store_update._REQUIRED = True
                store_update._METADATA_STARTED = False
                store_update._METADATA_LOOKUP_PENDING = False
                fetch = Mock(side_effect=answer) if isinstance(answer, Exception) else Mock(return_value=answer)
                with patch.dict(sys.modules, {'application._private_store_version': self.provider(fetch)}), \
                        patch.object(store_update.threading, 'Thread', InlineThread):
                    store_update._start_indicative_version_lookup()
                self.assertTrue(store_update.is_required())
                self.assertIsNone(store_update.available_version())
                self.assertFalse(store_update.get_version_status()['lookup_pending'])

    def test_store_version_takes_precedence_over_site(self):
        store_update._REQUIRED = True
        store_update._AVAILABLE_VERSION = '1.0.12.0'
        store_update._AVAILABLE_VERSION_SOURCE = 'store'
        fetch = Mock(return_value='1.0.20.0')
        with patch.dict(sys.modules, {'application._private_store_version': self.provider(fetch)}), \
                patch.object(store_update.threading, 'Thread', InlineThread):
            self.assertFalse(store_update._start_indicative_version_lookup())
        fetch.assert_not_called()
        self.assertEqual(store_update.get_version_status()['version_source'], 'store')
        self.assertEqual(store_update.available_version(), '1.0.12.0')

    def test_slow_provider_does_not_block_and_cannot_override_later_store_value(self):
        started, release, done = threading.Event(), threading.Event(), threading.Event()
        store_update._REQUIRED = True

        def fetch(*_args, **_kwargs):
            started.set()
            try:
                release.wait(2)
                return '1.0.20.0'
            finally:
                done.set()

        with patch.dict(sys.modules, {'application._private_store_version': self.provider(fetch)}):
            try:
                self.assertTrue(store_update._start_indicative_version_lookup())
                self.assertTrue(started.wait(1))
                self.assertTrue(store_update.is_required())
                self.assertTrue(store_update.get_version_status()['lookup_pending'])
                with store_update._STATE_LOCK:
                    store_update._AVAILABLE_VERSION = '1.0.12.0'
                    store_update._AVAILABLE_VERSION_SOURCE = 'store'
            finally:
                release.set()
                self.assertTrue(done.wait(2))
                deadline = time.monotonic() + 2
                while store_update.get_version_status()['lookup_pending'] and time.monotonic() < deadline:
                    time.sleep(0.01)
        self.assertFalse(store_update.get_version_status()['lookup_pending'])
        self.assertEqual(store_update.available_version(), '1.0.12.0')
        self.assertEqual(store_update.get_version_status()['version_source'], 'store')


if __name__ == '__main__':
    unittest.main()
