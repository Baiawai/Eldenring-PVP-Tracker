import unittest
import importlib.util
import json
import sys
import types
from pathlib import Path
from unittest.mock import patch
from application.locale_catalog import messages, classify, tracker_notifications, PLACEHOLDER, _EVENT_BY_ID


class MultilingualCatalogTests(unittest.TestCase):
    def test_statistics_translations_are_complete_and_synchronised(self):
        root = Path(__file__).resolve().parents[1]
        packs = json.loads((root / 'application/locales/ui_packs.json').read_text(encoding='utf-8'))
        script = (root / 'static/ui-packs.js').read_text(encoding='utf-8')
        self.assertEqual(packs, json.loads(script.removeprefix('window.ELDEN_UI_PACKS = ').strip().removesuffix(';')))
        keys = ('stats_win_rate', 'stats_rate_explanation', 'stats_capture_explanation',
                'stats_chart_empty', 'stats_chart_error', 'stats_chart_expand', 'stats_chart_collapse',
                'stats_current_win_streak', 'stats_current_loss_streak', 'stats_score', 'stats_abandons',
                'stats_opponent_left', 'stats_connection_errors', 'stats_game_closed')
        for language, pack in packs.items():
            for key in keys:
                with self.subTest(language=language, key=key):
                    self.assertTrue(pack['modern'].get(key))

    def test_leaderboard_translations_are_complete(self):
        root = Path(__file__).resolve().parents[1]
        packs = json.loads((root / 'application/locales/ui_packs.json').read_text(encoding='utf-8'))
        keys = ('leaderboard_eyebrow', 'leaderboard_title', 'leaderboard_intro',
                'leaderboard_refresh', 'leaderboard_loading', 'leaderboard_profile_required', 'leaderboard_error',
                'leaderboard_rank', 'leaderboard_level', 'leaderboard_close_card', 'leaderboard_no_avatar', 'leaderboard_open_card',
                'leaderboard_previous_player', 'leaderboard_next_player')
        for language, pack in packs.items():
            for key in keys:
                with self.subTest(language=language, key=key):
                    self.assertTrue(pack['modern'].get(key))

    def test_information_faq_has_all_translations(self):
        root = Path(__file__).resolve().parents[1]
        packs = json.loads((root / 'application/locales/ui_packs.json').read_text(encoding='utf-8'))
        for language, pack in packs.items():
            self.assertTrue(pack['modern'].get('information_title'))
            self.assertTrue(pack['modern'].get('faq_contact'))
            for index in range(1, 15):
                for kind in ('q', 'a'):
                    with self.subTest(language=language, question=index, kind=kind):
                        self.assertTrue(pack['modern'].get(f'faq_{kind}_{index:02d}'))

    def test_every_interface_language_has_a_game_catalog_and_ocr_model(self):
        root = Path(__file__).resolve().parents[1]
        init = types.ModuleType('application.init')
        init.database_setting = ':memory:'
        spec = importlib.util.spec_from_file_location('_test_game_language', root / 'application/game_language.py')
        game_language = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'application.init': init}):
            spec.loader.exec_module(game_language)
        packs = json.loads((root / 'application/locales/ui_packs.json').read_text(encoding='utf-8'))
        self.assertEqual(set(game_language.UI_TO_GAME), set(packs) | {'fra'})
        self.assertEqual(set(game_language.UI_TO_GAME.values()), set(messages()))
        self.assertEqual(set(game_language.LANGUAGES), set(messages()))
        for _, model in game_language.LANGUAGES.values():
            self.assertTrue((root / 'application/locales/tessdata' / (model + '.traineddata')).is_file(), model)

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

    def test_summon_failure_and_timeout_are_single_events_in_every_language(self):
        for language, entries in messages().items():
            for identifier in ('2460000', '2490000'):
                with self.subTest(language=language, identifier=identifier):
                    events = classify(entries[identifier], language)
                    self.assertEqual([event['event'] for event in events].count('ally_summon_failed'), 1)
        for language, text in [('frafr', "Impossible d'invoquer l'adversaire."),
                               ('engus', 'Unable to summon adversary')]:
            self.assertNotIn('ally_summon_failed', [event['event'] for event in classify(text, language)])

    def test_english_hunter_message_remains_ambiguous(self):
        text = messages()['engus']['2600304'].replace('<?joinName?>', 'Xeno')
        self.assertEqual(classify(text, 'engus'), [{'event':'hunter_observed', 'values':{'joinName':'Xeno'}}])

    def test_more_specific_russian_template_keeps_full_player_name(self):
        text = messages()['rusru']['2642000'].replace('<?leaveName?>', 'Xeno')
        self.assertEqual(classify(text, 'rusru'), [{'event':'cooperator_dismissed', 'values':{'leaveName':'Xeno'}}])


if __name__ == '__main__':
    unittest.main()
