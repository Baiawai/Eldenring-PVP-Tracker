"""Browser exercise using synthetic player and category data only."""
import re
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
html = re.sub(r'<script\b[^>]*>.*?</script>', '', (ROOT/'templates/index.html').read_text(encoding='utf-8'), flags=re.S|re.I)
sid = '76561198000000001'
player = {'name':'Synthetic', 'total':0, 'victories':0, 'defeats':0, 'draws':0, 'sightings':0,
          'roles':['steam'], 'relations':[], 'last_seen':'2026-01-01', 'history':[],
          'steam':{'id':sid, 'name':'Synthetic'}, 'steam_friend':True,
          'categories':['steam_friend'], 'favourite':False}
categories = [{'id':'steam_friend','builtin':True,'automatic':True,'color':'#3b8db7'},
              {'id':'friend','builtin':True,'automatic':False,'color':'#69c37b'},
              {'id':'rival','builtin':True,'automatic':False,'color':'#dc6a6a'}]
posts = []

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True, executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe')
    page = browser.new_page(viewport={'width':1200, 'height':800})
    def serve(route):
        path = urlparse(route.request.url).path
        if path == '/':
            route.fulfill(content_type='text/html', body=html)
        elif path == '/players/categories':
            route.fulfill(json={'categories':categories,'counts':{'steam_friend':1},'multi_category':True})
        elif path == '/players/preferences':
            payload = route.request.post_data_json
            posts.append(payload)
            assert payload['source'] == 'steam' and payload['identity'] == sid
            assert 'steam_friend' not in payload['categories']
            player['categories'] = ['steam_friend'] + payload['categories']
            player['favourite'] = payload['favourite']
            route.fulfill(json={'request':'success'})
        elif path == '/players':
            route.fulfill(json={'players':[player],'snapshot':'synthetic','next_offset':1,'has_more':False,
                                'filtered_count':1,'count':1,'victories':0,'defeats':0,'unnamed_captures':0,
                                'exact_match':False,'has_summoning':False,'has_steam':True})
        else:
            route.abort()
    page.route('**/*', serve)
    page.goto('http://tracker.test/')
    page.locator('.sprit').evaluate_all('(nodes) => nodes.forEach(node => node.remove())')
    page.locator('#profile_sidebar').evaluate('(node) => { node.style.display = "none"; }')
    for style in ('style.css','selects.css','players.css','app-typography.css'):
        page.add_style_tag(path=str(ROOT/'static'/style))
    page.add_script_tag(path=str(ROOT/'static/jquery.js'))
    page.evaluate("document.documentElement.lang='fr'; window.uiSetStatus = () => {}; window.appendIpCountry = () => {}")
    page.add_script_tag(path=str(ROOT/'static/players.js'))
    page.locator('#menu_button_players').evaluate('(el) => el.click()')
    page.wait_for_selector('#players_list .player-card')
    def check_category_position():
        assert page.locator('.player-category-tools').evaluate('''element => {
            const filters = document.querySelector('.players-controls').getBoundingClientRect();
            const tools = element.getBoundingClientRect();
            const heading = document.querySelector('#players_panel .players-list-heading').getBoundingClientRect();
            return tools.top >= filters.bottom && heading.top >= tools.bottom;
        }''')
    check_category_position()
    page.set_viewport_size({'width':600, 'height':800})
    check_category_position()
    page.set_viewport_size({'width':1200, 'height':800})
    assert page.locator('.player-category-tag').first.get_attribute('data-category-id') == 'steam_friend'
    assert page.locator('.player-category-tag').first.evaluate('(e) => getComputedStyle(e).color') == 'rgb(77, 153, 194)'
    card = page.locator('#players_list .player-card').first
    assert card.locator('.player-custom-category').all_text_contents() == ['Ami Steam']
    assert card.locator('.player-custom-category').first.evaluate('(e) => getComputedStyle(e).borderTopColor') == 'rgb(59, 141, 183)'
    card.locator('summary').first.click()
    card.locator('.player-category-trigger').click()
    assert card.locator('.player-category-option input[value=steam_friend]').count() == 0
    card.locator('.player-category-option:has(input[value=friend])').click()
    page.wait_for_function("document.querySelectorAll('#players_list .player-custom-category').length === 2")
    assert posts[-1]['categories'] == ['friend']
    card.locator('.player-favourite').click()
    page.wait_for_function("document.querySelector('#players_list .player-favourite').getAttribute('aria-pressed') === 'true'")
    assert posts[-1]['categories'] == ['friend'] and posts[-1]['favourite']
    assert card.locator('.player-custom-category').all_text_contents() == ['Ami Steam','Ami']
    browser.close()
print('Steam friend automatic tag browser UI: OK')
