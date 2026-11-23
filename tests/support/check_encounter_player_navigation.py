"""Exercise home and history navigation with synthetic player records only."""
from pathlib import Path
import os
import re
from urllib.parse import parse_qs
from playwright.sync_api import sync_playwright
ROOT = Path(__file__).resolve().parents[2]
html = (ROOT / 'templates/index.html').read_text(encoding='utf-8')
html = re.sub(r'<script\b[^>]*>.*?</script>', '', html, flags=re.S | re.I)
players = [
 {'name':'Same Name','total':1,'victories':1,'defeats':0,'draws':0,'sightings':0,'roles':['opponent'],'relations':['opponent'],'last_seen':'2026-01-01 12:00:00','history':[]},
 {'name':'Same Name','total':1,'victories':1,'defeats':0,'draws':0,'sightings':0,'roles':['steam'],'relations':['opponent'],'last_seen':'2026-01-01 12:00:00','history':[], 'steam':{'id':'76561198000000011','name':'Same Name','mode':'Arena','avatar_available':True}},
 {'name':'Missing Avatar','total':0,'victories':0,'defeats':0,'draws':0,'sightings':0,'roles':['steam'],'relations':[],'last_seen':'2026-01-01 10:00:00','history':[], 'steam':{'id':'76561198000000012','name':'Missing Avatar','mode':'Unknown','avatar_available':True}},
 {'name':'Queued Avatar','total':0,'victories':0,'defeats':0,'draws':0,'sightings':0,'roles':['steam'],'relations':[],'last_seen':'2026-01-01 09:00:00','history':[], 'steam':{'id':'76561198000000013','name':'Queued Avatar','mode':'Unknown','avatar_available':False}},
 {'name':'Other','total':0,'victories':0,'defeats':0,'draws':0,'sightings':1,'roles':['hunter'],'relations':['ally'],'last_seen':'2026-01-01 12:00:00','history':[]},
]
events = [
 {'id':1,'date':'2026-01-01 12:00:00','mode':'Arena','kind':'detection','message':'Vous avez perdu contre Same Name.\nTime: 17 s','metadata':{'opponent':'Same Name','opponent_source':'game'}},
 {'id':2,'date':'2026-01-01 11:00:00','mode':'Arena','kind':'steam_encounter','message':'Joueur Steam rencontré : Same Name','metadata':{'name':'Same Name','id':'76561198000000011'}},
 {'id':3,'date':'2026-01-01 10:00:00','mode':'Arena','kind':'detection','message':'Vous remportez la victoire contre Other !\nTime: 7 s','metadata':None},
 {'id':4,'date':'2026-01-01 09:00:00','mode':'Arena','kind':'detection','message':'Le combat s’achève par une égalité avec Other.\nTime: 7 s','metadata':None},
]
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True,executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe')
 page=browser.new_page()
 avatar_requests=[]
 def serve(route):
  path=route.request.url.split('?',1)[0]
  if path.endswith('/players/steam-avatar/76561198000000011'): route.fulfill(content_type='image/png',body=(ROOT/'static/icon-edit-profile-bronze.png').read_bytes())
  elif path.endswith('/players/steam-avatar/request'):
   sid=parse_qs(route.request.post_data or '').get('steam_id',[''])[0]
   avatar_requests.append(sid)
   route.fulfill(json={'state':'queued' if sid=='76561198000000013' else 'unavailable'})
  elif path.endswith('/players/steam-avatar/76561198000000013') and '76561198000000013' in avatar_requests:
   route.fulfill(content_type='image/png',body=(ROOT/'static/icon-edit-profile-bronze.png').read_bytes())
  elif '/players/steam-avatar/' in path: route.fulfill(status=404,body='')
  elif path.endswith('/players'): route.fulfill(json={'players':players,'unnamed_captures':0})
  elif path.endswith('/detection-history'):route.fulfill(json={'events':events,'has_more':False})
  elif path.endswith('/history-storage'):route.fulfill(json={'request':'success','history':{'bytes':0,'estimated':False,'events':0},'archives':[],'monitor_running':False})
  elif path=='http://tracker.test/':route.fulfill(content_type='text/html',body=html)
  else:route.abort()
 page.route('**/*',serve)
 page.goto('http://tracker.test/')
 page.add_style_tag(path=str(ROOT/'static/players.css'))
 page.add_script_tag(path=str(ROOT/'static/jquery.js'))
 page.evaluate("window.uiSetStatus = () => {}; window.appendIpCountry = () => {}")
 page.add_script_tag(path=str(ROOT/'static/players.js'))
 page.add_script_tag(path=str(ROOT/'static/history.js'))
 page.evaluate('''() => {let p=document.createElement('p'); p.innerHTML='<span class="combat-result-text" data-opponent="Same Name" data-opponent-source="steam">Vous avez perdu contre Same Name.</span>';document.querySelector('.cadreStats').append(p)}''')
 link=page.locator('.cadreStats .encounter-player-link'); link.wait_for(state='attached');link.evaluate('(el) => el.click()')
 page.wait_for_selector('#players_list details[open]')
 assert page.locator('#players_list details[open] .player-profile-button').count()==1
 steam_emblem=page.locator('#players_list details[open] .player-emblem-steam')
 steam_emblem.locator('img').wait_for(state='attached')
 page.wait_for_function("document.querySelector('#players_list details[open] .player-emblem-steam img')?.naturalWidth > 0")
 assert steam_emblem.locator('img').get_attribute('alt') == ''
 assert steam_emblem.evaluate("e => getComputedStyle(e).borderRadius") == '0px'
 page.locator('#players_search').fill('')
 missing=page.locator('#players_list details').filter(has_text='Missing Avatar').locator('.player-emblem-steam')
 missing.scroll_into_view_if_needed()
 page.wait_for_function("Array.from(document.querySelectorAll('#players_list .player-card')).some(card => card.querySelector('.player-name')?.textContent === 'Missing Avatar' && !card.querySelector('.player-emblem-steam img'))")
 assert missing.locator('img').count()==0 and missing.locator('svg').count()==1
 assert missing.evaluate("e => getComputedStyle(e).borderRadius") == '0px'
 queued=page.locator('#players_list details').filter(has_text='Queued Avatar').locator('.player-emblem-steam')
 queued.scroll_into_view_if_needed()
 page.wait_for_function("Array.from(document.querySelectorAll('#players_list .player-card')).some(card => card.querySelector('.player-name')?.textContent === 'Queued Avatar' && card.querySelector('.player-emblem-steam img')?.naturalWidth > 0)")
 assert avatar_requests.count('76561198000000013') == 1
 screenshot_dir=os.environ.get('TRACKER_PLAYERS_SCREENSHOT_DIR')
 if screenshot_dir:
  page.locator('#players_list').screenshot(path=str(Path(screenshot_dir)/'steam-avatars.png'))
 page.locator('#menu_button_history').evaluate('(el) => el.click()')
 page.wait_for_selector('#history_list .encounter-player-link')
 links=page.locator('#history_list .encounter-player-link');assert links.count()==4
 links.nth(0).evaluate('(el) => el.click()')
 page.wait_for_selector('#players_list details[open]')
 assert page.locator('#players_list details[open] .player-profile-button').count()==0
 assert page.locator('#players_list details[open] .player-emblem').inner_text()=='S'
 assert page.locator('#players_list details[open] .player-emblem').evaluate("e => getComputedStyle(e).borderRadius") == '0px'
 page.locator('#menu_button_history').evaluate('(el) => el.click()')
 page.wait_for_selector('#history_list .encounter-player-link')
 page.locator('#history_list .encounter-player-link').nth(1).evaluate('(el) => el.click()')
 page.wait_for_selector('#players_list details[open]')
 assert page.locator('#players_list details[open] .player-profile-button').count()==1
 source=(ROOT/'static/app.js').read_text(encoding='utf-8')
 summary=source[source.index('let sidebarSession = null;'):source.index('function renderProfileLegend',source.index('let sidebarSession = null;'))]
 page.add_script_tag(content="function appT(key, fallback) { return fallback; } function statsModeLabel(mode) { return mode; }\n"+summary)
 page.evaluate("renderSessionSummary({last:{result:'victory',mode:'Arena',opponent:'Other'}})")
 sidebar=page.locator('#sidebar_last_combat .encounter-player-link')
 assert sidebar.inner_text()=='Other'
 sidebar.evaluate('(el) => el.click()')
 page.wait_for_function("document.querySelector('#players_list details[open] .player-name')?.textContent === 'Other'")
 page.evaluate("renderSessionSummary({last:{result:'draw',mode:'Arena',opponent:''}})")
 assert page.locator('#sidebar_last_combat button').count()==0
 page.evaluate("renderSessionSummary({last:{result:'victory',mode:'Arena',opponent:'<img src=x onerror=alert(1)>'}})")
 assert page.locator('#sidebar_last_combat img').count()==0
 assert page.locator('#sidebar_last_combat button').inner_text()=='<img src=x onerror=alert(1)>'
 browser.close()
print('Home, history and sidebar results navigate safely to their matching player.')
