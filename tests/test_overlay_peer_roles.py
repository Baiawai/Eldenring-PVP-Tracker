import threading
import unittest

from application.overlay_peer_roles import RoleTracker


class OverlayPeerRolesTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.roles = RoleTracker(clock=lambda: self.now)
        self.alice = {'id': '76561198000000001', 'name': 'Alice'}
        self.bob = {'id': '76561198000000002', 'name': 'Bob'}
        self.roles.update_peers('active', [self.alice, self.bob])

    def observe(self, name='Alice', role='invader', event='invaded'):
        self.roles.observe({'name': name, 'role': role, 'event': event})

    def annotated(self, *cards):
        return self.roles.annotate(list(cards))

    def test_names_match_exactly_after_unicode_case_and_space_normalization(self):
        self.observe('  ALICE  ')
        self.assertEqual(self.annotated(self.alice, self.bob)[0]['role'], 'invader')
        self.assertIsNone(self.annotated(self.alice, self.bob)[1]['role'])
        self.roles.clear()
        self.roles.update_peers('active', [self.alice])
        self.observe('Alice2')
        self.assertIsNone(self.annotated(self.alice)[0]['role'])
        self.assertNotIn('role', self.alice)

    def test_ignores_invocation_not_yet_confirmed_and_unknown_events(self):
        for event in ('summoning', 'observed', 'unknown'):
            with self.subTest(event=event):
                self.observe(role='hunter', event=event)
                self.assertIsNone(self.annotated(self.alice)[0]['role'])
        self.observe(role='hunter', event='joined')
        self.assertEqual(self.annotated(self.alice)[0]['role'], 'hunter')

    def test_departures_and_death_clear_the_role(self):
        for event in ('left', 'dismissed', 'died'):
            with self.subTest(event=event):
                self.observe()
                self.assertEqual(self.annotated(self.alice)[0]['role'], 'invader')
                self.observe(event=event)
                self.assertIsNone(self.annotated(self.alice)[0]['role'])

    def test_disconnect_reconnect_rename_and_ambiguous_names_remove_binding(self):
        for peers in ([self.bob], [dict(self.alice, name='Other')],
                      [self.alice, dict(self.bob, name='alice')]):
            with self.subTest(peers=peers):
                self.roles.clear()
                self.roles.update_peers('active', [self.alice])
                self.observe()
                self.roles.update_peers('active', peers)
                self.roles.update_peers('active', [self.alice])
                self.assertIsNone(self.annotated(self.alice)[0]['role'])

    def test_pending_arrival_matches_only_for_a_short_time(self):
        self.observe('Carol', role='hunter', event='joined')
        carol = {'id': '76561198000000003', 'name': 'Carol'}
        self.now += 9
        self.roles.update_peers('active', [self.alice, carol])
        self.assertEqual(self.annotated(carol)[0]['role'], 'hunter')
        self.roles.update_peers('active', [self.alice])
        self.observe('Carol', role='hunter', event='joined')
        self.now += 11
        self.roles.update_peers('active', [self.alice, carol])
        self.assertIsNone(self.annotated(carol)[0]['role'])

    def test_confirmed_arrival_during_startup_is_matched_only_when_active(self):
        self.roles.update_peers('starting', [])
        self.observe(role='invader', event='invaded')
        self.assertIsNone(self.annotated(self.alice)[0]['role'])
        # Repeated startup snapshots must not discard a still-fresh arrival.
        self.now += 4
        self.roles.update_peers('starting', [])
        self.now += 5
        self.roles.update_peers('active', [self.alice])
        self.assertEqual(self.annotated(self.alice)[0]['role'], 'invader')

        # The helper may become active one update before the peer appears.
        self.roles.update_peers('starting', [])
        self.observe(role='hunter', event='joined')
        self.roles.update_peers('active', [])
        self.assertIsNone(self.annotated(self.alice)[0]['role'])
        self.roles.update_peers('active', [self.alice])
        self.assertEqual(self.annotated(self.alice)[0]['role'], 'hunter')

    def test_startup_arrival_expires_and_is_cleared_on_failure_or_stop(self):
        for status in ('helper_error', 'disabled', 'game_closed', 'stopped'):
            with self.subTest(status=status):
                self.roles.update_peers('starting', [])
                self.observe()
                self.roles.update_peers(status, [])
                self.roles.update_peers('active', [self.alice])
                self.assertIsNone(self.annotated(self.alice)[0]['role'])
        self.roles.update_peers('starting', [])
        self.observe()
        self.now += 11
        self.roles.update_peers('active', [self.alice])
        self.assertIsNone(self.annotated(self.alice)[0]['role'])

        self.roles.update_peers('starting', [])
        self.observe()
        self.roles.clear()
        self.roles.update_peers('active', [self.alice])
        self.assertIsNone(self.annotated(self.alice)[0]['role'])

    def test_startup_requires_unique_matching_peer_and_clears_previous_binding(self):
        self.observe()
        self.assertEqual(self.annotated(self.alice)[0]['role'], 'invader')
        self.roles.update_peers('starting', [])
        self.assertIsNone(self.annotated(self.alice)[0]['role'])
        self.observe()
        namesake = dict(self.bob, name='ALICE')
        self.roles.update_peers('active', [self.alice, namesake])
        self.assertTrue(all(item['role'] is None for item in self.annotated(self.alice, namesake)))
        self.roles.update_peers('active', [self.alice])
        self.assertIsNone(self.annotated(self.alice)[0]['role'])

        self.roles.update_peers('starting', [])
        self.observe('Carol')
        self.roles.update_peers('active', [self.alice])
        self.assertIsNone(self.annotated(self.alice)[0]['role'])

    def test_pending_is_cleared_when_peer_set_becomes_empty_or_status_fails(self):
        carol = {'id': '76561198000000003', 'name': 'Carol'}
        for status, peers in (('active', []), ('helper_error', []), ('disabled', [])):
            with self.subTest(status=status):
                self.roles.clear()
                self.roles.update_peers('active', [self.alice])
                self.observe('Carol', role='hunter', event='joined')
                self.roles.update_peers(status, peers)
                self.roles.update_peers('active', [carol])
                self.assertIsNone(self.annotated(carol)[0]['role'])

    def test_duplicate_names_and_conflicting_roles_never_guess(self):
        same_name = dict(self.bob, name='ALICE')
        self.roles.update_peers('active', [self.alice, same_name])
        self.observe()
        self.assertTrue(all(item['role'] is None for item in self.annotated(self.alice, same_name)))
        self.roles.update_peers('active', [self.alice])
        self.assertIsNone(self.annotated(self.alice)[0]['role'])
        self.observe()
        self.observe(role='hunter', event='joined')
        self.assertIsNone(self.annotated(self.alice)[0]['role'])
        self.roles.update_peers('active', [])
        self.roles.update_peers('active', [self.alice])
        self.assertIsNone(self.annotated(self.alice)[0]['role'])
        self.observe(role='hunter', event='joined')
        self.assertEqual(self.annotated(self.alice)[0]['role'], 'hunter')

    def test_caller_cannot_supply_a_role_and_stop_clears_everything(self):
        untrusted = dict(self.alice, role='hunter')
        self.assertIsNone(self.annotated(untrusted)[0]['role'])
        self.observe()
        self.roles.clear()
        self.observe()
        self.assertIsNone(self.annotated(untrusted)[0]['role'])

    def test_concurrent_updates_observations_and_reads_are_safe(self):
        errors = []
        def work():
            try:
                for _ in range(200):
                    self.roles.update_peers('active', [self.alice])
                    self.observe()
                    self.annotated(self.alice)
            except Exception as error:
                errors.append(error)
        threads = [threading.Thread(target=work) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertFalse(errors)


if __name__ == '__main__':
    unittest.main()
