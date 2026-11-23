"""Exercise automatic Steam categories with an isolated data directory."""
from unittest.mock import patch
from flask import Flask

app = Flask(__name__)
from application import players, steam_history, steam_friendships, player_tags, overlay_player_tags, tracker_overlay_scene
from application.detection_history import record_detection, read_steam_history

sid = '76561198000000001'
other = '76561198000000002'
peer = {'id': sid, 'name': 'Same name', 'steam_friend': True}
record_detection('Synthetic Steam encounter', 'Defense', 'steam_encounter', peer)
assert read_steam_history()[0]['steam']['steam_friend'] is True
with patch.object(steam_history, 'record_detection', return_value=1) as record, \
     patch.object(steam_history, 'update_detection', return_value=True) as update:
    assert steam_history.observe('active', [peer]) == 1
    assert record.call_args.args[3]['steam_friend'] is True
    assert steam_history.observe('active', [dict(peer, steam_friend=None)]) == 0
    assert steam_history.observe('active', [dict(peer, steam_friend=1)]) == 0
    assert steam_history.observe('active', [dict(peer, steam_friend=False)]) == 1
    assert update.call_args.args[3]['steam_friend'] is False
    assert steam_history.observe('active', [dict(peer, steam_friend=None)]) == 0
    steam_history.observe('disabled', [])

def event(number, ident, friend):
    return {'id':number, 'date':f'2026-01-01 12:00:{number:02}', 'mode':'Defense',
            'event':'steam_encounter', 'steam':{'id':ident, 'name':'Same name', 'steam_friend':friend}}

events = [event(5, sid, None), event(4, other, False), event(3, sid, True), event(2, other, True)]
assert steam_friendships.known_relationships(events) == {sid:True, other:False}
separate = player_tags.annotate([{'name':'Same name', 'steam_friend':True},
                                 {'name':'Same name', 'steam':{'id':sid}, 'steam_friend':True}])
assert separate[0]['categories'] == [] and separate[1]['categories'] == ['steam_friend']
with patch.object(players, 'read_steam_history', return_value=events), \
     patch.object(players, 'read_sightings', return_value=[]), \
     patch.object(players.steam_avatar_store, 'available', return_value=set()):
    client = app.test_client()
    response = client.get('/players/categories').get_json()
    assert [c['id'] for c in response['categories']][:3] == ['steam_friend', 'friend', 'rival']
    assert response['counts']['steam_friend'] == 1
    tagged = client.get('/players?limit=30&category=steam_friend').get_json()
    assert tagged['filtered_count'] == 1 and tagged['players'][0]['steam']['id'] == sid
    assert tagged['players'][0]['categories'] == ['steam_friend']
    token = tagged['snapshot']
    assert client.post('/players/preferences', json={'source':'steam','identity':sid,'categories':['friend'],'favourite':True}).status_code == 200
    result = client.get('/players', query_string={'limit':30, 'snapshot':token})
    assert result.status_code == 200 and result.get_json()['players'][0]['categories'] == ['steam_friend','friend']
    assert client.post('/players/preferences', json={'source':'steam','identity':sid,'categories':['steam_friend'],'favourite':True}).status_code == 400
    assert client.delete('/players/categories/steam_friend').status_code == 403
    # The overlay uses the Steam ID, never an identical character name, and
    # sees a preference edit immediately even while its cache is warm.
    with patch.object(overlay_player_tags, 'read_steam_history', return_value=events):
        cards = tracker_overlay_scene.cards({'status':'active','peers':[dict(peer, steam_friend=None)]}, {})
        overlay_player_tags.annotate(cards, {}, 'fra')
        assert cards[0]['favourite'] and [tag['name'] for tag in cards[0]['tags']] == ['Ami Steam','Ami']
        assert client.post('/players/preferences', json={'source':'steam','identity':sid,'categories':['rival'],'favourite':False}).status_code == 200
        cards = tracker_overlay_scene.cards({'status':'active','peers':[peer]}, {})
        overlay_player_tags.annotate(cards, {}, 'eng')
        assert not cards[0]['favourite'] and [tag['name'] for tag in cards[0]['tags']] == ['Steam friend','Rival']
        hidden = tracker_overlay_scene.cards({'status':'active','peers':[peer]}, {})
        overlay_player_tags.annotate(hidden, {'show_player_tags':False,'show_player_favourite':True}, 'fra')
        assert 'tags' not in hidden[0]
        assert client.post('/players/preferences', json={'source':'steam','identity':sid,'categories':['friend'],'favourite':True}).status_code == 200
        hidden = tracker_overlay_scene.cards({'status':'active','peers':[peer]}, {})
        overlay_player_tags.annotate(hidden, {'show_player_tags':True,'show_player_favourite':False}, 'fra')
        assert not hidden[0]['favourite'] and [tag['name'] for tag in hidden[0]['tags']] == ['Ami Steam','Ami']
    cards = tracker_overlay_scene.cards({'status':'active','peers':[dict(peer, id=other, steam_friend=False)]}, {})
    overlay_player_tags.annotate(cards, {}, 'fra')
    assert not cards[0]['favourite'] and cards[0]['tags'] == []
    assert player_tags.read_preferences().get('steam:' + other) is None
    # A newer confirmed revocation removes the automatic tag, not the manual one.
    events.insert(0, event(6, sid, False))
    tagged = client.get('/players?limit=30&category=steam_friend').get_json()
    assert tagged['filtered_count'] == 0
    manual = client.get('/players?limit=30&category=friend').get_json()['players']
    assert len(manual) == 1 and manual[0]['categories'] == ['friend']

print('Steam friend detection, persistence, filtering and preferences: OK')
