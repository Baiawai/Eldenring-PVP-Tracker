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


if __name__ == '__main__':
    unittest.main()
