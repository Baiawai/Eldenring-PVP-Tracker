"""Arena role inference uses only current, unambiguous synthetic peers."""
import importlib.util
import itertools
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from application.overlay_peer_roles import annotate_arena_duelist


def load_history():
    history = types.ModuleType('application.detection_history')
    identifiers = itertools.count(1)
    history.record_detection = Mock(side_effect=lambda *args: next(identifiers))
    history.update_detection = Mock(return_value=True)
    path = Path(__file__).resolve().parents[1] / 'application' / 'steam_history.py'
    spec = importlib.util.spec_from_file_location('application._arena_history_test', path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {'application.detection_history': history}):
        spec.loader.exec_module(module)
    return module, history


class ArenaOverlayRolesTests(unittest.TestCase):
    def setUp(self):
        self.history, self.storage = load_history()
        self.peer = {'id': '76561198000000001', 'name': 'Player'}
        self.other = {'id': '76561198000000002', 'name': 'Other'}

    def test_current_unique_participant_is_read_without_side_effects(self):
        self.assertEqual(self.history.active_arena_participant_id(), '')
        self.history.observe('active', [self.peer], 'Arena')
        self.history.begin_arena()
        before = self.storage.record_detection.call_count
        self.assertEqual(self.history.active_arena_participant_id(), self.peer['id'])
        self.assertEqual(self.storage.record_detection.call_count, before)
        self.history.seal_arena_participant()
        self.assertEqual(self.history.active_arena_participant_id(), '')

    def test_disconnect_and_reconnect_cannot_revive_stale_participant(self):
        self.history.observe('active', [self.peer], 'Arena')
        self.history.begin_arena()
        self.history.observe('active', [], 'Arena')
        self.assertEqual(self.history.active_arena_participant_id(), '')
        self.history.observe('active', [self.peer], 'Arena')
        self.assertEqual(self.history.active_arena_participant_id(), '')
        self.history.cancel_arena()
        self.assertEqual(self.history.active_arena_participant_id(), '')

    def test_more_than_one_peer_remains_ambiguous_for_the_encounter(self):
        self.history.observe('active', [self.peer], 'Arena')
        self.history.begin_arena()
        self.history.observe('active', [self.peer, self.other], 'Arena')
        self.assertEqual(self.history.active_arena_participant_id(), '')
        self.history.observe('active', [self.peer], 'Arena')
        self.assertEqual(self.history.active_arena_participant_id(), '')

    def test_arena_annotation_requires_active_tracking_and_matching_unique_peer(self):
        card = dict(self.peer, role='invader')
        flags = dict(mode='Arena', mode_detected=True, running=True, ready=True,
                     error=False, fight=True, participant_id=self.peer['id'])
        self.assertEqual(annotate_arena_duelist([card], **flags)[0]['role'], 'duelist')
        for key, value in [('running', False), ('ready', False), ('error', True),
                           ('fight', False), ('participant_id', ''),
                           ('participant_id', self.other['id'])]:
            with self.subTest(key=key, value=value):
                self.assertIsNone(annotate_arena_duelist([card], **dict(flags, **{key: value}))[0]['role'])
        both = annotate_arena_duelist([card, self.other], **flags)
        self.assertTrue(all(item['role'] is None for item in both))
        self.assertEqual(annotate_arena_duelist([card], **dict(flags, mode='Defense'))[0]['role'], 'invader')
        self.assertEqual(card['role'], 'invader')


if __name__ == '__main__':
    unittest.main()
