import io
import sys
import types
import unittest
from email.message import Message
from unittest.mock import patch
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
