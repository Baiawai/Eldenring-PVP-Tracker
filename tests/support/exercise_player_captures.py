"""Exercise player capture references with synthetic, isolated SQLite data."""
import base64
from io import BytesIO
from unittest.mock import patch

from flask import Flask
from PIL import Image

app = Flask(__name__)
from application import init, players

output = BytesIO()
Image.new('RGB', (3, 3), (80, 60, 30)).save(output, 'JPEG')
image = output.getvalue()
encoded = base64.b64encode(image).decode('ascii')
for i in range(25):
    init.add_capture('Alice', 1, 0, 0, 10, f'2026-01-01 12:00:{i:02}', 'Arena', encoded)
init.add_capture('Bob', 0, 1, 0, 10, '2026-01-01 12:01:00', 'Arena', encoded)
init.add_capture('', 1, 0, 0, 10, '2026-01-01 12:02:00', 'Arena', encoded)
init.add_capture('Charlie', 1, 0, 0, 10, '2026-01-01 12:03:00', 'Arena', encoded)

def steam(event_id, sid, name, date, mode='Arena', outcome=None, match_date=None):
    details = {'id':sid, 'name':name, 'country_code':None}
    if outcome:
        details.update(outcome=outcome, match_date=match_date)
    return {'id':event_id, 'date':date, 'mode':mode, 'event':'steam_encounter', 'steam':details}

events = [
    steam(101, '76561198000000001', 'SteamA', '2026-01-01 11:59:58', outcome='victory', match_date='2026-01-01 12:00:00'),
    steam(102, '76561198000000002', 'SteamB', '2026-01-01 12:01:50'),
    # Multiple Steam events for one result are ambiguous and must not link.
    steam(103, '76561198000000003', 'SteamC', '2026-01-01 12:02:59', outcome='victory', match_date='2026-01-01 12:03:00'),
    steam(104, '76561198000000004', 'SteamD', '2026-01-01 12:02:59', outcome='victory', match_date='2026-01-01 12:03:00'),
    # Identical Steam/game names do not establish a relationship.
    steam(105, '76561198000000005', 'Alice', '2026-01-01 12:05:00', mode='Defense'),
]
with patch.object(players, 'read_sightings', return_value=[]), \
        patch.object(players, 'read_steam_history', return_value=events), \
        patch.object(players.steam_avatar_store, 'available', return_value=set()):
    client = app.test_client()
    response = client.get('/players').get_json()
    entries = response['players']
    game_alice = next(p for p in entries if p['name'] == 'Alice' and not p.get('steam'))
    assert len(game_alice['history']) == 20 and len(game_alice['capture_refs']) == 25
    assert [r['id'] for r in game_alice['capture_refs']] == list(range(25, 0, -1))
    assert game_alice['history'][0]['capture_id'] == 25
    assert next(p for p in entries if p['name'] == 'Bob')['capture_refs'][0]['id'] == 26
    steam_a = next(p for p in entries if p.get('steam', {}).get('id') == '76561198000000001')
    steam_b = next(p for p in entries if p.get('steam', {}).get('id') == '76561198000000002')
    assert steam_a['history'][0]['capture_id'] == 1 and steam_a['capture_refs'][0]['id'] == 1
    assert steam_b['history'][0]['capture_id'] == 27 and steam_b['capture_refs'][0]['id'] == 27
    for sid in ('76561198000000003', '76561198000000004', '76561198000000005'):
        entry = next(p for p in entries if p.get('steam', {}).get('id') == sid)
        assert not entry['capture_refs'] and all('capture_id' not in h for h in entry['history'])
    capture = client.get('/players/capture/1')
    assert capture.status_code == 200 and capture.data == image and capture.mimetype == 'image/jpeg'
    assert capture.headers['Cache-Control'] == 'no-store'
    assert client.get('/players/capture/9999').status_code == 404
    assert not any('base64' in ref for player in entries for ref in player['capture_refs'])
print('Player capture references, ambiguity checks and on-demand images: OK')
