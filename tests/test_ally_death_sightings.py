"""Recognize observed cooperator deaths without assigning combat results."""
import html
import unittest

from application.locale_catalog import messages, tracker_notifications
from application.overlay_peer_roles import RoleTracker
from test_coinvader_sightings import load_sightings
from test_counter_localization import load_localization


class AllyDeathSightingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sightings = load_sightings()

    def test_game_catalog_deaths_are_classified_for_defense_and_invasion(self):
        for language, catalog in messages().items():
            for identifier in ('2620000', '2622000'):
                with self.subTest(language=language, identifier=identifier):
                    original = catalog[identifier].replace('<?deadName?>', 'TestAlly')
                    translated = '\n'.join(tracker_notifications(original, language))
                    self.assertTrue(translated)
                    for mode, role, relation in (('Defense', 'ally', 'ally'),
                                                 ('Invasion', 'cooperator', 'opponent')):
                        observed = self.sightings.parse_sightings(translated, mode, True, in_combat=True)
                        self.assertEqual(observed, [{'name': 'TestAlly', 'role': role, 'relation': relation,
                                                    'mode': mode, 'event': 'died'}])

    def test_defense_ally_can_die_before_pvp_combat_but_unknown_side_is_not_guessed(self):
        text = 'Le Doigt crochu TestAlly est mort.'
        expected = [{'name': 'TestAlly', 'role': 'ally', 'relation': 'ally',
                     'mode': 'Defense', 'event': 'died'}]
        self.assertEqual(self.sightings.parse_sightings(text, 'Defense', True, in_combat=False), expected)
        self.assertEqual(self.sightings.parse_sightings(text, 'Defense', False, in_combat=False), [])
        self.assertEqual(self.sightings.parse_sightings(text, 'Invasion', True, in_combat=False), [])
        self.assertEqual(self.sightings.parse_sightings(text, 'Arena', True, in_combat=True), [])

    def test_confirmation_clears_only_the_matching_overlay_role(self):
        tracker = self.sightings.SightingTracker()
        roles = RoleTracker()
        ally = {'id': '76561198000000001', 'name': 'TestAlly'}
        hunter = {'id': '76561198000000002', 'name': 'TestHunter'}
        roles.update_peers('active', [ally, hunter])
        roles.observe({'name': 'TestAlly', 'role': 'ally', 'event': 'joined'})
        roles.observe({'name': 'TestHunter', 'role': 'hunter', 'event': 'joined'})
        text = 'Le Doigt crochu TestAlly est mort.'
        self.assertEqual(tracker.observe(text, '', 'Defense', True, now=1), [])
        self.assertEqual(roles.annotate([ally, hunter])[0]['role'], 'ally')
        observations = tracker.observe(text, '', 'Defense', True, now=2)
        self.assertEqual(len(observations), 1)
        roles.observe(observations[0])
        self.assertIsNone(roles.annotate([ally, hunter])[0]['role'])
        self.assertEqual(roles.annotate([ally, hunter])[1]['role'], 'hunter')

    def test_ally_death_event_has_existing_translations_in_each_interface_language(self):
        _, localization = load_localization()
        for language, pack in localization.packs().items():
            with self.subTest(language=language):
                event = 'Allié mort : TestAlly'
                expected = event if language == 'fra' else html.escape(pack['modern']['ally_died'], quote=False) + ' : TestAlly'
                self.assertEqual(localization.localize_counter(event, language), expected)


if __name__ == '__main__':
    unittest.main()
