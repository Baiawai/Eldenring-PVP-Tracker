"""Only present Store-provided versions that are newer than this build."""
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from application import store_update


def version(*parts):
    return SimpleNamespace(major=parts[0], minor=parts[1], build=parts[2], revision=parts[3])


def package(family=None, signature=3, package_version=None):
    return SimpleNamespace(signature_kind=signature, id=SimpleNamespace(
        family_name=family or store_update.STORE_FAMILY, version=package_version))


def update(package_version, family=None):
    return SimpleNamespace(package=package(family=family, package_version=package_version))


class StoreUpdateVersionTests(unittest.TestCase):
    def setUp(self):
        self.original = (store_update._REQUIRED, store_update._PENDING, store_update._AVAILABLE_VERSION)
        lookup = patch.object(store_update, '_start_indicative_version_lookup')
        lookup.start()
        self.addCleanup(lookup.stop)
        store_update._REQUIRED = False
        store_update._PENDING = False
        store_update._AVAILABLE_VERSION = None
        self.build_version = patch.object(store_update, 'APP_VERSION', '1.0.11.0')
        self.build_version.start()
        self.addCleanup(self.build_version.stop)

    def tearDown(self):
        store_update._REQUIRED, store_update._PENDING, store_update._AVAILABLE_VERSION = self.original

    def test_same_or_older_package_version_is_not_presented_as_new(self):
        for parts in ((1, 0, 11, 0), (1, 0, 10, 0)):
            with self.subTest(parts=parts):
                result = store_update._main_package_update(package(), [update(version(*parts))])
                self.assertTrue(result.available)
                self.assertIsNone(result.version)

    def test_newest_version_is_selected_numerically_and_ignores_other_families(self):
        entries = [update(version(1, 0, 12, 0)), update(version(1, 0, 20, 0)),
                   update(version(2, 0, 0, 0), family='Another.family')]
        result = store_update._main_package_update(package(), entries)
        self.assertTrue(result.available)
        self.assertEqual(result.version, '1.0.20.0')
        self.assertFalse(store_update._main_package_update(package(), entries[-1:]).available)

    def test_missing_or_invalid_version_does_not_hide_a_confirmed_update(self):
        for candidate in (None, object(), version(1, 0, '12', 0),
                          version(1, 0, -1, 0), version(1, 0, 65536, 0),
                          version(1, 0, True, 0)):
            with self.subTest(candidate=candidate):
                result = store_update._main_package_update(package(), [update(candidate)])
                self.assertTrue(result.available)
                self.assertIsNone(result.version)

    def test_startup_exposes_confirmed_version(self):
        with patch.object(store_update, 'FROZEN', True), \
                patch.object(store_update, '_query_store_update',
                             return_value=store_update._StoreUpdateResult(True, '1.0.12.0')):
            self.assertTrue(store_update.check_at_start())
        self.assertEqual(store_update.available_version(), '1.0.12.0')

    def test_periodic_detection_exposes_confirmed_version(self):
        with patch.object(store_update, 'FROZEN', True), \
                patch.object(store_update, '_query_store_update',
                             return_value=store_update._StoreUpdateResult(True, '1.0.12.0')):
            store_update._check_periodic_once()
        self.assertTrue(store_update.is_pending())
        self.assertEqual(store_update.available_version(), '1.0.12.0')

    def test_timed_out_startup_does_not_expose_late_version(self):
        entered, release, complete = threading.Event(), threading.Event(), threading.Event()

        def delayed():
            entered.set()
            try:
                release.wait(3)
                return store_update._StoreUpdateResult(True, '1.0.12.0')
            finally:
                complete.set()

        with patch.object(store_update, 'FROZEN', True), \
                patch.object(store_update, '_query_store_update', side_effect=delayed):
            try:
                self.assertFalse(store_update.check_at_start(timeout=0.02))
                self.assertTrue(entered.wait(2))
            finally:
                release.set()
                self.assertTrue(complete.wait(2))
                acquired = store_update._CHECK_LOCK.acquire(timeout=2)
                if acquired:
                    store_update._CHECK_LOCK.release()
                self.assertTrue(acquired)
        self.assertFalse(store_update.is_required())
        self.assertIsNone(store_update.available_version())


if __name__ == '__main__':
    unittest.main()
