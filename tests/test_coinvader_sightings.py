import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from application.locale_catalog import messages, tracker_notifications

ROOT = Path(__file__).resolve().parents[1]

def load_sightings():
    init = types.ModuleType('application.init')
    init.database_capture = ':memory:'
    secur = types.ModuleType('application.secur')
    secur.app_get = secur.app_insert = secur.app_name = lambda *args: b''
    with patch.dict(sys.modules, {'application.init':init, 'application.secur':secur}):
        spec = importlib.util.spec_from_file_location('_test_coinvaders_sightings', ROOT/'application/player_sightings.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module

class CoinvaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.sightings = load_sightings()

    def check(self, text, context, event, relation, name='G'):
        result = self.sightings.parse_sightings(text, context, True, in_combat=True)
        self.assertEqual(result, [{'name':name, 'role':'invader', 'relation':relation, 'mode':context, 'event':event}])

    def test_french_bloody_finger_and_recusant(self):
        for text in ['Invasion par le Doigt sanglant G.', 'Invasion par le Réfractaire G.',
                     'Le Doigt sanglant G a envahi votre monde !', 'Le Réfractaire G a envahi votre monde !']:
            with self.subTest(text=text):
                self.check(text, 'Invasion', 'invaded', 'coinvader')
                self.check(text, 'Defense', 'invaded', 'opponent')
        for text in ['Le Doigt sanglant G est mort.', 'Le Réfractaire G a péri.', 'Le Refractaire G a peri.']:
            with self.subTest(text=text):
                self.check(text, 'Invasion', 'died', 'coinvader')
                self.check(text, 'Defense', 'died', 'opponent')
        self.assertFalse(self.sightings.parse_sightings('Invasion par le Réfractaire G.', 'Arena', True))
        self.assertFalse(self.sightings.parse_sightings('Invasion par le Réfractaire G.', 'Invasion', True, in_combat=False))

    def test_all_game_languages_adapt_arrival_and_death(self):
        for language, catalog in messages().items():
            for ident, event in [('2602250','invaded'),('2602260','invaded'),('2620200','died'),('2620210','died')]:
                with self.subTest(language=language, identifier=ident):
                    text = catalog[ident].replace('<?joinName?>','G').replace('<?deadName?>','G')
                    adapted = tracker_notifications(text, language)
                    self.assertTrue(adapted)
                    matches = [event for a in adapted for event in self.sightings.parse_sightings(a,'Invasion',True)]
                    self.assertTrue(any(x['name']=='G' and x['relation']=='coinvader' and x['event']==event for x in matches), matches)

    def test_confirmation_uses_both_ocr_readings(self):
        tracker = self.sightings.SightingTracker()
        text = 'Invasion par le Réfractaire G.'
        observed = tracker.observe(text, text, 'Invasion', True, now=1, in_combat=True)
        self.assertEqual(len(observed), 1)
        self.assertEqual(observed[0]['relation'], 'coinvader')
        self.assertEqual(observed[0]['name'], 'G')

if __name__ == '__main__': unittest.main()
