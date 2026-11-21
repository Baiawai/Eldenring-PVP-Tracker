"""Recognize a third-party hunter's completed objective without scoring it."""
import html
import unittest

from application.locale_catalog import messages, tracker_notifications
from application.overlay_peer_roles import RoleTracker
from test_coinvader_sightings import load_sightings
from test_counter_localization import load_localization


class HunterObjectiveSightingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sightings = load_sightings()

    def test_catalog_variants_match_in_all_game_languages(self):
        for language, catalog in messages().items():
            for identifier in ('2610304', '2612304'):
                with self.subTest(language=language, identifier=identifier):
                    source = catalog[identifier].replace('<?leaveName?>', 'TestHunter')
                    if language == 'frafr':
                        translated = source
                    else:
                        translated = '\n'.join(tracker_notifications(source, language))
                    for mode, relation in (('Defense', 'ally'), ('Invasion', 'opponent')):
                        self.assertEqual(self.sightings.parse_sightings(translated, mode, True),
                                         [{'name': 'TestHunter', 'role': 'hunter', 'relation': relation,
                                           'mode': mode, 'event': 'completed'}])

    def test_unknown_context_and_confirmation_do_not_assign_a_side(self):
        text = "Son objectif accompli, le Chasseur TestHunter s'en est retourné dans son monde."
        tracker = self.sightings.SightingTracker()
        self.assertEqual(tracker.observe(text, '', 'Defense', False, now=1), [])
        self.assertEqual(tracker.observe(text, '', 'Defense', False, now=2),
                         [{'name': 'TestHunter', 'role': 'hunter', 'relation': 'unknown',
                           'mode': 'Unknown', 'event': 'completed'}])

    def test_french_ocr_line_break_never_creates_a_false_departure(self):
        for separator in (' ', '\n'):
            text = "Son objectif accompli, le Chasseur TestHunter" + separator + "s'en est retourné dans son monde."
            with self.subTest(separator=repr(separator)):
                self.assertEqual(self.sightings.parse_sightings(text, 'Defense', True),
                                 [{'name': 'TestHunter', 'role': 'hunter', 'relation': 'ally',
                                   'mode': 'Defense', 'event': 'completed'}])

    def test_completion_removes_only_matching_player_role(self):
        roles = RoleTracker()
        a = {'id': '76561198000000001', 'name': 'TestHunter'}
        b = {'id': '76561198000000002', 'name': 'OtherHunter'}
        roles.update_peers('active', [a, b])
        for peer in (a, b):
            roles.observe({'name': peer['name'], 'role': 'hunter', 'event': 'joined'})
        roles.observe({'name': 'TestHunter', 'role': 'hunter', 'event': 'completed'})
        self.assertEqual([item['role'] for item in roles.annotate([a, b])], [None, 'hunter'])

    def test_event_is_localized_for_each_interface_language(self):
        _, localization = load_localization()
        for language, pack in localization.packs().items():
            with self.subTest(language=language):
                label = pack['modern']['hunter_objective_completed']
                self.assertTrue(label.strip())
                self.assertEqual(localization.localize_counter('Objectif du chasseur accompli : TestHunter', language),
                                 html.escape(label, quote=False) + ' : TestHunter')


if __name__ == '__main__':
    unittest.main()
