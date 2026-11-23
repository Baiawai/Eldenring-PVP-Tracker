"""Keep the interface translation catalog in sync with its consumers."""
import json
import re
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class InterfaceTranslationTests(unittest.TestCase):
    def test_steam_labels_use_natural_localized_word_order(self):
        packs = json.loads((ROOT / 'application/locales/ui_packs.json').read_text(encoding='utf-8'))
        expected = {'eng':'Steam avatars', 'deu':'Steam-Avatare', 'jap':'Steamアバター',
                    'kor':'Steam 아바타', 'chi':'Steam 头像', 'zht':'Steam 頭像',
                    'nld':'Steam-avatars', 'tur':'Steam avatarları', 'fin':'Steam-avatarit'}
        for language, label in expected.items():
            with self.subTest(language=language):
                self.assertEqual(packs[language]['modern']['overlay_avatar_label'], label)

    def test_faq_answers_describe_the_actual_workflows(self):
        packs = json.loads((ROOT / 'application/locales/ui_packs.json').read_text(encoding='utf-8'))
        for language, pack in packs.items():
            with self.subTest(language=language):
                modern = pack['modern']
                self.assertIn('Start', modern['faq_a_01'])
                self.assertIn('OCR', modern['faq_a_04'])
                self.assertIn('Steam', modern['faq_a_16'])
                self.assertFalse(any(mark in modern['faq_a_16'] for mark in ('?', '؟', '？')))
                for key in ('faq_a_04', 'faq_a_06'):
                    self.assertIn(modern['settings_tab_capture'].casefold(), modern[key].casefold(), key)
                for answer, tab in (('faq_a_13', 'settings_tab_exit'), ('faq_a_15', 'settings_tab_profile'),
                                    ('faq_a_17', 'settings_tab_p2p'), ('faq_a_18', 'online_title')):
                    self.assertIn(modern[tab].casefold(), modern[answer].casefold(), answer)

    def test_overlay_customization_labels_exist_in_all_languages(self):
        packs = json.loads((ROOT / 'application/locales/ui_packs.json').read_text(encoding='utf-8'))
        keys = ('overlay_custom_transparency', 'overlay_custom_background_color', 'overlay_custom_text_color',
                'overlay_custom_text_size', 'overlay_custom_show_status', 'overlay_custom_show_mode',
                'overlay_custom_show_peers', 'overlay_custom_show_event', 'overlay_custom_error',
                'overlay_custom_load_error', 'overlay_group_appearance', 'overlay_group_content',
                'overlay_group_players', 'overlay_group_cards', 'overlay_group_ping_colors',
                'overlay_player_data_availability', 'overlay_player_count', 'overlay_avatar_label',
                'overlay_steam_id', 'overlay_avatar_size', 'overlay_card_size', 'overlay_card_spacing',
                'overlay_ping_good_color', 'overlay_ping_medium_color', 'overlay_ping_bad_color',
                'steam_peer_connection_quality', 'steam_peer_quality_unknown', 'steam_peer_duration',
                'steam_peer_ping_average', 'steam_peer_jitter', 'overlay_visibility_mode',
                'overlay_visibility_capture', 'overlay_visibility_game_visible', 'overlay_visibility_always',
                'overlay_visibility_help', 'overlay_capture_paused', 'overlay_border_radius',
                'overlay_border_color', 'overlay_text_transparency')
        for language, pack in packs.items():
            with self.subTest(language=language):
                self.assertTrue(all(pack['modern'][key].strip() for key in keys))

    def test_overlay_event_labels_are_localized_in_every_pack(self):
        packs = json.loads((ROOT / 'application/locales/ui_packs.json').read_text(encoding='utf-8'))
        for language, pack in packs.items():
            with self.subTest(language=language):
                self.assertTrue(pack['modern']['overlay_last_event'].strip())
                self.assertTrue(pack['modern']['overlay_no_event'].strip())
        self.assertEqual(packs['eng']['modern']['overlay_last_event'], 'Latest event')
        self.assertEqual(packs['jap']['modern']['overlay_no_event'], 'イベントは検出されていません')

    def test_main_template_accessible_labels_have_translations(self):
        class Labels(HTMLParser):
            missing = []

            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                for attribute, key in (('aria-label', 'data-i18n-aria'),
                                       ('placeholder', 'data-i18n-placeholder')):
                    if attrs.get(attribute) and not attrs.get(key):
                        self.missing.append((self.getpos()[0], attribute))

        parser = Labels()
        parser.feed((ROOT / 'templates/index.html').read_text(encoding='utf-8'))
        self.assertEqual(parser.missing, [])

    def test_korean_basic_controls_are_not_corrupted(self):
        packs = json.loads((ROOT / 'application/locales/ui_packs.json').read_text(encoding='utf-8'))
        korean = packs['kor']
        self.assertEqual(korean['legacy'][44:46], ['아니요', '예'])
        self.assertEqual([korean['counter'][i] for i in (0, 2, 4)],
                         ['시작', '중지', '불러오는 중...'])

    def test_italian_help_does_not_fall_back_to_english(self):
        packs = json.loads((ROOT / 'application/locales/ui_packs.json').read_text(encoding='utf-8'))
        italian = packs['ita']['modern']
        self.assertIn('intervallo più lungo', italian['help_capture_interval'])
        self.assertIn('risoluzione rilevata', italian['help_resolution'])
        self.assertIn('lingua dell’interfaccia', italian['help_language_specific'])

    def test_all_interface_keys_exist_for_every_non_french_language(self):
        packs = json.loads((ROOT / 'application/locales/ui_packs.json').read_text(encoding='utf-8'))
        keys = set()
        for file in (ROOT / 'static').glob('*.js'):
            if file.name in ('jquery.js', 'ui-packs.js') or file.name.endswith('.min.js'):
                continue
            source = file.read_text(encoding='utf-8')
            keys.update(re.findall(r"\b(?:t|tr|appT|uiT)\(\s*['\"]([\w-]+)['\"]", source))
            keys.update(re.findall(r"\b(?:uiSetStatus|appStatus)\(\s*(?:[^,()]|\([^()]*\))+,\s*['\"]([\w-]+)['\"]", source))
            keys.update(re.findall(r"\bsetStatus\(\s*['\"]([\w-]+)['\"]", source))
            keys.update(re.findall(r'data-online=["\']([\w-]+)["\']', source))
            # Also cover labels created dynamically and cached-template patches.
            keys.update(key for key in re.findall(
                r"\.dataset\.i18n(?:Aria|Title|Placeholder)?\s*=\s*['\"]([\w-]+)['\"]", source)
                if not key.endswith('_'))
            keys.update(key for key in re.findall(r'data-i18n(?:-aria|-placeholder|-title)?=["\']([\w-]+)["\']', source)
                        if not key.endswith('_'))
        html = (ROOT / 'templates/index.html').read_text(encoding='utf-8')
        keys.update(re.findall(r'data-i18n(?:-aria|-placeholder|-title)?="([\w-]+)"', html))
        self.assertTrue({'nld', 'tur', 'ukr', 'ces', 'ron', 'hun', 'ell', 'swe', 'dan', 'nor', 'fin', 'ind', 'vie', 'hin', 'ptpt'}.issubset(packs))
        for language, pack in packs.items():
            with self.subTest(language=language):
                self.assertFalse(keys - set(pack['modern']))
                self.assertTrue(all(pack['modern'][key] for key in keys))
                self.assertGreaterEqual(len(pack['legacy']), 89)
                self.assertGreaterEqual(len(pack['counter']), 14)

    def test_every_catalog_contains_all_modern_keys(self):
        packs = json.loads((ROOT / 'application/locales/ui_packs.json').read_text(encoding='utf-8'))
        english_keys = set(packs['eng']['modern'])
        for language, pack in packs.items():
            with self.subTest(language=language):
                self.assertEqual(set(pack['modern']), english_keys)
                self.assertTrue(all(pack['modern'].values()))

    def test_modern_translation_placeholders_match_english(self):
        packs = json.loads((ROOT / 'application/locales/ui_packs.json').read_text(encoding='utf-8'))
        placeholders = lambda text: sorted(re.findall(r'\{\w+\}|%[sd]', text))
        for language, pack in packs.items():
            for key, english in packs['eng']['modern'].items():
                if key in pack['modern']:
                    with self.subTest(language=language, key=key):
                        self.assertEqual(placeholders(pack['modern'][key]), placeholders(english))

    def test_invader_arrival_uses_one_player_name_in_every_language(self):
        packs = json.loads((ROOT / 'application/locales/ui_packs.json').read_text(encoding='utf-8'))
        self.assertEqual(packs['eng']['modern']['tracking_defending_against'], '{name} invaded your world.')
        for language, pack in packs.items():
            with self.subTest(language=language):
                self.assertEqual(pack['modern']['tracking_defending_against'].count('{name}'), 1)

    def test_arabic_consent_preserves_pvp_acronym(self):
        packs = json.loads((ROOT / 'application/locales/ui_packs.json').read_text(encoding='utf-8'))
        self.assertIn('PvP', packs['ara']['modern']['online_consent_text'])

    def test_removal_messages_do_not_describe_money_withdrawals(self):
        packs = json.loads((ROOT / 'application/locales/ui_packs.json').read_text(encoding='utf-8'))
        money_terms = {
            'deu': ('auszahlung',), 'ita': ('prelievo',), 'pol': ('wypłat',),
            'rus': ('вывод средств',), 'jap': ('出金', '引き出し'), 'kor': ('출금',),
            'chi': ('提现', '提款'), 'zht': ('提現', '提款'), 'eng': ('withdrawal',),
        }
        for language, terms in money_terms.items():
            for key in ('online_disable_text', 'online_delete_pending'):
                with self.subTest(language=language, key=key):
                    message = packs[language]['modern'][key].casefold()
                    for term in terms:
                        self.assertNotIn(term, message)

    def test_leaderboard_faq_identifies_server_and_steam_in_every_language(self):
        packs = json.loads((ROOT / 'application/locales/ui_packs.json').read_text(encoding='utf-8'))
        for language, pack in packs.items():
            with self.subTest(language=language):
                faq = pack['modern']['faq_a_11']
                self.assertIn('eldenringpvp.com', faq)
                self.assertIn('Steam', faq)
                self.assertIn('PvP', pack['modern']['online_consent_text'])
                self.assertIn('Steam', pack['modern']['faq_q_18'])
                self.assertIn('Steam', pack['modern']['faq_a_18'])

    def test_browser_and_backend_use_identical_packs(self):
        backend = json.loads((ROOT / 'application/locales/ui_packs.json').read_text(encoding='utf-8'))
        source = (ROOT / 'static/ui-packs.js').read_text(encoding='utf-8').strip()
        prefix = 'window.ELDEN_UI_PACKS = '
        self.assertTrue(source.startswith(prefix) and source.endswith(';'))
        self.assertEqual(backend, json.loads(source[len(prefix):-1]))

    def test_overlay_encounter_count_is_translated_without_remote_notice(self):
        packs = json.loads((ROOT / 'application/locales/ui_packs.json').read_text(encoding='utf-8'))
        for language, pack in packs.items():
            with self.subTest(language=language):
                self.assertTrue(pack['modern']['overlay_encounter_count'].strip())
        script = (ROOT / 'static/overlay-settings.js').read_text(encoding='utf-8')
        self.assertIn("['show_player_stats', 'overlay_encounter_count'", script)
        self.assertNotIn("privacy.dataset.i18n = 'overlay_rank_privacy_notice'", script)

    def test_overlay_position_options_are_translated(self):
        packs = json.loads((ROOT / 'application/locales/ui_packs.json').read_text(encoding='utf-8'))
        keys = ('overlay_position', 'overlay_position_top_left', 'overlay_position_top_right',
                'overlay_position_bottom_left', 'overlay_position_bottom_right')
        for language, pack in packs.items():
            with self.subTest(language=language):
                self.assertTrue(all(pack['modern'].get(key) for key in keys))
                self.assertEqual(len({pack['modern'][key] for key in keys[1:]}), 4)

    def test_overlay_player_roles_are_translated(self):
        packs = json.loads((ROOT / 'application/locales/ui_packs.json').read_text(encoding='utf-8'))
        for language, pack in packs.items():
            with self.subTest(language=language):
                for key in ('duelist', 'ally', 'hunter', 'invader', 'enemy_cooperator', 'overlay_show_role'):
                    self.assertTrue(pack['modern'].get(key), key)

    def test_ping_faq_explains_store_and_development_behavior(self):
        packs = json.loads((ROOT / 'application/locales/ui_packs.json').read_text(encoding='utf-8'))
        for language, pack in packs.items():
            with self.subTest(language=language):
                self.assertIn('Steam', pack['modern']['faq_a_09'])
        self.assertIn('only in the development version', packs['eng']['modern']['faq_a_09'])
        self.assertIn('the Store version uses Steam ping', packs['eng']['modern']['faq_a_09'])
        template = (ROOT / 'templates/index.html').read_text(encoding='utf-8')
        fallback = (ROOT / 'static/ui-i18n.js').read_text(encoding='utf-8')
        self.assertIn('uniquement dans la version de développement', template)
        self.assertIn('la version Store utilise le ping Steam', fallback)

    def test_overlay_encounter_count_is_translated(self):
        packs = json.loads((ROOT / 'application/locales/ui_packs.json').read_text(encoding='utf-8'))
        for language, pack in packs.items():
            with self.subTest(language=language):
                self.assertTrue(pack['modern'].get('overlay_encounter_count'))
        self.assertEqual(packs['eng']['modern']['overlay_encounter_count'], 'Number of encounters')
        self.assertEqual(packs['jap']['modern']['overlay_encounter_count'], '遭遇回数')

    def test_overlay_width_and_border_labels_are_translated(self):
        packs = json.loads((ROOT / 'application/locales/ui_packs.json').read_text(encoding='utf-8'))
        for language, pack in packs.items():
            with self.subTest(language=language):
                self.assertTrue(pack['modern'].get('overlay_width_percent'))
                self.assertTrue(pack['modern'].get('overlay_show_border'))

    def test_faq_order_and_ocr_explanation_are_available_in_every_language(self):
        html = (ROOT / 'templates/index.html').read_text(encoding='utf-8')
        questions = re.findall(r'<summary data-i18n="faq_q_(\d+)">', html)
        self.assertEqual(questions, ['12', '01', '05', '03', '19', '02', '06', '20',
                                     '04', '07', '15', '08', '17', '09', '11', '18',
                                     '21', '22', '23', '10', '14', '16', '13'])
        packs = json.loads((ROOT / 'application/locales/ui_packs.json').read_text(encoding='utf-8'))
        for language, pack in packs.items():
            with self.subTest(language=language):
                self.assertIn('OCR', pack['modern']['faq_a_19'])
                for number in range(19, 24):
                    self.assertTrue(pack['modern'][f'faq_q_{number}'])
                    self.assertTrue(pack['modern'][f'faq_a_{number}'])

    def test_match_results_and_settings_are_readable_in_asian_languages(self):
        packs = json.loads((ROOT / 'application/locales/ui_packs.json').read_text(encoding='utf-8'))
        expected = {
            'jap': ('勝利', '敗北', '引き分け'),
            'kor': ('승리', '패배', '무승부'),
            'chi': ('胜利', '失败', '平局'),
            'zht': ('勝利', '失敗', '平手'),
            'tha': ('ชัยชนะ', 'พ่ายแพ้', 'เสมอ'),
        }
        for language, terms in expected.items():
            with self.subTest(language=language):
                modern = packs[language]['modern']
                self.assertEqual(tuple(modern[key] for key in ('victory', 'defeat', 'draw')), terms)
                self.assertEqual(tuple(packs[language]['legacy'][:3]), terms)
        self.assertEqual(packs['jap']['legacy'][44:46], ['いいえ', 'はい'])
        self.assertEqual(packs['chi']['legacy'][25:30], ['24小时', '48小时', '7天', '30天', '全部'])
        self.assertEqual(packs['jap']['modern']['all'], 'すべて')
        self.assertEqual(packs['tha']['modern']['fights'], 'การต่อสู้')

    def test_game_mode_and_legacy_result_labels_keep_their_meaning(self):
        packs = json.loads((ROOT / 'application/locales/ui_packs.json').read_text(encoding='utf-8'))
        for language, pack in packs.items():
            with self.subTest(language=language):
                modern, legacy = pack['modern'], pack['legacy']
                self.assertEqual(modern['online_mode'], modern['mode'])
                self.assertEqual(modern['online_level'], modern['leaderboard_level'])
                self.assertEqual(legacy[35], modern['victories'])
                self.assertEqual(legacy[36], modern['defeats'])
                self.assertEqual(legacy[79], modern['stats_abandons'])
                self.assertEqual(legacy[80], modern['stats_opponent_left'])
                self.assertEqual(legacy[86], modern['session_streak'])
                self.assertTrue(modern['leaderboard_avatar'])
        self.assertEqual(packs['kor']['modern']['mode'], '모드')
        self.assertEqual(packs['ara']['legacy'][7], packs['ara']['legacy'][63])
        self.assertIn('لقطات', packs['ara']['legacy'][7])
        for language in ('spaes', 'spaar'):
            self.assertEqual(packs[language]['legacy'][77], 'Combates totales')
            self.assertEqual(packs[language]['legacy'][87], 'Racha de derrotas')

    def test_player_and_event_labels_are_not_corrupted(self):
        packs = json.loads((ROOT / 'application/locales/ui_packs.json').read_text(encoding='utf-8'))
        self.assertEqual(packs['jap']['modern']['defeated_players'], '倒したプレイヤー')
        self.assertEqual(packs['kor']['modern']['defeated_me'], '나를 이긴 플레이어')
        self.assertEqual(packs['kor']['modern']['hunter'], '사냥꾼')
        self.assertEqual(packs['ara']['modern']['hunter_opponent'], 'صياد الخصم')
        self.assertEqual(packs['chi']['modern']['invader_died'], '入侵者死亡')
        self.assertEqual(packs['pol']['legacy'][79], 'Poddania')
        self.assertEqual(packs['deu']['modern']['online_level'], 'Stufe')
        self.assertEqual(packs['deu']['modern']['ally_dismissed'], 'Verbündeter zurückgeschickt')
        self.assertEqual(packs['kor']['modern']['ally'], '아군')
        self.assertEqual(packs['kor']['modern']['unknown_side'], '진영 알 수 없음')
        for language, pack in packs.items():
            with self.subTest(language=language):
                for key in ('hunter_opponent', 'hunter_mixed', 'hunter_unknown', 'hunter_left', 'invader_died'):
                    self.assertNotIn('Hunter', pack['modern'][key] if language != 'eng' else '')
                    self.assertNotIn('\\3c', pack['modern'][key])

if __name__ == '__main__':
    unittest.main()
