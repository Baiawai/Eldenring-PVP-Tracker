"""Exercise player pagination without a live tracker or real user data."""
from flask import Flask
from unittest.mock import patch
app = Flask(__name__)
from application import players

entries = []
for n in range(77):
    entries.append({'name': ('Éclaireur' if n == 75 else f'Player {n:03}'), 'total': n,
                    'victories': n % 3, 'defeats': n % 2, 'draws': 0, 'sightings': 0,
                    'roles': ['hunter'] if n == 75 else ['opponent'],
                    'relations': ['ally'] if n == 75 else ['opponent'],
                    'last_seen': f'2026-01-{1+n//24:02} {n%24:02}:00:00', 'history': []})
entries.append({'name':'Éclaireur', 'total':1, 'victories':1, 'defeats':0, 'draws':0, 'sightings':0,
                'roles':['steam'], 'relations':['opponent'], 'last_seen':'2025-01-01 00:00:00', 'history':[],
                'steam': {'id':'76561198000000011', 'name':'Éclaireur', 'mode':'Arena', 'country_code':None}})
client = app.test_client()
with patch.object(players, '_build_players', return_value=(entries, 2)) as build, \
     patch.object(players.steam_avatar_store, 'available', return_value={'76561198000000011'}):
    old = client.get('/players').get_json()
    assert len(old['players']) == 78 and old['unnamed_captures'] == 2
    first = client.get('/players?limit=30&offset=0').get_json()
    assert len(first['players']) == 30 and first['has_more'] and first['count'] == 78
    assert first['filtered_count'] == 78 and first['victories'] == sum(p['victories'] for p in entries)
    assert first['defeats'] == sum(p['defeats'] for p in entries)
    assert first['has_steam'] and first['next_offset'] == 30
    # A stable snapshot does not re-run aggregation when another page is fetched.
    count = build.call_count
    second = client.get('/players', query_string={'limit':30, 'offset':30, 'snapshot':first['snapshot']}).get_json()
    third = client.get('/players', query_string={'limit':30, 'offset':60, 'snapshot':first['snapshot']}).get_json()
    assert build.call_count == count and len(second['players']) == 30 and len(third['players']) == 18 and not third['has_more']
    assert len({p['name'] for p in first['players'] + second['players'] + third['players']}) == 77
    hunter = client.get('/players?limit=30&filter=hunter&q=eclaireur').get_json()
    assert hunter['filtered_count'] == 1 and hunter['players'][0]['name'] == 'Éclaireur' and hunter['count'] == 78
    steam = client.get('/players', query_string={'limit':30, 'q':'éclaireur', 'target_id':'76561198000000011'}).get_json()
    assert steam['exact_match'] and steam['players'][0]['steam']['avatar_available']
    game = client.get('/players', query_string={'limit':30, 'q':'éclaireur', 'target_name':'Éclaireur', 'target_source':'game'}).get_json()
    assert game['exact_match'] and 'steam' not in game['players'][0]
    assert client.get('/players?limit=30&offset=-1').status_code == 400
    assert client.get('/players?limit=30&snapshot=missing').status_code == 409
    # Categories and favourites are stored locally and keep game names and
    # Steam profiles separate, even if they have the same displayed name.
    defaults = client.get('/players/categories').get_json()['categories']
    assert [c['id'] for c in defaults] == ['steam_friend', 'friend', 'rival']
    assert {c['id']:c['color'] for c in defaults} == {'steam_friend':'#3b8db7', 'friend':'#69c37b', 'rival':'#dc6a6a'}
    assert defaults[0]['automatic'] and client.delete('/players/categories/steam_friend').status_code == 403
    assert client.post('/players/preferences', json={'source':'steam','identity':'76561198000000011','categories':['steam_friend'],'favourite':False}).status_code == 400
    created = client.post('/players/categories', json={'name':'Duellistes','color':'#4378AB'}).get_json()['category']
    assert created['name'] == 'Duellistes' and created['color'] == '#4378ab'
    assert client.post('/players/categories', json={'name':'Invalid color','color':'red; background:red'}).status_code == 400
    assert next(c for c in client.get('/players/categories').get_json()['categories'] if c['id'] == created['id'])['color'] == '#4378ab'
    assert client.post('/players/categories', json={'name':'  DUELLISTES  '}).status_code == 400
    assert client.post('/players/categories', json={'name':'  '}).status_code == 400
    assert client.post('/players/preferences', json={'source':'game', 'identity':'Éclaireur', 'category':created['id'], 'favourite':True}).status_code == 200
    assert client.post('/players/preferences', json={'source':'steam', 'identity':'76561198000000011', 'category':'rival', 'favourite':False}).status_code == 200
    counts = client.get('/players/categories').get_json()['counts']
    assert counts == {created['id']:1, 'rival':1}
    assert client.get('/players', query_string={'limit':30, 'snapshot':first['snapshot']}).status_code == 409
    fav = client.get('/players?limit=30&filter=favourite').get_json()
    assert fav['filtered_count'] == 1 and fav['players'][0]['name'] == 'Éclaireur' and not fav['players'][0].get('steam')
    tagged = client.get('/players', query_string={'limit':30, 'category':'rival'}).get_json()
    assert tagged['filtered_count'] == 1 and tagged['players'][0]['steam']['id'] == '76561198000000011'
    assert client.post('/players/preferences', json={'source':'game', 'identity':'Éclaireur', 'category':'missing', 'favourite':True}).status_code == 400
    assert client.post('/players/preferences', json={'source':'steam', 'identity':'bad', 'category':None, 'favourite':True}).status_code == 400
    assert client.post('/players/preferences', json={'source':'game', 'identity':'éclaireur', 'category':'rival', 'favourite':True}).status_code == 200
    assert client.get('/players/categories').get_json()['counts'] == {'rival':2}
    assert client.post('/players/preferences', json={'source':'game', 'identity':'éclaireur', 'category':None, 'favourite':False}).status_code == 200
    assert client.get('/players/categories').get_json()['counts'] == {'rival':1}
    assert client.get('/players?limit=30&filter=favourite').get_json()['filtered_count'] == 0
    from application import player_tags
    assert player_tags.read_preferences()['steam:76561198000000011']['category'] == 'rival'
    import sqlite3
    with sqlite3.connect(player_tags.database_setting) as db:
        raw = db.execute('SELECT identity FROM player_preferences').fetchone()[0]
        assert b'76561198000000011' not in raw
    # Portable data migration must also re-encrypt the new fields.
    import tempfile
    from contextlib import closing
    from pathlib import Path
    from cryptography.fernet import Fernet
    from application import data_protection
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / 'settings.db'
        with closing(sqlite3.connect(player_tags.database_setting)) as source, closing(sqlite3.connect(copy)) as dest:
            source.backup(dest)
        new_key = Fernet.generate_key()
        data_protection._migrate_db(copy, new_key)
        with closing(sqlite3.connect(copy)) as db:
            encrypted_name = db.execute('SELECT name FROM player_categories WHERE id=?', (created['id'],)).fetchone()[0]
            encrypted_identity = db.execute('SELECT identity FROM player_preferences').fetchone()[0]
            assert db.execute('SELECT colour FROM player_category_colours WHERE category_id=?', (created['id'],)).fetchone()[0] == '#4378ab'
        assert Fernet(new_key).decrypt(encrypted_name[3:]).decode() == 'Duellistes'
        assert Fernet(new_key).decrypt(encrypted_identity[3:]).decode() == 'steam:76561198000000011'
    # Deleting a custom category removes only its assignments, never a
    # favourite; cached pages must not retain the removed category.
    assert client.post('/players/preferences', json={'source':'game', 'identity':'Éclaireur', 'category':created['id'], 'favourite':True}).status_code == 200
    assert client.post('/players/preferences', json={'source':'steam', 'identity':'76561198000000011', 'category':created['id'], 'favourite':False}).status_code == 200
    stale = client.get('/players?limit=30').get_json()['snapshot']
    assert client.delete('/players/categories/' + created['id']).status_code == 200
    assert client.get('/players', query_string={'limit':30, 'snapshot':stale}).status_code == 409
    assert player_tags.read_preferences()['game:éclaireur'] == {'category':None, 'categories':[], 'favourite':True}
    assert 'steam:76561198000000011' not in player_tags.read_preferences()
    assert created['id'] not in {item['id'] for item in client.get('/players/categories').get_json()['categories']}
    assert client.delete('/players/categories/' + created['id']).status_code == 404
    # Built-in categories cannot be removed, even by direct API calls, and
    # defaults hidden by an older version become visible again.
    assert client.delete('/players/categories/friend').status_code == 403
    with closing(sqlite3.connect(player_tags.database_setting)) as db, db:
        db.execute("INSERT OR IGNORE INTO player_hidden_categories(id) VALUES('friend')")
    assert {c['id'] for c in player_tags.categories()} == {'steam_friend','friend','rival'}
    # An old Partner assignment stays accessible as a removable legacy tag.
    with closing(sqlite3.connect(player_tags.database_setting)) as db, db:
        pref_id = db.execute('SELECT id FROM player_preferences').fetchone()[0]
        db.execute("UPDATE player_preferences SET category='partner' WHERE id=?", (pref_id,))
        db.execute("INSERT INTO player_preference_categories(preference_id,category) VALUES(?,'partner')", (pref_id,))
    assert player_tags.read_preferences()['game:éclaireur'] == {'category':'partner', 'categories':['partner'], 'favourite':True}
    assert {c['id'] for c in player_tags.categories()} == {'steam_friend','friend','rival','partner'}
    # A category created by an older version has no colour record.
    from application.secur import encrypt_value
    with closing(sqlite3.connect(player_tags.database_setting)) as db, db:
        db.execute('INSERT INTO player_categories(id,name) VALUES(?,?)', ('legacy', encrypt_value('Ancienne')))
    assert next(c for c in player_tags.categories() if c['id']=='legacy')['color'] == player_tags.CUSTOM_COLOUR
    # Multi-category saves, counts and filters work across all pages. The old
    # single-category data remains readable, and a legacy favourite toggle does
    # not erase extra categories.
    assert client.post('/players/preferences', json={'source':'game','identity':'Éclaireur','categories':['partner','friend','legacy'],'favourite':True}).status_code == 200
    assert player_tags.read_preferences()['game:éclaireur'] == {'category':'partner','categories':['partner','friend','legacy'],'favourite':True}
    assert client.get('/players/categories').get_json()['counts'] == {'partner':1, 'friend':1, 'legacy':1}
    assert client.get('/players?limit=30&category=friend').get_json()['filtered_count'] == 1
    assert client.get('/players?limit=30&category=legacy').get_json()['filtered_count'] == 1
    ordinary = client.get('/players?limit=30&q=eclaireur').get_json()['snapshot']
    tagged = client.get('/players?limit=30&category=friend').get_json()['snapshot']
    favourites = client.get('/players?limit=30&filter=favourite').get_json()['snapshot']
    assert client.post('/players/preferences', json={'source':'game','identity':'Éclaireur','category':'partner','favourite':False}).status_code == 200
    assert player_tags.read_preferences()['game:éclaireur']['categories'] == ['partner','friend','legacy']
    ordinary_result = client.get('/players', query_string={'limit':30,'snapshot':ordinary})
    assert ordinary_result.status_code == 200
    assert next(p for p in ordinary_result.get_json()['players'] if not p.get('steam'))['favourite'] is False
    assert client.get('/players', query_string={'limit':30,'snapshot':tagged}).status_code == 200
    assert client.get('/players', query_string={'limit':30,'snapshot':favourites}).status_code == 409
    assert client.post('/players/preferences', json={'source':'game','identity':'Éclaireur','categories':['partner','missing'],'favourite':True}).status_code == 400
    ordinary = client.get('/players?limit=30&q=eclaireur').get_json()['snapshot']
    tagged = client.get('/players?limit=30&category=friend').get_json()['snapshot']
    removed_tag = client.get('/players?limit=30&category=legacy').get_json()['snapshot']
    assert client.post('/players/preferences', json={'source':'game','identity':'Éclaireur','categories':['partner','friend'],'favourite':False}).status_code == 200
    ordinary_result = client.get('/players', query_string={'limit':30,'snapshot':ordinary})
    assert ordinary_result.status_code == 200
    assert next(p for p in ordinary_result.get_json()['players'] if not p.get('steam'))['categories'] == ['partner','friend']
    assert client.get('/players', query_string={'limit':30,'snapshot':tagged}).status_code == 200
    assert client.get('/players', query_string={'limit':30,'snapshot':removed_tag}).status_code == 409
    assert client.post('/players/preferences', json={'source':'game','identity':'Éclaireur','categories':['partner','friend','legacy'],'favourite':False}).status_code == 200
    assert client.delete('/players/categories/legacy').status_code == 200
    assert player_tags.read_preferences()['game:éclaireur'] == {'category':'partner','categories':['partner','friend'],'favourite':False}
    assert client.get('/players/categories').get_json()['counts'] == {'partner':1,'friend':1}
    assert client.post('/players/preferences', json={'source':'game','identity':'Éclaireur','categories':[],'favourite':True}).status_code == 200
    assert player_tags.read_preferences()['game:éclaireur'] == {'category':None,'categories':[],'favourite':True}
    # A row from the old single-category schema is readable without an
    # eager migration, and becomes multi-category when the user updates it.
    with closing(sqlite3.connect(player_tags.database_setting)) as db, db:
        db.execute('INSERT INTO player_preferences(identity,category,favourite) VALUES(?,?,?)', (encrypt_value('game:olduser'), 'partner', 1))
    assert player_tags.read_preferences()['game:olduser'] == {'category':'partner','categories':['partner'],'favourite':True}
    assert client.post('/players/preferences', json={'source':'game','identity':'OldUser','categories':['friend','partner'],'favourite':True}).status_code == 200
    assert player_tags.read_preferences()['game:olduser']['categories'] == ['friend','partner']
    another = client.post('/players/categories', json={'name':'Autre','color':'#4378ab'}).get_json()['category']['id']
    assert client.post('/players/preferences', json={'source':'game','identity':'OldUser','categories':[another,'friend'],'favourite':True}).status_code == 200
    assert client.delete('/players/categories/'+another).status_code == 200
    assert player_tags.read_preferences()['game:olduser'] == {'category':'friend','categories':['friend'],'favourite':True}
print('Player pagination, global filters, metrics and direct navigation: OK')
