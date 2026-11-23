"""Resolve a hunter's side only within an unambiguous observed episode."""
import tempfile
import unittest
import re
from contextlib import closing
from pathlib import Path

from test_coinvader_sightings import load_sightings
from application.locale_catalog import messages, tracker_notifications


class HunterContextTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.sightings = load_sightings()
        self.sightings.database_capture = str(Path(self.temp.name) / 'history.sqlite')
        self.sightings.encryption_key = lambda: b'test-key'
        self.sightings.encrypt_value = lambda value: value.encode('utf-8')
        self.sightings.decrypt_value = lambda value: value

    def add(self, name, event, timestamp, mode='Unknown', relation='unknown'):
        self.sightings.record_sighting({'name': name, 'role': 'hunter', 'event': event,
                                        'mode': mode, 'relation': relation}, observed_at=timestamp)

    def test_historical_join_and_departure_enrich_each_other_without_rewriting_data(self):
        for name, mode, relation in [('BlueAlly', 'Defense', 'ally'), ('BlueEnemy', 'Invasion', 'opponent')]:
            self.add(name, 'summoning', '2026-01-01 12:00:00')
            self.add(name, 'joined', '2026-01-01 12:00:10', mode, relation)
            self.add(name, 'completed', '2026-01-01 12:03:00')
        result = self.sightings.read_sightings()
        for item in result:
            expected = ('Defense', 'ally') if item['name'] == 'BlueAlly' else ('Invasion', 'opponent')
            self.assertEqual((item['mode'], item['relation']), expected)
        with closing(self.sightings._connect()) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM player_sightings WHERE mode='Unknown' AND relation='unknown'").fetchone()[0], 4)

    def test_unknown_conflicting_and_separate_encounters_stay_unknown(self):
        self.add('Unknown', 'joined', '2026-01-01 12:00:00')
        self.add('Unknown', 'died', '2026-01-01 12:02:00')
        self.add('Conflict', 'summoning', '2026-01-01 12:00:00', 'Defense', 'ally')
        self.add('Conflict', 'joined', '2026-01-01 12:00:10', 'Invasion', 'opponent')
        self.add('Conflict', 'died', '2026-01-01 12:02:00')
        self.add('Again', 'joined', '2026-01-01 12:00:00', 'Defense', 'ally')
        self.add('Again', 'left', '2026-01-01 12:01:00', 'Defense', 'ally')
        self.add('Again', 'joined', '2026-01-01 12:02:00')
        self.add('Again', 'died', '2026-01-01 12:03:00')
        self.add('Late', 'joined', '2026-01-01 12:00:00', 'Defense', 'ally')
        self.add('Late', 'died', '2026-01-01 12:31:00')
        self.add('Alone', 'died', '2026-01-01 12:00:00', 'Defense', 'ally')
        self.add('Alone', 'completed', '2026-01-01 12:01:00')
        items = self.sightings.read_sightings()
        unknown = [(item['name'], item['event']) for item in items if item['mode'] == 'Unknown']
        self.assertCountEqual(unknown, [('Unknown', 'joined'), ('Unknown', 'died'), ('Conflict', 'died'),
                                        ('Again', 'joined'), ('Again', 'died'), ('Late', 'died'),
                                        ('Alone', 'completed')])

    def test_repeated_arrival_starts_a_new_episode(self):
        self.add('Hunter', 'joined', '2026-01-01 12:00:00', 'Defense', 'ally')
        self.add('Hunter', 'joined', '2026-01-01 12:02:00')
        self.add('Hunter', 'left', '2026-01-01 12:03:00')
        items = self.sightings.read_sightings()
        self.assertEqual([item['mode'] for item in items], ['Defense', 'Unknown', 'Unknown'])

    def test_hunter_messages_use_the_confirmed_combat_side_in_every_game_language(self):
        for language, catalog in messages().items():
            for identifier in ('2600304', '2602304', '2602354', '2620304', '2622304',
                               '2630304', '2632304', '2640304', '2642304'):
                source = re.sub(r'<\?[^>]+\?>', 'TestHunter', catalog[identifier])
                translated = '\n'.join(tracker_notifications(source, language))
                for mode, relation in (('Defense', 'ally'), ('Invasion', 'opponent')):
                    with self.subTest(language=language, identifier=identifier, mode=mode):
                        found = self.sightings.parse_sightings(translated, mode, True)
                        self.assertTrue(found)
                        self.assertTrue(all(item['mode'] == mode and item['relation'] == relation for item in found))


if __name__ == '__main__':
    unittest.main()
