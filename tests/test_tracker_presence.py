import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import URLError

from application import tracker_presence


class TrackerPresenceTest(unittest.TestCase):
    def test_identity_is_stable_and_distinct_for_separate_data_directories(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            with patch.object(tracker_presence, 'database_path', return_value=base / 'first.db'):
                first = tracker_presence.installation_id()
                self.assertEqual(first, tracker_presence.installation_id())
            with patch.object(tracker_presence, 'database_path', return_value=base / 'second.db'):
                self.assertNotEqual(first, tracker_presence.installation_id())
            self.assertRegex(first, r'^[a-f0-9]{32}$')

    def test_worker_registers_inactive_and_does_not_signal_an_idle_background_process(self):
        class StopWorker(BaseException):
            pass
        event = MagicMock()
        event.wait.side_effect = [True, False, False, StopWorker()]
        with patch.object(tracker_presence, '_pulse', event), \
                patch.object(tracker_presence, '_is_tracking', side_effect=[False, True, False]), \
                patch.object(tracker_presence, '_send_safely') as send:
            with self.assertRaises(StopWorker):
                tracker_presence._run()
            self.assertEqual([call.args[0] for call in send.call_args_list], [False, True, True])

    def test_transient_presence_failure_is_retried_without_blocking_the_application(self):
        with patch.object(tracker_presence, 'send_heartbeat', side_effect=[URLError(TimeoutError()), True]) as send, \
                patch.object(tracker_presence.network_retry.time, 'sleep'), \
                patch.object(tracker_presence.network_retry.random, 'uniform', return_value=1.0):
            tracker_presence._send_safely(True)
            self.assertEqual(send.call_count, 2)
            self.assertTrue(all(call.args == (True,) for call in send.call_args_list))

    def test_active_heartbeat_reports_the_activity_flag(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(tracker_presence, 'database_path', return_value=Path(temp) / 'usage.db'):
            opener = MagicMock()
            opener.open.return_value.__enter__.return_value.status = 204
            with patch.object(tracker_presence, 'build_opener', return_value=opener):
                self.assertTrue(tracker_presence.send_heartbeat(True))
            self.assertEqual(json.loads(opener.open.call_args.args[0].data), {'installation_id': tracker_presence.installation_id(), 'active': True})

    def test_browser_notifications_are_rate_limited_and_do_not_require_leaderboard(self):
        with patch.object(tracker_presence, '_started', True), patch.object(tracker_presence, '_last_browser_pulse', 0.0), \
                patch.object(tracker_presence, '_pulse') as pulse, patch.object(tracker_presence.time, 'monotonic', side_effect=[100, 101, 131]):
            tracker_presence.notify_browser()
            tracker_presence.notify_browser()
            tracker_presence.notify_browser()
            self.assertEqual(pulse.set.call_count, 2)

    def test_heartbeat_sends_only_the_random_identifier_without_leaderboard(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(tracker_presence, 'database_path', return_value=Path(temp) / 'usage.db'):
            opener = MagicMock()
            opener.open.return_value.__enter__.return_value.status = 204
            with patch.object(tracker_presence, 'build_opener', return_value=opener):
                self.assertTrue(tracker_presence.send_heartbeat())
            request = opener.open.call_args.args[0]
            self.assertEqual(request.full_url, 'https://eldenringpvp.com/api/v1/tracker-presence')
            self.assertEqual(request.method, 'POST')
            self.assertEqual(json.loads(request.data), {'installation_id': tracker_presence.installation_id(), 'active': False})
            self.assertEqual(opener.open.call_args.kwargs['timeout'], 5)


if __name__ == '__main__':
    unittest.main()
