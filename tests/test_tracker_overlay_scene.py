import unittest
from unittest.mock import patch

from application import tracker_overlay_scene as scene
from application import overlay_country_names


class OverlaySceneTests(unittest.TestCase):
    def test_cards_use_only_current_steam_peers_and_cached_avatar(self):
        steam_id = '76561198000000000'
        snapshot = {'enabled': True, 'status': 'active', 'peers': [
            {'id': steam_id, 'name': ' Player\nName ', 'ping': 57, 'quality': .9,
             'average_ping': 60, 'jitter': 5, 'connected_seconds': 121,
             'avatar_available': True, 'ip': '198.51.100.1'}]}
        seen = []
        cards = scene.cards(snapshot, {}, lambda ident: seen.append(ident) or b'png')
        self.assertEqual(seen, [steam_id])
        self.assertEqual(cards[0]['name'], 'Player Name')
        self.assertEqual(cards[0]['duration'], '00:02:01')
        self.assertEqual(cards[0]['avatar'], b'png')
        self.assertNotIn('ip', cards[0])
        self.assertEqual(scene.cards(snapshot, {'show_avatars': False}, lambda _: self.fail('avatar requested'))[0]['avatar'], None)
        self.assertEqual(scene.cards(snapshot, {'show_peers': False}), [])
        self.assertEqual(scene.cards(dict(snapshot, enabled=False), {}), [])

    def test_invalid_measurements_and_ids_do_not_create_fictitious_data(self):
        snapshot = {'status': 'active', 'peers': [
            {'id': 'invalid', 'name': 'Bad'},
            {'id': '76561198000000000', 'ping': -1, 'quality': 4,
             'average_ping': float('nan'), 'jitter': True}]}
        card = scene.cards(snapshot, {})[0]
        self.assertIsNone(card['ping'])
        self.assertIsNone(card['quality'])
        self.assertIsNone(card['average_ping'])
        self.assertIsNone(card['jitter'])
        self.assertIsNone(card['duration'])

    def test_duration_uses_same_hours_minutes_seconds_format_as_app(self):
        for seconds, expected in ((0, '00:00:00'), (59, '00:00:59'),
                                  (121, '00:02:01'), (3600, '01:00:00'),
                                  (360000, '100:00:00'), (None, None), (-1, None)):
            with self.subTest(seconds=seconds):
                self.assertEqual(scene._duration(seconds), expected)

    def test_ping_colors_follow_independent_preferences(self):
        options = {'ping_good_color': '#112233', 'ping_medium_color': '#445566',
                   'ping_bad_color': '#778899'}
        self.assertEqual(scene.ping_color(35, options), '#112233')
        self.assertEqual(scene.ping_color(110, options), '#445566')
        self.assertEqual(scene.ping_color(250, options), '#778899')

    def test_role_is_only_taken_from_an_explicit_recognized_value(self):
        peer = {'id': '76561198000000000', 'name': 'Player'}
        for role in ('invader', 'hunter', 'ally', 'cooperator', 'duelist'):
            with self.subTest(role=role):
                snapshot = {'status': 'active', 'peers': [dict(peer, role=role)]}
                self.assertEqual(scene.cards(snapshot, {})[0]['role'], role)
        for role in (None, 'INVADER', 'unknown', '', True, ['invader']):
            with self.subTest(role=role):
                snapshot = {'status': 'active', 'peers': [dict(peer, role=role)]}
                self.assertIsNone(scene.cards(snapshot, {})[0]['role'])
        self.assertIsNone(scene.cards({'status': 'active', 'peers': [peer]}, {})[0]['role'])

    def test_untrusted_peer_snapshot_cannot_forge_tracker_membership(self):
        peer = {'id': '76561198000000000', 'name': 'Player', 'tracker_member': True}
        card = scene.cards({'status': 'active', 'peers': [peer]}, {})[0]
        self.assertNotIn('tracker_member', card)

    def test_country_is_validated_without_inferring_language(self):
        peer = {'id': '76561198000000000', 'country_code': 'FR'}
        snapshot = {'status': 'active', 'peers': [peer]}
        self.assertEqual(scene.cards(snapshot, {})[0]['country_code'], 'FR')
        for invalid in (None, 'fr', 'FRA', '1A', '../FR', 'ÉU', ['FR']):
            with self.subTest(country=invalid):
                peer['country_code'] = invalid
                self.assertIsNone(scene.cards(snapshot, {})[0]['country_code'])

    def test_country_names_follow_interface_language_without_avatar(self):
        peer = {'id': '76561198000000000', 'country_code': 'DE', 'avatar_available': True}
        snapshot = {'status': 'active', 'peers': [peer]}
        for language, expected in [('fra', 'Allemagne'), ('eng', 'Germany'),
                                   ('deu', 'Deutschland'), ('chi', '德国')]:
            with self.subTest(language=language):
                card = scene.cards(snapshot, {'show_avatars': False}, language=language)[0]
                self.assertEqual(card['country_name'], expected)
                self.assertIsNone(card['avatar'])
        self.assertEqual(scene.cards(snapshot, {}, language='unsupported')[0]['country_name'], 'Germany')

    def test_country_catalog_covers_supported_languages_and_known_regions(self):
        import json
        from pathlib import Path
        catalog = overlay_country_names._catalog()
        languages = json.loads((Path(__file__).resolve().parents[1] / 'application/locales/ui_packs.json').read_text(encoding='utf-8'))
        self.assertEqual(set(catalog), {'fra', *languages})
        for language in catalog:
            with self.subTest(language=language):
                self.assertEqual(set(catalog[language]), set(catalog['eng']))
                self.assertTrue(all(isinstance(name, str) and name.strip() for name in catalog[language].values()))
        packs = json.loads((Path(__file__).resolve().parents[1] / 'application' / 'locales' / 'ui_packs.json').read_text(encoding='utf-8'))
        snapshot = {'status': 'active', 'peers': [{'id': '76561198000000000', 'country_code': 'FR'}]}
        for language in ['fra', *packs]:
            with self.subTest(language=language):
                self.assertTrue(scene.cards(snapshot, {}, language=language)[0]['country_name'])
        self.assertIsNone(overlay_country_names.country_name('ZZ', 'fra'))
        self.assertIsNone(overlay_country_names.country_name('../FR', 'fra'))
        with patch.object(overlay_country_names, '_catalog', return_value={}):
            self.assertIsNone(overlay_country_names.country_name('FR', 'fra'))


if __name__ == '__main__':
    unittest.main()
