import importlib.util
import sqlite3
import sys
import tempfile
import types
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch


def load_module(database):
    init = types.ModuleType('application.init')
    init.database_setting = str(database)
    path = Path(__file__).resolve().parents[1] / 'application' / 'overlay_settings.py'
    spec = importlib.util.spec_from_file_location('application._overlay_settings_test', path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {'application.init': init}):
        spec.loader.exec_module(module)
    return module


class OverlaySettingsTests(unittest.TestCase):
    def test_new_installation_uses_the_requested_overlay_defaults(self):
        with tempfile.TemporaryDirectory() as temp:
            module = load_module(Path(temp) / 'settings.db')
            expected = {
                'avatar_size': 48, 'background_color': '#1a1a1a', 'background_opacity': 50,
                'border_color': '#cab486', 'border_radius': 4, 'show_overlay_border': False, 'card_size': 60, 'card_spacing': 8,
                'font_size': 15, 'width_percent': 80, 'ping_bad_color': '#de7777', 'ping_good_color': '#85cda4',
                'ping_medium_color': '#e1c16e', 'position': 'top_right',
                'show_status': True, 'show_mode': True, 'show_peers': True, 'show_event': True,
                'show_avatars': True, 'show_player_name': True, 'show_role': True, 'show_steam_id': False, 'show_country': True, 'show_ping': True,
                'show_ping_average': False, 'show_jitter': False, 'show_quality': False, 'show_duration': True,
                'show_player_count': False, 'show_rank': True, 'show_player_stats': True,
                'text_color': '#c7c7c7', 'text_opacity': 50, 'visibility_mode': 'game_visible',
            }
            self.assertTrue(module.enabled())
            self.assertEqual(module.options(), expected)

    def test_saved_preferences_remain_prioritized_over_new_defaults(self):
        with tempfile.TemporaryDirectory() as temp:
            module = load_module(Path(temp) / 'settings.db')
            previous = {'background_opacity': 85, 'text_opacity': 100, 'background_color': '#18181a',
                        'text_color': '#f5efdc', 'border_color': '#ab8e53', 'border_radius': 9,
                        'font_size': 18, 'card_size': 80, 'visibility_mode': 'capture', 'show_mode': False}
            module.set_enabled(False)
            module.set_options(previous)
            self.assertFalse(module.enabled())
            values = load_module(module.database_setting).options()
            for key, value in previous.items():
                self.assertEqual(values[key], value, key)

    def test_border_options_default_persist_and_validate_atomically(self):
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / 'settings.db'
            module = load_module(database)
            module.set_options({'background_color': '#654321', 'show_mode': False})
            self.assertEqual(module.options()['border_radius'], 4)
            self.assertEqual(module.options()['border_color'], '#cab486')
            for radius in (0, 30):
                module.set_options({'border_radius': radius, 'border_color': '#CDEF12'})
                saved = load_module(database).options()
                self.assertEqual(saved['border_radius'], radius)
                self.assertEqual(saved['border_color'], '#cdef12')
                self.assertEqual(saved['background_color'], '#654321')
                self.assertFalse(saved['show_mode'])
            for invalid in ({'border_radius': -1}, {'border_radius': 31},
                            {'border_radius': True}, {'border_radius': 1.5},
                            {'border_color': 'red'}, {'border_color': '#123'},
                            {'border_color': '#ffffff00'},
                            {'border_color': '#abcdef', 'border_radius': 31}):
                with self.subTest(options=invalid), self.assertRaises(ValueError):
                    module.set_options(invalid)
                saved = module.options()
                self.assertEqual(saved['border_radius'], 30)
                self.assertEqual(saved['border_color'], '#cdef12')

    def test_outer_border_visibility_is_independent_and_persistent(self):
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / 'settings.db'
            module = load_module(database)
            module.set_enabled(False)
            module.set_options({'border_radius': 21, 'border_color': '#123456'})
            self.assertFalse(module.options()['show_overlay_border'])
            for value in (False, True, False):
                module.set_options({'show_overlay_border': value})
                loaded = load_module(database)
                self.assertIs(loaded.options()['show_overlay_border'], value)
                self.assertEqual(loaded.options()['border_radius'], 21)
                self.assertEqual(loaded.options()['border_color'], '#123456')
                self.assertFalse(loaded.enabled())
            for invalid in (0, 1, 'false', None):
                with self.subTest(value=invalid), self.assertRaises(ValueError):
                    module.set_options({'show_overlay_border': invalid, 'border_radius': 0})
                self.assertFalse(module.options()['show_overlay_border'])
                self.assertEqual(module.options()['border_radius'], 21)

    def test_text_opacity_defaults_persists_and_rejects_invalid(self):
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / 'settings.db'
            module = load_module(database)
            self.assertEqual(module.options()['text_opacity'], 50)
            module.set_options({'background_opacity': 23, 'text_opacity': 0})
            self.assertEqual(load_module(database).options()['text_opacity'], 0)
            module.set_options({'text_opacity': 67})
            self.assertEqual(load_module(database).options()['text_opacity'], 67)
            self.assertEqual(module.options()['background_opacity'], 23)
            for value in (-1, 101, 1.5, True, '50', None):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    module.set_options({'text_opacity': value, 'background_opacity': 0})
                self.assertEqual(module.options()['text_opacity'], 67)
                self.assertEqual(module.options()['background_opacity'], 23)

    def test_text_size_accepts_smaller_values_without_changing_default(self):
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / 'settings.db'
            module = load_module(database)
            self.assertEqual(module.options()['font_size'], 15)
            for value in (12, 17, 18, 32):
                module.set_options({'font_size': value})
                self.assertEqual(load_module(database).options()['font_size'], value)
            for value in (11, 33, True, 12.5, '12'):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    module.set_options({'font_size': value})
                self.assertEqual(module.options()['font_size'], 32)

    def test_width_defaults_to_current_layout_and_preserves_other_preferences(self):
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / 'settings.db'
            module = load_module(database)
            module.set_enabled(False)
            module.set_options({'font_size': 22, 'position': 'bottom_left'})
            self.assertEqual(module.options()['width_percent'], 80)
            for value in (60, 73, 100):
                module.set_options({'width_percent': value})
                reloaded = load_module(database)
                self.assertEqual(reloaded.options()['width_percent'], value)
                self.assertEqual(reloaded.options()['font_size'], 22)
                self.assertEqual(reloaded.options()['position'], 'bottom_left')
                self.assertFalse(reloaded.enabled())
            for invalid in (59, 101, -1, 60.0, True, '60', None):
                with self.subTest(width=invalid), self.assertRaises(ValueError):
                    module.set_options({'width_percent': invalid, 'font_size': 12})
                self.assertEqual(module.options()['width_percent'], 100)
                self.assertEqual(module.options()['font_size'], 22)

    def test_invalid_stored_width_falls_back_without_rewriting_it(self):
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / 'settings.db'
            module = load_module(database)
            module.set_options({'show_mode': False})
            with closing(sqlite3.connect(database)) as db, db:
                db.execute('INSERT INTO overlay_options (name, value) VALUES (?, ?)', ('width_percent', '20'))
            self.assertEqual(module.options()['width_percent'], 80)
            self.assertFalse(module.options()['show_mode'])
            with closing(sqlite3.connect(database)) as db:
                self.assertEqual(db.execute('SELECT value FROM overlay_options WHERE name=?', ('width_percent',)).fetchone()[0], '20')

    def test_default_and_saved_values_leave_other_preferences_unchanged(self):
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / 'settings.db'
            with closing(sqlite3.connect(database)) as con, con:
                con.execute('CREATE TABLE existing_preference (value TEXT)')
                con.execute("INSERT INTO existing_preference VALUES ('preserved')")
            module = load_module(database)
            self.assertTrue(module.enabled())
            with closing(sqlite3.connect(database)) as con, con:
                con.execute('CREATE TABLE overlay_setting (id INTEGER PRIMARY KEY CHECK(id=1), enabled INTEGER NOT NULL CHECK(enabled IN (0,1)))')
            self.assertTrue(load_module(database).enabled())
            module.set_enabled(True)
            self.assertTrue(load_module(database).enabled())
            module.set_enabled(False)
            self.assertFalse(load_module(database).enabled())
            module.set_enabled(True)
            self.assertTrue(load_module(database).enabled())
            with closing(sqlite3.connect(database)) as con:
                self.assertEqual(con.execute('SELECT value FROM existing_preference').fetchone(), ('preserved',))

    def test_invalid_values_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            module = load_module(Path(temp) / 'settings.db')
            for value in ('true', 1, None):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    module.set_enabled(value)
            self.assertTrue(module.enabled())

    def test_position_defaults_persists_and_rejects_invalid(self):
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / 'settings.db'
            module = load_module(database)
            self.assertEqual(module.options()['position'], 'top_right')
            for position in ('top_left', 'top_right', 'bottom_left', 'bottom_right'):
                module.set_options({'position': position})
                self.assertEqual(load_module(database).options()['position'], position)
            for position in ('centre', '', None, 2, True):
                with self.subTest(position=position), self.assertRaises(ValueError):
                    module.set_options({'position': position})
            self.assertEqual(module.options()['position'], 'bottom_right')

    def test_visibility_defaults_persists_and_preserves_existing_preferences(self):
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / 'settings.db'
            module = load_module(database)
            module.set_enabled(False)
            module.set_options({'position': 'bottom_left', 'show_mode': False})
            self.assertEqual(module.options()['visibility_mode'], 'game_visible')
            for mode in ('always', 'game_visible', 'capture'):
                module.set_options({'visibility_mode': mode})
                saved = load_module(database)
                self.assertEqual(saved.options()['visibility_mode'], mode)
                self.assertEqual(saved.options()['position'], 'bottom_left')
                self.assertFalse(saved.options()['show_mode'])
                self.assertFalse(saved.enabled())
            for invalid in ('', 'on', 'game', 'CAPTURE', None, 0, False, ['capture']):
                with self.subTest(mode=invalid), self.assertRaises(ValueError):
                    module.set_options({'visibility_mode': invalid, 'show_mode': True})
                self.assertEqual(module.options()['visibility_mode'], 'capture')
                self.assertFalse(module.options()['show_mode'])

    def test_invalid_saved_visibility_falls_back_without_rewriting_data(self):
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / 'settings.db'
            module = load_module(database)
            module.set_options({'show_event': False})
            with closing(sqlite3.connect(database)) as con, con:
                con.execute('INSERT INTO overlay_options VALUES (?, ?)', ('visibility_mode', '"invalid"'))
            self.assertEqual(module.options()['visibility_mode'], 'game_visible')
            self.assertFalse(module.options()['show_event'])
            with closing(sqlite3.connect(database)) as con:
                self.assertEqual(con.execute('SELECT value FROM overlay_options WHERE name=?',
                                             ('visibility_mode',)).fetchone()[0], '"invalid"')

    def test_options_defaults_partial_updates_and_existing_enabled(self):
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / 'settings.db'
            module = load_module(database)
            module.set_enabled(False)
            self.assertEqual(module.options(), module.DEFAULT_OPTIONS)
            module.set_options({'background_opacity': 0, 'background_color': '#AaBBcc',
                                'font_size': 32, 'show_peers': False})
            saved = load_module(database).options()
            self.assertEqual(saved['background_opacity'], 0)
            self.assertEqual(saved['background_color'], '#aabbcc')
            self.assertEqual(saved['font_size'], 32)
            self.assertFalse(saved['show_peers'])
            self.assertTrue(saved['show_event'])
            self.assertFalse(module.enabled())
            module.set_options({'text_color': '#123456'})
            self.assertEqual(module.options()['background_opacity'], 0)

    def test_invalid_option_patches_are_atomic(self):
        with tempfile.TemporaryDirectory() as temp:
            module = load_module(Path(temp) / 'settings.db')
            for patch in ({}, {'unknown': True}, {'font_size': 11}, {'font_size': 33},
                          {'font_size': True}, {'background_opacity': -1},
                          {'background_opacity': 101}, {'background_opacity': 1.5},
                          {'text_color': 'red'}, {'background_color': '#fff'},
                          {'show_event': 1}, {'show_mode': 'false'},
                          {'show_mode': False, 'font_size': 100}):
                with self.subTest(patch=patch), self.assertRaises(ValueError):
                    module.set_options(patch)
                self.assertEqual(module.options(), module.DEFAULT_OPTIONS)

    def test_bad_persisted_values_fall_back_without_losing_valid_ones(self):
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / 'settings.db'
            module = load_module(database)
            with closing(sqlite3.connect(database)) as con, con:
                con.execute('CREATE TABLE overlay_options (name TEXT PRIMARY KEY, value TEXT NOT NULL)')
                con.executemany('INSERT INTO overlay_options VALUES(?,?)', [
                    ('font_size', '999'), ('show_peers', 'invalid json'), ('show_event', 'false')])
            values = module.options()
            self.assertEqual(values['font_size'], 15)
            self.assertTrue(values['show_peers'])
            self.assertFalse(values['show_event'])

    def test_player_card_options_are_independent_and_persist(self):
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / 'settings.db'
            module = load_module(database)
            keys = ('show_avatars', 'show_player_name', 'show_role', 'show_steam_id', 'show_country', 'show_ping',
                    'show_ping_average', 'show_jitter', 'show_quality', 'show_duration',
                    'show_player_count', 'show_rank', 'show_player_stats')
            for key in keys:
                module.set_options({key: True})
                self.assertIs(load_module(database).options()[key], True)
                module.set_options({key: False})
                self.assertIs(load_module(database).options()[key], False)
            module.set_options({'avatar_size': 24, 'card_size': 160, 'card_spacing': 0,
                                'ping_good_color': '#AaBBcc', 'ping_medium_color': '#334455',
                                'ping_bad_color': '#FF0000'})
            saved = load_module(database).options()
            self.assertEqual((saved['avatar_size'], saved['card_size'], saved['card_spacing']), (24, 160, 0))
            self.assertEqual(saved['ping_good_color'], '#aabbcc')
            self.assertTrue(all(saved[key] is False for key in keys))
            self.assertEqual(saved['background_opacity'], 50)

    def test_player_card_options_reject_invalid_values_atomically(self):
        with tempfile.TemporaryDirectory() as temp:
            module = load_module(Path(temp) / 'settings.db')
            for values in ({'avatar_size': 23}, {'avatar_size': 97}, {'card_size': 47},
                           {'card_size': 161}, {'card_spacing': -1}, {'card_spacing': 25},
                           {'ping_good_color': 'green'}, {'ping_bad_color': '#12'},
                           {'show_rank': 'true'}, {'show_role': 1}, {'show_role': 'false'}, {'show_steam_id': 1}, {'show_country': 1},
                           {'show_country': 'false'}, {'show_country': None},
                           {'show_avatars': False, 'avatar_size': 1}):
                with self.subTest(values=values), self.assertRaises(ValueError):
                    module.set_options(values)
                self.assertEqual(module.options(), module.DEFAULT_OPTIONS)
