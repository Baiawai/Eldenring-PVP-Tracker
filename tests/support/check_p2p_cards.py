"""Browser smoke check of live P2P cards with fake local-only data."""
from io import BytesIO
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
CHROME = Path(os.environ.get('ProgramFiles', r'C:\Program Files')) / 'Google/Chrome/Application/chrome.exe'
_image = BytesIO()
Image.new('RGBA', (4, 4), (123, 80, 20, 255)).save(_image, 'PNG')
PNG = _image.getvalue()


def check(browser, url, width, height):
    context = browser.new_context(viewport={'width':width, 'height':height})
    context.route('**/*', lambda route: route.continue_() if route.request.url.startswith(url + '/') else route.abort())
    calls = {'peer':0, 'avatar':0, 'profile':[], 'revision':1, 'fail_avatar':False,
             'unknown_quality':None, 'unknown_name':'Sans avatar', 'world_host':None, 'first_ping':42}
    peer_id = '76561198000000001'
    unknown_id = '76561198000000002'
    def peers(route):
        calls['peer'] += 1
        route.fulfill(json={'status':'active', 'enabled':True, 'ping_mode':'active', 'world_host':calls['world_host'], 'peers':[
            {'id':peer_id, 'name':'Faux joueur', 'ping':calls['first_ping'], 'average_ping':47,
             'jitter':4, 'quality':.93, 'connected_seconds':123, 'avatar_available':True,
             'avatar_revision':calls['revision'], 'country_code':'FR', 'encounters':8},
            {'id':unknown_id, 'name':calls['unknown_name'], 'ping':None, 'average_ping':None,
             'jitter':None, 'quality':calls['unknown_quality'], 'connected_seconds':None, 'avatar_available':False, 'country_code':None}]})
    def avatar(route):
        calls['avatar'] += 1
        route.fulfill(status=503 if calls['fail_avatar'] else 200, content_type='image/png', body=b'' if calls['fail_avatar'] else PNG)
    def profile(route):
        calls['profile'].append(route.request.post_data)
        route.fulfill(json={'request':'success'})
    context.route('**/steam-peers', peers)
    context.route('**/steam-peer-avatar/*', avatar)
    context.route('**/steam-profile', profile)
    page = context.new_page()
    page.add_init_script("""(() => { const original = Date.now.bind(Date); window.__testOffset = 0;
        Date.now = () => original() + window.__testOffset;
        const schedule = window.setInterval.bind(window);
        window.setInterval = (callback, delay, ...args) => {
            if (delay === 3000 && String(callback).includes("'/steam-peers'")) window.__testPeerRefresh = callback;
            return schedule(callback, delay, ...args);
        };
    })();""")
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    def check_live_layout():
        preview = page.locator('.live-preview').bounding_box()
        peer_panel = page.locator('.steam-peer-card').bounding_box()
        toggle = page.locator('.sidebar-toggle').bounding_box()
        assert preview and peer_panel and toggle
        preview_center = preview['x'] + preview['width'] / 2
        panel_center = peer_panel['x'] + peer_panel['width'] / 2
        assert abs(panel_center - preview_center) <= 1, (width, preview, peer_panel)
        assert 0 <= height - (toggle['y'] + toggle['height']) <= 36, (width, height, toggle)
    def check_name_ping_alignment(card):
        geometry = card.evaluate('''node => {
            const name = node.querySelector('.steam-peer-name');
            const ping = node.querySelector('.steam-peer-ping');
            const heading = node.querySelector('.steam-peer-heading');
            const range = document.createRange();
            range.setStart(name.firstChild, 0); range.setEnd(name.firstChild, 1);
            const char = range.getBoundingClientRect();
            const n = name.getBoundingClientRect(), p = ping.getBoundingClientRect();
            const h = heading.getBoundingClientRect();
            return {nameRight:n.right, pingLeft:p.left, pingRight:p.right,
                headingRight:h.right, nameCenter:(char.top + char.bottom)/2,
                pingCenter:(p.top + p.bottom)/2, scrollHeight:name.scrollHeight,
                clientHeight:name.clientHeight, lineHeight:parseFloat(getComputedStyle(name).lineHeight)};
        }''')
        assert geometry['nameRight'] <= geometry['pingLeft'] + 1, (width, geometry)
        assert abs(geometry['pingRight'] - geometry['headingRight']) <= 1, (width, geometry)
        assert abs(geometry['nameCenter'] - geometry['pingCenter']) <= 4, (width, geometry)
        assert geometry['scrollHeight'] <= geometry['clientHeight'] + 1, (width, geometry)
        return geometry
    def check_player_columns(card):
        avatar = card.locator('.steam-peer-avatar').bounding_box()
        info = card.locator('.steam-peer-info').bounding_box()
        country = card.locator('.steam-peer-country').bounding_box()
        flag = card.locator('.steam-peer-country .ip-country img').bounding_box()
        heading = card.locator('.steam-peer-heading').bounding_box()
        details = card.locator('.steam-peer-details').bounding_box()
        assert avatar and info and country and flag and heading and details, (width, avatar, info, country, flag, heading, details)
        assert avatar['x'] + avatar['width'] <= heading['x'] + 1, (width, avatar, heading)
        assert country['y'] >= max(avatar['y'] + avatar['height'], info['y'] + info['height']) - 1, (width, avatar, info, country)
        assert abs(country['x'] - avatar['x']) <= 1, (width, avatar, country)
        assert card.locator('.steam-peer-country').inner_text() == 'France'
        flag_text = card.locator('.steam-peer-country .ip-country').evaluate('''node => {
            const image = node.querySelector('img').getBoundingClientRect();
            const text = [...node.childNodes].find(child => child.nodeType === Node.TEXT_NODE);
            const range = document.createRange(); range.selectNodeContents(text);
            const label = range.getBoundingClientRect();
            return {imageRight:image.right, imageCenter:(image.top+image.bottom)/2,
                    labelLeft:label.left, labelCenter:(label.top+label.bottom)/2};
        }''')
        assert flag_text['labelLeft'] >= flag_text['imageRight'], (width, flag_text)
        assert abs(flag_text['imageCenter'] - flag_text['labelCenter']) <= 2, (width, flag_text)
        assert details['x'] >= heading['x'] - 1, (width, details, heading)
        assert details['y'] >= heading['y'] + heading['height'] - 1, (width, details, heading)
        detail_lefts = card.evaluate("node => [...node.querySelectorAll('.steam-peer-details span')].filter(e => !e.hidden).map(e => e.getBoundingClientRect().left)")
        assert detail_lefts and all(x >= heading['x'] - 1 for x in detail_lefts), (width, detail_lefts, heading)
        flag_image = card.locator('.steam-peer-country .ip-country img')
        assert flag_image.get_attribute('src').endswith('/static/flags/fr.svg')
        page.wait_for_function("node => node.complete && node.naturalWidth > 0", arg=flag_image.element_handle())
    try:
        page.goto(url, wait_until='load')
        page.wait_for_selector('.sprit', state='detached', timeout=30000)
        # Make the existing preview visible without starting the real monitor.
        page.evaluate("""() => {
            document.querySelector('.presentation').style.display = 'none';
            document.querySelector('.live').style.display = 'block';
            launchLanguages('fra');
        }""")
        page.wait_for_selector('.steam-peer-item')
        card = page.locator('.steam-peer-item').first
        check_live_layout()
        assert card.locator('.steam-peer-name').inner_text() == 'Faux joueur'
        assert card.locator('.steam-peer-encounters').inner_text() == 'Nombre de rencontres : 8'
        assert card.locator('.steam-peer-id').is_hidden()
        assert peer_id not in card.inner_text()
        check_name_ping_alignment(card)
        check_player_columns(card)
        unknown = page.locator('.steam-peer-item').nth(1)
        assert unknown.locator('.steam-peer-encounters').inner_text() == 'Nombre de rencontres : —'
        assert unknown.locator('.steam-peer-country .ip-country').count() == 0
        page.evaluate("document.body.classList.add('hide-steam-country')")
        assert card.locator('.steam-peer-country .ip-country').is_hidden()
        page.evaluate("document.body.classList.remove('hide-steam-country')")
        check_player_columns(card)
        # The application must use the overlay's thresholds on the raw value,
        # even when the displayed value rounds across a threshold.
        for value, shown, color, quality in [
            (0, '0 ms', 'rgb(133, 205, 164)', 'good'),
            (99, '99 ms', 'rgb(133, 205, 164)', 'good'),
            (99.9, '100 ms', 'rgb(133, 205, 164)', 'good'),
            (100, '100 ms', 'rgb(225, 193, 110)', 'fair'),
            (179, '179 ms', 'rgb(225, 193, 110)', 'fair'),
            (179.9, '180 ms', 'rgb(225, 193, 110)', 'fair'),
            (180, '180 ms', 'rgb(222, 119, 119)', 'poor'),
            (60000, '60000 ms', 'rgb(222, 119, 119)', 'poor'),
            (None, '—', 'rgb(235, 212, 166)', 'unknown'),
            (-1, '—', 'rgb(235, 212, 166)', 'unknown'),
            (60001, '—', 'rgb(235, 212, 166)', 'unknown'),
            ('invalid', '—', 'rgb(235, 212, 166)', 'unknown'),
        ]:
            calls['first_ping'] = value
            page.evaluate('() => window.__testPeerRefresh()')
            ping = card.locator('.steam-peer-ping')
            assert ping.inner_text() == shown, (width, value, ping.inner_text())
            assert ping.evaluate('node => getComputedStyle(node).color') == color, (width, value)
            assert 'is-' + quality in ping.get_attribute('class').split(), (width, value)
        calls['first_ping'] = 42
        page.evaluate('() => window.__testPeerRefresh()')
        check_name_ping_alignment(card)
        long_name = 'Pseudo très long pour vérifier les lignes et le placement du ping'
        name = card.locator('.steam-peer-name')
        name.evaluate('(node, text) => { node.textContent = text; }', long_name)
        geometry = check_name_ping_alignment(card)
        assert name.inner_text() == long_name
        assert geometry['clientHeight'] > geometry['lineHeight'] * 1.5, (width, geometry)
        check_player_columns(card)
        name.evaluate("node => { node.textContent = 'Faux joueur'; }")
        page.evaluate("document.body.classList.add('hide-steam-name')")
        assert name.is_hidden() and card.locator('.steam-peer-ping').is_visible()
        page.evaluate("document.body.classList.remove('hide-steam-name'); document.body.classList.add('hide-steam-ping')")
        assert name.is_visible() and card.locator('.steam-peer-ping').is_hidden()
        page.evaluate("document.body.classList.remove('hide-steam-ping')")
        check_name_ping_alignment(card)
        calls['world_host'] = {'peer_id':peer_id, 'name':'Faux joueur'}
        page.wait_for_function("() => !document.querySelector('.steam-peer-host').hidden", timeout=5000)
        assert card.locator('.steam-peer-host').is_visible()
        check_name_ping_alignment(card)
        calls['world_host'] = None
        if width > 760:
            # The fixed profile-panel chevron must not cover the player's name.
            clear = card.locator('.steam-peer-name').evaluate('''node => {
                const toggle = document.querySelector('.sidebar-toggle').getBoundingClientRect();
                const range = document.createRange(); range.selectNodeContents(node);
                return [...range.getClientRects()].every(rect =>
                    rect.right <= toggle.left || rect.left >= toggle.right ||
                    rect.bottom <= toggle.top || rect.top >= toggle.bottom);
            }''')
            assert clear, 'Player name overlaps the profile-panel chevron'
            page.locator('.sidebar-toggle').click()
            page.wait_for_timeout(900)
            check_live_layout()
            clear = card.locator('.steam-peer-name').evaluate('''node => {
                const toggle = document.querySelector('.sidebar-toggle').getBoundingClientRect();
                const range = document.createRange(); range.selectNodeContents(node);
                return [...range.getClientRects()].every(rect =>
                    rect.right <= toggle.left || rect.left >= toggle.right ||
                    rect.bottom <= toggle.top || rect.top >= toggle.bottom);
            }''')
            assert clear, 'Player name overlaps the closed profile-panel chevron'
            page.locator('.sidebar-toggle').click()
            page.wait_for_timeout(900)
            check_live_layout()
        assert 'ms' in card.locator('.steam-peer-ping').inner_text()
        assert '93 %' in card.locator('.steam-peer-quality').inner_text()
        assert '00:02:03' in card.locator('.steam-peer-details').inner_text()
        assert '47 ms' in card.locator('.steam-peer-details').inner_text()
        assert 'Jitter' not in card.locator('.steam-peer-details').inner_text()
        assert '4 ms' not in card.locator('.steam-peer-details').inner_text()
        unknown = page.locator('.steam-peer-item').nth(1)
        assert unknown.locator('.steam-peer-quality').is_visible()
        assert unknown.locator('.steam-peer-network').is_visible()
        assert 'indisponible' in unknown.locator('.steam-peer-quality').inner_text().lower()
        card.locator('.steam-peer-avatar img').wait_for(state='attached')
        assert page.locator('.steam-peer-item').nth(1).locator('svg').count() == 1
        card.locator('.steam-peer-name').click(timeout=3000)
        assert calls['profile'] == ['steam_id=' + peer_id]
        page.wait_for_function("() => document.querySelector('.steam-peer-ping').textContent.includes('ms')")
        page.wait_for_timeout(6500)
        assert calls['peer'] >= 3 and calls['avatar'] == 1, calls
        # Quality can become available and disappear again on a later refresh.
        calls['unknown_quality'] = 0
        calls['unknown_name'] = unknown_id
        page.wait_for_function("() => document.querySelectorAll('.steam-peer-quality')[1].textContent.includes('0 %')", timeout=5000)
        assert unknown.locator('.steam-peer-quality').is_visible()
        assert unknown_id not in unknown.inner_text()
        calls['unknown_quality'] = None
        page.wait_for_function("() => document.querySelectorAll('.steam-peer-quality')[1].textContent.toLowerCase().includes('indisponible')", timeout=5000)
        # One changed cache revision refreshes the image; ping updates alone do not.
        calls['revision'] = 2
        page.wait_for_timeout(3500)
        assert calls['avatar'] == 2, calls
        # A transient local cache error retries only after its delay, never at
        # the regular three-second ping refresh frequency.
        calls['revision'] = 3
        calls['fail_avatar'] = True
        page.wait_for_timeout(3500)
        assert calls['avatar'] == 3, calls
        page.wait_for_timeout(3500)
        assert calls['avatar'] == 3, calls
        calls['fail_avatar'] = False
        page.evaluate('window.__testOffset += 31000')
        page.wait_for_timeout(3500)
        assert calls['avatar'] == 4, calls
        assert not errors, errors
        page.screenshot(path=str(Path(os.environ['TEMP']) / ('p2p-cards-' + str(width) + '.png')))
        print('P2P cards passed:', width, calls, flush=True)
    finally:
        context.close()


def main():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    url = 'http://127.0.0.1:' + str(port)
    with tempfile.TemporaryDirectory(prefix='tracker-p2p-ui-', ignore_cleanup_errors=True) as directory:
        env = os.environ.copy()
        env.update(APPDATA=directory, TRACKER_TEST_PORT=str(port))
        server = subprocess.Popen([sys.executable, str(ROOT / 'tests/support/browser_server.py')], cwd=ROOT,
                                  env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(100):
                try:
                    urllib.request.urlopen(url, timeout=1).close()
                    break
                except OSError:
                    if server.poll() is not None:
                        raise RuntimeError('isolated server exited')
                    time.sleep(.1)
            else:
                raise RuntimeError('isolated server failed')
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(executable_path=str(CHROME), headless=True)
                try:
                    check(browser, url, 1440, 900)
                    check(browser, url, 900, 700)
                    check(browser, url, 390, 844)
                finally:
                    browser.close()
        finally:
            subprocess.run(['taskkill', '/PID', str(server.pid), '/T', '/F'], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, check=False)
            server.wait(timeout=10)


if __name__ == '__main__':
    main()
