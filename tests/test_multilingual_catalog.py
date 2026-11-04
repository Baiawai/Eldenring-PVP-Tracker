import unittest
from application.locale_catalog import messages, classify, tracker_notifications, PLACEHOLDER, _EVENT_BY_ID


class MultilingualCatalogTests(unittest.TestCase):
    def test_all_catalog_messages_map_to_their_intended_events(self):
        catalog = messages()
        self.assertEqual(len(catalog), 15)
        for language, entries in catalog.items():
            for identifier, template in entries.items():
                with self.subTest(language=language, identifier=identifier):
                    sample = PLACEHOLDER.sub(
                        lambda m: '42' if 'Count' in m.group(1) or 'Time' in m.group(1) else 'TestPlayer', template)
                    intended = _EVENT_BY_ID[identifier]
                    events = classify(sample, language)
                    acceptable = {intended}
                    if intended in ('hunter_joined', 'hunter_summoning'):
                        acceptable.add('hunter_observed')
                    candidates = [event for event in events if event['event'] in acceptable]
                    self.assertTrue(candidates, events)
                    if any(m.group(1).endswith('Name') for m in PLACEHOLDER.finditer(template)):
                        self.assertTrue(any('TestPlayer' in event['values'].values() for event in candidates), events)
                    self.assertFalse([event for event in events if event['event'] not in acceptable], events)

    def test_legacy_adapter_preserves_host_and_outcome_for_each_language(self):
        for language, entries in messages().items():
            with self.subTest(language=language):
                start = entries['2601200'].replace('<?hostName?>', 'Ash.The One')
                converted = tracker_notifications(start, language)
                self.assertTrue(any('Ash.The One' in message and 'Hôte des Doigts' in message for message in converted), converted)
                victory = tracker_notifications(entries['2611200'], language)
                self.assertTrue(any('Hôte des Doigts vaincu' in message for message in victory), victory)
                self.assertFalse(any('Vous avez péri' in message for message in victory), victory)
                defeat = tracker_notifications(entries['2621200'], language)
                self.assertTrue(any('Vous avez péri' in message for message in defeat), defeat)
                self.assertFalse(any('Hôte des Doigts vaincu' in message for message in defeat), defeat)

    def test_nonprinting_thai_separators_do_not_break_recognition(self):
        text = messages()['thath']['2300000'].replace('\u200b', '')
        self.assertIn('ally_summoning', [event['event'] for event in classify(text, 'thath')])

    def test_player_names_with_internal_punctuation_are_preserved(self):
        for language in ('frafr', 'engus', 'jpnjp', 'araae'):
            text = messages()[language]['2600200'].replace('<?joinName?>', 'Ash.The One')
            matches = classify(text, language)
            self.assertIn({'event':'defense_invaded', 'values':{'joinName':'Ash.The One'}}, matches)

    def test_unrelated_text_is_not_a_pvp_result(self):
        for language in messages():
            events = classify('This is not an Elden Ring notification.', language)
            self.assertFalse(any(item['event'] in ('invasion_victory', 'invasion_defeat', 'arena_victory', 'arena_defeat') for item in events))

    def test_english_hunter_message_remains_ambiguous(self):
        text = messages()['engus']['2600304'].replace('<?joinName?>', 'Xeno')
        self.assertEqual(classify(text, 'engus'), [{'event':'hunter_observed', 'values':{'joinName':'Xeno'}}])

    def test_more_specific_russian_template_keeps_full_player_name(self):
        text = messages()['rusru']['2642000'].replace('<?leaveName?>', 'Xeno')
        self.assertEqual(classify(text, 'rusru'), [{'event':'cooperator_dismissed', 'values':{'leaveName':'Xeno'}}])


if __name__ == '__main__':
    unittest.main()
