"""Tests use synthetic credentials and never contact a remote service."""
import sys
import threading
import types
import unittest
from unittest.mock import Mock, patch

try:
    from application import _private_peer_badges as adapter
except ImportError:
    adapter = None


@unittest.skipIf(adapter is None, 'Private badge adapter not present')
class PrivatePeerBadgeTests(unittest.TestCase):
    def setUp(self):
        self.origin = 'https://example.invalid'
        self.peer = '76561198000000000'
        self.encrypted = b'synthetic-protected-token'
        self.state = (True, 'synthetic-installation', self.encrypted, False, self.origin)
        self.row = (self.encrypted, None, None, self.origin, self.origin, None)
        self.db = types.SimpleNamespace(
            execute=Mock(side_effect=lambda *_: types.SimpleNamespace(fetchone=lambda: self.row)),
            close=Mock())
        self.online = types.SimpleNamespace(
            _LOCK=threading.RLock(), _settings=lambda: self.state,
            _base_url=Mock(return_value=self.origin), _event_permission=Mock(return_value=True),
            _db=Mock(return_value=self.db),
            win32crypt=types.SimpleNamespace(CryptUnprotectData=Mock(return_value=('', b'a' * 64))),
            _call=Mock(return_value={'entries': [{'steam_id': self.peer}]}))
        self.overlay_settings = types.SimpleNamespace(options=Mock(return_value={'show_tracker_user': True}))
        self.modules = patch.dict(sys.modules, {'application.online_leaderboard': self.online,
                                              'application.overlay_settings': self.overlay_settings})
        self.attribute = patch('application.online_leaderboard', self.online, create=True)
        self.overlay_attribute = patch('application.overlay_settings', self.overlay_settings, create=True)
        self.modules.start()
        self.attribute.start()
        self.overlay_attribute.start()
        self.addCleanup(self.modules.stop)
        self.addCleanup(self.attribute.stop)
        self.addCleanup(self.overlay_attribute.stop)

    def lookup(self):
        return adapter.request_badges((self.peer,), self.origin)

    def test_existing_credential_is_sent_only_to_its_exact_origin(self):
        self.assertEqual(self.lookup(), {'entries': [{'steam_id': self.peer}]})
        args, kwargs = self.online._call.call_args
        self.assertEqual(args[0], 'POST')
        self.assertEqual(args[2], {'steam_ids': [self.peer]})
        self.assertEqual(kwargs, {'token': 'a' * 64, 'root': self.origin})
        self.assertEqual(self.online._call.call_count, 1)

    def test_absent_disabled_or_unconsented_identity_never_calls_remote(self):
        states = [
            (False, 'id', self.encrypted, False, self.origin),
            (True, None, self.encrypted, False, self.origin),
            (True, 'id', None, False, self.origin),
            (True, 'id', self.encrypted, True, self.origin),
            (True, 'id', self.encrypted, False, 'https://other.invalid'),
        ]
        for state in states:
            with self.subTest(state=state[:2]):
                self.state = state
                with self.assertRaises(RuntimeError):
                    self.lookup()
        self.state = (True, 'id', self.encrypted, False, self.origin)
        self.online._event_permission.return_value = False
        with self.assertRaises(RuntimeError):
            self.lookup()
        self.online._call.assert_not_called()

    def test_rotation_recovery_transition_or_origin_mismatch_never_calls_remote(self):
        rows = [
            None,
            (b'other-protected-token', None, None, self.origin, self.origin, None),
            (self.encrypted, b'rotation', None, self.origin, self.origin, None),
            (self.encrypted, None, b'recovery', self.origin, self.origin, None),
            (self.encrypted, None, None, 'https://other.invalid', self.origin, None),
            (self.encrypted, None, None, self.origin, 'https://other.invalid', None),
            (self.encrypted, None, None, self.origin, self.origin, 'transition'),
        ]
        for row in rows:
            with self.subTest(row_present=row is not None):
                self.row = row
                with self.assertRaises(RuntimeError):
                    self.lookup()
        self.online._call.assert_not_called()

    def test_invalid_or_unreadable_credential_and_changed_destination_are_rejected(self):
        for token in (b'A' * 64, b'a' * 63, b'not-a-token', b'\xff'):
            with self.subTest(token_length=len(token)):
                self.online.win32crypt.CryptUnprotectData.return_value = ('', token)
                with self.assertRaises(RuntimeError):
                    self.lookup()
        self.online.win32crypt.CryptUnprotectData.side_effect = OSError('synthetic decryption failure')
        with self.assertRaises(RuntimeError):
            self.lookup()
        self.online.win32crypt.CryptUnprotectData.side_effect = None
        self.online.win32crypt.CryptUnprotectData.return_value = ('', b'a' * 64)
        self.online._base_url.side_effect = [self.origin, 'https://other.invalid']
        with self.assertRaises(RuntimeError):
            self.lookup()
        self.online._call.assert_not_called()

    def test_disabling_badge_before_network_request_blocks_sending(self):
        self.overlay_settings.options.return_value = {'show_tracker_user': False}
        with self.assertRaises(RuntimeError):
            self.lookup()
        self.overlay_settings.options.side_effect = [{'show_tracker_user': True}, {'show_tracker_user': False}]
        with self.assertRaises(RuntimeError):
            self.lookup()
        self.online._call.assert_not_called()


if __name__ == '__main__':
    unittest.main()
