import base64
import math
import unittest
from io import BytesIO

from PIL import Image

from application.steam_peer_enrichment import PeerCache, _MAX_ENTRIES, _TTL_SECONDS


def avatar():
    buffer = BytesIO()
    Image.new('RGBA', (4, 4), (123, 80, 20, 255)).save(buffer, 'PNG')
    return buffer.getvalue()


class SteamPeerEnrichmentTests(unittest.TestCase):
    def test_avatar_and_duration_are_memory_only_and_peer_scoped(self):
        cache = PeerCache()
        sid = '76561198000000001'
        image = avatar()
        first = cache.update([{'id':sid, 'name':'player', 'avatar_png':base64.b64encode(image).decode()}], now=5)
        self.assertEqual(first[0]['connected_seconds'], 0)
        self.assertTrue(first[0]['avatar_available'])
        first_revision = first[0]['avatar_revision']
        self.assertNotIn('avatar_png', first[0])
        self.assertEqual(cache.avatar(sid, now=5), image)
        self.assertIsNone(cache.avatar('76561198000000002', now=5))
        again = cache.update([{'id':sid}], now=18)
        self.assertEqual(again[0]['connected_seconds'], 13)
        self.assertTrue(again[0]['avatar_available'])
        self.assertEqual(again[0]['avatar_revision'], first_revision)
        unchanged = cache.update([{'id':sid, 'avatar_png':base64.b64encode(image).decode()}], now=18.5)[0]
        self.assertEqual(unchanged['avatar_revision'], first_revision)
        other = BytesIO()
        Image.new('RGBA', (4, 4), (3, 10, 245, 255)).save(other, 'PNG')
        changed = cache.update([{'id':sid, 'avatar_png':base64.b64encode(other.getvalue()).decode()}], now=18.75)[0]
        self.assertGreater(changed['avatar_revision'], first_revision)
        cache.update([], now=19)
        self.assertIsNone(cache.avatar(sid, now=19))
        reconnect = cache.update([{'id':sid}], now=22)
        self.assertEqual(reconnect[0]['connected_seconds'], 0)
        self.assertEqual(cache.avatar(sid, now=22), other.getvalue())
        self.assertIsNone(cache.avatar(sid, now=18.75 + _TTL_SECONDS))

    def test_bad_images_identifiers_and_measurements_are_not_exposed(self):
        cache = PeerCache()
        sid = '76561198000000001'
        item = cache.update([{'id':'bad', 'avatar_png':base64.b64encode(avatar()).decode()},
                             {'id':sid, 'avatar_png':'not a png', 'ping':float('nan'),
                              'average_ping':-1, 'jitter':True, 'quality':1.5}], now=0)[0]
        self.assertFalse(item['avatar_available'])
        self.assertIsNone(item['ping'])
        self.assertIsNone(item['average_ping'])
        self.assertIsNone(item['jitter'])
        self.assertIsNone(item['quality'])
        item = cache.update([{'id':sid, 'ping':45, 'average_ping':48.5, 'jitter':2.4, 'quality':0.9}], now=2)[0]
        self.assertEqual((item['ping'], item['average_ping'], item['jitter'], item['quality']), (45, 48.5, 2.4, 0.9))

    def test_cache_is_bounded(self):
        cache = PeerCache()
        encoded = base64.b64encode(avatar()).decode()
        for i in range(_MAX_ENTRIES + 20):
            cache.update([{'id':f'{76561198000000000 + i:017}', 'avatar_png':encoded}], now=i)
        self.assertLessEqual(len(cache._avatars), _MAX_ENTRIES)


if __name__ == '__main__':
    unittest.main()
