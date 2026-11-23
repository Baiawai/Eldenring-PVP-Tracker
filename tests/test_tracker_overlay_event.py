import unittest

from application import tracker_overlay_event as event


class TrackerOverlayEventTests(unittest.TestCase):
    def setUp(self):
        event.clear()

    def tearDown(self):
        event.clear()

    def test_removes_internal_markup_decodes_entities_and_does_not_consume(self):
        event.publish_html('<!--search-update--><span data-opponent="hidden">Victoire contre &lt;Joueur&gt;&#44; ami</span><br> Time: 42 s')
        self.assertEqual(event.latest(), 'Victoire contre <Joueur>, ami Time: 42 s')
        self.assertEqual(event.latest(), 'Victoire contre <Joueur>, ami Time: 42 s')

    def test_empty_events_do_not_erase_previous_event_and_clear_does(self):
        event.publish_html('Joueur détecté')
        event.publish_html('<!--internal-->')
        self.assertEqual(event.latest(), 'Joueur détecté')
        event.clear()
        self.assertEqual(event.latest(), '')

    def test_event_is_compact_and_whitespace_is_normalized(self):
        event.publish_html('a\n  b<br>' + 'x' * 300)
        self.assertTrue(event.latest().startswith('a b x'))
        self.assertEqual(len(event.latest()), 240)

    def test_language_change_retranslates_the_last_event_without_consuming_it(self):
        event.publish_html('Arrivée : &lt;Joueur&gt;', language='fra',
                           renderer=lambda language: 'Arrival : &lt;Joueur&gt;' if language == 'eng' else 'Ankunft')
        self.assertEqual(event.latest(), 'Arrivée : <Joueur>')
        self.assertEqual(event.latest('fra'), 'Arrivée : <Joueur>')
        self.assertEqual(event.latest('eng'), 'Arrival : <Joueur>')
        self.assertEqual(event.latest('deu'), 'Ankunft')
        self.assertEqual(event.latest('fra'), 'Arrivée : <Joueur>')
        event.publish_html('Nouvel événement')
        self.assertEqual(event.latest('eng'), 'Nouvel événement')

    def test_translation_failure_keeps_the_last_event_available(self):
        def fail(_language):
            raise RuntimeError('synthetic error')
        event.publish_html('Événement', language='fra', renderer=fail)
        with self.assertLogs('application.tracker_overlay_event', level='ERROR'):
            self.assertEqual(event.latest('eng'), 'Événement')


if __name__ == '__main__':
    unittest.main()
