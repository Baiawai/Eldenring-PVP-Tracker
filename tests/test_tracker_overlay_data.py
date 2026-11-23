import copy
import unittest

from application import tracker_overlay_data as overlay


class TrackerOverlayDataTests(unittest.TestCase):
    def test_all_interface_languages_cover_every_display_state(self):
        for language in ['fra', *overlay._packs()]:
            with self.subTest(language=language):
                for kwargs in ({'error': True}, {}, {'running': True},
                               {'running': True, 'ready': True},
                               {'running': True, 'ready': True, 'game_running': True},
                               {'running': True, 'ready': True, 'game_running': True,
                                'game_detected': True, 'fight': True},
                               {'running': True, 'ready': True, 'game_running': True,
                                'game_detected': True}):
                    snapshot = overlay.build_snapshot(language=language, **kwargs)
                    self.assertTrue(snapshot['status_text'])
                for mode in ('Arena', 'Invasion', 'Defense', ''):
                    for result in ('victory', 'defeat', 'draw', 'no_result', 'connection_error'):
                        snapshot = overlay.build_snapshot(language=language, mode=mode,
                            session={'last': {'mode': mode, 'result': result}})
                        self.assertTrue(snapshot['mode_text'])
                        self.assertTrue(snapshot['last']['result_text'])
                        self.assertTrue(snapshot['last']['mode_text'])
                for state in ('active', 'disabled', 'starting', 'game_closed', 'waiting_log',
                              'steam_unavailable', 'helper_error'):
                    self.assertTrue(overlay.build_snapshot(language=language,
                                    peers={'status': state})['peer_status_text'])

    def test_input_is_not_mutated_or_matched_and_names_are_single_line(self):
        session = {'last': {'mode': 'Invasion', 'result': 'victory', 'opponent': 'Game\nName'}}
        peers = {'enabled': True, 'status': 'active', 'peers': [
            {'name': 'Steam\nName', 'ping': 72, 'id': '123', 'ip': '127.0.0.1'},
            {'name': 'Other', 'ping': None}]}
        before = copy.deepcopy((session, peers))
        snapshot = overlay.build_snapshot(language='fra', session=session, peers=peers)
        self.assertEqual((session, peers), before)
        self.assertEqual(snapshot['last']['opponent'], 'Game Name')
        self.assertEqual(snapshot['peers'], [{'name': 'Steam Name', 'ping': 72},
                                             {'name': 'Other', 'ping': None}])
        self.assertNotIn('id', snapshot['peers'][0])
        self.assertNotIn('ip', snapshot['peers'][0])
        self.assertEqual(snapshot['last']['result_text'], 'Victoire')

    def test_disabled_detection_does_not_expose_stale_peers(self):
        snapshot = overlay.build_snapshot(peers={'enabled': False, 'status': 'active',
                                                'peers': [{'name': 'old', 'ping': 20}]})
        self.assertEqual(snapshot['peer_status'], 'disabled')
        self.assertEqual(snapshot['peers'], [])

    def test_invalid_pings_become_unavailable(self):
        values = [-1, float('inf'), float('nan'), '42', True, 60001, 41.6, None]
        snapshot = overlay.build_snapshot(peers={'status': 'active', 'peers':
                                          [{'name': 'n', 'ping': value} for value in values]})
        self.assertEqual([p['ping'] for p in snapshot['peers']],
                         [None, None, None, None, None, None, 42, None])

    def test_unknown_language_uses_english(self):
        self.assertEqual(overlay.build_snapshot(language='xyz'), overlay.build_snapshot(language='eng'))

    def test_roles_are_localized_for_each_interface_language(self):
        for language in ['fra', *overlay._packs()]:
            with self.subTest(language=language):
                modern, _ = overlay._translation(language)
                labels = overlay.build_snapshot(language=language)['labels']
                for role, key in [('ally', 'ally'), ('cooperator', 'enemy_cooperator'),
                                  ('hunter', 'hunter'), ('invader', 'invader'), ('duelist', 'duelist')]:
                    self.assertEqual(labels['role_' + role], modern[key])
                    self.assertTrue(labels['role_' + role])

    def test_quality_and_encounter_labels_are_localized(self):
        for language in ['fra', *overlay._packs()]:
            with self.subTest(language=language):
                modern, _ = overlay._translation(language)
                labels = overlay.build_snapshot(language=language)['labels']
                self.assertEqual(labels['quality_unavailable'], modern['steam_peer_quality_unknown'])
                self.assertEqual(labels['encounters'], modern['overlay_encounter_count'])
                self.assertEqual(labels['duration'], modern['steam_peer_duration'])
                self.assertEqual(labels['unknown_name'], modern['steam_world_host_unknown'])
                self.assertTrue(labels['quality_unavailable'])
                self.assertTrue(labels['encounters'])
        labels = overlay.build_snapshot(language='fra')['labels']
        self.assertEqual(labels['duration'], 'Connexion')
        self.assertEqual(labels['unknown_name'], 'Non identifié')

    def test_ping_variation_label_is_clear_in_each_language(self):
        self.assertEqual(overlay.build_snapshot(language='fra')['labels']['jitter'], 'Variation du ping')
        self.assertEqual(overlay.build_snapshot(language='eng')['labels']['jitter'], 'Ping variation')
        for language in overlay._packs():
            with self.subTest(language=language):
                label = overlay.build_snapshot(language=language)['labels']['jitter']
                self.assertTrue(label.strip())
                self.assertNotEqual(label.casefold(), 'jitter')

    def test_all_overlay_labels_follow_selected_interface_language(self):
        keys = {'tracking':'sidebar_tracking', 'mode':'mode', 'last':'last_combat',
                'empty_last':'last_combat_empty', 'peers':'steam_peer_title', 'ping':'steam_ping_label',
                'last_event':'overlay_last_event', 'no_event':'overlay_no_event',
                'player_count':'overlay_player_count', 'quality':'steam_peer_connection_quality',
                'quality_unavailable':'steam_peer_quality_unknown', 'encounters':'overlay_encounter_count',
                'unknown_name':'steam_world_host_unknown', 'duration':'steam_peer_duration',
                'average_ping':'steam_peer_ping_average', 'jitter':'steam_peer_jitter',
                'tracker_user':'tracker_user_badge', 'capture_paused':'overlay_capture_paused'}
        for language in ['fra', *overlay._packs()]:
            modern, _ = overlay._translation(language)
            labels = overlay.build_snapshot(language=language)['labels']
            for field, key in keys.items():
                with self.subTest(language=language, field=field):
                    self.assertEqual(labels[field], modern[key])
                    self.assertTrue(labels[field].strip())

    def test_fight_status_uses_the_in_progress_translation(self):
        for language in ['fra', *overlay._packs()]:
            with self.subTest(language=language):
                modern, _ = overlay._translation(language)
                snapshot = overlay.build_snapshot(language=language, running=True, ready=True,
                                                  game_running=True, game_detected=True, fight=True)
                self.assertEqual(snapshot['status'], 'fight')
                self.assertEqual(snapshot['status_text'], modern['overlay_fight_active'])
                self.assertTrue(snapshot['status_text'])
        self.assertEqual(overlay._FRENCH['overlay_fight_active'], 'Combat en cours')
        self.assertEqual(overlay._packs()['eng']['modern']['overlay_fight_active'], 'Fight in progress')


if __name__ == '__main__':
    unittest.main()
