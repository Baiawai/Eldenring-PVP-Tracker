"""Optional browser test using Playwright and installed Chrome, with isolated data."""
import os
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
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(url, wait_until='load')
                page.wait_for_timeout(1500)
                for code in ['fra','eng','deu','ita','spaes','spaar','por','pol','rus','jap','kor','chi','zht','tha','ara']:
                    page.evaluate('(code) => launchLanguages(code)', code)
                    expected = page.evaluate('(code) => code === "fra" ? window.interface_fr[0] : window.ELDEN_UI_PACKS[code].legacy[0]', code)
                    actual = page.locator('.scoreboard .victory').first.text_content()
                    if actual != expected:
                        raise AssertionError((width, code, actual, expected))
                page.evaluate("() => { launchLanguages('fra'); launchLanguages('spaes'); }")
                page.wait_for_timeout(500)
                if errors:
                    raise AssertionError((width, errors))
                page.evaluate("() => launchLanguages('fra')")
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
                image_bytes = io.BytesIO()
                Image.new('RGB', (50, 60), '#876b42').save(image_bytes, format='JPEG')
                avatar = base64.b64encode(image_bytes.getvalue()).decode('ascii')
                ranking = [0, 0, 'Malenia', 38, 12, 1, 'fra', '74.51', avatar, '', 52, 0, 0, 0, 0, 0, 0, 8.5, 150, 0, 0]
                suspicious = [0, 0, '<img src=x onerror=alert(1)>', 2, 1, 0, 'eng', '66.67', '', '', 3, 0, 0, 0, 0, 0, 0, 0.2, 100, 0, 0]
                page.route('**/syncMulti', lambda route: route.fulfill(json={'request':'success', 'online':False, 'datas':[ranking, suspicious]}))
                page.locator('#menu_button_multi').click()
                page.wait_for_timeout(600)
                if not page.locator('#leaderboard_status').is_visible() or page.locator('#table_multi tbody tr').count() != 2:
                    raise AssertionError(('Offline leaderboard unavailable', width))
                if page.locator('#table_multi tbody tr').nth(1).locator('td').nth(2).text_content() != suspicious[2]:
                    raise AssertionError(('Leaderboard player name not escaped', width))
                if page.locator('#table_multi tbody tr').nth(1).locator('td').nth(2).locator('img').count():
                    raise AssertionError(('Untrusted leaderboard markup rendered', width))
                search_box = page.locator('#table_multi_filter input').bounding_box()
                if search_box['x'] < 0 or search_box['x'] + search_box['width'] > width + 1:
                    raise AssertionError(('Leaderboard search clipped', width, search_box))
                page.screenshot(path=str(ROOT / 'build' / ('leaderboard-ui-' + str(width) + '.png')), full_page=True)
                page.locator('#table_multi tbody tr').first.click()
                card = page.locator('#leaderboard_player_dialog')
                if not card.is_visible() or card.locator('#leaderboard_player_name').text_content() != 'Malenia':
                    raise AssertionError(('Player card failed to open', width))
                if card.locator('[data-player-stat="victories"]').text_content() != '38' or card.locator('[data-player-stat="rate"]').text_content() != '74,51 %':
                    raise AssertionError(('Player stats incorrect', width))
                if not card.locator('#leaderboard_player_avatar').is_visible():
                    raise AssertionError(('Player avatar not visible', width))
                previous = card.locator('.leaderboard-player-prev')
                following = card.locator('.leaderboard-player-next')
                close_button = card.locator('.leaderboard-player-close')
                if not previous.is_disabled() or following.is_disabled():
                    raise AssertionError(('Initial player navigation incorrect', width))
                if close_button.evaluate('(el) => getComputedStyle(el).borderTopWidth') != '0px':
                    raise AssertionError(('Close button has a border', width))
                close_box = close_button.bounding_box()
                card_box = card.locator('.leaderboard-player-card').bounding_box()
                if abs((card_box['x'] + card_box['width']) - (close_box['x'] + close_box['width'])) > 8:
                    raise AssertionError(('Close button not in corner', width))
                page.screenshot(path=str(ROOT / 'build' / ('player-card-ui-' + str(width) + '.png')), full_page=True)
                following.click()
                if card.locator('#leaderboard_player_name').text_content() != suspicious[2] or not following.is_disabled() or previous.is_disabled():
                    raise AssertionError(('Next player incorrect', width))
                page.keyboard.press('ArrowLeft')
                if card.locator('#leaderboard_player_name').text_content() != 'Malenia':
                    raise AssertionError(('Previous player keyboard shortcut failed', width))
                page.keyboard.press('Escape')
                if card.is_visible():
                    raise AssertionError(('Player card failed to close with Escape', width))
                if not page.locator('#table_multi tbody tr').first.evaluate('(row) => document.activeElement === row'):
                    raise AssertionError(('Player card did not restore focus', width))
                page.locator('#table_multi_filter input').fill('Malenia')
                if page.locator('#table_multi tbody tr').count() != 1:
                    raise AssertionError(('Leaderboard search failed', width))
                page.locator('#table_multi tbody tr').first.click()
                if not previous.is_disabled() or not following.is_disabled():
                    raise AssertionError(('Player navigation ignored filter', width))
                close_button.click()
                page.locator('#table_multi_filter input').fill('')
                page.evaluate("() => $('#table_multi').DataTable().order([5, 'desc']).page.len(1).draw()")
                if page.locator('#table_multi tbody tr').count() != 1 or page.locator('#table_multi tbody tr').first.locator('td').nth(2).text_content() != 'Malenia':
                    raise AssertionError(('Leaderboard sorting or pagination failed', width))
                page.locator('#table_multi tbody tr').first.click()
                following.click()
                if card.locator('#leaderboard_player_name').text_content() != suspicious[2]:
                    raise AssertionError(('Player navigation across pages failed', width))
                close_button.click()
                page.evaluate("() => $('#table_multi').DataTable().order([5, 'asc']).page.len(1).draw()")
                page.locator('#table_multi tbody tr').first.click()
                if card.locator('#leaderboard_player_name').text_content() != suspicious[2]:
                    raise AssertionError(('Player sort order ignored', width))
                following.click()
                if card.locator('#leaderboard_player_name').text_content() != 'Malenia':
                    raise AssertionError(('Next player did not follow sort order', width))
                close_button.click()
                page.evaluate("() => $('#table_multi').DataTable().order([5, 'desc']).page.len(1).draw()")
                page.evaluate("() => $('#table_multi').DataTable().page('next').draw('page')")
                if page.locator('#table_multi tbody tr').first.locator('td').nth(2).text_content() != suspicious[2]:
                    raise AssertionError(('Leaderboard next page failed', width))
                page.locator('#table_multi tbody tr').first.focus()
                page.keyboard.press('Enter')
                if not card.is_visible() or not card.locator('#leaderboard_player_no_avatar').is_visible() or card.locator('#leaderboard_player_name img').count():
                    raise AssertionError(('Keyboard card or avatar fallback failed', width))
                card.locator('.leaderboard-player-close').click()
                page.route('**/syncMulti', lambda route: route.fulfill(json={'request':'error'}))
                page.locator('#leaderboard_refresh').click()
                page.wait_for_timeout(400)
                if 'profil' not in page.locator('#leaderboard_status').text_content().lower() and 'pseudo' not in page.locator('#leaderboard_status').text_content().lower():
                    raise AssertionError(('Missing profile status unavailable', width))
                page.locator('#menu_button_multi').click()
                page.locator('#menu_button_settings').click()
                page.locator('.btn_menu_settings[menu="4"]').click()
                if not page.locator('#close_nav').is_visible() or not page.locator('#close_app').is_visible():
                    raise AssertionError(('Settings buttons unavailable', width))
                page.screenshot(path=str(ROOT / 'build' / ('settings-ui-' + str(width) + '.png')), full_page=True)
                page.locator('#menu_button_settings').click()
                information = page.locator('#information_panel')
                page.locator('#menu_button_information').click()
                if not information.is_visible() or information.locator('.faq-item').count() != 14:
                    raise AssertionError(('Information FAQ unavailable', width))
                information.locator('.faq-item summary').first.click()
                if not information.locator('.faq-item p').first.is_visible():
                    raise AssertionError(('FAQ answer did not open', width))
                for code in ['eng','deu','ita','spaes','spaar','por','pol','rus','jap','kor','chi','zht','tha','ara']:
                    page.evaluate('(code) => launchLanguages(code)', code)
                    if information.locator('.faq-item summary').first.text_content() != page.evaluate('(code) => ELDEN_UI_PACKS[code].modern.faq_q_01', code):
                        raise AssertionError(('FAQ language did not change', width, code))
                page.evaluate("() => launchLanguages('fra')")
                if information.locator('.information-contact a').get_attribute('href') != 'mailto:gael.pitras@gmail.com':
                    raise AssertionError(('FAQ contact missing', width))
                page.screenshot(path=str(ROOT / 'build' / ('information-ui-' + str(width) + '.png')), full_page=True)
                page.locator('#menu_button_info').click()
                if information.is_visible() or not page.locator('#stats_panel').is_visible():
                    raise AssertionError(('FAQ navigation did not close', width))
                page.locator('#menu_button_info').click()
                if width <= 760:
                    content = page.locator('.app-content').bounding_box()
                    if content['width'] < width * .95:
                        raise AssertionError(('Content too narrow', width, content))
                    counters = page.locator('.scoreboard li').all()
                    for counter in counters:
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
            browser.close()
    finally:
        # A Windows venv launcher can have a child interpreter holding SQLite files.
        subprocess.run(['taskkill', '/PID', str(server.pid), '/T', '/F'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        server.wait(timeout=10)
        time.sleep(.5)
