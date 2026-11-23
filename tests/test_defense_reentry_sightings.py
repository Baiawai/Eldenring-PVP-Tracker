"""Separate a confirmed new invasion from repeated OCR frames."""
import tempfile
import unittest
from pathlib import Path

from test_coinvader_sightings import load_sightings


class DefenseReentrySightingsTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.sightings = load_sightings()
        self.sightings.database_capture = str(Path(self.directory.name) / 'sightings.sqlite')

    def record(self, event, name='Invader', mode='Defense', relation='opponent'):
        return self.sightings.record_sighting({
            'name': name, 'role': 'invader', 'relation': relation,
            'mode': mode, 'event': event,
        }, observed_at='2026-01-01 12:00:00')

    def test_confirmed_death_and_reentry_open_a_new_cycle_even_in_same_second(self):
        self.assertTrue(self.record('invaded'))
        self.assertFalse(self.record('invaded'))
        self.assertTrue(self.record('died'))
        self.assertFalse(self.record('died'))
        self.assertTrue(self.record('invaded'))
        self.assertFalse(self.record('invaded'))
        self.assertTrue(self.record('died'))
        self.assertFalse(self.record('died'))

    def test_other_players_or_modes_cannot_open_a_defense_cycle(self):
        self.assertTrue(self.record('invaded'))
        self.assertTrue(self.record('died', name='Other'))
        self.assertFalse(self.record('invaded'))
        self.assertTrue(self.record('died', mode='Invasion', relation='coinvader'))
        self.assertFalse(self.record('invaded'))


if __name__ == '__main__':
    unittest.main()
