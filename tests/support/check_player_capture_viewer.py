"""Exercise the existing capture modal from player cards using synthetic data."""
import re
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
html = re.sub(r'<script\b[^>]*>.*?</script>', '', (ROOT / 'templates/index.html').read_text(encoding='utf-8'), flags=re.S | re.I)
source = (ROOT / 'static/app.js').read_text(encoding='utf-8')
captions = source[source.index('function captureResultKey('):source.index('function getCapture(')]
viewer = source[source.index('let captureViewerIndex = -1;'):source.index('var up_capture = false;')]
image = (ROOT / 'static/icon-edit-profile-bronze.png').read_bytes()
requests = []

def ref(ident, name):
    return {'id':ident, 'date':f'2026-01-01 12:00:0{ident}', 'mode':'Arena',
            'duration':'12', 'outcome':'victory', 'opponent':name}

def player(name, references, history):
    return {'name':name, 'total':len(references), 'victories':len(references), 'defeats':0,
            'draws':0, 'sightings':0, 'roles':['opponent'], 'relations':['opponent'],
            'last_seen':'2026-01-01 12:00:03', 'history':history, 'capture_refs':references}

players = [player('Alice', [ref(3,'Alice'), ref(2,'Alice'), ref(1,'Alice')], [
    {'kind':'combat','date':'2026-01-01 12:00:02','mode':'Arena','outcome':'victory','capture_id':2},
    {'kind':'sighting','date':'2026-01-01 12:00:01','mode':'Arena','role':'ally','event':'joined','relation':'ally'},
    {'kind':'combat','date':'2026-01-01 12:00:01','mode':'Arena','outcome':'victory','capture_id':1},
]), player('Bob', [ref(4,'Bob')], [
    {'kind':'combat','date':'2026-01-01 12:00:04','mode':'Arena','outcome':'victory','capture_id':4},
])]

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe')
    page = browser.new_page(viewport={'width':1200, 'height':800})
    def serve(route):
        path = urlparse(route.request.url).path
        if path == '/': route.fulfill(content_type='text/html', body=html); return
        if path == '/players/categories':
            route.fulfill(json={'categories':[], 'counts':{}, 'multi_category':True}); return
        if path == '/players':
            route.fulfill(json={'players':players, 'unnamed_captures':0}); return
        if path == '/static/icon-camera-bronze.png':
            route.fulfill(content_type='image/png', body=(ROOT/'static/icon-camera-bronze.png').read_bytes()); return
        if path.startswith('/players/capture/'):
            ident = int(path.rsplit('/',1)[-1]); requests.append(ident)
            if ident == 4: route.fulfill(status=404, body=''); return
            route.fulfill(content_type='image/png', body=image); return
        route.abort()
    page.route('**/*', serve)
    page.goto('http://tracker.test/')
    page.locator('.sprit').evaluate_all('(nodes) => nodes.forEach(node => node.remove())')
    page.locator('#profile_sidebar').evaluate('(node) => { node.style.display = "none"; }')
    for name in ('style.css','selects.css','players.css','history.css','stats-page.css','app-typography.css'):
        page.add_style_tag(path=str(ROOT/'static'/name))
    page.add_script_tag(path=str(ROOT/'static/jquery.js'))
    page.evaluate("window.uiSetStatus = () => {}; window.appendIpCountry = () => {}")
    page.add_script_tag(content='function appT(key, fallback) { return fallback; }\n' + captions + '\n' + viewer)
    page.add_script_tag(path=str(ROOT/'static/players.js'))
    page.locator('#menu_button_players').evaluate('(node) => node.click()')
    page.wait_for_function("document.querySelectorAll('#players_list .player-card').length === 2")
    alice = page.locator('#players_list .player-card').filter(has_text='Alice')
    alice.locator('summary').first.click()
    assert alice.locator('.player-match').count() == 3
    assert alice.locator('.player-capture-link').count() == 2
    page.wait_for_function("document.querySelector('#players_list .player-capture-link img')?.naturalWidth > 0")
    assert alice.locator('.player-capture-empty').count() == 1
    assert requests == []
    alice.locator('.player-capture-link').first.click()
    page.wait_for_function("!document.getElementById('capture_viewer_overlay').hidden && document.querySelector('.capture-viewer-card img')?.naturalWidth > 0")
    assert requests == [2]
    assert page.locator('.capture-viewer-card .posted').inner_text() == '2'
    assert 'Alice' in page.locator('.capture-viewer-card b').inner_text()
    page.keyboard.press('ArrowRight')
    page.wait_for_function("document.querySelector('.capture-viewer-card .posted')?.textContent === '1'")
    assert page.locator('.capture-viewer-next').is_disabled()
    page.keyboard.press('ArrowLeft')
    page.keyboard.press('ArrowLeft')
    page.wait_for_function("document.querySelector('.capture-viewer-card .posted')?.textContent === '3'")
    assert page.locator('.capture-viewer-prev').is_disabled()
    page.keyboard.press('Escape')
    assert not page.locator('#capture_viewer_overlay').is_visible()
    bob = page.locator('#players_list .player-card').filter(has_text='Bob')
    bob.locator('summary').first.click()
    bob.locator('.player-capture-link').click()
    page.locator('.capture-viewer-unavailable').wait_for(state='visible')
    assert page.locator('.capture-viewer-prev').is_disabled() and page.locator('.capture-viewer-next').is_disabled()
    assert requests[-1] == 4
    page.locator('.capture-viewer-close').click()
    assert not page.locator('#capture_viewer_overlay').is_visible()
    # Switching back to the original capture page restores its own source.
    page.evaluate('''() => {
        const panel = document.createElement('div'); panel.className='captures-panel';
        panel.style.cssText='display:block;position:fixed;left:0;top:0;width:200px;height:200px';
        for (const id of ['normal-1','normal-2']) {
            const card=document.createElement('div'); card.className='para_capture'; card.id=id;
            const caption=document.createElement('span'); const title=document.createElement('b');
            title.textContent=id; caption.appendChild(title); card.appendChild(caption); panel.appendChild(card);
        }
        document.body.appendChild(panel); document.getElementById('normal-1').click();
    }''')
    assert page.locator('.capture-viewer-card b').inner_text() == 'normal-1'
    assert page.locator('.capture-viewer-prev').is_disabled()
    page.keyboard.press('ArrowRight')
    assert page.locator('.capture-viewer-card b').inner_text() == 'normal-2'
    assert page.locator('.capture-viewer-next').is_disabled()
    browser.close()
print('Player capture viewer, per-player navigation, missing images and original modal: OK')
