import io
import sys
import types
import unittest
from email.message import Message
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from application import peer_rankings


class _DeferredThread:
    tasks = []

    def __init__(self, target, args, **kwargs):
        self.target, self.args = target, args

    def start(self):
        self.tasks.append((self.target, self.args))

    @classmethod
    def run(cls):
        target, args = cls.tasks.pop(0)
        target(*args)


class PeerRankingsTests(unittest.TestCase):
    def setUp(self):
        _DeferredThread.tasks.clear()
        self.now = 100.0
        self.allowed = True
        self.requests = []
        self.ident = '76561198000000000'
        self.other = '76561198000000001'
        self.response = {'mode': 'Arena', 'entries': [{'steam_id': self.ident, 'rank': 27,
                         'stats': {'victory': 12, 'defeat': 2, 'ratio': 85.7, 'hidden': 'private'},
                         'history_unverified': True}]}

        def request(mode, ids, origin):
            self.requests.append((mode, ids))
            return self.response

        self.origin = 'https://example.invalid'
        self.cache = peer_rankings.PeerRankingCache(request, lambda: self.allowed, lambda: self.now, lambda: self.origin)
        self.patch = patch.object(peer_rankings.threading, 'Thread', _DeferredThread)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_lookup_is_async_exact_bounded_and_expires(self):
        self.assertEqual(self.cache.snapshot('Arena', [self.ident, self.other], permitted=True), {})
        self.assertEqual(self.requests, [])
        self.assertEqual(len(_DeferredThread.tasks), 1)
        self.cache.snapshot('Arena', [self.ident, self.other], permitted=True)
        self.assertEqual(len(_DeferredThread.tasks), 1)
        _DeferredThread.run()
        result = self.cache.snapshot('Arena', [self.ident, self.other], permitted=True)
        self.assertEqual(result[self.ident]['rank'], 27)
        self.assertEqual(result[self.ident]['stats'], {'victory': 12, 'defeat': 2, 'ratio': 85.7})
        self.assertNotIn(self.other, result)
        result[self.ident]['stats']['victory'] = 999
        self.assertEqual(self.cache.snapshot('Arena', [self.ident, self.other], permitted=True)[self.ident]['stats']['victory'], 12)
        self.now += 30
        self.assertEqual(self.cache.snapshot('Arena', [self.ident, self.other], permitted=True), {})
        self.assertEqual(len(_DeferredThread.tasks), 1)

    def test_all_modes_lookup_is_positive_only_and_discards_unneeded_fields(self):
        self.response = {'entries': [{'steam_id': self.ident, 'rank': 99,
                         'stats': {'victory': 100}}]}
        self.assertEqual(self.cache.snapshot('All', [self.ident, self.other], permitted=True), {})
        _DeferredThread.run()
        self.assertEqual(self.cache.snapshot('All', [self.ident, self.other], permitted=True),
                         {self.ident: True})
        self.assertEqual(self.requests, [('All', (self.ident, self.other))])
        with self.assertRaises(ValueError):
            peer_rankings._parse({'entries': [{'steam_id': self.other}]},
                                 'All', (self.ident,))
        with self.assertRaises(ValueError):
            peer_rankings._parse({'entries': [{'steam_id': self.ident},
                                                             {'steam_id': self.ident}]},
                                 'All', (self.ident,))

    def test_member_lookup_uses_the_private_badge_only_adapter(self):
        request = Mock(return_value={'entries': [{'steam_id': self.ident}]})
        adapter = types.SimpleNamespace(request_badges=request)
        with patch.dict(sys.modules, {'application._private_peer_badges': adapter}):
            result = peer_rankings._request_members('All', (self.ident,), self.origin)
            self.assertEqual(result, {'entries': [{'steam_id': self.ident}]})
            request.assert_called_once_with((self.ident,), self.origin)
            with self.assertRaises(ValueError):
                peer_rankings._request_members('Arena', (self.ident,), self.origin)

    def test_member_option_and_local_consent_gate_the_lookup(self):
        with patch.object(peer_rankings, '_MEMBER_CACHE') as cache, \
             patch.object(peer_rankings, 'locally_permitted', return_value=False) as permission:
            cache.snapshot.return_value = {}
            peer_rankings.tracker_members([self.ident], enabled=False)
            permission.assert_not_called()
            cache.snapshot.assert_called_once_with('All', (), permitted=False)
            cache.reset_mock()
            peer_rankings.tracker_members([self.ident], enabled=True)
            cache.snapshot.assert_called_once_with('All', [self.ident], permitted=False)
            cache.reset_mock()
            permission.return_value = True
            cache.snapshot.return_value = {self.ident: True}
            self.assertEqual(peer_rankings.tracker_members([self.ident], enabled=True), {self.ident: True})
            cache.snapshot.assert_called_once_with('All', [self.ident], permitted=True)

    def test_inflight_lookup_rechecks_badge_option_before_publishing(self):
        settings = types.SimpleNamespace(options=lambda: {'show_tracker_user': False})
        with patch.dict(sys.modules, {'application.overlay_settings': settings}), \
             patch('application.overlay_settings', settings, create=True), \
             patch.object(peer_rankings, 'locally_permitted', return_value=True) as permission:
            self.assertFalse(peer_rankings._tracker_member_permitted())
            permission.assert_not_called()
            settings.options = lambda: {'show_tracker_user': True}
            self.assertTrue(peer_rankings._tracker_member_permitted())
            permission.assert_called_once_with()

    def test_app_and_overlay_share_one_asynchronous_member_request(self):
        self.response = {'entries': [{'steam_id': self.ident}]}
        with patch.object(peer_rankings, '_MEMBER_CACHE', self.cache), \
             patch.object(peer_rankings, 'locally_permitted', return_value=True):
            self.assertEqual(peer_rankings.tracker_members([self.ident, self.other], enabled=True), {})
            self.assertEqual(peer_rankings.tracker_members([self.other, self.ident], enabled=True), {})
            self.assertEqual(len(_DeferredThread.tasks), 1)
            _DeferredThread.run()
            self.assertEqual(peer_rankings.tracker_members([self.ident, self.other], enabled=True),
                             {self.ident: True})
            self.assertEqual(self.requests, [('All', (self.ident, self.other))])

    def test_local_consent_revocation_discards_cache_and_inflight_results(self):
        self.cache.snapshot('Arena', [self.ident], permitted=True)
        self.assertEqual(self.cache.snapshot('Arena', [self.ident], permitted=False), {})
        _DeferredThread.run()
        self.assertEqual(self.cache.snapshot('Arena', [self.ident], permitted=True), {})
        self.assertEqual(len(_DeferredThread.tasks), 0)  # common 10 s throttle still applies
        self.now += 10
        self.cache.snapshot('Arena', [self.ident], permitted=True)
        self.allowed = False
        _DeferredThread.run()
        self.assertEqual(self.requests, [])
        self.assertEqual(self.cache.snapshot('Arena', [self.ident], permitted=False), {})

    def test_no_request_for_invalid_modes_and_ids(self):
        self.assertEqual(self.cache.snapshot('Unknown', [self.ident], permitted=True), {})
        self.assertEqual(self.cache.snapshot('Arena', ['invalid', '76561197000000000'], permitted=True), {})
        self.assertEqual(_DeferredThread.tasks, [])

    def test_results_do_not_cross_server_origins(self):
        self.cache.snapshot('Arena', [self.ident], permitted=True)
        _DeferredThread.run()
        self.assertTrue(self.cache.snapshot('Arena', [self.ident], permitted=True))
        self.origin = 'https://other.example.invalid'
        self.assertEqual(self.cache.snapshot('Arena', [self.ident], permitted=True), {})

    def test_local_permission_requires_terms_and_current_origin(self):
        class DB:
            def execute(self, statement):
                return types.SimpleNamespace(fetchone=lambda: ('https://site.invalid', None))
            def close(self):
                pass
        fake = types.SimpleNamespace(_settings=lambda: (True, 'id', 'token', False, 'https://site.invalid'),
                                     _base_url=lambda: 'https://site.invalid', _event_permission=lambda: True,
                                     _db=DB, FROZEN=False)
        with patch.dict(sys.modules, {'application.online_leaderboard': fake}), \
             patch('application.online_leaderboard', fake, create=True):
            self.assertTrue(peer_rankings.locally_permitted())
            fake._event_permission = lambda: False
            self.assertFalse(peer_rankings.locally_permitted())
            fake._event_permission = lambda: True
            fake._base_url = lambda: 'https://other.invalid'
            self.assertFalse(peer_rankings.locally_permitted())
            fake._settings = lambda: (False, 'id', 'token', False, 'https://site.invalid')
            self.assertFalse(peer_rankings.locally_permitted())

    def test_server_delay_and_malformed_data_are_not_retried_continuously(self):
        headers = Message()
        headers['Retry-After'] = '120'
        def limited(*args):
            raise HTTPError('https://example.invalid', 429, 'limited', headers, io.BytesIO())
        cache = peer_rankings.PeerRankingCache(limited, lambda: True, lambda: self.now, lambda: self.origin)
        cache.snapshot('Arena', [self.ident], permitted=True)
        _DeferredThread.run()
        self.now += 119
        cache.snapshot('Arena', [self.ident], permitted=True)
        self.assertEqual(_DeferredThread.tasks, [])
        self.now += 1
        cache.snapshot('Arena', [self.ident], permitted=True)
        self.assertEqual(len(_DeferredThread.tasks), 1)
        with self.assertRaises(ValueError):
            peer_rankings._parse({'mode': 'Arena', 'entries': [dict(self.response['entries'][0], steam_id=self.other)]},
                                 'Arena', (self.ident,))

    def test_unsupported_endpoint_waits_ten_minutes_before_retry(self):
        for status in (404, 405):
            with self.subTest(status=status):
                def unavailable(*args):
                    raise HTTPError('https://example.invalid', status, 'unavailable', Message(), io.BytesIO())
                cache = peer_rankings.PeerRankingCache(unavailable, lambda: True, lambda: self.now, lambda: self.origin)
                cache.snapshot('Arena', [self.ident], permitted=True)
                _DeferredThread.run()
                self.now += 599
                cache.snapshot('Arena', [self.ident], permitted=True)
                self.assertEqual(_DeferredThread.tasks, [])
                self.now += 1
                cache.snapshot('Arena', [self.ident], permitted=True)
                self.assertEqual(len(_DeferredThread.tasks), 1)
                cache.snapshot('Arena', [self.ident], permitted=False)
                _DeferredThread.run()
                self.assertEqual(cache.snapshot('Arena', [self.ident], permitted=False), {})


if __name__ == '__main__':
    unittest.main()
