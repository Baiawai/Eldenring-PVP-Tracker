"""Check tracker-generated labels without opening the user's data directory."""
import html
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from application.locale_catalog import messages

ROOT = Path(__file__).resolve().parents[1]


def load_localization():
    # Loading the real language mapping needs only this stub and avoids
    # importing application.init, which creates and migrates user databases.
    init = types.ModuleType('application.init')
    init.database_setting = ':memory:'
    language_spec = importlib.util.spec_from_file_location('_isolated_game_language', ROOT / 'application/game_language.py')
    language = importlib.util.module_from_spec(language_spec)
    with patch.dict(sys.modules, {'application.init': init}):
        language_spec.loader.exec_module(language)
    localization_spec = importlib.util.spec_from_file_location('_isolated_ui_localization', ROOT / 'application/ui_localization.py')
    localization = importlib.util.module_from_spec(localization_spec)
    with patch.dict(sys.modules, {'application.game_language': language}):
        localization_spec.loader.exec_module(localization)
    return language, localization


class CounterLocalizationTests(unittest.TestCase):
    def test_hunter_objective_uses_complete_localized_sentence_and_safe_name(self):
        language, localization = load_localization()
        name = 'A&lt;B&gt;&amp;C&#x27;s,Test'
        original = "Son objectif accompli, le Chasseur " + name + " s'en est retourné dans son monde."
        self.assertEqual(localization.localize_counter(original, 'fra'), original)
        for interface, pack in localization.packs().items():
            with self.subTest(language=interface):
                template = pack['modern']['hunter_objective_completed_message']
                self.assertEqual(template.count('{name}'), 1)
                self.assertEqual(localization.localize_counter(original, interface),
                                 html.escape(template, quote=False).replace('{name}', name).replace('\n', '<br>'))
                if interface in language.UI_TO_GAME:
                    official = localization.display_game_text(messages()[language.UI_TO_GAME[interface]]['2610304'])
                    self.assertEqual(template, official.replace('<?leaveName?>', '{name}'))
                self.assertIn(name, localization.localize_counter(original, interface))
                self.assertNotIn('<B>', localization.localize_counter(original, interface))
        # Existing event labels remain interpretable without migrating history.
        self.assertEqual(localization.localize_counter('Objectif du chasseur accompli : A', 'eng'),
                         localization.packs()['eng']['modern']['hunter_objective_completed'] + ' : A')

    def test_overlay_result_duration_is_localized_without_changing_other_text(self):
        _, localization = load_localization()
        cases = ('<br> Time: 23 s', '<br> Time: —', '<br> Time: -2 s')
        for interface in ['fra', *localization.packs()]:
            with self.subTest(language=interface):
                label = 'Temps' if interface == 'fra' else localization.packs()[interface]['modern']['time']
                for suffix in cases:
                    original = 'Résultat &lt;Joueur&gt;' + suffix
                    expected = original.replace('Time:', html.escape(label, quote=False) + ':')
                    self.assertEqual(localization.localize_overlay_time(original, interface), expected)
                # Text belonging to a player or a different notification is untouched.
                untouched = 'Time: Player &lt;br&gt; <br> Time: combat'
                self.assertEqual(localization.localize_overlay_time(untouched, interface), untouched)

    def test_defense_arrival_uses_localized_player_first_message(self):
        _, localization = load_localization()
        name = 'Ztira&lt;test&gt;&amp;'
        original = name + ' a envahi votre monde'
        self.assertEqual(localization.localize_counter(original, 'fra'), original)
        for interface, pack in localization.packs().items():
            with self.subTest(language=interface):
                template = pack['modern']['tracking_defending_against']
                self.assertEqual(template.count('{name}'), 1)
                expected = html.escape(template, quote=False).replace('{name}', name).replace('\n', '<br>')
                result = localization.localize_counter(original, interface)
                self.assertEqual(result, expected)
                self.assertIn(name, result)
                self.assertNotIn('<test>', result)

    def test_previous_defense_message_still_localizes(self):
        _, localization = load_localization()
        result = localization.localize_counter('Monde envahi : combat contre Ztira', 'eng')
        self.assertIn('Ztira', result)
        self.assertNotIn('Monde envahi', result)

    def test_unnamed_invasion_uses_the_first_complete_game_line(self):
        language, localization = load_localization()
        for interface, locale in language.UI_TO_GAME.items():
            with self.subTest(language=interface):
                text = localization.localize_counter('Vous avez envahi un autre monde', interface)
                expected = ('Vous avez envahi un autre monde' if interface == 'fra' else
                            html.escape(localization.display_game_text(messages()[locale]['2601200'].split('\n', 1)[0]), quote=False))
                self.assertEqual(text, expected)
                self.assertNotIn('<?hostName?>', text)
                self.assertNotIn('&lt;?hostName?&gt;', text)

    def test_arena_mode_prefix_translates_without_touching_existing_suffix(self):
        language, localization = load_localization()
        suffix = 'A &lt;B&gt; &amp; C - 1v1'
        original = 'MODE : DUEL - ' + suffix
        for interface in language.UI_TO_GAME:
            with self.subTest(language=interface):
                text = localization.localize_counter(original, interface)
                if interface == 'fra':
                    self.assertEqual(text, original)
                else:
                    modern = localization.packs()[interface]['modern']
                    expected = html.escape(modern['online_mode'], quote=False) + ' : ' + html.escape(modern['capture_duel'], quote=False) + ' - ' + suffix
                    self.assertEqual(text, expected)
                self.assertNotIn('<B>', text)

    def test_game_templates_render_without_private_glyphs_and_keep_names_intact(self):
        language, localization = load_localization()
        # Names are already HTML-escaped by the caller. A private-use code point
        # in a name must not be changed when normalizing the game template.
        name = 'Player&lt;\uf716&gt;&amp;Friend'
        for interface, locale in language.UI_TO_GAME.items():
            if interface == 'fra':
                continue
            with self.subTest(language=interface):
                game = messages()[locale]
                rendered = localization.localize_counter('Vous avez envahi le monde de ' + name, interface)
                expected = html.escape(localization.display_game_text(game['2601200']), quote=False)
                expected = expected.replace('&lt;?hostName?&gt;', name).replace('\n', '<br>')
                self.assertEqual(rendered, expected)
                self.assertIn(name, rendered)
                self.assertNotIn('<Player', rendered)
                self.assertFalse(any('\ue000' <= ch <= '\uf8ff' for ch in rendered.replace(name, '')))
                for source in ("Impossible d'invoquer l'allié.", 'Invocation de l’allié…',
                               "Invasion d'un autre monde…", "Vous tentez d'envahir un autre monde",
                               'Vous avez envahi un autre monde'):
                    display = localization.localize_counter(source, interface)
                    self.assertFalse(any('\ue000' <= ch <= '\uf8ff' for ch in display), (source, display))
                for ident in ('2611010', '2661210', '2661220', '2661225'):
                    notice = localization.display_game_text(game[ident])
                    self.assertFalse(any('\ue000' <= ch <= '\uf8ff' for ch in notice), ident)

    def test_interface_only_languages_translate_tracking_events_and_preserve_names(self):
        language, localization = load_localization()
        for interface, pack in localization.packs().items():
            if interface in language.UI_TO_GAME:
                continue
            with self.subTest(language=interface):
                modern = pack['modern']
                self.assertEqual(localization.localize_counter('Invocation de l’allié…', interface),
                                 html.escape(modern['tracking_summoning_ally'], quote=False))
                self.assertEqual(localization.localize_counter('Vous avez envahi un autre monde', interface),
                                 html.escape(modern['tracking_invaded_world'], quote=False))
                name = 'A&lt;B&gt;&amp;C'
                result = localization.localize_counter('Vous avez envahi le monde de ' + name, interface)
                self.assertEqual(result, html.escape(modern['tracking_invaded_host'], quote=False).replace('{name}', name))
                self.assertNotIn('<B>', result)
                item = 'A&lt;B&gt;'
                result = localization.localize_counter('Impossible d’acquérir ' + item + '.<br>warning', interface)
                self.assertIn(item, result)
                self.assertNotIn('<B>', result)
                near = localization.localize_counter("Vous tentez d'envahir un autre monde (proches uniquement)", interface)
                self.assertEqual(near, html.escape(modern['tracking_search_near'], quote=False))

    def test_counter_match_result_labels_match_backend_events(self):
        _, localization = load_localization()
        for interface, pack in localization.packs().items():
            for counter, backend in ((7, 9), (8, 10), (9, 12), (12, 20)):
                with self.subTest(language=interface, counter=counter):
                    self.assertTrue(pack['counter'][counter])
                    self.assertEqual(pack['counter'][counter], pack['backend'][backend])


if __name__ == '__main__':
    unittest.main()
