"""Optional browser test using Playwright and installed Chrome, with isolated data."""
import os
import re
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime
import base64
import io
from PIL import Image

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
CHROME = Path(os.environ.get('ProgramFiles', r'C:\Program Files')) / 'Google/Chrome/Application/chrome.exe'
with socket.socket() as sock:
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
with tempfile.TemporaryDirectory(prefix='tracker-browser-test-') as directory:
    env = os.environ.copy()
    env.update(APPDATA=directory, TRACKER_TEST_PORT=str(port))
    server = subprocess.Popen([sys.executable, str(ROOT / 'tests/support/browser_server.py')],
                              cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        url = 'http://127.0.0.1:' + str(port)
        for attempt in range(100):
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
            for width, height in [(1440, 900), (900, 700), (390, 844)]:
                page = browser.new_page(viewport={'width':width, 'height':height})
                page.route('**/*', lambda route: route.continue_() if route.request.url.startswith(url + '/') else route.abort())
                page.route('**/online-leaderboard/settings', lambda route: route.fulfill(json={'enabled':True, 'configured':True, 'state':'idle'}))
                page.route('**/online-leaderboard/sync', lambda route: route.fulfill(json={'state':'success'}))
                errors = []
                leaderboard_reads = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.on('request', lambda request: leaderboard_reads.append(request.url) if '/online-leaderboard/entries?' in request.url else None)
                page.goto(url, wait_until='load')
                page.wait_for_timeout(1500)
                for selector in ('.online-server-move', '.online-server-consent-review'):
                    if page.locator(selector).evaluate('(element) => getComputedStyle(element).display') != 'none':
                        raise AssertionError(('Inactive server transition control is visible', width, selector))
                for code in ['fra','eng','deu','ita','spaes','spaar','por','pol','rus','jap','kor','chi','zht','tha','ara']:
                    page.evaluate('(code) => launchLanguages(code)', code)
                    if page.locator('.leaderboard-report').get_attribute('href') != 'https://discord.gg/y79z83D2Ua':
                        raise AssertionError(('Incorrect Discord report link', width, code))
                    ranking_faq = page.locator('[data-i18n="faq_a_11"]').text_content()
                    if 'eldenringpvp.com' not in ranking_faq or 'Steam' not in ranking_faq:
                        raise AssertionError(('Leaderboard FAQ missing server or Steam', width, code, ranking_faq))
                    if code != 'fra':
                        mismatches = page.evaluate('''(code) => {
                            const modern = window.ELDEN_UI_PACKS[code].modern;
                            return Array.from(document.querySelectorAll('[data-i18n]'))
                                // The leaderboard replaces its eyebrow with the current mode.
                                .filter(node => node.dataset.i18n !== 'leaderboard_eyebrow')
                                .filter(node => node.textContent !== modern[node.dataset.i18n])
                                .map(node => [node.dataset.i18n, node.textContent, modern[node.dataset.i18n]])
                                .concat(['title', 'placeholder', 'aria'].flatMap(kind =>
                                    Array.from(document.querySelectorAll('[data-i18n-' + kind + ']'))
                                        .map(node => {
                                            const key = node.dataset['i18n' + kind[0].toUpperCase() + kind.slice(1)];
                                            const actual = node.getAttribute(kind === 'aria' ? 'aria-label' : kind);
                                            return [key, actual, modern[key]];
                                        }).filter(entry => entry[1] !== entry[2])));
                        }''', code)
                        if mismatches:
                            raise AssertionError(('Incorrect translated interface text', width, code, mismatches))
                    expected = page.evaluate('(code) => code === "fra" ? window.interface_fr[0] : window.ELDEN_UI_PACKS[code].legacy[0]', code)
                    for selector in ('#retention_captures', '#retention_steam'):
                        actual_period = page.locator(selector + ' option[value="30"]').text_content()
                        expected_period = page.evaluate('() => new Intl.NumberFormat(document.documentElement.lang, {style: "unit", unit: "day", unitDisplay: "long"}).format(30)')
                        if actual_period != expected_period:
                            raise AssertionError((width, code, selector, actual_period, expected_period))
                    actual = page.locator('.scoreboard .victory').first.text_content()
                    if actual != expected:
                        raise AssertionError((width, code, actual, expected))
                page.evaluate("() => { launchLanguages('fra'); launchLanguages('spaes'); }")
                page.wait_for_timeout(500)
                if errors:
                    raise AssertionError((width, errors))
                page.evaluate("() => launchLanguages('fra')")
                if page.locator('.online-settings > [data-online=online_explain]').count() or page.locator('.online-settings .settings-info').count() != 3:
                    raise AssertionError(('Leaderboard settings help is missing or misplaced', width))
                today = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                page.route('**/allCapturesChart?**', lambda route: route.fulfill(json={
                    'request':'success', 'captures':[[1, '', 1, 0, 0, '10', today, 'Arena']]}))
                user = ['0'] * 20
                user[2], user[3], user[4], user[7], user[9] = '2', '1', '1', '99', '4'
                page.route('**/modeStats?**', lambda route: route.fulfill(json={'request':'success', 'user':user}))
                page.locator('#menu_button_info').click()
                page.wait_for_timeout(700)
                if page.locator('#stats_panel .stats-explanation').count():
                    raise AssertionError(('Removed statistics text still present', width))
                if page.locator('#stats_panel .ratio_count').text_content() != '50':
                    raise AssertionError(('Incorrect win rate', width))
                if not page.locator('#stats_user').is_visible():
                    raise AssertionError(('Chart not visible', width, errors))
                page.locator('#stats_mode_choice').select_option('Invasion')
                page.wait_for_timeout(500)
                if page.locator('#stats_panel .arena-draw-row').is_visible():
                    raise AssertionError(('Draw visible in invasion', width))
                if page.locator('#stats_panel .ratio_count').text_content() != '66,67':
                    raise AssertionError(('Incorrect invasion win rate', width))
                page.locator('#stats_panel .btn-chart button[mode="30j"]').click()
                page.wait_for_timeout(400)
                if page.evaluate('myChart.data.labels.length') != 30:
                    raise AssertionError(('Chart period incorrect', width))
                page.screenshot(path=str(ROOT / 'build' / ('stats-ui-' + str(width) + '.png')), full_page=True)
                page.locator('#stats_panel .chartResize').click()
                page.wait_for_timeout(400)
                if not page.locator('.modal_chart #stats_user').is_visible():
                    raise AssertionError(('Expanded chart unavailable', width))
                page.locator('.modal_chart .chartResize').click()
                page.wait_for_timeout(400)
                page.route('**/allCapturesChart?**', lambda route: route.fulfill(json={'request':'success', 'captures':[]}))
                page.locator('#stats_panel .btn-chart button[mode="7j"]').click()
                page.wait_for_timeout(400)
                if not page.locator('#stats_panel .chart-status').is_visible():
                    raise AssertionError(('Empty chart message unavailable', width))
                if errors:
                    raise AssertionError((width, errors))
                page.locator('#menu_button_info').click()
                leaderboard_requests = []
                page.on('request', lambda request: leaderboard_requests.append(request.url) if '/syncMulti' in request.url else None)
                def leaderboard_response(route):
                    from urllib.parse import parse_qs, urlparse
                    params = parse_qs(urlparse(route.request.url).query)
                    page_number = int(params.get('page', ['1'])[0])
                    players = [{'rank': rank, 'name': 'UniqueFoe&bcc=intruder@example.test' if rank == 6 else 'Player ' + str(rank), 'level': 150, 'score': 10 - rank,
                                'avatar': None, 'language': 'fra', 'steam_id': '76561198000000000' if rank == 6 else None, 'history_unverified': rank == 6, 'stats': {'victory': rank, 'defeat': 1, 'egality': 0,
                                                          'combats': rank + 1, 'ratio': 50}}
                               for rank in range(1, 7)]
                    search = params.get('search', [''])[0].lower()
                    filtered = [player for player in players if search in player['name'].lower()]
                    route.fulfill(json={'mode': params.get('mode', ['Arena'])[0], 'entries': filtered[(page_number-1)*5:page_number*5],
                                        'page': page_number, 'per_page': 5, 'total': 6, 'filtered_total': len(filtered)})
                page.route('**/online-leaderboard/entries?**', leaderboard_response)
                page.locator('#menu_button_multi').click()
                if not page.locator('.leaderboard-report').is_visible() or page.locator('#leaderboard_content_toggle').count():
                    raise AssertionError(('Leaderboard report missing or extra content toggle present', width))
                page.wait_for_function("() => document.querySelector('#table_multi tbody')?.textContent.includes('Player 1')")
                page.locator('.cadre_multi .dataTables_paginate .next').click()
                page.wait_for_function("() => document.querySelector('#table_multi tbody')?.textContent.includes('UniqueFoe')")
                if not page.locator('.panel_multi_body').is_visible() or not page.locator('#leaderboard_refresh').is_visible():
                    raise AssertionError(('Leaderboard layout missing', width))
                borders = page.locator('#table_multi').evaluate("el => [el, el.querySelector('thead tr'), el.querySelector('tbody tr')].map(node => getComputedStyle(node).borderWidth)")
                if any(border != '0px' for border in borders):
                    raise AssertionError(('Leaderboard table has borders', width, borders))
                flag = page.locator('#table_multi tbody tr').filter(has_text='UniqueFoe').locator('td:nth-child(2) img')
                if flag.count() != 1 or not 0 < flag.bounding_box()['height'] <= 20:
                    raise AssertionError(('Leaderboard flag height incorrect', width))
                if page.locator('#leaderboard_status').is_visible():
                    raise AssertionError(('Leaderboard status should start hidden', width))
                page.locator('#table_multi tbody tr').filter(has_text='UniqueFoe').click()
                if not page.locator('#leaderboard_player_dialog').is_visible() or page.locator('#leaderboard_player_name').text_content() != 'UniqueFoe&bcc=intruder@example.test':
                    raise AssertionError(('Leaderboard player card unavailable', width))
                if page.locator('.leaderboard-steam-link').get_attribute('href') != 'https://steamcommunity.com/profiles/76561198000000000':
                    raise AssertionError(('Steam link missing from player card', width))
                if page.locator('.leaderboard-steam-unavailable').is_visible():
                    raise AssertionError('A shared Steam profile was shown as unavailable')
                if not page.locator('.leaderboard-history-notice').is_visible():
                    raise AssertionError('Legacy score must be identified as unverified')
                if page.locator('.leaderboard-player-report').get_attribute('href') != 'https://discord.gg/y79z83D2Ua':
                    raise AssertionError(('Player report must open Discord', width))
                page.locator('.leaderboard-player-close').click()
                page.locator('.cadre_multi .dataTables_paginate .previous').click()
                page.wait_for_function("() => document.querySelector('#table_multi tbody')?.textContent.includes('Player 1')")
                page.locator('#table_multi tbody tr').filter(has_text='Player 1').click()
                if page.locator('.leaderboard-steam-link').is_visible() or not page.locator('.leaderboard-steam-unavailable').is_visible():
                    raise AssertionError('An unshared Steam profile was displayed as a link')
                if page.locator('.leaderboard-history-notice').is_visible():
                    raise AssertionError('New event-only score was marked as legacy')
                if page.locator('.leaderboard-steam-link').get_attribute('href') is not None:
                    raise AssertionError('An unshared Steam profile retained a previous player’s link')
                page.locator('.leaderboard-player-close').click()
                search = page.locator('.cadre_multi .dataTables_filter input')
                search.fill('UniqueFoe')
                search.press('End')
                page.wait_for_function("() => document.querySelectorAll('#table_multi tbody tr').length === 1 && document.querySelector('#table_multi tbody').textContent.includes('UniqueFoe')")
                if page.locator('#table_multi tbody tr').count() != 1 or 'UniqueFoe' not in page.locator('#table_multi tbody').text_content():
                    raise AssertionError(('Leaderboard search did not cover all API pages', width))
                search.fill('')
                search.press('End')
                page.locator('#leaderboard_refresh').click()
                page.wait_for_function("() => !document.querySelector('#leaderboard_refresh').disabled")
                notice = page.locator('.online-main-status')
                previous_reads = len(leaderboard_reads)
                page.locator('#leaderboard_refresh').click()
                page.wait_for_function("() => document.querySelector('.online-main-status').textContent.includes('actualisation')")
                if not page.locator('#leaderboard_refresh').is_disabled():
                    raise AssertionError(('Refresh remains enabled during cooldown', width))
                page.wait_for_timeout(250)
                if len(leaderboard_reads) != previous_reads or 'actualisation' not in notice.text_content():
                    raise AssertionError(('Refresh cooldown did not prevent another request', width))
                page.wait_for_timeout(1100)
                if '10 s' in notice.text_content():
                    raise AssertionError(('Refresh countdown did not decrease', width))
                if leaderboard_requests:
                    raise AssertionError(('Leaderboard contacted the old server', leaderboard_requests))
                page.screenshot(path=str(ROOT / 'build' / ('leaderboard-ui-' + str(width) + '.png')), full_page=True)
                page.unroute('**/online-leaderboard/entries?**', leaderboard_response)
                page.route('**/online-leaderboard/entries?**', lambda route: route.fulfill(status=503, json={'error': 'unavailable'}))
                page.evaluate('window.trackerTestDateNow = Date.now; Date.now = () => window.trackerTestDateNow() + 11000')
                page.wait_for_function("() => !document.querySelector('#leaderboard_status').hidden")
                page.wait_for_function("() => !document.querySelector('#leaderboard_refresh').disabled")
                page.evaluate('Date.now = window.trackerTestDateNow')
                if 'UniqueFoe' in page.locator('#table_multi tbody').text_content():
                    raise AssertionError(('Unavailable leaderboard retained stale results', width))
                page.locator('#menu_button_multi').click()
                page.locator('#menu_button_settings').click()
                page.locator('.btn_menu_settings[menu="4"]').click()
                if not page.locator('#close_nav').is_visible() or not page.locator('#close_app').is_visible():
                    raise AssertionError(('Settings buttons unavailable', width))
                page.screenshot(path=str(ROOT / 'build' / ('settings-ui-' + str(width) + '.png')), full_page=True)
                page.locator('#menu_button_settings').click()
                information = page.locator('#information_panel')
                page.locator('#menu_button_information').click()
                if not information.is_visible() or information.locator('.faq-item').count() != 18:
                    raise AssertionError(('Information FAQ unavailable', width))
                discord = information.locator('.information-discord')
                if discord.count() != 1 or not discord.is_visible() or discord.get_attribute('href') != 'https://discord.gg/y79z83D2Ua':
                    raise AssertionError(('Discord invitation missing or incorrect', width))
                if discord.get_attribute('target') != '_blank' or 'noopener' not in discord.get_attribute('rel'):
                    raise AssertionError(('Discord invitation should open safely in a new tab', width))
                panel = information.locator('.information-discord-panel')
                if panel.count() != 1 or not information.locator('.information-shell').evaluate("el => el.firstElementChild.classList.contains('information-discord-panel')"):
                    raise AssertionError(('Discord support should precede the FAQ', width))
                if not panel.locator('img').evaluate('img => img.complete && img.naturalWidth > 0'):
                    raise AssertionError(('Discord icon did not load', width))
                if panel.evaluate('el => el.scrollWidth > el.clientWidth + 1'):
                    raise AssertionError(('Discord support overflows', width))
                information.locator('.faq-item summary').first.click()
                if not information.locator('.faq-item p').first.is_visible():
                    raise AssertionError(('FAQ answer did not open', width))
                for code in ['eng','deu','ita','spaes','spaar','por','pol','rus','jap','kor','chi','zht','tha','ara']:
                    page.evaluate('(code) => launchLanguages(code)', code)
                    if information.locator('.faq-item summary').first.text_content() != page.evaluate('(code) => ELDEN_UI_PACKS[code].modern.faq_q_01', code):
                        raise AssertionError(('FAQ language did not change', width, code))
                    if discord.text_content() != page.evaluate('(code) => ELDEN_UI_PACKS[code].modern.information_discord', code):
                        raise AssertionError(('Discord link language did not change', width, code))
                    if panel.locator('[data-i18n="information_discord_help"]').text_content() != page.evaluate('(code) => ELDEN_UI_PACKS[code].modern.information_discord_help', code):
                        raise AssertionError(('Discord support description language did not change', width, code))
                page.evaluate("() => launchLanguages('fra')")
                if information.locator('.information-contact:visible').count():
                    raise AssertionError(('FAQ contact still visible', width))
                page.screenshot(path=str(ROOT / 'build' / ('information-ui-' + str(width) + '.png')), full_page=True)
                page.locator('#menu_button_info').click()
                if information.is_visible() or not page.locator('#stats_panel').is_visible():
                    raise AssertionError(('FAQ navigation did not close', width))
                page.locator('#menu_button_info').click()
                if width <= 760:
                    page.wait_for_timeout(750)  # Allow the profile drawer transition to finish.
                    content = page.locator('.app-content').bounding_box()
                    if content['width'] < width * .95:
                        raise AssertionError(('Content too narrow', width, content))
                    counters = page.locator('.scoreboard li').all()
                    for counter in counters:
                        if not counter.is_visible():
                            continue
                        box = counter.bounding_box()
                        if box and (box['x'] < 0 or box['x'] + box['width'] > width + 1):
                            raise AssertionError(('Counter clipped', width, box))
                    toggle = page.locator('.sidebar-toggle')
                    toggle.click()
                    page.wait_for_timeout(750)
                    if page.locator('.profile-sidebar').bounding_box()['width'] < 250:
                        raise AssertionError('Profile drawer too narrow')
                    toggle.click()
                    page.wait_for_timeout(750)
                    page.locator('#menu_button_captures').click()
                    if not page.locator('.capture-toolbar').is_visible() or not page.locator('.capture-scroll').is_visible():
                        raise AssertionError('Capture toolbar or scroll area unavailable')
                page.screenshot(path=str(ROOT / 'build' / ('audit-ui-' + str(width) + '.png')), full_page=True)
                print('UI OK', width, height, '15 languages', flush=True)
                page.close()
            # A running backend may still serve its older cached HTML template.
            context = browser.new_context()
            page = context.new_page()
            def serve_cached_template(route):
                response = route.fetch()
                cached = re.sub(r'<details class="faq-item"><summary data-i18n="faq_q_18">.*?</details>', '', response.text(), count=1)
                route.fulfill(response=response, body=cached)
            page.route(url + '/', serve_cached_template)
            page.goto(url, wait_until='load')
            page.evaluate("() => launchLanguages('fra')")
            assert page.locator('[data-i18n="faq_q_18"]').count() == 1
            assert 'code temporaire' in page.locator('[data-i18n="faq_a_18"]').text_content()
            page.evaluate("() => launchLanguages('eng')")
            assert 'temporary code' in page.locator('[data-i18n="faq_a_18"]').text_content()
            context.close()
            # Reproduce a running server without its newer limiter: the UI must
            # still suppress repeat uploads and notices across tabs and reloads.
            context = browser.new_context()
            sync_calls = []
            legacy_steam_checks = []
            context.route('**/online-leaderboard/settings', lambda route: route.fulfill(json={'enabled': True, 'configured': True, 'state': 'idle'}))
            def legacy_steam_status(route):
                legacy_steam_checks.append(route.request.url)
                route.fulfill(json={'connected':True})
            context.route('**/online-leaderboard/steam-status**', legacy_steam_status)
            def record_sync(route):
                sync_calls.append(route.request.method)
                route.fulfill(json={'state': 'success'})
            context.route('**/online-leaderboard/sync', record_sync)
            context.route('**/online-leaderboard/entries?**', lambda route: route.fulfill(json={'mode': 'Arena', 'entries': [], 'page': 1, 'per_page': 5, 'total': 0, 'filtered_total': 0}))
            page = context.new_page()
            page.goto(url, wait_until='load')
            page.locator('#menu_button_multi').click()
            page.wait_for_timeout(400)
            page.locator('#menu_button_multi').click()
            page.locator('#menu_button_multi').click()
            page.wait_for_timeout(700)
            if sync_calls != ['POST'] or page.locator('.online-main-status').text_content():
                raise AssertionError(('Cooldown failed across navigation', sync_calls))
            page.reload(wait_until='load')
            page.wait_for_timeout(300)
            if legacy_steam_checks:
                raise AssertionError(('A page reload checked Steam on the previous backend', legacy_steam_checks))
            page.locator('#menu_button_multi').click()
            page.wait_for_timeout(400)
            second = context.new_page()
            second.goto(url, wait_until='load')
            second.locator('#menu_button_multi').click()
            second.wait_for_timeout(400)
            if sync_calls != ['POST']:
                raise AssertionError(('Cooldown failed across reload or tabs', sync_calls))
            second.evaluate('Date.now = (() => { const original = Date.now; return () => original() + 11000; })()')
            second.locator('#menu_button_multi').click()
            second.locator('#menu_button_multi').click()
            second.wait_for_timeout(400)
            if sync_calls != ['POST', 'POST']:
                raise AssertionError(('Cooldown did not expire', sync_calls))
            context.close()

            # A requested refresh waits out the cooldown, then synchronizes and
            # reloads the table before enabling the button again.
            context = browser.new_context()
            sync_state = {'state': 'idle', 'posts': 0, 'reads': 0}
            context.route('**/online-leaderboard/settings', lambda route: route.fulfill(json={'enabled': True, 'configured': True, 'state': sync_state['state'], 'retry_after_ms': 0}))
            def queued_sync(route):
                sync_state['posts'] += 1
                sync_state['state'] = 'syncing'
                route.fulfill(json={'state': 'syncing', 'retry_after_ms': 0})
            def queued_status(route):
                sync_state['state'] = 'success'
                route.fulfill(json={'state': 'success'})
            def queued_entries(route):
                sync_state['reads'] += 1
                route.fulfill(json={'mode': 'Arena', 'entries': [], 'page': 1, 'per_page': 5, 'total': 0, 'filtered_total': 0})
            context.route('**/online-leaderboard/sync', queued_sync)
            context.route('**/online-leaderboard/status', queued_status)
            context.route('**/online-leaderboard/entries?**', queued_entries)
            page = context.new_page()
            page.goto(url, wait_until='load')
            page.locator('#menu_button_multi').click()
            page.wait_for_function("() => document.querySelector('.online-main-status').textContent.includes('synchronization')")
            if not page.locator('#leaderboard_refresh').is_disabled():
                raise AssertionError('Refresh enabled during synchronization on opening')
            page.wait_for_function("() => document.querySelector('.online-main-status').textContent.includes('Synchronized leaderboard')")
            page.wait_for_function("() => !document.querySelector('#leaderboard_refresh').disabled")
            page.locator('#leaderboard_refresh').click()
            page.wait_for_function("() => document.querySelector('.online-main-status').textContent.includes('Next refresh')")
            if not page.locator('#leaderboard_refresh').is_disabled() or sync_state['posts'] != 1:
                raise AssertionError(('Queued refresh did not wait', sync_state))
            page.evaluate('window.trackerTestDateNow = Date.now; Date.now = () => window.trackerTestDateNow() + 11000')
            page.wait_for_function("() => document.querySelector('.online-main-status').textContent.includes('synchronization')")
            if not page.locator('#leaderboard_refresh').is_disabled():
                raise AssertionError('Refresh enabled during synchronization')
            page.wait_for_function("() => !document.querySelector('#leaderboard_refresh').disabled")
            if sync_state['posts'] != 2 or sync_state['reads'] < 2:
                raise AssertionError(('Queued refresh did not complete', sync_state))
            page.locator('#leaderboard_refresh').click()
            page.wait_for_function("() => document.querySelector('.online-main-status').textContent.includes('Next refresh')")
            page.locator('#menu_button_settings').click()
            page.evaluate('Date.now = () => window.trackerTestDateNow() + 22000')
            page.wait_for_timeout(700)
            if sync_state['posts'] != 2:
                raise AssertionError(('Navigation did not cancel queued refresh', sync_state))
            context.close()

            # Consent opens Steam and sync only follows verified connection.
            context = browser.new_context()
            login_state = {'enabled': False, 'verified': False, 'pending': False, 'syncs': 0}
            sharing_choices = []
            def login_settings(route):
                if route.request.method == 'POST':
                    login_state['enabled'] = route.request.post_data_json['enabled']
                    if login_state['enabled'] and route.request.post_data_json.get('event_consent') is not True:
                        raise AssertionError('The event-specific consent was not sent')
                route.fulfill(json={'enabled': login_state['enabled'], 'configured': True, 'state': 'idle', 'steam_consent': False})
            def login_status(route):
                route.fulfill(json={'connected': login_state['verified'], 'confirmation_pending':login_state['pending']})
            def confirm_steam(route):
                if route.request.post_data_json['code'] != '12345678':
                    route.fulfill(status=400, json={'error':'invalid_code'})
                    return
                login_state['verified'] = True
                login_state['pending'] = False
                route.fulfill(json={'connected':True})
            def login_sync(route):
                if not login_state['verified']:
                    raise AssertionError('Profile synchronization began before Steam verification')
                login_state['syncs'] += 1
                route.fulfill(json={'state':'success'})
            context.route('**/online-leaderboard/settings', login_settings)
            from urllib.parse import urlencode, urlparse, parse_qs
            callback = 'https://tracker.example/api/v1/steam/callback?state=fixture&lang=eng'
            steam_login_url = 'https://steamcommunity.com/openid/login?' + urlencode({'openid.return_to':callback})
            context.route('**/online-leaderboard/steam-login', lambda route: route.fulfill(json={'url':steam_login_url}))
            context.route('**/online-leaderboard/steam-status**', login_status)
            context.route('**/online-leaderboard/steam-confirm', confirm_steam)
            context.route('**/online-leaderboard/sync', login_sync)
            def steam_consent(route):
                sharing_choices.append(route.request.post_data_json['consent'])
                route.fulfill(json={'ok':True, 'steam_consent':sharing_choices[-1]})
            context.route('**/online-leaderboard/steam-consent', steam_consent)
            recovery_requests = []
            def recovery(route):
                if route.request.method == 'GET':
                    route.fulfill(json={'installations':[{'uuid':'223e4567-e89b-42d3-a456-426614174000','name':'Ancien profil','updated_at':'2026-01-01'}]})
                else:
                    recovery_requests.append(route.request.post_data_json)
                    route.fulfill(json={'ok':True})
            context.route('**/online-leaderboard/steam-recovery', recovery)
            context.route('https://steamcommunity.com/**', lambda route: route.fulfill(status=200, body='Steam test'))
            context.route('**/online-leaderboard/entries?**', lambda route: route.fulfill(json={'mode':'Arena', 'entries':[], 'page':1, 'per_page':5, 'total':0, 'filtered_total':0}))
            page = context.new_page()
            page.goto(url, wait_until='load')
            page.wait_for_function("() => typeof window.launchLanguages === 'function'")
            page.wait_for_timeout(1000)
            page.evaluate("() => launchLanguages('fra')")
            page.locator('#menu_button_settings').click()
            page.locator('.btn_menu_settings[menu="7"]').click()
            page.locator('#online_enabled').evaluate('(element) => element.click()')
            if not page.locator('#online_dialog_text').is_visible():
                raise AssertionError('Leaderboard consent dialog did not open')
            consent_text = page.locator('#online_dialog_text').text_content()
            for detail in ('pseudo', 'langue', 'Steam', 'résultats des combats', 'statistiques locales ne sont pas importées'):
                if detail not in consent_text:
                    raise AssertionError(('Incomplete leaderboard consent dialog', detail, consent_text))
            with page.expect_popup() as popup_event:
                page.locator('#online_accept').click()
            popup = popup_event.value
            popup.wait_for_url('https://steamcommunity.com/**')
            returned = parse_qs(urlparse(popup.url).query)['openid.return_to'][0]
            if parse_qs(urlparse(returned).query).get('lang') != ['fra']:
                raise AssertionError('The tracker language was not passed to the Steam result page')
            if login_state['syncs']:
                raise AssertionError('Profile synchronized before Steam was verified')
            if not page.locator('#online_steam_code').is_visible() or page.locator('#online_accept').is_enabled():
                raise AssertionError('The confirmation code must be available while waiting for Steam')
            page.locator('#online_steam_code').fill('87654321')
            if not page.locator('#online_accept').is_enabled():
                raise AssertionError('A complete code must be confirmable without waiting for polling')
            page.locator('#online_accept').click()
            page.wait_for_function("() => document.querySelector('.online-dialog').dataset.step === 'invalid_code'")
            login_state['pending'] = True
            page.wait_for_function("() => document.querySelector('.online-dialog').dataset.step === 'code'")
            if login_state['syncs']:
                raise AssertionError('Profile synchronized before code confirmation')
            page.locator('#online_steam_code').fill('87654321')
            page.locator('#online_accept').click()
            page.wait_for_function("() => document.querySelector('.online-dialog').dataset.step === 'invalid_code'")
            page.locator('#online_steam_code').fill('12345678')
            page.locator('#online_accept').click()
            for _ in range(40):
                if login_state['syncs']:
                    break
                page.wait_for_timeout(250)
            if login_state['syncs'] != 1:
                raise AssertionError(('Steam login did not trigger synchronization', login_state))
            if not page.locator('.online-dialog').is_visible() or page.locator('#online_steam_state').get_attribute('data-state') != 'connected':
                raise AssertionError('Steam connection state did not update without a reload')
            if page.locator('.online-steam-login').count():
                raise AssertionError('A separate Steam login button is still present')
            page.locator('#online_accept').click()
            if page.locator('.online-dialog').is_visible():
                raise AssertionError('Completion did not close the participation dialog')
            steam_label = page.locator('.online-steam-state-row .form_single_left').bounding_box()
            steam_state = page.locator('#online_steam_state').bounding_box()
            if abs((steam_label['y'] + steam_label['height'] / 2) - (steam_state['y'] + steam_state['height'] / 2)) > 1:
                raise AssertionError(('Steam account label and connection state are not vertically aligned', steam_label, steam_state, page.locator('.online-steam-state-row .form_single_right').evaluate('(el) => [getComputedStyle(el).justifyContent, getComputedStyle(el).margin, getComputedStyle(el).padding]')))
            for choice in (True, False, True):
                page.locator('#online_steam').evaluate('(element) => element.click()')
                page.wait_for_timeout(100)
                if not sharing_choices or sharing_choices[-1] != choice:
                    raise AssertionError(('Steam sharing choice was not saved', sharing_choices))
            if sharing_choices != [True, False, True] or login_state['syncs'] != 1:
                raise AssertionError(('Changing Steam sharing triggered a synchronization', sharing_choices, login_state))
            with page.expect_popup() as recovery_popup_event:
                page.locator('#online_recover').click()
            recovery_popup = recovery_popup_event.value
            recovery_popup.wait_for_url('https://steamcommunity.com/**')
            page.wait_for_timeout(2500)
            if page.locator('.online-dialog').get_attribute('data-step') != 'waiting':
                raise AssertionError('Recovery ended before a connected user confirmed Steam again')
            if not page.locator('#settings_info_online_recover').count():
                raise AssertionError('Recovery help is missing')
            login_state['pending'] = True
            page.wait_for_function("() => document.querySelector('.online-dialog').dataset.step === 'code'")
            page.locator('#online_steam_code').fill('12345678')
            page.locator('#online_accept').click()
            page.wait_for_function("() => document.querySelector('.online-dialog').dataset.step === 'recovery_choose'")
            page.locator('#online_recovery_select').select_option('223e4567-e89b-42d3-a456-426614174000')
            page.locator('#online_accept').click()
            page.wait_for_function("() => document.querySelector('.online-dialog').dataset.step === 'recovery_done'")
            if recovery_requests != [{'uuid':'223e4567-e89b-42d3-a456-426614174000'}] or login_state['syncs'] != 1:
                raise AssertionError(('Recovery was not explicit or triggered synchronization', recovery_requests, login_state))
            page.locator('#online_accept').click()
            context.close()

            # An older running backend cannot confirm codes: explain that a
            # restart is needed before opening a Steam login that cannot finish.
            context = browser.new_context()
            context.route('**/online-leaderboard/settings', lambda route: route.fulfill(json={'enabled':True, 'configured':True, 'state':'idle'}))
            context.route('**/online-leaderboard/steam-status**', lambda route: route.fulfill(json={'connected':False}))
            login_attempts = []
            context.route('**/online-leaderboard/steam-login', lambda route: (login_attempts.append(True), route.fulfill(json={'url':'https://steamcommunity.com/'})))
            page = context.new_page()
            page.goto(url, wait_until='load')
            page.locator('#menu_button_settings').click()
            page.locator('.btn_menu_settings[menu="7"]').click()
            page.locator('#online_enabled').evaluate('(element) => element.click()')
            page.locator('#online_accept').click()
            page.wait_for_function("() => document.querySelector('.online-dialog').dataset.step === 'restart_required'")
            if login_attempts:
                raise AssertionError('An incompatible backend started an unusable Steam login')
            context.close()

            # Closing Steam offers retry inside the same dialog; cancelling a
            # newly started participation keeps previously published data.
            context = browser.new_context()
            cancelled = {'enabled': False, 'requests': []}
            def cancel_settings(route):
                if route.request.method == 'POST':
                    body = route.request.post_data_json
                    cancelled['requests'].append(body)
                    cancelled['enabled'] = body['enabled']
                route.fulfill(json={'enabled':cancelled['enabled'], 'configured':True, 'state':'idle', 'steam_consent':False})
            context.route('**/online-leaderboard/settings', cancel_settings)
            context.route('**/online-leaderboard/steam-status**', lambda route: route.fulfill(json={'connected':False, 'confirmation_pending':False, 'observation_only':True}))
            context.route('**/online-leaderboard/steam-login', lambda route: route.fulfill(json={'url':'https://steamcommunity.com/openid/login?test=1'}))
            context.route('https://steamcommunity.com/**', lambda route: route.fulfill(status=200, body='Steam test'))
            context.route('**/online-leaderboard/entries?**', lambda route: route.fulfill(json={'mode':'Arena', 'entries':[], 'page':1, 'per_page':5, 'total':0, 'filtered_total':0}))
            page = context.new_page()
            page.goto(url, wait_until='load')
            page.locator('#menu_button_settings').click()
            page.locator('.btn_menu_settings[menu="7"]').click()
            page.locator('#online_enabled').evaluate('(element) => element.click()')
            with page.expect_popup() as popup_event:
                page.locator('#online_accept').click()
            popup = popup_event.value
            popup.wait_for_url('https://steamcommunity.com/**')
            popup.close()
            page.wait_for_function("() => document.querySelector('.online-dialog').dataset.step === 'closed'", timeout=8000)
            with page.expect_popup() as popup_event:
                page.locator('#online_accept').click()
            retry_popup = popup_event.value
            retry_popup.wait_for_url('https://steamcommunity.com/**')
            page.locator('#online_cancel').click()
            for _ in range(20):
                if len(cancelled['requests']) >= 2:
                    break
                page.wait_for_timeout(100)
            if cancelled['enabled'] or cancelled['requests'][-1].get('remove') is not False or not retry_popup.is_closed():
                raise AssertionError(('Cancelling Steam participation was not safe', cancelled))
            page.wait_for_function("() => !document.querySelector('#online_enabled').checked")
            page.evaluate('window.open = () => null')
            page.locator('#online_enabled').evaluate('(element) => element.click()')
            page.locator('#online_accept').click()
            page.wait_for_function("() => document.querySelector('.online-dialog').dataset.step === 'blocked'")
            if not page.locator('#online_dialog_text').text_content():
                raise AssertionError('Blocked popup did not provide guidance')
            page.locator('#online_cancel').click()
            context.close()

            # Existing participants may review the new event consent later.
            context = browser.new_context()
            consent = {'pending':True, 'accepted':0}
            def existing_settings(route):
                route.fulfill(json={'enabled':True, 'configured':True, 'state':'event_consent_required' if consent['pending'] else 'idle', 'event_consent_pending':consent['pending'], 'language_shared':True, 'steam_consent':False})
            def accept_events(route):
                consent['pending'] = False
                consent['accepted'] += 1
                route.fulfill(json={'ok':True})
            context.route('**/online-leaderboard/settings', existing_settings)
            context.route('**/online-leaderboard/event-consent', accept_events)
            context.route('**/online-leaderboard/language-consent', lambda route: route.fulfill(json={'ok':True}))
            context.route('**/online-leaderboard/sync', lambda route: route.fulfill(json={'state':'success'}))
            page = context.new_page()
            page.goto(url, wait_until='load')
            page.wait_for_function("() => document.querySelector('.online-dialog').open && document.querySelector('.online-dialog').dataset.action === 'revalidate'")
            page.locator('#online_cancel').click()
            page.locator('#menu_button_settings').click()
            page.locator('.btn_menu_settings[menu="7"]').click()
            if not page.locator('.online-event-review').is_visible() or consent['accepted']:
                raise AssertionError('Declined consent could not be reviewed later')
            page.locator('.online-event-review button').click()
            page.locator('#online_accept').click()
            page.wait_for_function("() => document.querySelector('.online-event-review').hidden")
            if consent['accepted'] != 1:
                raise AssertionError('Event consent was not recorded explicitly')
            context.close()

            # A missing server configuration must be shown instead of looking
            # like a Steam button that does nothing.
            context = browser.new_context()
            context.route('**/online-leaderboard/settings', lambda route: route.fulfill(json={'enabled':True, 'configured':False, 'state':'idle', 'steam_consent':False}))
            context.route('**/online-leaderboard/steam-login', lambda route: route.fulfill(status=503, json={'error':'not_configured'}))
            context.route('**/online-leaderboard/steam-status**', lambda route: route.fulfill(status=503, json={'error':'not_configured'}))
            page = context.new_page()
            page.goto(url, wait_until='load')
            page.locator('#menu_button_settings').click()
            page.locator('.btn_menu_settings[menu="7"]').click()
            page.wait_for_function("() => document.querySelector('.online-main-status').textContent === window.uiT('online_not_configured', 'Serveur du classement non configuré.')")
            if page.locator('#online_settings_status').count():
                raise AssertionError('Ranking settings must not duplicate the main notification')
            page.locator('#online_enabled').evaluate('(element) => element.click()')
            with page.expect_popup() as popup_event:
                page.locator('#online_accept').click()
            popup = popup_event.value
            page.wait_for_function("() => document.querySelector('#online_dialog_text').textContent === window.uiT('online_not_configured', 'Serveur du classement non configuré.')")
            for _ in range(20):
                if popup.is_closed():
                    break
                page.wait_for_timeout(250)
            if not popup.is_closed():
                raise AssertionError('Unconfigured Steam window did not close')
            context.close()

            # Server migration requires a deliberate confirmation and a fresh
            # consent dialog carrying the nonce received after the transition.
            context = browser.new_context()
            transition = {'migrated':False, 'posts':[]}
            def migration_settings(route):
                if route.request.method == 'POST':
                    transition['posts'].append(route.request.post_data_json)
                    route.fulfill(json={'enabled':True, 'configured':True, 'state':'idle', 'steam_consent':False})
                else:
                    route.fulfill(json={'enabled':not transition['migrated'], 'configured':True,
                                        'state':'disabled' if transition['migrated'] else 'server_changed',
                                        'steam_consent':False, 'migration_available':not transition['migrated'],
                                        'transition_nonce':'fresh-nonce' if transition['migrated'] else None})
            def migrate_server(route):
                if route.request.post_data_json != {'confirm':True}:
                    raise AssertionError('Migration did not require explicit confirmation')
                transition['migrated'] = True
                route.fulfill(json={'ok':True})
            context.route('**/online-leaderboard/settings', migration_settings)
            context.route('**/online-leaderboard/migrate-server', migrate_server)
            page = context.new_page()
            page.on('dialog', lambda dialog: dialog.accept())
            page.goto(url, wait_until='load')
            page.locator('#menu_button_settings').click()
            page.locator('.btn_menu_settings[menu="7"]').click()
            page.wait_for_function("() => document.querySelector('.online-main-status').textContent === window.uiT('online_server_move_required', 'Une ancienne connexion utilise un autre serveur. Utilise « Utiliser le serveur public » pour continuer sans la supprimer.')")
            for width, height in [(1440, 900), (900, 700), (390, 844)]:
                page.set_viewport_size({'width':width, 'height':height})
                page.wait_for_timeout(400)
                for code in ['fra','eng','deu','ita','spaes','spaar','por','pol','rus','jap','kor','chi','zht','tha','ara']:
                    page.evaluate('(code) => launchLanguages(code)', code)
                    if page.locator('.online-server-move').evaluate('(element) => element.scrollWidth > element.clientWidth + 1'):
                        raise AssertionError(('Server transition row overflows', width, code))
            page.evaluate("() => launchLanguages('fra')")
            page.set_viewport_size({'width':1440, 'height':900})
            page.wait_for_timeout(400)
            page.locator('.online-server-move button').click()
            page.wait_for_function("() => !document.querySelector('.online-server-move-notice').hidden")
            if not transition['migrated'] or page.locator('#online_enabled').is_checked():
                raise AssertionError('Migration did not suspend participation')
            page.evaluate('window.open = () => null')
            page.locator('#online_enabled').evaluate('(element) => element.click()')
            page.locator('#online_accept').click()
            page.wait_for_function("() => document.querySelector('.online-dialog').dataset.step === 'blocked'")
            if not transition['posts'] or transition['posts'][-1].get('transition_nonce') != 'fresh-nonce':
                raise AssertionError('Fresh consent did not carry the transition nonce')
            context.close()

            # An older participation without an identity must also ask for
            # fresh consent to the public server before creating an account.
            context = browser.new_context()
            consent_posts = []
            def unbound_settings(route):
                if route.request.method == 'POST':
                    consent_posts.append(route.request.post_data_json)
                    route.fulfill(json={'enabled':True, 'configured':True, 'state':'idle', 'steam_consent':False})
                else:
                    route.fulfill(json={'enabled':True, 'configured':True, 'state':'fresh_consent_required',
                                        'steam_consent':False, 'server_consent_required':True,
                                        'transition_nonce':'legacy-nonce'})
            context.route('**/online-leaderboard/settings', unbound_settings)
            page = context.new_page()
            page.goto(url, wait_until='load')
            page.evaluate("() => { document.body.dataset.storeBuild = 'true'; window.open = () => null; }")
            page.locator('#menu_button_settings').click()
            page.locator('.btn_menu_settings[menu="7"]').click()
            page.locator('.online-server-consent-review button').click()
            if 'https://eldenringpvp.com' not in page.locator('#online_dialog_text').text_content():
                raise AssertionError('Public server was not disclosed in the consent dialog')
            page.locator('#online_accept').click()
            page.wait_for_function("() => document.querySelector('.online-dialog').dataset.step === 'blocked'")
            if not consent_posts or consent_posts[-1].get('transition_nonce') != 'legacy-nonce':
                raise AssertionError('Fresh legacy consent did not carry the transition nonce')
            context.close()

            # Partial identities and unbound pending events must direct the
            # user to support instead of suggesting deletion or going offline.
            for flag, key in [('partial_identity', 'online_server_identity_incomplete'), ('transition_blocked', 'online_server_move_blocked')]:
                context = browser.new_context()
                payload = {'enabled':True, 'configured':True, 'state':'server_changed', 'steam_consent':False,
                           'server_consent_required':flag == 'transition_blocked', flag:True}
                context.route('**/online-leaderboard/settings', lambda route: route.fulfill(json=payload))
                page = context.new_page()
                page.goto(url, wait_until='load')
                page.locator('#menu_button_settings').click()
                page.locator('.btn_menu_settings[menu="7"]').click()
                page.wait_for_function("key => document.querySelector('.online-main-status').textContent === window.uiT(key, '')", arg=key)
                if flag == 'transition_blocked' and page.locator('.online-server-consent-review').is_visible():
                    raise AssertionError('Blocked pending events offered new consent')
                context.close()
            browser.close()
    finally:
        # A Windows venv launcher can have a child interpreter holding SQLite files.
        subprocess.run(['taskkill', '/PID', str(server.pid), '/T', '/F'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        server.wait(timeout=10)
        time.sleep(.5)
