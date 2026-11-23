"""Exercise lazy pages in Chromium with synthetic data, never personal files."""
from pathlib import Path
import re
from urllib.parse import urlparse, parse_qs
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
html = re.sub(r'<script\b[^>]*>.*?</script>', '', (ROOT/'templates/index.html').read_text(encoding='utf-8'), flags=re.S|re.I)
players = [{'name':f'Player {i:03}', 'total':1, 'victories':i%2, 'defeats':1-i%2, 'draws':0, 'sightings':0, 'roles':['opponent'], 'relations':['opponent'], 'last_seen':f'2026-01-01 12:{59-i//60:02}:{59-i%60:02}', 'history':[]} for i in range(75)]
events = [{'id':i, 'date':'2026-01-01 12:00:00', 'mode':'Arena' if i%2 else 'Defense', 'kind':'detection', 'message':f'Event {i}', 'metadata':None} for i in range(90,0,-1)]
player_calls=[]
history_calls=[]
fail_older=[]
legacy_mode=[]
old_category_api=[]
category_posts=[]
preference_posts=[]
preference_fail=[]
categories=[{'id':'friend','builtin':True,'color':'#69c37b'}, {'id':'rival','builtin':True,'color':'#dc6a6a'}, {'id':'partner','builtin':True,'color':'#d4af37'}]
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True, executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe')
    page=browser.new_page(viewport={'width':1200,'height':800})
    def serve(route):
        u=urlparse(route.request.url); q=parse_qs(u.query)
        if u.path=='/': route.fulfill(content_type='text/html',body=html); return
        if u.path=='/players/categories':
            if route.request.method == 'POST':
                category_posts.append(route.request.post_data_json)
                category={'id':'custom1','name':route.request.post_data_json['name'],'builtin':False,'color':route.request.post_data_json['color']}
                categories.append(category); route.fulfill(json={'category':category},status=201)
            else:
                counts={}
                for player in players:
                    for category in player.get('categories', [player['category']] if player.get('category') else []):
                        counts[category]=counts.get(category,0)+1
                payload=[{k:v for k,v in c.items() if k != 'color'} for c in categories] if old_category_api else categories
                route.fulfill(json={'categories':payload,'counts':counts,'multi_category':not bool(old_category_api)})
            return
        if u.path.startswith('/players/categories/') and route.request.method == 'DELETE':
            removed=u.path.rsplit('/',1)[-1]
            categories[:]=[category for category in categories if category['id'] != removed]
            for player in players:
                values=player.get('categories', [player['category']] if player.get('category') else [])
                player['categories']=[value for value in values if value != removed]
                player['category']=player['categories'][0] if player['categories'] else None
            route.fulfill(json={'request':'success'}); return
        if u.path=='/players/preferences':
            payload=route.request.post_data_json
            preference_posts.append(payload)
            if preference_fail:
                preference_fail.pop(); route.fulfill(status=503,body='error'); return
            player=next(x for x in players if x['name']==payload['identity'])
            player['categories']=payload.get('categories', [payload['category']] if payload.get('category') else [])
            player['category']=player['categories'][0] if player['categories'] else None
            player['favourite']=payload['favourite']
            route.fulfill(json={'request':'success'}); return
        if u.path=='/players':
            player_calls.append(q)
            if legacy_mode:
                route.fulfill(json={'request':'success', 'players':players, 'unnamed_captures':0}); return
            selected=list(players)
            query=q.get('q',[''])[0].casefold()
            selected=[x for x in selected if query in x['name'].casefold()]
            filt=q.get('filter',['all'])[0]
            if filt=='victory': selected=[x for x in selected if x['victories']]
            if filt=='defeat': selected=[x for x in selected if x['defeats']]
            if filt=='favourite': selected=[x for x in selected if x.get('favourite')]
            category=q.get('category',[''])[0]
            if category: selected=[x for x in selected if category in x.get('categories', [x['category']] if x.get('category') else [])]
            sort=q.get('sort',['recent'])[0]
            if sort=='name': selected.sort(key=lambda x:x['name'].casefold())
            else: selected.sort(key=lambda x:x['last_seen'],reverse=True)
            target=q.get('target_name',[''])[0]
            offset=int(q.get('offset',['0'])[0]); limit=int(q.get('limit',['30'])[0])
            if target:
                found=next((i for i,x in enumerate(selected) if x['name']==target),None)
                if found is not None: offset=(found//limit)*limit
            subset=selected[offset:offset+limit]
            route.fulfill(json={'request':'success','players':subset,'snapshot':'synthetic','next_offset':offset+len(subset),'has_more':offset+len(subset)<len(selected),'filtered_count':len(selected),'count':len(players),'victories':sum(x['victories'] for x in players),'defeats':sum(x['defeats'] for x in players),'unnamed_captures':0,'exact_match':bool(target and len(selected)==1),'has_summoning':False,'has_steam':False}); return
        if u.path=='/detection-history':
            history_calls.append(q)
            if q.get('before') and fail_older:
                fail_older.pop(); route.fulfill(status=503, body='error'); return
            before=int(q.get('before',['0'])[0]); mode=q.get('mode',['all'])[0]
            subset=[x for x in events if (not before or x['id']<before) and (mode=='all' or x['mode']==mode)]
            route.fulfill(json={'request':'success','events':subset[:30],'has_more':len(subset)>30}); return
        if u.path=='/history-storage': route.fulfill(json={'request':'success','history':{'bytes':0,'estimated':False,'events':90},'archives':[{'id':1,'created_at':'2026-01-01 00:00:00','events':3,'bytes':100}],'monitor_running':False}); return
        if u.path.startswith('/players/steam-avatar/'): route.fulfill(status=404,body=''); return
        route.abort()
    page.route('**/*',serve)
    page.goto('http://tracker.test/')
    page.locator('.sprit').evaluate_all('(nodes) => nodes.forEach(node => node.remove())')
    # The standalone fixture omits app.js, which normally initializes the sidebar.
    page.locator('#profile_sidebar').evaluate('(node) => { node.style.display = "none"; }')
    for name in ('style.css','selects.css','players.css','history.css','stats-page.css','app-typography.css'):
        page.add_style_tag(path=str(ROOT/'static'/name))
    page.add_script_tag(path=str(ROOT/'static/jquery.js'))
    page.evaluate("document.documentElement.lang='fr'; window.uiSetStatus = () => {}; window.appendIpCountry = () => {}")
    page.add_script_tag(path=str(ROOT/'static/players.js'))
    page.add_script_tag(path=str(ROOT/'static/history.js'))
    page.locator('#menu_button_players').evaluate('(el) => el.click()')
    page.wait_for_function("document.querySelectorAll('#players_list .player-card').length === 30")
    assert page.locator('#players_count').inner_text()=='75', (page.locator('#players_count').inner_text(), player_calls)
    assert len(player_calls)==1 and player_calls[0].get('limit')==['30']
    assert page.locator('.player-category-remove[data-category-id=friend], .player-category-remove[data-category-id=rival], .player-category-remove[data-category-id=partner]').count() == 0
    for ident, color, rendered in [('friend','#69c37b','rgb(105, 195, 123)'),('rival','#dc6a6a','rgb(220, 106, 106)'),('partner','#d4af37','rgb(212, 175, 55)')]:
        assert page.locator(f'.player-category-tag[data-category-id={ident}]').locator('..').evaluate('(el) => el.style.getPropertyValue("--category-colour")') == color
        assert page.locator(f'.player-category-tag[data-category-id={ident}]').locator('..').evaluate('(el) => getComputedStyle(el).borderTopColor') == rendered
    assert page.locator('.player-category-count').first.evaluate('(el) => getComputedStyle(el).borderTopWidth') == '0px'
    # Create a personal category and assign it to a player, independently of
    # marking that same player as favourite; both filters use the full list.
    page.locator('.player-category-toggle').click()
    page.locator('.player-category-form input[type=text]').fill('Duellistes')
    page.locator('.player-category-form input[type=color]').fill('#4378ab')
    page.locator('.player-category-form button[type=submit]').click()
    page.wait_for_function("Array.from(document.querySelectorAll('.players-category-filter option')).some(o => o.value === 'custom1')")
    assert page.locator('.player-category-tag[data-category-id=custom1]').inner_text().splitlines() == ['Duellistes', '0']
    assert page.locator('.player-category-tag[data-category-id=custom1]').locator('..').evaluate('(el) => el.style.getPropertyValue("--category-colour")') == '#4378ab'
    page.wait_for_function("document.querySelectorAll('#players_list .player-card').length === 30")
    card=page.locator('#players_list .player-card').first
    player_name=card.locator('.player-name').inner_text()
    assert card.locator('.player-favourite img').get_attribute('src') == '/static/icon-favourite-bronze.svg'
    assert card.locator('.player-favourite').get_attribute('aria-pressed') == 'false'
    assert card.locator('.player-favourite').evaluate('(e) => { const s=getComputedStyle(e), i=e.getBoundingClientRect(), a=e.parentElement.querySelector(".player-emblem").getBoundingClientRect(); return s.position === "absolute" && s.borderTopWidth === "0px" && s.backgroundImage === "none" && i.right <= a.left && Math.abs((i.top+i.bottom-a.top-a.bottom)/2) < 1; }')
    assert 'grayscale(1)' in card.locator('.player-favourite img').evaluate('(e) => getComputedStyle(e).filter')
    card.locator('summary').first.click()
    card.locator('.player-category-trigger').click()
    assert card.locator('.player-category-options').is_visible()
    assert card.locator('.player-categories-save').count() == 0
    assert card.locator('.player-category-option input[value=friend]').evaluate('(e) => getComputedStyle(e).width') == '1px'
    before_category_requests=len(player_calls)
    page.evaluate("window.originalCategoryCard = document.querySelector('#players_list .player-card')")
    # Keep the first save pending while the next option is selected. The UI
    # must serialize both choices without closing the menu or losing a tag.
    page.evaluate('''() => {
        const original = window.fetch.bind(window); let hold = true;
        window.fetch = (url, options) => {
            if (url === '/players/preferences' && hold) {
                hold = false;
                return new Promise(resolve => { window.releaseFirstCategorySave = () => resolve(original(url, options)); });
            }
            return original(url, options);
        };
    }''')
    previous_saves=len(preference_posts)
    card.locator('.player-category-option:has(input[value=friend])').click()
    card.locator('.player-category-option:has(input[value=custom1])').click()
    assert 'Ami' in card.locator('.player-category-trigger').inner_text()
    assert 'Duellistes' in card.locator('.player-category-trigger').inner_text()
    assert len(preference_posts) == previous_saves
    page.evaluate('window.releaseFirstCategorySave()')
    page.wait_for_function("document.querySelectorAll('#players_list .player-card:first-child .player-custom-category').length === 2")
    assert len(player_calls) == before_category_requests
    assert page.evaluate("window.originalCategoryCard === document.querySelector('#players_list .player-card')")
    assert card.locator('.player-category-multiselect').get_attribute('open') is not None
    assert [item['categories'] for item in preference_posts[previous_saves:]] == [['friend'], ['friend','custom1']]
    # A failed immediate save restores the last saved selection.
    preference_fail.append(True)
    card.locator('.player-category-option:has(input[value=partner])').click()
    page.wait_for_function("document.querySelector('#players_list .player-card:first-child .player-category-status')?.textContent.length > 0")
    assert not card.locator('.player-category-option input[value=partner]').is_checked()
    assert set(page.locator('#players_list .player-card').first.locator('.player-custom-category').all_text_contents()) == {'Ami','Duellistes'}
    assert set(page.locator('#players_list .player-card').first.locator('.player-custom-category').all_text_contents()) == {'Ami','Duellistes'}
    custom_badge = page.locator('#players_list .player-custom-category').filter(has_text='Duellistes').first
    assert custom_badge.evaluate('(el) => el.style.getPropertyValue("--category-colour")') == '#4378ab'
    assert custom_badge.evaluate('(el) => getComputedStyle(el).borderTopColor') == 'rgb(67, 120, 171)'
    page.wait_for_function("document.querySelector('.player-category-tag[data-category-id=custom1] .player-category-count')?.textContent === '1'")
    before_favourite_requests=len(player_calls)
    page.evaluate("window.originalFavouriteCard = document.querySelector('#players_list .player-card')")
    page.locator('#players_list .player-card').first.locator('.player-favourite').click()
    page.wait_for_function("document.querySelector('#players_list .player-favourite')?.getAttribute('aria-pressed') === 'true'")
    page.wait_for_timeout(600)
    assert page.evaluate("window.originalFavouriteCard === document.querySelector('#players_list .player-card')")
    assert len(player_calls) == before_favourite_requests
    assert page.locator('#players_list .player-card').first.locator('.player-favourite img').evaluate('(e) => getComputedStyle(e).filter') == 'none'
    page.locator('#players_list .player-favourite').first.click()
    page.wait_for_function("document.querySelector('#players_list .player-favourite')?.getAttribute('aria-pressed') === 'false'")
    page.wait_for_timeout(600)
    assert len(player_calls) == before_favourite_requests
    assert page.evaluate("window.originalFavouriteCard === document.querySelector('#players_list .player-card')")
    page.locator('#players_list .player-favourite').first.click()
    page.wait_for_function("document.querySelector('#players_list .player-favourite')?.getAttribute('aria-pressed') === 'true'")
    page.locator('.players-category-filter select').select_option('custom1')
    page.wait_for_function("document.querySelectorAll('#players_list .player-card').length === 1")
    assert page.locator('#players_list .player-name').inner_text()==player_name
    assert page.locator('.player-category-tag[data-category-id=custom1] .player-category-count').inner_text() == '1'
    page.locator('.players-category-filter select').select_option('')
    page.locator('.player-category-tag[data-category-id=custom1]').click()
    page.wait_for_function("document.querySelectorAll('#players_list .player-card').length === 1 && document.querySelector('.player-category-tag[data-category-id=custom1]').getAttribute('aria-pressed') === 'true'")
    page.locator('.player-category-tag[data-category-id=custom1]').click()
    page.wait_for_function("document.querySelectorAll('#players_list .player-card').length === 30")
    page.locator('.players-filter[data-filter=favourite]').click()
    page.wait_for_function("document.querySelectorAll('#players_list .player-card').length === 1")
    assert page.locator('#players_list .player-name').inner_text()==player_name
    before_favourite_requests=len(player_calls)
    page.locator('#players_list .player-favourite').click()
    page.wait_for_function("document.querySelectorAll('#players_list .player-card').length === 0")
    assert len(player_calls) > before_favourite_requests
    page.locator('.players-filter[data-filter=all]').click()
    page.wait_for_function("document.querySelectorAll('#players_list .player-card').length === 30")
    page.locator('#players_list .player-favourite').first.click()
    page.wait_for_function("document.querySelector('#players_list .player-favourite')?.getAttribute('aria-pressed') === 'true'")
    # Cancel, then confirm deletion while the category filter is active.
    page.locator('.player-category-tag[data-category-id=custom1]').click()
    page.wait_for_function("document.querySelectorAll('#players_list .player-card').length === 1")
    page.once('dialog', lambda dialog: dialog.dismiss())
    page.locator('.player-category-remove[data-category-id=custom1]').click()
    assert page.locator('.player-category-tag[data-category-id=custom1]').count() == 1
    page.once('dialog', lambda dialog: dialog.accept())
    page.locator('.player-category-remove[data-category-id=custom1]').click()
    page.wait_for_function("!document.querySelector('.player-category-tag[data-category-id=custom1]') && document.querySelectorAll('#players_list .player-card').length === 30")
    assert page.locator('.players-category-filter select').input_value() == ''
    page.locator('.players-filter[data-filter=favourite]').click()
    page.wait_for_function("document.querySelectorAll('#players_list .player-card').length === 1")
    assert page.locator('#players_list .player-name').inner_text() == player_name
    assert page.locator('#players_list .player-custom-category').all_text_contents() == ['Ami']
    page.locator('.players-filter[data-filter=all]').click()
    page.wait_for_function("document.querySelectorAll('#players_list .player-card').length === 30")
    page.locator('.players-list-scroll').evaluate('(e) => e.scrollTop = e.scrollHeight')
    page.wait_for_function("document.querySelectorAll('#players_list .player-card').length === 60")
    assert player_calls[-1].get('offset')==['30']
    page.locator('.players-list-scroll').evaluate('(e) => e.scrollTop = e.scrollHeight')
    page.wait_for_function("document.querySelectorAll('#players_list .player-card').length === 75")
    names=page.locator('#players_list .player-name').all_text_contents()
    assert len(set(names))==75
    # Background encounter updates rebuild the snapshot. Preserve loaded pages,
    # the open card and scroll position rather than jumping back to the top.
    page.locator('.players-filter[data-filter="opponent"]').evaluate('(e) => e.click()')
    page.wait_for_function("document.querySelectorAll('#players_list .player-card').length === 30")
    page.locator('.players-list-scroll').evaluate('(e) => e.scrollTop = e.scrollHeight')
    page.wait_for_function("document.querySelectorAll('#players_list .player-card').length >= 60")
    page.locator('#players_list .player-card').nth(45).evaluate('(e) => e.open = true')
    opened_name=page.locator('#players_list .player-card').nth(45).locator('.player-name').inner_text()
    page.locator('.players-list-scroll').evaluate('(e) => e.scrollTop = e.scrollHeight')
    page.wait_for_function("document.querySelectorAll('#players_list .player-card').length === 75")
    page.locator('.players-list-scroll').evaluate('(e) => e.scrollTop = e.scrollHeight')
    position=page.locator('.players-list-scroll').evaluate('(e) => e.scrollTop')
    previous_calls=len(player_calls)
    page.evaluate("$(document).trigger('ajaxSuccess', [{}, {url:'/capture'}])")
    page.wait_for_timeout(500)
    page.wait_for_function("document.querySelectorAll('#players_list .player-card').length === 75 && document.querySelectorAll('#players_list .player-card[open]').length === 1", timeout=12000)
    assert len(player_calls) >= previous_calls+3
    assert player_calls[previous_calls].get('filter')==['opponent']
    assert [q.get('offset') for q in player_calls[previous_calls:previous_calls+3]] == [['0'],['30'],['60']]
    assert all(q.get('limit')==['30'] for q in player_calls[previous_calls:previous_calls+3])
    assert page.locator('#players_list .player-card[open] .player-name').inner_text()==opened_name
    assert abs(page.locator('.players-list-scroll').evaluate('(e) => e.scrollTop')-position) <= 2
    assert page.locator('#players_count').inner_text()=='75'
    page.locator('#players_search').fill('Player 074')
    page.wait_for_function("document.querySelectorAll('#players_list .player-card').length === 1")
    assert page.locator('#players_list .player-name').inner_text()=='Player 074'
    page.locator('#players_search').fill('')
    page.locator('.players-filter[data-filter="victory"]').evaluate('(e) => e.click()')
    page.wait_for_function("document.querySelectorAll('#players_list .player-card').length === 30")
    assert page.locator('#players_count').inner_text()=='75', (page.locator('#players_count').inner_text(), player_calls)
    page.evaluate("window.openEncounteredPlayer('Player 074','game','')")
    page.wait_for_function("document.querySelector('#players_list details[open] .player-name')?.textContent === 'Player 074'")
    # A still-running older backend returns all players at once. Render those
    # locally in the same batches until the backend is restarted.
    legacy_mode.append(True)
    page.locator('#players_search').fill('')
    page.wait_for_function("document.querySelectorAll('#players_list .player-card').length === 30")
    legacy_calls = len(player_calls)
    assert page.locator('.players-list-scroll').evaluate('(e) => e.scrollHeight > e.clientHeight')
    page.locator('.players-list-scroll').evaluate('(e) => e.scrollTop = e.scrollHeight')
    page.wait_for_function("document.querySelectorAll('#players_list .player-card').length === 60")
    page.locator('.players-list-scroll').evaluate('(e) => e.scrollTop = e.scrollHeight')
    page.wait_for_function("document.querySelectorAll('#players_list .player-card').length === 75")
    assert len(player_calls) == legacy_calls
    page.locator('#players_list .player-card').nth(45).evaluate('(e) => e.open = true')
    legacy_open = page.locator('#players_list .player-card').nth(45).locator('.player-name').inner_text()
    page.locator('.players-list-scroll').evaluate('(e) => e.scrollTop = e.scrollHeight')
    legacy_position = page.locator('.players-list-scroll').evaluate('(e) => e.scrollTop')
    page.evaluate("$(document).trigger('ajaxSuccess', [{}, {url:'/capture'}])")
    page.wait_for_timeout(500)
    page.wait_for_function("document.querySelectorAll('#players_list .player-card').length === 75 && document.querySelectorAll('#players_list .player-card[open]').length === 1", timeout=12000)
    assert page.locator('#players_list .player-card[open] .player-name').inner_text() == legacy_open
    assert abs(page.locator('.players-list-scroll').evaluate('(e) => e.scrollTop') - legacy_position) <= 2
    assert len(player_calls) == legacy_calls + 1
    page.evaluate("window.openEncounteredPlayer('Player 074','game','')")
    page.wait_for_function("document.querySelector('#players_list details[open] .player-name')?.textContent === 'Player 074'")
    legacy_mode.clear()
    page.locator('#menu_button_history').evaluate('(el) => el.click()')
    page.wait_for_function("document.querySelectorAll('#history_list .history-entry').length === 30")
    page.locator('#history_list').evaluate('(e) => { e.scrollTop = e.scrollHeight; }')
    page.wait_for_function("document.querySelectorAll('#history_list .history-entry').length >= 60")
    assert any(x.get('before')==['61'] for x in history_calls)
    before_top=page.locator('#history_list').evaluate('(e) => e.scrollTop')
    for i in range(125,90,-1):
        events.insert(125-i, {'id':i, 'date':'2026-01-01 12:00:00', 'mode':'Arena', 'kind':'detection', 'message':f'Event {i}', 'metadata':None})
    page.wait_for_function("document.querySelectorAll('#history_list .history-entry').length === 95", timeout=12000)
    ids=page.locator('#history_list .history-entry').evaluate_all('(xs) => xs.map(x => x.dataset.historyId)')
    assert len(ids)==len(set(ids))==95 and ids[0]=='125' and ids[-1]=='31'
    assert page.locator('#history_list').evaluate('(e) => e.scrollTop') > before_top
    page.locator('#history_mode').select_option('Defense')
    page.wait_for_function("document.querySelectorAll('#history_list .history-entry').length === 30")
    assert page.locator('#history_list .history-entry').count()==30
    fail_older.append(True)
    page.locator('#history_list').evaluate('(e) => { e.scrollTop = e.scrollHeight; }')
    page.wait_for_timeout(300)
    assert not fail_older and page.locator('#history_list .history-entry').count()==30
    page.locator('#history_more').evaluate('(e) => e.click()')
    page.wait_for_function("document.querySelectorAll('#history_list .history-entry').length === 45")
    page.evaluate("window.lazyTestFirstHistoryCard = document.querySelector('#history_list .history-entry')")
    refresh_calls = len(history_calls)
    page.wait_for_timeout(5500)
    assert len(history_calls) > refresh_calls
    assert page.evaluate("window.lazyTestFirstHistoryCard === document.querySelector('#history_list .history-entry')")
    assert page.locator('.settings-panel #history_archives_list').count() == 1
    # Category controls remain usable at a narrow viewport.
    page.set_viewport_size({'width':390, 'height':844})
    page.locator('#menu_button_players').evaluate('(e) => e.click()')
    page.wait_for_function("document.querySelectorAll('#players_list .player-card').length > 0")
    assert page.locator('#players_list .player-favourite').first.evaluate('(e) => { const i=e.getBoundingClientRect(), a=e.parentElement.querySelector(".player-emblem").getBoundingClientRect(); return Math.abs((i.top+i.bottom-a.top-a.bottom)/2) < 1 && i.right <= a.left; }')
    page.locator('.player-category-toggle').click()
    assert page.locator('.player-category-form input[type=text]').is_visible()
    assert page.locator('.player-category-form input[type=color]').is_visible()
    assert page.locator('#players_panel').evaluate('(e) => e.scrollWidth <= e.clientWidth + 1')
    # An older running backend does not persist the chosen colour. Prevent a
    # misleading successful creation until the tracker is restarted.
    old_category_api.append(True)
    page.locator('#menu_button_players').evaluate('(e) => e.click()')
    with page.expect_response('**/players/categories'):
        page.locator('#menu_button_players').evaluate('(e) => e.click()')
    page.wait_for_function("document.querySelectorAll('#players_list .player-card').length > 0")
    page.locator('#players_list .player-card').first.locator('summary').first.evaluate('(e) => { e.parentElement.open = true; }')
    assert page.locator('#players_list .player-card').first.locator('.player-category-trigger').get_attribute('aria-disabled') == 'true'
    page.locator('.player-category-form input[type=text]').fill('Nouvelle')
    previous_posts=len(category_posts)
    page.locator('.player-category-form button[type=submit]').click()
    assert 'tracker' in page.locator('.player-category-tools > .player-category-status').inner_text().lower()
    assert len(category_posts)==previous_posts
    browser.close()
print('Lazy player and history pages: paging, filters, navigation, counts and archives OK.')
