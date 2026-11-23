"""Check the actual leaderboard control with isolated data and responses."""
import base64
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
CHROME = Path(os.environ.get('ProgramFiles', r'C:\Program Files')) / 'Google/Chrome/Application/chrome.exe'

with socket.socket() as sock:
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
with tempfile.TemporaryDirectory(prefix='tracker-ranking-pagination-', ignore_cleanup_errors=True) as directory:
    env = os.environ.copy()
    env.update(APPDATA=directory, LOCALAPPDATA=directory, TRACKER_TEST_PORT=str(port), TRACKER_TEST_NO_STEAM='1')
    server = subprocess.Popen([sys.executable, str(ROOT / 'tests/support/browser_server.py')], cwd=ROOT, env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        url = f'http://127.0.0.1:{port}'
        for _ in range(100):
            try:
                urllib.request.urlopen(url, timeout=1).close()
                break
            except OSError:
                if server.poll() is not None:
                    raise RuntimeError('Isolated server exited')
                time.sleep(.1)
        else:
            raise RuntimeError('Isolated server did not start')

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=str(CHROME), headless=True)
            for width in (1440, 390):
                context = browser.new_context(viewport={'width': width, 'height': 900})
                context.add_init_script('''(() => {
                  const original = window.setTimeout;
                  window.setTimeout = function (callback, delay, ...args) {
                    if (delay === 300000 && String(callback).includes('rankingContentVisible')) {
                      window.__presenceTick = callback;
                      window.__presenceTimers = (window.__presenceTimers || 0) + 1;
                    }
                    return original.call(this, callback, delay, ...args);
                  };
                })()''')
                context.route('**/*', lambda route: route.continue_() if route.request.url.startswith(url + '/') else route.abort())
                context.route('**/online-leaderboard/settings', lambda route: route.fulfill(json={'enabled': True, 'configured': True, 'state': 'idle'}))
                context.route('**/online-leaderboard/sync', lambda route: route.fulfill(json={'state': 'success'}))
                requests = []
                name_state = {'long': False}
                long_name = 'W' * 80 + '<test>'
                def entries(route):
                    params = parse_qs(urlsplit(route.request.url).query)
                    size, page = int(params['per_page'][0]), int(params['page'][0])
                    requests.append((size, page))
                    players = [{'rank': rank, 'name': (long_name if name_state['long'] and rank == 1 else 'P' + str(rank)), 'level': 1, 'score': 1, 'stats': {}}
                               for rank in range(1, 26)]
                    players[0]['tracker_active'] = True
                    players[1]['tracker_active'] = False
                    players[2]['tracker_active'] = 'true'  # Never treat malformed or missing presence as active.
                    players[3]['tracker_active'] = True
                    players[3]['avatar'] = 'data:image/png;base64,' + base64.b64encode((ROOT / 'static/default-profile-silhouette.png').read_bytes()).decode('ascii')
                    route.fulfill(json={'mode': params['mode'][0], 'entries': players[(page - 1) * size:page * size],
                                        'page': page, 'per_page': size, 'total': 25, 'filtered_total': 25})
                context.route('**/online-leaderboard/entries?**', entries)
                page = context.new_page()
                page.goto(url, wait_until='load')
                page.locator('#menu_button_multi').click()
                page.wait_for_function("() => document.querySelectorAll('#table_multi tbody tr').length === 10")
                assert page.evaluate('window.__presenceTimers >= 1'), 'A response must schedule the five-minute refresh'
                page.evaluate("uiApplyLanguage('fra')")
                indicators = page.locator('#table_multi tbody .leaderboard-active-indicator')
                assert indicators.count() == 2
                assert indicators.first.locator('xpath=..').get_attribute('class') == 'leaderboard-avatar-frame'
                assert indicators.first.get_attribute('role') == 'img'
                assert indicators.first.get_attribute('aria-label') == 'Tracker actif récemment'
                assert indicators.first.get_attribute('title') == 'Tracker actif récemment'
                for indicator in indicators.all():
                    geometry = indicator.evaluate('''node => {
                        const dot = node.getBoundingClientRect(), frame = node.parentElement.getBoundingClientRect();
                        const avatar = node.parentElement.querySelector('img, .fakeImageuser').getBoundingClientRect();
                        return {top: dot.top - avatar.top, right: avatar.right - dot.right,
                                width: dot.width, height: dot.height, frameHeight: frame.height, avatarHeight: avatar.height};
                    }''')
                    assert abs(geometry['top'] + 3) < .1 and abs(geometry['right'] + 3) < .1, (width, geometry)
                    assert geometry['width'] == 10 and geometry['height'] == 10, (width, geometry)
                    assert geometry['frameHeight'] == 54 and geometry['avatarHeight'] == 54, (width, geometry)
                screenshot_dir = os.environ.get('TRACKER_RANKING_SCREENSHOT_DIR')
                if screenshot_dir:
                    page.locator('#table_multi').screenshot(path=str(Path(screenshot_dir) / ('ranking-presence-' + str(width) + '.png')))
                selector = page.locator('.cadre_multi .dataTables_length select')
                assert selector.is_visible() and selector.input_value() == '10'
                assert selector.locator('option').all_text_contents() == ['5', '10', '20']
                assert (10, 1) in requests
                name_cell = page.locator('#table_multi tbody tr:first-child td:nth-child(3)')
                short_width = name_cell.bounding_box()['width']
                name_state['long'] = True
                scheduled_before_reload = page.evaluate('window.__presenceTimers')
                with page.expect_response(lambda response: '/online-leaderboard/entries?' in response.url):
                    page.evaluate("$('#table_multi').DataTable().ajax.reload()")
                page.wait_for_function("() => document.querySelector('#table_multi tbody tr:first-child td:nth-child(3) span')?.textContent.includes('<test>')")
                assert page.evaluate('window.__presenceTimers') > scheduled_before_reload, 'Each later response must rearm the full interval'
                long_width = name_cell.bounding_box()['width']
                name_span = name_cell.locator('.leaderboard-player-name')
                assert long_width > short_width and long_width <= 150.5, (width, short_width, long_width)
                assert name_span.text_content() == long_name and name_span.get_attribute('title') == long_name
                with page.expect_response(lambda response: '/online-leaderboard/entries?' in response.url and 'per_page=5' in response.url):
                    selector.select_option('5')
                page.wait_for_function("() => document.querySelectorAll('#table_multi tbody tr').length === 5")
                with page.expect_response(lambda response: '/online-leaderboard/entries?' in response.url and 'per_page=5' in response.url and 'page=2' in response.url):
                    page.locator('.cadre_multi .dataTables_paginate .next').click()
                page.wait_for_function("() => document.querySelector('#table_multi tbody').textContent.includes('P6')")
                page.wait_for_function("() => typeof window.__presenceTick === 'function' && !document.querySelector('#leaderboard_refresh').disabled")
                # A hidden window must not issue requests, but a stale table is
                # refreshed once on return, without changing the current page.
                page.evaluate('''() => {
                  window.__realNow = Date.now;
                  Date.now = () => window.__realNow() + 301000;
                  Object.defineProperty(document, 'hidden', {configurable:true, get:() => true});
                  window.__presenceTick();
                }''')
                before_return = len(requests)
                page.wait_for_timeout(300)
                assert len(requests) == before_return
                with page.expect_response(lambda response: '/online-leaderboard/entries?' in response.url and 'per_page=5' in response.url and 'page=2' in response.url):
                    page.evaluate('''() => {
                      Object.defineProperty(document, 'hidden', {configurable:true, get:() => false});
                      document.dispatchEvent(new Event('visibilitychange'));
                    }''')
                page.wait_for_function("() => document.querySelector('#table_multi tbody').textContent.includes('P6')")
                page.evaluate('''() => { Date.now = window.__realNow; delete document.hidden; }''')
                page.wait_for_timeout(300)
                assert len(requests) == before_return + 1
                with page.expect_response(lambda response: '/online-leaderboard/entries?' in response.url and 'per_page=20' in response.url):
                    selector.select_option('20')
                page.wait_for_function("() => document.querySelectorAll('#table_multi tbody tr').length === 20")
                assert requests[-1] == (20, 1)
                page.evaluate("launchLanguages('deu')")
                page.wait_for_function("() => { const heading = document.querySelector('#table_multi th.tb-3'); return heading && heading.title === heading.textContent.trim(); }")
                assert indicators.count() == 2
                assert indicators.first.get_attribute('aria-label') == 'Tracker kürzlich aktiv'
                context.close()
            browser.close()
        print('Leaderboard pagination works with 5, 10 and 20 rows at desktop and mobile widths.')
    finally:
        subprocess.run(['taskkill', '/PID', str(server.pid), '/T', '/F'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        server.wait(timeout=10)
