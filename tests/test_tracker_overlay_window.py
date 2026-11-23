import ctypes
import threading
import unittest
from io import BytesIO
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PIL import Image
from application import tracker_overlay_window as overlay


class OverlayWindowTests(unittest.TestCase):
    def test_personal_tags_and_favourite_are_independent(self):
        view = self.scene()
        view['cards'][0].update(favourite=True, tags=[{'name':'Ami Steam','color':'#3b8db7'}, {'name':'Rival','color':'#dc6a6a'}])
        def plan(**values):
            return overlay._scene_plan(view, overlay._scene_options(values), (0, 0, 1920, 1080))
        def entries(**values):
            return plan(**values)['entries']
        full = entries()
        self.assertTrue(any(text == 'Joueur' for text, _, _ in full))
        self.assertEqual(len(plan()['stars']), 1)
        self.assertGreater(plan()['stars'][0][2], overlay._scene_options({})['font_size'])
        self.assertTrue(any(text == 'Ami Steam' and color == '#3b8db7' for text, _, color in full))
        self.assertTrue(any(text == 'Rival' and color == '#dc6a6a' for text, _, color in full))
        self.assertEqual([color for _, color in plan()['badges']], ['#3b8db7', '#dc6a6a'])
        self.assertEqual(plan(show_player_tags=False)['badges'], [])
        self.assertFalse(any(text == 'Ami Steam' for text, _, _ in entries(show_player_tags=False)))
        self.assertEqual(len(plan(show_player_tags=False)['stars']), 1)
        self.assertTrue(any(text == 'Ami Steam' for text, _, _ in entries(show_player_favourite=False)))
        self.assertTrue(any(text == 'Joueur' for text, _, _ in entries(show_player_favourite=False)))
        self.assertEqual(plan(show_player_favourite=False)['stars'], [])
        self.assertEqual(len(plan(show_player_name=False)['stars']), 1)

    def test_many_tags_stay_on_one_line_and_indicate_hidden_items(self):
        view = self.scene()
        view['cards'][0]['tags'] = [{'name':f'Tag {n}', 'color':'#69c37b'} for n in range(9)]
        plan = overlay._scene_plan(view, overlay._scene_options({}), (0, 0, 1920, 1080))
        texts = [entry[0] for entry in plan['entries']]
        self.assertTrue(any(value.startswith('+') for value in texts))
        self.assertEqual(len({rect[1] for rect, _ in plan['badges']}), 1)
        self.assertTrue(all(plan['badges'][i][0][2] < plan['badges'][i+1][0][0] for i in range(len(plan['badges'])-1)))

    def test_badges_are_below_country_and_star_is_gold(self):
        view = self.scene()
        view['cards'][0].update(favourite=True, country_code='FR', country_name='France',
                                tags=[{'name':'Ami','color':'#69c37b'}, {'name':'Rival','color':'#dc6a6a'}])
        options = overlay._scene_options({'text_opacity':100})
        plan = overlay._scene_plan(view, options, (0, 0, 1920, 1080))
        france = next(rect for value, rect, _ in plan['entries'] if value == 'France')
        card = plan['cards'][0][0]
        self.assertTrue(all(rect[1] >= france[3] and rect[3] <= card[3] for rect, _ in plan['badges']))
        self.assertEqual(len({rect[1] for rect, _ in plan['badges']}), 1)
        x, y, size = plan['stars'][0]
        image = overlay._scene_base(plan, options, True)
        self.assertEqual(image.getpixel((x + size // 2, y + size // 2))[:3], (215, 185, 112))

    def test_paint_callback_brackets_paint_request(self):
        window = overlay.OverlayWindow(lambda: [])
        paint = object()
        with patch.object(overlay.win32gui, 'BeginPaint', return_value=(1, paint)) as begin, \
             patch.object(overlay.win32gui, 'EndPaint') as end:
            self.assertEqual(window._window_proc(42, overlay.win32con.WM_PAINT, 0, 0), 0)
        begin.assert_called_once_with(42)
        end.assert_called_once_with(42, paint)
        self.assertIsNone(window.error)

    def test_paint_failure_reports_error_and_stops_pump(self):
        window = overlay.OverlayWindow(lambda: [])
        window._stop = threading.Event()
        with patch.object(overlay.win32gui, 'BeginPaint', side_effect=OSError('paint failed')), \
             patch.object(overlay.win32gui, 'PostQuitMessage') as quit_message, \
             self.assertLogs(overlay._LOG, level='ERROR'):
            self.assertEqual(window._window_proc(42, overlay.win32con.WM_PAINT, 0, 0), 0)
        self.assertEqual(window.error, 'window_error')
        self.assertTrue(window._stop.is_set())
        quit_message.assert_called_once_with(0)

    def test_real_hidden_window_reaches_render_and_stops(self):
        # Create a real window and pump messages, but never permit it to be
        # shown or draw on the desktop. This catches internal WM_PAINT storms.
        rendered = threading.Event()
        window = overlay.OverlayWindow(lambda: ['synthetic'], interval=.1)
        visibility = []

        def render(hwnd, *_args):
            visibility.append(bool(overlay.win32gui.IsWindowVisible(hwnd)))
            rendered.set()

        with patch.object(overlay, '_exclude_from_capture', return_value=True), \
             patch.object(overlay, '_render_layer', side_effect=render), \
             patch.object(overlay.win32gui, 'SetWindowPos'):
            try:
                self.assertTrue(window.start())
                self.assertTrue(rendered.wait(3), 'message pump did not reach the first frame')
                self.assertTrue(window.stop(timeout=2), 'message pump did not stop')
                self.assertEqual(visibility, [False])
                self.assertIsNone(window.error)
            finally:
                window.stop(timeout=2)

    @staticmethod
    def scene():
        return {'status':'Suivi actif', 'mode':'Arène', 'peer_status':'Aucun joueur',
                'labels':{'tracking':'Suivi', 'mode':'Mode', 'player_count':'Joueurs',
                          'quality':'Qualité', 'duration':'Durée', 'average_ping':'Moyenne',
                          'jitter':'Variation du ping', 'rank':'Rang', 'wins':'Victoires', 'losses':'Défaites',
                          'no_event':'Aucun événement', 'encounters':'Nombre de rencontres'},
                'player_count':1, 'event':'Envahisseur arrivé',
                'cards':[{'id':'76561198000000001', 'name':'Joueur', 'ping':42,
                          'average_ping':51, 'jitter':3, 'quality':.96,
                          'duration':'00:01:25', 'avatar':None, 'rank':142, 'wins':125, 'losses':48,
                          'encounters':8}]}

    def test_scene_contains_real_data_and_respects_individual_switches(self):
        view = self.scene()
        options = overlay._scene_options({'show_steam_id': True, 'show_jitter': True, 'width_percent': 100,
                                          'show_quality': True, 'show_ping_average': True})
        plan = overlay._scene_plan(view, options, (0, 0, 1920, 1080))
        texts = [item[0] for item in plan['entries']]
        self.assertEqual(texts[0], 'Suivi actif')
        self.assertTrue(any('Joueur' == t for t in texts))
        self.assertTrue(any('42 ms' == t for t in texts))
        self.assertTrue(any('76561198000000001' in t for t in texts))
        self.assertTrue(any('96 %' in t for t in texts))
        self.assertTrue(any('01:25' in t for t in texts))
        self.assertTrue(any('Envahisseur arrivé' in t for t in texts))
        self.assertNotIn('142 · Rang', texts)
        self.assertNotIn('125 · Victoires', texts)
        self.assertIn('Nombre de rencontres : 8', texts)
        self.assertEqual(plan['visible_cards'], 1)
        unknown = self.scene()
        unknown['cards'][0]['encounters'] = None
        unknown_text = [item[0] for item in overlay._scene_plan(unknown, options, (0, 0, 1920, 1080))['entries']]
        self.assertFalse(any('Rang' in t or 'Victoires' in t or 'Défaites' in t for t in unknown_text))
        self.assertIn('Nombre de rencontres : —', unknown_text)
        for key, expected in [('show_player_name', 'Joueur'), ('show_steam_id', '76561198000000001'),
                              ('show_ping', '42 ms'), ('show_quality', 'Qualité'),
                              ('show_duration', 'Durée'), ('show_ping_average', 'Moyenne'),
                              ('show_jitter', 'Variation du ping'),
                              ('show_player_stats', 'Nombre de rencontres'), ('show_event', 'Envahisseur')]:
            with self.subTest(key=key):
                opts = dict(options, **{key:False})
                values = [entry[0] for entry in overlay._scene_plan(view, opts, (0, 0, 1920, 1080))['entries']]
                self.assertFalse(any((expected == t if key == 'show_player_name' else expected in t) for t in values), values)
        self.assertIsNone(overlay._scene_plan(view, dict(options, show_status=False), (0, 0, 1920, 1080))['status_y'])
        self.assertEqual(overlay._scene_plan(view, dict(options, show_avatars=False), (0, 0, 1920, 1080))['cards'][0][2], 0)

    def test_player_role_is_translated_and_can_be_hidden_independently(self):
        view = self.scene()
        view['labels'].update(role_ally='Allié', role_hunter='Chasseur', role_invader='Envahisseur',
                              role_cooperator='Allié adverse', role_duelist='Duelliste')
        options = overlay._scene_options({'show_event': False})
        self.assertTrue(options['show_role'])
        for role, expected in [('ally', 'Allié'), ('hunter', 'Chasseur'), ('invader', 'Envahisseur'),
                               ('cooperator', 'Allié adverse'), ('duelist', 'Duelliste')]:
            with self.subTest(role=role):
                view['cards'][0]['role'] = role
                entries = overlay._scene_plan(view, options, (0, 0, 1920, 1080))['entries']
                self.assertIn(expected, [entry[0] for entry in entries])
                hidden = overlay._scene_plan(view, dict(options, show_role=False), (0, 0, 1920, 1080))['entries']
                self.assertNotIn(expected, [entry[0] for entry in hidden])
        view['cards'][0]['role'] = 'unknown'
        entries = overlay._scene_plan(view, options, (0, 0, 1920, 1080))['entries']
        self.assertFalse(any(entry[0] in view['labels'].values() for entry in entries))
        view['cards'][0]['role'] = 'hunter'
        role_only = {key: False for key in ('show_avatars', 'show_player_name', 'show_steam_id', 'show_ping',
                     'show_quality', 'show_duration', 'show_ping_average', 'show_jitter', 'show_rank', 'show_player_stats')}
        role_only.update(show_role=True, show_event=False)
        only_options = overlay._scene_options(role_only)
        plan = overlay._scene_plan(view, only_options, (0, 0, 1920, 1080))
        self.assertIn('Chasseur', [entry[0] for entry in plan['entries']])
        self.assertEqual(plan['visible_cards'], 1)
        self.assertEqual(overlay._scene_plan(view, dict(only_options, show_role=False),
                                            (0, 0, 1920, 1080))['visible_cards'], 0)

    def test_ping_aligns_right_and_uses_available_space_next_to_name(self):
        view = self.scene()
        view['cards'][0]['name'] = 'A player name that fits beside ping'
        options = overlay._scene_options({'font_size': 15, 'width_percent': 100, 'show_avatars': False})
        plan = overlay._scene_plan(view, options, (0, 0, 1920, 1080))
        name = next(entry for entry in plan['entries'] if entry[0] == view['cards'][0]['name'])
        ping = next(entry for entry in plan['entries'] if entry[0] == '42 ms')
        card = plan['cards'][0][0]
        self.assertGreater(overlay._measure_text(name[0], 15), (card[2] - card[0] - 16) // 2)
        self.assertEqual(name[1][1], ping[1][1])
        self.assertLessEqual(name[1][2] + 10, ping[1][0])
        self.assertEqual(ping[1][2], card[2] - 8)
        self.assertEqual(ping[1][2] - ping[1][0], overlay._measure_text('42 ms', 15))

    def test_tracker_badge_requires_confirmed_membership_and_enabled_option(self):
        view = self.scene()
        view['labels']['tracker_user'] = 'Utilisateur du tracker'
        options = overlay._scene_options({'width_percent': 100})
        for value, enabled, expected in ((True, True, True), (True, False, False),
                                         (False, True, False), (None, True, False),
                                         ('true', True, False)):
            with self.subTest(value=value, enabled=enabled):
                view['cards'][0]['tracker_member'] = value
                plan = overlay._scene_plan(view, dict(options, show_tracker_user=enabled), (0, 0, 1920, 1080))
                entries = plan['entries']
                self.assertEqual(any(entry[0] == 'Utilisateur du tracker' for entry in entries), expected)
                self.assertEqual([color for _, color in plan['badges']], ['#d4af37'] if expected else [])
        view['cards'][0].update(tracker_member=True, tags=[{'name':'Ami','color':'#69c37b'}])
        plan = overlay._scene_plan(view, dict(options, show_tracker_user=True, show_player_tags=True), (0, 0, 1920, 1080))
        self.assertEqual([color for _, color in plan['badges']], ['#d4af37', '#69c37b'])
        plan = overlay._scene_plan(view, dict(options, show_tracker_user=True, show_player_tags=False), (0, 0, 1920, 1080))
        self.assertEqual([color for _, color in plan['badges']], ['#d4af37'])
        plan = overlay._scene_plan(view, dict(options, show_tracker_user=False, show_player_tags=True), (0, 0, 1920, 1080))
        self.assertEqual([color for _, color in plan['badges']], ['#69c37b'])

    def test_ping_and_long_or_rtl_names_fit_small_cards(self):
        for name in ('A player name that continues on a second line',
                     'لاعب طويل الاسم داخل اللعبة'):
            for width in (60, 100):
                with self.subTest(name=name, width=width):
                    view = self.scene()
                    view['cards'][0]['name'] = name
                    options = overlay._scene_options({'font_size': 12, 'width_percent': width, 'avatar_size': 96,
                        'show_status': False, 'show_mode': False, 'show_player_count': False, 'show_event': False,
                        'show_quality': False, 'show_duration': False, 'show_ping_average': False,
                        'show_jitter': False, 'show_rank': False, 'show_player_stats': False})
                    plan = overlay._scene_plan(view, options, (0, 0, 400, 1600))
                    ping = next(entry for entry in plan['entries'] if entry[0] == '42 ms')
                    card = plan['cards'][0][0]
                    name_lines = [entry for entry in plan['entries'] if entry[0] != '42 ms']
                    self.assertGreater(len(name_lines), 1)
                    self.assertEqual(ping[1][2], card[2] - 8)
                    self.assertEqual(name_lines[0][1][1], ping[1][1])
                    self.assertLessEqual(name_lines[0][1][2] + 10, ping[1][0])
                    self.assertEqual(' '.join(line[0] for line in name_lines), name)
                    for value, rect, _ in name_lines:
                        self.assertLessEqual(overlay._measure_text(value, 12), rect[2] - rect[0])

    def test_player_name_ellipsis_only_after_four_lines(self):
        view = self.scene()
        view['cards'][0]['name'] = ' '.join(['longplayername'] * 30)
        options = overlay._scene_options({'font_size': 12, 'width_percent': 60, 'avatar_size': 96,
            'show_status': False, 'show_mode': False, 'show_player_count': False, 'show_event': False,
            'show_quality': False, 'show_duration': False, 'show_ping_average': False,
            'show_jitter': False, 'show_rank': False, 'show_player_stats': False})
        plan = overlay._scene_plan(view, options, (0, 0, 400, 1600))
        name_lines = [entry for entry in plan['entries'] if entry[0] != '42 ms']
        self.assertEqual(len(name_lines), 4)
        self.assertTrue(all(not entry[0].endswith('…') for entry in name_lines[:3]))
        self.assertTrue(name_lines[3][0].endswith('…'))

    def test_quality_shows_unavailable_until_a_measurement_arrives(self):
        options = overlay._scene_options({'width_percent': 100, 'show_avatars': False, 'show_quality': True})
        for quality in (None, -1, 1.1, float('nan'), True):
            with self.subTest(quality=quality):
                view = self.scene()
                view['labels']['quality_unavailable'] = 'Qualité indisponible'
                view['cards'][0]['quality'] = quality
                entries = overlay._scene_plan(view, options, (0, 0, 1920, 1080))['entries']
                self.assertIn('Qualité indisponible', [item[0] for item in entries])
                hidden = overlay._scene_plan(view, dict(options, show_quality=False), (0, 0, 1920, 1080))['entries']
                self.assertNotIn('Qualité indisponible', [item[0] for item in hidden])
        for quality, expected in ((0, 'Qualité : 0 %'), (.96, 'Qualité : 96 %'), (1, 'Qualité : 100 %')):
            with self.subTest(quality=quality):
                view = self.scene()
                view['labels']['quality_unavailable'] = 'Qualité indisponible'
                view['cards'][0]['quality'] = quality
                entries = overlay._scene_plan(view, options, (0, 0, 1920, 1080))['entries']
                values = [item[0] for item in entries]
                self.assertIn(expected, values)
                self.assertNotIn('Qualité indisponible', values)

    def test_card_fields_follow_app_order_format_and_rounding(self):
        view = self.scene()
        view['cards'][0].update(ping=42.5, average_ping=50.5, jitter=2.5, quality=.905)
        options = overlay._scene_options({'font_size': 15, 'width_percent': 100, 'show_avatars': False,
                                          'show_steam_id': True, 'show_jitter': True, 'show_event': False,
                                          'show_quality': True, 'show_ping_average': True})
        values = [entry[0] for entry in overlay._scene_plan(view, options, (0, 0, 1920, 1080))['entries']]
        expected = ['Joueur', '43 ms', 'SteamID : 76561198000000001', 'Durée : 00:01:25',
                    'Moyenne : 51 ms', 'Variation du ping : 3 ms', 'Qualité : 91 %', 'Nombre de rencontres : 8']
        self.assertEqual([value for value in values if value in expected], expected)

        view['cards'][0].update(name='', duration=None, average_ping=None, jitter=None, quality=None, encounters=None)
        view['labels'].update(unknown_name='Non identifié', quality_unavailable='Qualité indisponible')
        values = [entry[0] for entry in overlay._scene_plan(view, options, (0, 0, 1920, 1080))['entries']]
        for expected in ('Non identifié', 'Durée : —', 'Moyenne : —', 'Variation du ping : —',
                         'Qualité indisponible', 'Nombre de rencontres : —'):
            self.assertIn(expected, values)

    def test_quality_indicator_matches_app_and_does_not_overlap_text(self):
        options = overlay._scene_options({'font_size': 15, 'width_percent': 100, 'show_avatars': False,
                                          'text_opacity': 100, 'show_quality': True})
        for quality, expected_color in ((None, '#9a9a92'), (.6, '#e07878'),
                                        (.7, '#e6be72'), (.9, '#82d7a1')):
            with self.subTest(quality=quality):
                view = self.scene()
                view['labels']['quality_unavailable'] = 'Qualité indisponible'
                view['cards'][0]['quality'] = quality
                plan = overlay._scene_plan(view, options, (0, 0, 1920, 1080))
                self.assertEqual(len(plan['quality_indicators']), 1)
                x, y, color = plan['quality_indicators'][0]
                self.assertEqual(color, expected_color)
                entry = next(item for item in plan['entries'] if item[0].startswith('Qualité'))
                self.assertGreaterEqual(entry[1][0], x + 12)
                self.assertEqual(overlay._scene_base(plan, options, False).getpixel((x + 3, y + 3))[:3],
                                 overlay._rgb(expected_color))
                hidden = overlay._scene_plan(view, dict(options, show_quality=False), (0, 0, 1920, 1080))
                self.assertEqual(hidden['quality_indicators'], [])

    def test_encounters_are_validated_and_can_be_hidden(self):
        view = self.scene()
        card = view['cards'][0]
        options = overlay._scene_options({'width_percent': 100, 'show_avatars': False})

        def values(overrides=None):
            return [item[0] for item in overlay._scene_plan(
                view, dict(options, **(overrides or {})), (0, 0, 1920, 1080))['entries']]

        for count, expected in [(None, '—'), (0, '0'), (8, '8'), (True, '—'),
                                (-1, '—'), (1.5, '—'), ('8', '—'), (2**53, '—')]:
            with self.subTest(count=count):
                card['encounters'] = count
                self.assertIn('Nombre de rencontres : ' + expected, values())
                self.assertFalse(any('Nombre de rencontres' in item for item in values({'show_player_stats': False})))

    def test_saved_rank_preference_never_displays_rank_or_suppresses_encounters(self):
        view = self.scene()
        for value in (True, False):
            with self.subTest(saved_rank=value):
                options = overlay._scene_options({'show_rank': value, 'show_player_stats': True, 'width_percent': 100})
                entries = overlay._scene_plan(view, options, (0, 0, 1920, 1080))['entries']
                rendered = [entry[0] for entry in entries]
                self.assertNotIn('142 · Rang', rendered)
                self.assertNotIn('125 · Victoires', rendered)
                self.assertIn('Nombre de rencontres : 8', rendered)

    def test_divider_has_spacing_before_empty_peer_status_and_cards(self):
        options = overlay._scene_options({'show_player_count': True})
        for has_card in (False, True):
            with self.subTest(has_card=has_card):
                view = self.scene()
                if not has_card:
                    view['cards'] = []
                    view['player_count'] = 0
                plan = overlay._scene_plan(view, options, (0, 0, 1920, 1080))
                count = next(item for item in plan['entries'] if item[0].startswith('Joueurs'))
                after = plan['cards'][0][0][1] if has_card else next(
                    item[1][1] for item in plan['entries'] if item[0] == 'Aucun joueur')
                self.assertEqual(plan['header_y'] - count[1][3], 8)
                self.assertEqual(after - plan['header_y'], 9)

        no_header = dict(options, show_status=False, show_mode=False, show_player_count=False)
        plan = overlay._scene_plan(self.scene(), no_header, (0, 0, 1920, 1080))
        self.assertEqual(plan['header_y'], overlay._MARGIN)
        self.assertEqual(plan['cards'][0][0][1], overlay._MARGIN)

    def test_player_count_distinguishes_unknown_from_empty_and_does_not_require_cards(self):
        view = self.scene()
        options = overlay._scene_options({'show_player_count': True, 'show_peers': False,
                                          'show_status': False, 'show_mode': False, 'show_event': False})
        for count, expected in ((None, '—'), (0, '0'), (2, '2'), (-1, '—'), (True, '—')):
            with self.subTest(count=count):
                view['player_count'] = count
                plan = overlay._scene_plan(view, options, (0, 0, 1920, 1080))
                self.assertIn('Joueurs : ' + expected, [item[0] for item in plan['entries']])
                self.assertEqual(plan['cards'], [])

    def test_scene_first_line_is_status_including_paused_status(self):
        view = self.scene()
        view['labels']['tracking'] = 'PREFIX_MUST_NOT_APPEAR'
        options = overlay._scene_options(None)
        for status, active in [('Fight in progress', True), ('Capture en pause', False)]:
            with self.subTest(status=status):
                view['status'] = status
                plan = overlay._scene_plan(view, options, (0, 0, 1920, 1080))
                self.assertEqual(plan['entries'][0][0], status)
                self.assertFalse(any('PREFIX_MUST_NOT_APPEAR' in entry[0] for entry in plan['entries']))
                point = (overlay._MARGIN + 5, plan['status_y'] + 5)
                color = overlay._scene_base(plan, options, active).getpixel(point)
                self.assertEqual(color[:3], (92, 218, 133) if active else (239, 100, 100))

    def test_scene_uses_custom_ping_color_and_bounds_overflow(self):
        view = self.scene()
        view['cards'] *= 16
        options = overlay._scene_options({'ping_good_color':'#123456', 'card_size':160,
                                          'avatar_size':96, 'card_spacing':24, 'font_size':32})
        plan = overlay._scene_plan(view, options, (-500, 0, 0, 500))
        x, y, w, h = plan['bounds']
        self.assertGreaterEqual(x, -500)
        self.assertLessEqual(x + w, 0)
        self.assertLessEqual(y + h, 500)
        self.assertGreater(plan['hidden_cards'], 0)
        self.assertTrue(any(entry[0].startswith('… (+') for entry in plan['entries']))
        if plan['visible_cards']:
            self.assertTrue(any(entry[0] == '42 ms' and entry[2] == '#123456' for entry in plan['entries']))

    def test_scene_text_fits_and_card_size_respects_avatar(self):
        view = self.scene()
        view['labels']['quality'] = 'Qualité de connexion'
        view['labels']['duration'] = 'Durée de connexion'
        for size in (12, 17, 18, 32):
            options = overlay._scene_options({'font_size':size, 'avatar_size':96, 'card_size':48})
            plan = overlay._scene_plan(view, options, (0, 0, 1920, 1080))
            self.assertEqual(plan['visible_cards'], 1)
            rect = plan['cards'][0][0]
            self.assertGreaterEqual(rect[3] - rect[1], 112)
            for value, box, _ in plan['entries']:
                self.assertLessEqual(overlay._measure_text(value, size), box[2] - box[0], value)
            large = overlay._scene_plan(view, dict(options, card_size=160), (0, 0, 1920, 1080))
            self.assertGreaterEqual(large['cards'][0][0][3] - large['cards'][0][0][1], 160)

    def test_scene_all_card_fields_disabled_does_not_draw_empty_cards(self):
        view = self.scene()
        values = {key:False for key in ('show_avatars', 'show_player_name', 'show_steam_id', 'show_ping',
                    'show_ping_average', 'show_jitter', 'show_quality', 'show_duration', 'show_rank', 'show_player_stats')}
        values['show_player_count'] = True
        plan = overlay._scene_plan(view, overlay._scene_options(values), (0, 0, 1920, 1080))
        self.assertEqual(plan['cards'], [])
        self.assertTrue(any(item[0] == 'Joueurs : 1' for item in plan['entries']))

    def test_old_statistics_are_not_displayed_in_any_mode(self):
        view = self.scene()
        view['mode_id'] = 'Arena'
        view['labels'].update(draws='Égalités', combats='Combats', ratio='Ratio')
        view['cards'][0].update(draws=4, combats=37, ratio=72.3)
        options = overlay._scene_options({'width_percent': 100})
        for mode in ('Arena', 'Invasion', 'Defense'):
            with self.subTest(mode=mode):
                view['mode_id'] = mode
                values = [entry[0] for entry in overlay._scene_plan(view, options, (0, 0, 1920, 1080))['entries']]
                self.assertIn('Nombre de rencontres : 8', values)
                self.assertFalse(any(label in value for value in values for label in ('Égalités', 'Combats', 'Ratio', 'Victoires', 'Défaites')))

    def test_obsolete_leaderboard_notice_is_not_displayed(self):
        view = self.scene()
        view['labels']['online_history_unverified'] = 'Historique antérieur non vérifié.'
        view['cards'][0]['history_unverified'] = True
        options = overlay._scene_options(None)
        def text(opts):
            entries = overlay._scene_plan(view, opts, (0, 0, 1920, 1080))['entries']
            return ' '.join(value for value, _, _ in entries)
        result = text(options)
        self.assertNotIn('Historique antérieur non vérifié.', result)
        self.assertNotIn('142 · Rang', result)
        self.assertNotIn('125 · Victoires', result)

    def test_scene_background_opacity_and_avatar_fallback(self):
        view = self.scene()
        options = overlay._scene_options({'background_opacity':0, 'show_status':False})
        plan = overlay._scene_plan(view, options, (0, 0, 1920, 1080))
        image = overlay._scene_base(plan, options, True)
        self.assertEqual(image.getpixel((0, 0))[3], 0)
        self.assertTrue(plan['cards'])
        rect = plan['cards'][0][0]
        avatar_pixel = image.getpixel((rect[0] + 8 + 24, rect[1] + 8 + 16))
        self.assertEqual(avatar_pixel[3], 255)
        buffer = BytesIO()
        Image.new('RGBA', (8, 8), (255, 0, 0, 255)).save(buffer, format='PNG')
        view['cards'][0]['avatar'] = buffer.getvalue()
        plan = overlay._scene_plan(view, options, (0, 0, 1920, 1080))
        image = overlay._scene_base(plan, options, True)
        rect = plan['cards'][0][0]
        self.assertEqual(image.getpixel((rect[0] + 8 + 24, rect[1] + 8 + 24)), (255, 0, 0, 255))

    def test_card_surface_uses_warm_tone_and_respects_custom_background(self):
        view = self.scene()
        opts = overlay._scene_options({'show_avatars': False, 'show_status': False,
                                       'background_opacity': 100, 'background_color': '#1b1818'})
        plan = overlay._scene_plan(view, opts, (0, 0, 1920, 1080))
        rect = plan['cards'][0][0]
        point = (rect[2] - 12, rect[1] + 12)
        default_pixel = overlay._scene_base(plan, opts, True).getpixel(point)
        self.assertGreater(default_pixel[0], default_pixel[1])
        self.assertGreater(default_pixel[1], default_pixel[2])
        self.assertEqual(default_pixel[3], round(255 * .86))

        custom = dict(opts, background_color='#501c18')
        custom_pixel = overlay._scene_base(plan, custom, True).getpixel(point)
        self.assertGreater(custom_pixel[0], default_pixel[0])
        self.assertEqual(custom_pixel[3], default_pixel[3])
        transparent = dict(custom, background_opacity=0)
        self.assertEqual(overlay._scene_base(plan, transparent, True).getpixel(point)[3], 0)

    def test_card_surfaces_follow_explicit_role_without_changing_opacity_or_border(self):
        view = self.scene()
        view['cards'] = [dict(view['cards'][0], role=role) for role in
                         (None, 'ally', 'duelist', 'invader', 'hunter', 'unknown')]
        options = overlay._scene_options({'show_avatars': False, 'background_color': '#352a27',
                                          'background_opacity': 50, 'border_color': '#abc123'})
        plan = overlay._scene_plan(view, options, (0, 0, 1920, 2000))
        self.assertEqual(plan['visible_cards'], len(view['cards']))
        image = overlay._scene_base(plan, options, True)
        samples = []
        for rect, _, _, _, _ in plan['cards']:
            samples.append(image.getpixel((rect[2] - 12, rect[1] + 12)))
            self.assertEqual(image.getpixel((rect[0] + 10, rect[1]))[:3], (171, 193, 35))
        neutral, ally, duelist, invader, hunter, unknown = samples
        self.assertEqual(neutral, ally)
        self.assertEqual(neutral, duelist)
        self.assertEqual(neutral, unknown)
        self.assertLess(invader[1], neutral[1])
        self.assertGreater(hunter[2], neutral[2])
        self.assertTrue(all(pixel[3] == round(round(255 * .5) * .86) for pixel in samples))
        transparent = overlay._scene_base(plan, dict(options, background_opacity=0), True)
        for rect, _, _, _, _ in plan['cards']:
            self.assertEqual(transparent.getpixel((rect[2] - 12, rect[1] + 12))[3], 0)

    def test_role_tints_remain_visible_at_default_opacity(self):
        view = self.scene()
        view['cards'] = [dict(view['cards'][0], role=role) for role in (None, 'invader', 'hunter')]
        options = overlay._scene_options({'show_avatars': False})
        plan = overlay._scene_plan(view, options, (0, 0, 1920, 1600))
        self.assertEqual(plan['visible_cards'], 3)
        image = overlay._scene_base(plan, options, True)
        # Compare the surfaces composited on a black background: with the
        # default 50% opacity, both role colors must still be noticeable.
        composed = Image.alpha_composite(Image.new('RGBA', image.size, (0, 0, 0, 255)), image)
        pixels = [composed.getpixel((rect[2] - 12, rect[1] + 12)) for rect, *_ in plan['cards']]
        neutral, invader, hunter = pixels
        self.assertGreaterEqual(invader[0] - neutral[0], 12)
        self.assertGreaterEqual(hunter[2] - neutral[2], 12)
        self.assertGreater(invader[0], invader[2])
        self.assertGreater(hunter[2], hunter[0])

    def test_country_flag_and_name_follow_both_player_columns(self):
        view = self.scene()
        view['cards'][0].update(country_code='FR', country_name='France')
        for settings in ({'avatar_size': 48, 'font_size': 15, 'width_percent': 100},
                         {'avatar_size': 96, 'font_size': 12, 'width_percent': 60}):
            options = overlay._scene_options(dict(settings, background_opacity=0))
            plan = overlay._scene_plan(view, options, (0, 0, 1920, 1600))
            rect, _, size, _, flag_data = plan['cards'][0]
            self.assertIsNotNone(flag_data)
            flag, (flag_x, flag_y) = flag_data
            country = next(item[1] for item in plan['entries'] if item[0] == 'France')
            self.assertEqual(flag_x, rect[0] + 8)
            self.assertEqual(country[0], flag_x + flag.width + 6)
            self.assertGreaterEqual(flag_y, rect[1] + 8 + size)
            self.assertLessEqual(flag_y + flag.height, rect[3] - 8)
            self.assertLessEqual(country[3], rect[3] - 8)
            self.assertLess(abs((flag_y + flag.height / 2) - (country[1] + (country[3] - country[1]) / 2)), 1)
            other_rows = [item[1] for item in plan['entries']
                          if item[0] not in ('France', 'Suivi actif', 'Mode : Arène', 'Joueurs : 1', 'Envahisseur arrivé')]
            self.assertTrue(all(box[3] <= country[1] for box in other_rows))
            for opacity in (0, 50, 100):
                image = overlay._scene_base(plan, dict(options, background_opacity=opacity), True)
                self.assertEqual(image.getpixel((flag_x + flag.width // 2, flag_y + flag.height // 2)),
                                 flag.getpixel((flag.width // 2, flag.height // 2)))

    def test_country_line_requires_data_and_setting_but_not_avatar(self):
        view = self.scene()
        options = overlay._scene_options(None)
        for country in (None, 'fr', '../FR', ['FR']):
            with self.subTest(country=country):
                view['cards'][0].update(country_code=country, country_name='France')
                plan = overlay._scene_plan(view, options, (0, 0, 1920, 1080))
                self.assertIsNone(plan['cards'][0][4])
                self.assertNotIn('France', [entry[0] for entry in plan['entries']])
        view['cards'][0].update(country_code='FR', country_name='')
        plan = overlay._scene_plan(view, options, (0, 0, 1920, 1080))
        self.assertIsNone(plan['cards'][0][4])
        view['cards'][0]['country_name'] = 'France'
        for overrides in ({'show_country': False},):
            with self.subTest(overrides=overrides):
                plan = overlay._scene_plan(view, dict(options, **overrides), (0, 0, 1920, 1080))
                self.assertIsNone(plan['cards'][0][4])
                self.assertNotIn('France', [entry[0] for entry in plan['entries']])
        self.assertIsNotNone(overlay._scene_plan(view, options, (0, 0, 1920, 1080))['cards'][0][4])
        plan = overlay._scene_plan(view, dict(options, show_avatars=False), (0, 0, 1920, 1080))
        self.assertEqual(plan['cards'][0][2], 0)
        self.assertIsNotNone(plan['cards'][0][4])
        self.assertIn('France', [entry[0] for entry in plan['entries']])
        flag, (flag_x, flag_y) = plan['cards'][0][4]
        image = overlay._scene_base(plan, options, True)
        self.assertEqual(image.getpixel((flag_x + flag.width // 2, flag_y + flag.height // 2)),
                         flag.getpixel((flag.width // 2, flag.height // 2)))

    def test_country_name_uses_available_width_and_ellipsizes_on_one_line(self):
        view = self.scene()
        view['cards'][0].update(country_code='FR', country_name='Pays au nom particulièrement long qui ne tient pas sur une ligne')
        options = overlay._scene_options({'font_size':12, 'width_percent':60})
        plan = overlay._scene_plan(view, options, (0, 0, 1920, 1200))
        entries = [entry for entry in plan['entries'] if entry[0].startswith('Pays')]
        self.assertEqual(len(entries), 1)
        text, rect, _ = entries[0]
        self.assertTrue(text.endswith('…'))
        self.assertLessEqual(overlay._measure_text(text, 12), rect[2] - rect[0])

    def test_country_alone_can_be_displayed(self):
        view = self.scene()
        view['cards'][0].update(country_code='FR', country_name='France')
        hidden = {key:False for key in ('show_avatars', 'show_player_name', 'show_role', 'show_steam_id',
                  'show_ping', 'show_ping_average', 'show_jitter', 'show_quality', 'show_duration',
                  'show_rank', 'show_player_stats', 'show_event')}
        options = overlay._scene_options(hidden)
        plan = overlay._scene_plan(view, options, (0, 0, 1920, 1080))
        self.assertEqual(plan['visible_cards'], 1)
        self.assertIn('France', [entry[0] for entry in plan['entries']])
        self.assertEqual(overlay._scene_plan(view, dict(options, show_country=False),
                                            (0, 0, 1920, 1080))['visible_cards'], 0)

    def test_country_flag_assets_are_loaded_and_resized_once(self):
        overlay._flag_atlas.cache_clear()
        overlay._country_flag.cache_clear()
        first = overlay._country_flag('FR', 24)
        second = overlay._country_flag('FR', 24)
        self.assertIsNotNone(first)
        self.assertIs(first, second)
        self.assertEqual(first.size, (24, 18))
        self.assertEqual(overlay._flag_atlas.cache_info().misses, 1)
        self.assertEqual(overlay._country_flag.cache_info().hits, 1)

    def test_missing_flag_atlas_leaves_the_overlay_usable(self):
        overlay._flag_atlas.cache_clear()
        overlay._country_flag.cache_clear()
        self.addCleanup(overlay._flag_atlas.cache_clear)
        self.addCleanup(overlay._country_flag.cache_clear)
        with patch.object(overlay, '_FLAG_ATLAS', 'nonexistent-overlay-flags.png'):
            view = self.scene()
            view['cards'][0].update(country_code='FR', country_name='France')
            plan = overlay._scene_plan(view, overlay._scene_options(None), (0, 0, 1920, 1080))
            self.assertIsNone(plan['cards'][0][4])
            self.assertTrue(any(item[0] == 'Joueur' for item in plan['entries']))
            self.assertTrue(any(item[0] == 'France' for item in plan['entries']))

    def test_border_color_and_radius_apply_to_outer_frame_and_cards(self):
        view = self.scene()
        options = overlay._scene_options({'border_radius': 0, 'border_color': '#12A4E0',
                                          'background_opacity': 100, 'show_avatars': False, 'show_overlay_border': True})
        plan = overlay._scene_plan(view, options, (0, 0, 1920, 1080))
        square = overlay._scene_base(plan, options, True)
        card = plan['cards'][0][0]
        border = (18, 164, 224)
        self.assertEqual(square.getpixel((0, 0)), border + (round(255 * .45),))
        self.assertEqual(square.getpixel((card[0], card[1] + 1)), border + (round(255 * .38),))
        rounded = overlay._scene_base(plan, dict(options, border_radius=20), True)
        self.assertEqual(rounded.getpixel((0, 0))[3], 0)
        self.assertNotEqual(rounded.getpixel((card[0], card[1] + 1))[:3], border)
        self.assertEqual(rounded.getpixel((plan['bounds'][2] // 2, 0))[:3], border)
        transparent = overlay._scene_base(plan, dict(options, background_opacity=0), True)
        self.assertEqual(transparent.getpixel((0, 0))[3], 0)
        self.assertEqual(transparent.getpixel((card[0], card[1] + 1))[3], 0)

    def test_changed_border_options_rerender_without_new_content(self):
        class Stop:
            count = 0
            def is_set(self): return self.count >= 2
            def wait(self, _): self.count += 1
        scene = self.scene()
        window = overlay.OverlayWindow(Mock(side_effect=[
            {'lines':['status'], 'capture_active':True, 'view':scene},
            {'lines':['status'], 'capture_active':True, 'view':scene,
             'options':{'border_radius':20, 'border_color':'#12a4e0'}}]))
        with ExitStack() as stack:
            self._window_mocks(stack)
            stack.enter_context(patch.object(overlay, '_exclude_from_capture', return_value=True))
            stack.enter_context(patch.object(overlay, '_monitor_rect', return_value=(0, 0, 1920, 1080)))
            render = stack.enter_context(patch.object(overlay, '_render_scene_layer'))
            window._run(Stop())
            self.assertEqual(render.call_count, 2)
            self.assertEqual((window._options['border_radius'], window._options['border_color']), (20, '#12a4e0'))

    def test_scene_renders_with_real_gdi_without_opening_a_window(self):
        view = self.scene()
        view['cards'][0]['name'] = '日本語 العربية'
        opts = overlay._scene_options({'background_opacity':0})
        plan = overlay._scene_plan(view, opts, (0, 0, 1920, 1080))
        update = Mock(return_value=True)
        with patch.object(overlay.ctypes.windll.user32, 'UpdateLayeredWindow', update):
            overlay._render_scene_layer(42, plan, True, opts)
        update.assert_called_once()

    def test_scene_gdi_text_alpha_is_applied_to_all_text_colors(self):
        view = self.scene()
        copied = []
        move = ctypes.memmove
        def record(destination, source, size):
            copied.append(bytes(source))
            return move(destination, source, size)
        maximum = []
        with patch.object(overlay.ctypes.windll.user32, 'UpdateLayeredWindow', Mock(return_value=True)), \
             patch.object(overlay.ctypes, 'memmove', side_effect=record):
            for opacity in (0, 50, 100):
                options = overlay._scene_options({'background_opacity': 0, 'show_status': False,
                                                   'show_avatars': False, 'text_opacity': opacity})
                plan = overlay._scene_plan(view, options, (0, 0, 1920, 1080))
                colors = {entry[2] for entry in plan['entries']}
                self.assertGreaterEqual(len(colors), 2)  # General text and colored ping.
                overlay._render_scene_layer(42, plan, True, options)
                maximum.append(max(copied[-1][3::4]))
        self.assertEqual(maximum, [0, 128, 255])

    def test_scene_replans_only_after_data_changes(self):
        class Stop:
            count = 0
            def is_set(self): return self.count >= 3
            def wait(self, _): self.count += 1
        scene = self.scene()
        changed = dict(scene, event='Nouvel événement')
        provider = Mock(side_effect=[{'lines':['x'], 'capture_active':True, 'view':scene},
                                     {'lines':['x'], 'capture_active':True, 'view':scene},
                                     {'lines':['x'], 'capture_active':True, 'view':changed}])
        window = overlay.OverlayWindow(provider)
        with ExitStack() as stack:
            self._window_mocks(stack)
            stack.enter_context(patch.object(overlay, '_exclude_from_capture', return_value=True))
            stack.enter_context(patch.object(overlay, '_monitor_rect', return_value=(0, 0, 1920, 1080)))
            plan = stack.enter_context(patch.object(overlay, '_scene_plan', wraps=overlay._scene_plan))
            render = stack.enter_context(patch.object(overlay, '_render_scene_layer'))
            window._run(Stop())
            self.assertEqual(plan.call_count, 2)
            self.assertEqual(render.call_count, 2)

    def test_lines_and_options_are_bounded(self):
        lines = overlay._lines(['日本語 中文', 'نتيجة المعركة', 'x' * 300] + ['a'] * 25)
        self.assertEqual(lines[:2], ('日本語 中文', 'نتيجة المعركة'))
        self.assertEqual(len(lines), 22)
        self.assertEqual(len(lines[2]), 160)
        self.assertEqual(overlay._lines(['one\ntwo']), ('one two',))
        options = overlay._options({'background_opacity': 0, 'font_size': 32,
                                   'background_color': '#ABCDEF', 'text_color': '#123456',
                                   'show_status': False})
        self.assertEqual(options, {'background_opacity': 0, 'font_size': 32, 'position': 'top_right',
                                   'background_color': '#abcdef', 'text_color': '#123456',
                                   'show_status': False, 'border_radius': 4, 'border_color': '#cab486',
                                   'text_opacity': 50, 'width_percent': 80, 'show_overlay_border': False})
        for invalid in (-1, 101, '50', True, None):
            self.assertEqual(overlay._options({'background_opacity': invalid})['background_opacity'], 50)
        for invalid in (11, 33, 18.0, True, None):
            self.assertEqual(overlay._options({'font_size': invalid})['font_size'], 15)
        for valid in (12, 17, 18, 32):
            self.assertEqual(overlay._options({'font_size': valid})['font_size'], valid)
        for invalid in (-1, 101, '50', True, None):
            self.assertEqual(overlay._options({'text_opacity': invalid})['text_opacity'], 50)
        for invalid in ('#fff', 'red', '#xyzxyz', None):
            self.assertEqual(overlay._options({'text_color': invalid})['text_color'], '#c7c7c7')
            self.assertEqual(overlay._options({'border_color': invalid})['border_color'], '#cab486')
        for invalid in (-1, 31, 9.0, True, None):
            self.assertEqual(overlay._options({'border_radius': invalid})['border_radius'], 4)
        self.assertEqual(overlay._options({'border_radius': 30, 'border_color': '#ABCDEF'})['border_color'], '#abcdef')
        for invalid in (59, 101, '80', True, None):
            self.assertEqual(overlay._options({'width_percent': invalid})['width_percent'], 80)
        for valid in (60, 75, 100):
            self.assertEqual(overlay._options({'width_percent': valid})['width_percent'], valid)
        for invalid in (None, 0, 1, 'false'):
            self.assertFalse(overlay._options({'show_overlay_border': invalid})['show_overlay_border'])
        self.assertFalse(overlay._options({'show_overlay_border': False})['show_overlay_border'])
        self.assertTrue(overlay._options({'show_overlay_border': True})['show_overlay_border'])
        scene_options = overlay._scene_options(None)
        self.assertFalse(scene_options['show_steam_id'])
        self.assertFalse(scene_options['show_jitter'])
        self.assertFalse(scene_options['show_ping_average'])
        self.assertFalse(scene_options['show_quality'])
        self.assertFalse(scene_options['show_player_count'])
        for name in ('show_ping_average', 'show_quality', 'show_player_count'):
            self.assertTrue(overlay._scene_options({name: True})[name])

    def test_outer_border_can_be_hidden_without_changing_cards_or_opacity(self):
        view = self.scene()
        for alpha in (0, 100):
            for radius in (0, 20):
                options = overlay._scene_options({'border_radius': radius, 'border_color': '#12a4e0',
                                                  'background_opacity': alpha, 'show_avatars': False, 'show_overlay_border': True})
                plan = overlay._scene_plan(view, options, (0, 0, 1920, 1080))
                border = overlay._scene_base(plan, options, True)
                plain = overlay._scene_base(plan, dict(options, show_overlay_border=False), True)
                width = plan['bounds'][2]
                card = plan['cards'][0][0]
                if alpha:
                    self.assertEqual(border.getpixel((width // 2, 0))[:3], (18, 164, 224))
                    self.assertEqual(plain.getpixel((width // 2, 0))[:3], overlay._rgb(options['background_color']))
                else:
                    self.assertEqual(border.getpixel((width // 2, 0))[3], 0)
                    self.assertEqual(plain.getpixel((width // 2, 0))[3], 0)
                self.assertEqual(border.crop(card).tobytes(), plain.crop(card).tobytes())
                if radius:
                    self.assertEqual(plain.getpixel((0, 0))[3], 0)

    def test_outer_border_setting_updates_existing_window(self):
        class Stop:
            count = 0
            def is_set(self): return self.count >= 2
            def wait(self, _): self.count += 1
        scene = self.scene()
        window = overlay.OverlayWindow(Mock(side_effect=[
            {'lines':['status'], 'capture_active':True, 'view':scene,
             'options':{'show_overlay_border':True}},
            {'lines':['status'], 'capture_active':True, 'view':scene,
             'options':{'show_overlay_border':False}}]))
        with ExitStack() as stack:
            self._window_mocks(stack)
            stack.enter_context(patch.object(overlay, '_exclude_from_capture', return_value=True))
            stack.enter_context(patch.object(overlay, '_monitor_rect', return_value=(0, 0, 1920, 1080)))
            render = stack.enter_context(patch.object(overlay, '_render_scene_layer'))
            window._run(Stop())
            self.assertEqual(render.call_count, 2)
            self.assertTrue(render.call_args_list[0].args[-1]['show_overlay_border'])
            self.assertFalse(render.call_args_list[1].args[-1]['show_overlay_border'])

    def test_width_resizes_both_renderers_and_fits_small_player_cards(self):
        view = self.scene()
        view['cards'][0]['name'] = 'Joueur au nom assez long'
        opts = overlay._scene_options({'font_size': 12, 'avatar_size': 96, 'width_percent': 60, 'show_steam_id': True})
        for monitor in ((0, 0, 1920, 1600), (-1920, -200, 0, 1400)):
            for position in ('top_left', 'top_right', 'bottom_left', 'bottom_right'):
                narrow = overlay._scene_plan(view, dict(opts, position=position), monitor)
                full = overlay._scene_plan(view, dict(opts, position=position, width_percent=100), monitor)
                self.assertLess(narrow['bounds'][2], full['bounds'][2])
                for bounds in (narrow['bounds'], overlay._bounds(monitor, 2, 12, position, 60)):
                    x, y, width, height = bounds
                    self.assertGreaterEqual(x, monitor[0]); self.assertGreaterEqual(y, monitor[1])
                    self.assertLessEqual(x + width, monitor[2]); self.assertLessEqual(y + height, monitor[3])
                self.assertEqual(narrow['visible_cards'], 1)
                card, _, avatar_size, _, _ = narrow['cards'][0]
                avatar = (card[0] + 8, card[1] + 8, card[0] + 8 + avatar_size, card[1] + 8 + avatar_size)
                texts = [entry[0] for entry in narrow['entries']]
                self.assertIn('42 ms', texts)
                self.assertIn(view['cards'][0]['id'], ''.join(texts).replace(' ', ''))
                for value, box, _ in narrow['entries']:
                    self.assertGreaterEqual(box[0], 0)
                    self.assertLessEqual(box[2], narrow['bounds'][2])
                    self.assertLessEqual(overlay._measure_text(value, 12), box[2] - box[0], value)
                    if card[1] <= box[1] < card[3]:
                        self.assertTrue(box[2] <= avatar[0] or box[0] >= avatar[2] or
                                        box[3] <= avatar[1] or box[1] >= avatar[3], value)

    def test_width_option_updates_existing_window_without_new_content(self):
        class Stop:
            count = 0
            def is_set(self): return self.count >= 2
            def wait(self, _): self.count += 1
        scene = self.scene()
        window = overlay.OverlayWindow(Mock(side_effect=[
            {'lines':['status'], 'capture_active':True, 'view':scene},
            {'lines':['status'], 'capture_active':True, 'view':scene, 'options':{'width_percent':60}}]))
        with ExitStack() as stack:
            self._window_mocks(stack)
            stack.enter_context(patch.object(overlay, '_exclude_from_capture', return_value=True))
            stack.enter_context(patch.object(overlay, '_monitor_rect', return_value=(0, 0, 1920, 1080)))
            render = stack.enter_context(patch.object(overlay, '_render_scene_layer'))
            window._run(Stop())
            self.assertEqual(render.call_count, 2)
            self.assertGreater(render.call_args_list[0].args[1]['bounds'][2], render.call_args_list[1].args[1]['bounds'][2])

    def test_corners_apply_to_both_renderers_and_stay_on_monitor(self):
        view = self.scene()
        for monitor in ((0, 0, 1920, 1080), (-1920, -200, 0, 880), (1920, 0, 2320, 300)):
            positions = {}
            for position in ('top_left', 'top_right', 'bottom_left', 'bottom_right'):
                opts = overlay._scene_options({'position':position})
                bounds = overlay._scene_plan(view, opts, monitor)['bounds']
                legacy = overlay._bounds(monitor, 2, 18, position)
                for x, y, width, height in (bounds, legacy):
                    self.assertGreaterEqual(x, monitor[0]); self.assertGreaterEqual(y, monitor[1])
                    self.assertLessEqual(x + width, monitor[2]); self.assertLessEqual(y + height, monitor[3])
                positions[position] = bounds
            self.assertEqual(positions['top_left'][0], positions['bottom_left'][0])
            self.assertEqual(positions['top_right'][0], positions['bottom_right'][0])
            self.assertEqual(positions['top_left'][1], positions['top_right'][1])
            self.assertEqual(positions['bottom_left'][1], positions['bottom_right'][1])
            self.assertLessEqual(positions['top_left'][0], positions['top_right'][0])
            self.assertLessEqual(positions['top_left'][1], positions['bottom_left'][1])
        self.assertEqual(overlay._options({'position':'bad'})['position'], 'top_right')

    def test_background_alpha_does_not_change_text_opacity(self):
        mask = Image.new('L', (3, 1))
        mask.putdata([0, 128, 255])
        opts = overlay._options({'background_color': '#203040', 'text_color': '#c08040',
                                 'background_opacity': 0, 'text_opacity': 100, 'show_status': False})
        transparent = overlay._compose(mask, opts, True)
        self.assertEqual(transparent[:4], bytes((0, 0, 0, 0)))
        self.assertEqual(transparent[-4:], bytes((64, 128, 192, 255)))
        opts['background_opacity'] = 100
        opaque = overlay._compose(mask, opts, True)
        self.assertEqual(opaque[:4], bytes((64, 48, 32, 255)))
        self.assertEqual(opaque[-4:], transparent[-4:])
        self.assertEqual(opaque[7], 255)

    def test_text_opacity_is_independent_of_background_and_colored_indicators(self):
        mask = Image.new('L', (2, 1))
        mask.putdata([255, 128])
        for opacity, expected in ((0, (0, 0)), (50, (128, 64)), (100, (255, 128))):
            with self.subTest(opacity=opacity):
                options = overlay._options({'background_opacity': 0, 'text_color': '#c08040',
                                            'text_opacity': opacity, 'show_status': False})
                pixels = overlay._compose(mask, options, True)
                self.assertEqual((pixels[3], pixels[7]), expected)
                canvas = Image.new('RGBA', (2, 1), (0, 0, 0, 0))
                overlay._composite_text(canvas, mask, '#00ff00', options)
                self.assertEqual(tuple(canvas.getpixel((x, 0))[3] for x in range(2)), expected)
                if opacity:
                    self.assertEqual(canvas.getpixel((0, 0))[:3], (0, 255, 0))
        options = overlay._scene_options({'background_opacity': 60, 'show_quality': False})
        plan = overlay._scene_plan(self.scene(), options, (0, 0, 1920, 1080))
        full = overlay._scene_base(plan, dict(options, text_opacity=100), True)
        hidden = overlay._scene_base(plan, dict(options, text_opacity=0), True)
        self.assertEqual(full.tobytes(), hidden.tobytes())  # Borders, avatars and status point do not fade.

    def test_status_indicator_can_be_hidden_and_has_opaque_color(self):
        mask = Image.new('L', (40, 40))
        options = overlay._options({'background_opacity': 0})
        green = overlay._compose(mask, options, True)
        red = overlay._compose(mask, options, False)
        offset = ((overlay._MARGIN + 10) * 40 + overlay._MARGIN + 5) * 4
        self.assertEqual(green[offset:offset+4], bytes((133, 218, 92, 255)))
        self.assertEqual(red[offset:offset+4], bytes((100, 100, 239, 255)))
        options['show_status'] = False
        hidden = overlay._compose(mask, options, True)
        self.assertEqual(hidden[offset:offset+4], bytes((0, 0, 0, 0)))

    def test_unicode_mask_passes_strings_and_rtl_flags_to_gdi(self):
        with ExitStack() as stack:
            gui = overlay.win32gui
            for name in ('FillRect', 'GetStockObject', 'CreateFontIndirect', 'SelectObject',
                         'SetBkMode', 'SetTextColor', 'DrawText', 'DeleteObject'):
                stack.enter_context(patch.object(gui, name))
            gui.CreateFontIndirect.return_value = 44
            options = overlay._options({'font_size': 28, 'show_status': False})
            overlay._draw_mask(10, 500, 150, ('日本語 中文', 'نتيجة المعركة'), options)
            self.assertEqual(gui.CreateFontIndirect.call_args.args[0].lfHeight, -28)
            drawn = gui.DrawText.call_args_list
            self.assertEqual([call.args[1] for call in drawn], ['日本語 中文', 'نتيجة المعركة'])
            self.assertFalse(drawn[0].args[-1] & overlay.win32con.DT_RTLREADING)
            self.assertTrue(drawn[1].args[-1] & overlay.win32con.DT_RTLREADING)
            self.assertTrue(all(call.args[-1] & overlay.win32con.DT_END_ELLIPSIS for call in drawn))
            gui.DeleteObject.assert_called_once_with(44)

    def test_render_to_memory_uses_per_pixel_alpha_without_a_window(self):
        # Actual GDI resources and rasterization, but the final display call is
        # replaced: no window is created and no pixels reach the desktop.
        update = Mock(return_value=True)
        compose = overlay._compose
        masks = []
        def check_mask(mask, options, active):
            masks.append((mask.crop((0, 12, 380, 38)).getbbox(),
                          mask.crop((0, 38, 380, 64)).getbbox()))
            return compose(mask, options, active)
        with patch.object(overlay.ctypes.windll.user32, 'UpdateLayeredWindow', update), \
             patch.object(overlay, '_compose', side_effect=check_mask):
            overlay._render_layer(42, (0, 0, 380, 100), ('日本語', 'العربية'), True,
                                  overlay._options({'background_opacity': 0}))
        update.assert_called_once()
        self.assertTrue(all(masks[0]))
        blend = ctypes.cast(update.call_args.args[7], ctypes.POINTER(overlay._BlendFunction)).contents
        self.assertEqual((blend.SourceConstantAlpha, blend.AlphaFormat), (255, 1))

    def test_presentation_preserves_legacy_and_reads_options(self):
        lines, active, opts = overlay._presentation(['x'])
        self.assertEqual((lines, active), (('x',), True))
        self.assertEqual(opts, overlay._options(None))
        lines, active, opts = overlay._presentation({'lines':['x'] * 25, 'capture_active':False,
                                                      'options':{'font_size':30}})
        self.assertEqual((lines, active, opts['font_size']), (('x',) * 22, False, 30))

    def test_bounds_and_fit_adapt_to_font_size_and_monitor(self):
        lines = tuple(str(n) for n in range(22))
        self.assertEqual(overlay._fit_lines(lines, (0, 0, 800, 180)), ('0', '1', '… (+17)', '19', '20', '21'))
        self.assertLess(len(overlay._fit_lines(lines, (0, 0, 800, 180), 32)),
                        len(overlay._fit_lines(lines, (0, 0, 800, 180), 18)))
        for monitor in [(-1920, 0, 0, 1080), (0, -800, 100, 0), (1920, 0, 4480, 1440)]:
            for size in (18, 32):
                x, y, width, height = overlay._bounds(monitor, 8, size)
                left, top, right, bottom = monitor
                self.assertGreaterEqual(x, left)
                self.assertGreaterEqual(y, top)
                self.assertLessEqual(x + width, right)
                self.assertLessEqual(y + height, bottom)

    def test_monitor_selection_uses_game_or_primary(self):
        with patch.object(overlay.win32gui, 'IsWindow', return_value=True), \
             patch.object(overlay.win32api, 'MonitorFromWindow', return_value=2), \
             patch.object(overlay.win32api, 'MonitorFromPoint', return_value=1), \
             patch.object(overlay.win32api, 'GetMonitorInfo', side_effect=lambda h: {'Monitor': (h, 0, 100, 100)}):
            self.assertEqual(overlay._monitor_rect(lambda: 55)[0], 2)
            self.assertEqual(overlay._monitor_rect(lambda: 0)[0], 1)

    def test_capture_exclusion_fails_closed(self):
        with patch.object(overlay.sys, 'getwindowsversion', return_value=SimpleNamespace(major=10, build=18363)):
            self.assertFalse(overlay._exclude_from_capture(1))
        def getter(_hwnd, pointer):
            ctypes.cast(pointer, ctypes.POINTER(ctypes.c_uint32)).contents.value = 0x11
            return 1
        set_affinity = Mock(return_value=1)
        get_affinity = Mock(side_effect=getter)
        user32 = SimpleNamespace(SetWindowDisplayAffinity=set_affinity, GetWindowDisplayAffinity=get_affinity)
        with patch.object(overlay.sys, 'getwindowsversion', return_value=SimpleNamespace(major=10, build=19041)), \
             patch.object(overlay.ctypes, 'windll', SimpleNamespace(user32=user32)):
            self.assertTrue(overlay._exclude_from_capture(1))
            get_affinity.side_effect = lambda *_: 0
            self.assertFalse(overlay._exclude_from_capture(1))

    def _window_mocks(self, stack):
        gui = overlay.win32gui
        for name in ('RegisterClass', 'UnregisterClass', 'CreateWindowEx', 'DestroyWindow',
                     'SetWindowPos', 'ShowWindow', 'PumpWaitingMessages'):
            stack.enter_context(patch.object(gui, name))
        stack.enter_context(patch.object(overlay.win32api, 'GetModuleHandle', return_value=10))
        gui.CreateWindowEx.return_value = 42
        return gui

    def test_failed_exclusion_never_renders_or_shows(self):
        window = overlay.OverlayWindow(lambda: ['visible'])
        with ExitStack() as stack:
            gui = self._window_mocks(stack)
            stack.enter_context(patch.object(overlay, '_exclude_from_capture', return_value=False))
            render = stack.enter_context(patch.object(overlay, '_render_layer'))
            window._run(Mock())
            self.assertEqual(window.error, 'capture_exclusion_unavailable')
            render.assert_not_called()
            gui.SetWindowPos.assert_not_called()
            gui.DestroyWindow.assert_called_once_with(42)

    def test_empty_snapshot_hides_and_nonempty_reappears(self):
        class Stop:
            count = 0
            def is_set(self): return self.count >= 4
            def wait(self, _): self.count += 1
        window = overlay.OverlayWindow(Mock(side_effect=[[], ['one'], [], ['two']]))
        with ExitStack() as stack:
            gui = self._window_mocks(stack)
            stack.enter_context(patch.object(overlay, '_exclude_from_capture', return_value=True))
            stack.enter_context(patch.object(overlay, '_monitor_rect', return_value=(0, 0, 1920, 1080)))
            render = stack.enter_context(patch.object(overlay, '_render_layer'))
            window._run(Stop())
            self.assertEqual(render.call_count, 2)
            self.assertEqual(gui.SetWindowPos.call_count, 2)
            gui.ShowWindow.assert_called_once_with(42, overlay.win32con.SW_HIDE)
            self.assertEqual(window._content, ('two',))
            gui.DestroyWindow.assert_called_once_with(42)

    def test_color_change_rerenders_even_when_content_is_unchanged(self):
        class Stop:
            count = 0
            def is_set(self): return self.count >= 2
            def wait(self, _): self.count += 1
        window = overlay.OverlayWindow(Mock(side_effect=[{'lines':['status'], 'capture_active':True},
            {'lines':['status'], 'capture_active':True, 'options':{'text_color':'#abcdef'}}]))
        with ExitStack() as stack:
            self._window_mocks(stack)
            stack.enter_context(patch.object(overlay, '_exclude_from_capture', return_value=True))
            stack.enter_context(patch.object(overlay, '_monitor_rect', return_value=(0, 0, 1920, 1080)))
            render = stack.enter_context(patch.object(overlay, '_render_layer'))
            window._run(Stop())
            self.assertEqual(render.call_count, 2)
            self.assertEqual(window._options['text_color'], '#abcdef')

    def test_render_error_destroys_window(self):
        window = overlay.OverlayWindow(lambda: ['visible'])
        with ExitStack() as stack:
            gui = self._window_mocks(stack)
            stack.enter_context(patch.object(overlay, '_exclude_from_capture', return_value=True))
            stack.enter_context(patch.object(overlay, '_monitor_rect', return_value=(0, 0, 1920, 1080)))
            stack.enter_context(patch.object(overlay, '_render_layer', side_effect=OSError('render failed')))
            stack.enter_context(self.assertLogs(overlay._LOG, level='ERROR'))
            stop = Mock()
            stop.is_set.return_value = False
            window._run(stop)
            self.assertEqual(window.error, 'window_error')
            gui.SetWindowPos.assert_not_called()
            gui.DestroyWindow.assert_called_once_with(42)


if __name__ == '__main__':
    unittest.main()
