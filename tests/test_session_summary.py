import unittest
from application.session_summary import SessionSummary

class SessionSummaryTests(unittest.TestCase):
    def test_modes_results_and_reset(self):
        session = SessionSummary()
        session.start()
        session.combat_started('Arena')
        session.combat_finished('victory', 'SteamPlayer')
        session.combat_started('Invasion', 'Hôte')
        session.combat_finished('victory')
        self.assertEqual(session.snapshot(), {'combats':2, 'victories':2, 'defeats':0, 'streak':2,
                         'last':{'mode':'Invasion', 'opponent':'Hôte', 'result':'victory'}})
        session.combat_started('Defense', 'Envahisseur')
        session.combat_finished('defeat')
        self.assertEqual((session.snapshot()['defeats'], session.snapshot()['streak']), (1, 0))
        session.start()
        self.assertEqual(session.snapshot()['combats'], 0)
        self.assertEqual(session.snapshot()['last']['opponent'], 'Envahisseur')

    def test_draw_no_result_and_correction(self):
        session = SessionSummary()
        session.combat_finished('victory')
        self.assertEqual(session.snapshot()['victories'], 0)
        session.combat_started('Arena')
        session.combat_finished('victory')
        session.combat_started('Arena')
        session.combat_finished('draw')
        self.assertEqual(session.snapshot()['streak'], 0)
        session.combat_started('Invasion', 'Hôte')
        session.combat_finished('no_result')
        session.correct_connection_error()
        self.assertEqual(session.snapshot()['last']['result'], 'connection_error')
        self.assertEqual(session.snapshot()['combats'], 3)
        self.assertEqual(session.snapshot()['victories'], 1)
        self.assertEqual(session.snapshot()['defeats'], 0)

if __name__ == '__main__':
    unittest.main()
