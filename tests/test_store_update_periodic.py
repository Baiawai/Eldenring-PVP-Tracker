"""Periodic Store checks use isolated mocks, never the real Microsoft Store."""
import threading
import unittest
from unittest.mock import patch

from application import store_update


class StorePeriodicUpdateTests(unittest.TestCase):
    def setUp(self):
        self.previous_required = store_update._REQUIRED
        self.previous_pending = store_update._PENDING
        lookup = patch.object(store_update, '_start_indicative_version_lookup')
        lookup.start()
        self.addCleanup(lookup.stop)
        store_update._REQUIRED = False
        store_update._PENDING = False

    def tearDown(self):
        store_update._REQUIRED = self.previous_required
        store_update._PENDING = self.previous_pending

    def test_available_main_package_marks_an_update_pending(self):
        with patch.object(store_update, 'FROZEN', True), \
                patch.object(store_update, '_query_store_update', return_value=True) as query:
            store_update._check_periodic_once()
        query.assert_called_once_with()
        self.assertTrue(store_update.is_pending())
        self.assertFalse(store_update.is_required())

    def test_offline_and_no_update_do_not_block(self):
        with patch.object(store_update, 'FROZEN', True):
            for result in (False, OSError('Store unavailable')):
                with self.subTest(result=result):
                    with patch.object(store_update, '_query_store_update', side_effect=result if isinstance(result, Exception) else None,
                                      return_value=False):
                        store_update._check_periodic_once()
                    self.assertFalse(store_update.is_required())
                    self.assertFalse(store_update.is_pending())

    def test_detected_update_remains_pending_after_failure_or_empty_result(self):
        with patch.object(store_update, 'FROZEN', True):
            with patch.object(store_update, '_query_store_update', return_value=True):
                store_update._check_periodic_once()
            for result in (False, OSError('Store unavailable')):
                with self.subTest(result=result):
                    with patch.object(store_update, '_query_store_update', side_effect=result if isinstance(result, Exception) else None,
                                      return_value=False):
                        store_update._check_periodic_once()
                    self.assertTrue(store_update.is_pending())

    def test_periodic_worker_waits_ten_minutes_and_defers_blocking(self):
        class FakeStopEvent:
            def __init__(self):
                self.waits = []

            def wait(self, seconds):
                self.waits.append(seconds)
                # End the worker after it confirms the update and starts its
                # next cycle, if the implementation chooses to keep running.
                return store_update.is_required() or len(self.waits) > 6

        stop = FakeStopEvent()
        calls = []

        def prepare():
            calls.append('prepare')
            return len(calls) >= 2

        with patch.object(store_update, 'FROZEN', True), \
                patch.object(store_update, '_query_store_update', side_effect=[False, True]) as query:
            store_update._periodic_worker(600, prepare, stop)
        self.assertEqual(stop.waits[:3], [600, 600, 1])
        self.assertEqual(query.call_count, 2)
        self.assertEqual(calls, ['prepare', 'prepare'])
        self.assertTrue(store_update.is_required())

    def test_non_frozen_app_never_starts_periodic_worker(self):
        with patch.object(store_update, 'FROZEN', False), \
                patch.object(store_update, '_PERIODIC_STARTED', False), \
                patch.object(store_update.threading, 'Thread') as thread:
            store_update.start_periodic_check()
            thread.assert_not_called()

    def test_only_one_periodic_worker_can_be_started(self):
        with patch.object(store_update, 'FROZEN', True), \
                patch.object(store_update, '_PERIODIC_STARTED', False), \
                patch.object(store_update.threading, 'Thread') as thread:
            store_update.start_periodic_check(prepare_block=lambda: True)
            store_update.start_periodic_check(prepare_block=lambda: True)
            self.assertEqual(thread.call_count, 1)
            self.assertTrue(thread.call_args.kwargs.get('daemon'))
            thread.return_value.start.assert_called_once_with()

    def test_concurrent_checks_never_query_store_simultaneously(self):
        entered, release = threading.Event(), threading.Event()
        attempted_second, overlapping = threading.Event(), threading.Event()
        state_lock = threading.Lock()
        active = 0
        peak = 0
        errors = []

        def delayed_query():
            nonlocal active, peak
            with state_lock:
                active += 1
                peak = max(peak, active)
                if active > 1:
                    overlapping.set()
            entered.set()
            try:
                if not release.wait(3):
                    raise TimeoutError('test did not release query')
                return False
            finally:
                with state_lock:
                    active -= 1

        def check(second=False):
            try:
                if second:
                    attempted_second.set()
                store_update._check_periodic_once()
            except Exception as error:
                errors.append(error)

        with patch.object(store_update, 'FROZEN', True), \
                patch.object(store_update, '_query_store_update', side_effect=delayed_query):
            first = threading.Thread(target=check, daemon=True)
            second = threading.Thread(target=check, args=(True,), daemon=True)
            first.start()
            try:
                self.assertTrue(entered.wait(2), 'first query did not start')
                second.start()
                self.assertTrue(attempted_second.wait(2), 'second check did not start')
                self.assertFalse(overlapping.wait(0.2), 'Store queries overlapped')
            finally:
                release.set()
                first.join(3)
                if second.ident is not None:
                    second.join(3)
            self.assertFalse(first.is_alive())
            self.assertFalse(second.is_alive())
        self.assertFalse(errors)
        self.assertEqual(peak, 1)

    def test_startup_timeout_cannot_overlap_with_periodic_check(self):
        entered, release, finished = threading.Event(), threading.Event(), threading.Event()

        def delayed_query():
            entered.set()
            try:
                release.wait(3)
                return True
            finally:
                finished.set()

        with patch.object(store_update, 'FROZEN', True), \
                patch.object(store_update, '_query_store_update', side_effect=delayed_query) as query:
            try:
                self.assertFalse(store_update.check_at_start(timeout=0.02))
                self.assertTrue(entered.wait(2))
                self.assertFalse(store_update._check_periodic_once())
                self.assertEqual(query.call_count, 1)
            finally:
                release.set()
                self.assertTrue(finished.wait(2))
                # The startup worker releases this lock after the query.
                acquired = store_update._CHECK_LOCK.acquire(timeout=2)
                if acquired:
                    store_update._CHECK_LOCK.release()
                self.assertTrue(acquired)
        self.assertFalse(store_update.is_required())
        self.assertFalse(store_update.is_pending())


if __name__ == '__main__':
    unittest.main()
