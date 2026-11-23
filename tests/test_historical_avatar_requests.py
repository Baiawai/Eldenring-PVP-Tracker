"""Historical avatar requests use only an existing Steam helper."""
import base64
import io
import sys
import threading
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from test_store_ping import load_peer_tracking


class HistoricalAvatarRequestsTests(unittest.TestCase):
    def setUp(self):
        self.peers = load_peer_tracking()
        self.peers.HELPER = Path('TrackerSteamPeersV7.exe')
        self.peers._snapshot = {'status': 'active', 'ping_mode': 'steam_only', 'peers': []}
        self.writer = Mock()
        self.peers._command_writer = self.writer
        self.enabled = patch.object(self.peers, 'enabled', return_value=True)
        self.window = patch.object(self.peers.ctypes.windll.user32, 'FindWindowW', return_value=1)
        self.steam_session = Mock(return_value=(1, 'current', Path('steam.exe')))
        self.steam = patch.dict(sys.modules, {'application.steam_log_auto': types.SimpleNamespace(steam_session=self.steam_session)})
        self.enabled.start()
        self.window.start()
        self.steam.start()
        self.addCleanup(self.enabled.stop)
        self.addCleanup(self.window.stop)
        self.addCleanup(self.steam.stop)
        self.steam_id = '76561198000000001'

    def test_deduplicates_and_caps_concurrent_requests(self):
        p = self.peers
        self.assertEqual(p.request_historical_avatar(self.steam_id, (42,)), 'queued')
        self.assertEqual(p.request_historical_avatar(self.steam_id, (42,)), 'queued')
        self.writer.assert_called_once_with('avatar:' + self.steam_id)
        for value in ('76561198000000002', '76561198000000003', '76561198000000004'):
            self.assertEqual(p.request_historical_avatar(value, (42,)), 'queued')
        self.assertEqual(p.request_historical_avatar('76561198000000005', (42,)), 'rate_limited')
        self.assertEqual(self.writer.call_count, 4)

    def test_simultaneous_requests_for_same_peer_send_once(self):
        p = self.peers
        barrier = threading.Barrier(8)
        results = []
        def request():
            barrier.wait()
            results.append(p.request_historical_avatar(self.steam_id, (42,)))
        threads = [threading.Thread(target=request) for _ in range(8)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(timeout=3)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(results, ['queued'] * 8)
        self.writer.assert_called_once_with('avatar:' + self.steam_id)

    def test_does_not_start_a_helper_when_unavailable_or_game_closed(self):
        p = self.peers
        with patch.object(p.ctypes.windll.user32, 'FindWindowW', return_value=0), \
                patch.object(p.subprocess, 'Popen') as launch:
            self.assertEqual(p.request_historical_avatar(self.steam_id, (42,)), 'unavailable')
            launch.assert_not_called()
        with patch.object(p, 'HELPER', Path('TrackerSteamPeersV6.exe')):
            self.assertEqual(p.request_historical_avatar(self.steam_id, (42,)), 'unavailable')
        with patch.object(p, '_command_writer', None):
            self.assertEqual(p.request_historical_avatar(self.steam_id, (42,)), 'unavailable')
        self.steam_session.return_value = None
        self.assertEqual(p.request_historical_avatar(self.steam_id, (42,)), 'unavailable')
        self.steam_session.return_value = (1, 'current', Path('steam.exe'))
        p._snapshot['status'] = 'steam_unavailable'
        self.assertEqual(p.request_historical_avatar(self.steam_id, (42,)), 'unavailable')
        self.writer.assert_not_called()

    def test_ignores_invalid_ids_and_unsolicited_or_duplicate_responses(self):
        p = self.peers
        for invalid in ('', '76561198000000001\n', '１２３４５６７８９０１２３４５６７', '00000000000000000'):
            self.assertEqual(p.request_historical_avatar(invalid, (42,)), 'unavailable')
        fake = types.SimpleNamespace(save_historical=Mock())
        import application
        with patch.object(application, 'steam_avatar_store', fake, create=True):
            p._handle_historical_avatar({'id': self.steam_id, 'state': 'ready', 'avatar_png': 'cG5n'})
            fake.save_historical.assert_not_called()
            self.assertEqual(p.request_historical_avatar(self.steam_id, (42,)), 'queued')
            data = {'id': self.steam_id, 'state': 'ready', 'avatar_png': base64.b64encode(b'png').decode()}
            p._handle_historical_avatar(data)
            p._handle_historical_avatar(data)
            p._historical_avatar_save_queue.join()
        fake.save_historical.assert_called_once_with(self.steam_id, b'png', (42,))
        self.assertEqual(p._snapshot['status'], 'active')

    def test_event_ids_are_required_bounded_and_never_sent_to_helper(self):
        p = self.peers
        for invalid in ((), (True,), (0,), (-1,), (1.0,), tuple(range(1, 130))):
            self.assertEqual(p.request_historical_avatar(self.steam_id, invalid), 'unavailable')
        self.assertEqual(p.request_historical_avatar(self.steam_id, (42, 43)), 'queued')
        self.assertEqual(p.request_historical_avatar(self.steam_id, (44, 42)), 'queued')
        self.writer.assert_called_once_with('avatar:' + self.steam_id)
        self.assertEqual(p._historical_avatar_pending[self.steam_id]['event_ids'], (44, 42, 43))

    def test_busy_storage_does_not_block_peer_updates(self):
        p = self.peers
        entered, release = threading.Event(), threading.Event()
        def slow_save(*args):
            entered.set()
            release.wait(3)
        fake = types.SimpleNamespace(save_historical=Mock(side_effect=slow_save))
        import application
        try:
            with patch.object(application, 'steam_avatar_store', fake, create=True):
                self.assertEqual(p.request_historical_avatar(self.steam_id, (42,)), 'queued')
                p._handle_historical_avatar({'id': self.steam_id, 'state': 'ready', 'avatar_png': 'cG5n'})
                self.assertTrue(entered.wait(1))
                # This update must run even while storage is waiting.
                p._publish('active', [{'id':'76561198000000002', 'name':'Test', 'ping':42}])
                self.assertEqual(p._snapshot['peers'][0]['ping'], 42)
                self.assertEqual(p.request_historical_avatar(self.steam_id, (42,)), 'queued')
                release.set()
                p._historical_avatar_save_queue.join()
        finally:
            release.set()
        fake.save_historical.assert_called_once_with(self.steam_id, b'png', (42,))

    def test_unavailable_and_bad_payloads_are_rate_limited(self):
        p = self.peers
        import application
        fake = types.SimpleNamespace(save_historical=Mock())
        with patch.object(p.time, 'monotonic', return_value=10.0), \
                patch.object(application, 'steam_avatar_store', fake, create=True):
            self.assertEqual(p.request_historical_avatar(self.steam_id, (42,)), 'queued')
            p._handle_historical_avatar({'id': self.steam_id, 'state': 'ready', 'avatar_png': 'not-base64!'})
            self.assertEqual(p.request_historical_avatar(self.steam_id, (42,)), 'rate_limited')
        fake.save_historical.assert_not_called()
        with patch.object(p.time, 'monotonic', return_value=311.0):
            self.assertEqual(p.request_historical_avatar(self.steam_id, (42,)), 'queued')
            p._handle_historical_avatar({'id': self.steam_id, 'state': 'unavailable'})
            self.assertEqual(p.request_historical_avatar(self.steam_id, (42,)), 'rate_limited')

    def test_helper_disconnect_clears_pending_and_bounds_retry(self):
        p = self.peers
        self.assertEqual(p.request_historical_avatar(self.steam_id, (42,)), 'queued')
        p._clear_historical_avatar_requests()
        self.assertEqual(p.request_historical_avatar(self.steam_id, (42,)), 'rate_limited')
        self.assertFalse(p._historical_avatar_pending)

    def test_broken_pipe_does_not_crash_or_retry_unbounded(self):
        p = self.peers
        p._command_writer = Mock(side_effect=BrokenPipeError())
        self.assertEqual(p.request_historical_avatar(self.steam_id, (42,)), 'unavailable')
        self.assertEqual(p.request_historical_avatar(self.steam_id, (42,)), 'rate_limited')
        self.assertEqual(p._command_writer.call_count, 1)

    def test_avatar_message_does_not_overwrite_connected_peers(self):
        p = self.peers
        p._historical_avatar_pending[self.steam_id] = {'started': p.time.monotonic(), 'saving': False, 'event_ids': (42,)}
        avatar = '{"type":"avatar","id":"' + self.steam_id + '","state":"ready","avatar_png":"cG5n"}\n'
        peers = '{"status":"active","ping_mode":"admin_required","peers":[{"id":"76561198000000002","name":"Test","ping":42}]}\n'
        process = Mock()
        process.stdout = io.StringIO(peers + avatar)
        process.poll.return_value = 0
        fake = types.SimpleNamespace(save_historical=Mock())
        import application
        with patch.object(application, 'steam_avatar_store', fake, create=True), \
             patch.object(p, '_steam_path', return_value=Path('.')), \
             patch.object(p.HELPER.__class__, 'exists', return_value=True), \
             patch.object(p.subprocess, 'Popen', return_value=process), \
             patch.object(p, 'country_code', return_value=None), \
             patch.object(p.time, 'sleep', side_effect=StopIteration):
            with self.assertRaises(StopIteration):
                p._worker()
            p._historical_avatar_save_queue.join()
        self.assertEqual(p._snapshot['status'], 'active')
        self.assertEqual(p._snapshot['peers'][0]['ping'], 42)
        fake.save_historical.assert_called_once_with(self.steam_id, b'png', (42,))


if __name__ == '__main__':
    unittest.main()
