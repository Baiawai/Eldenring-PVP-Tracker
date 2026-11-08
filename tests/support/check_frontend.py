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
                leaderboard_requests = []
                page.on('request', lambda request: leaderboard_requests.append(request.url) if '/syncMulti' in request.url else None)
                page.locator('#menu_button_multi').click()
                page.wait_for_timeout(400)
                if not page.locator('#leaderboard_status').is_visible() or 'désactivé' not in page.locator('#leaderboard_status').text_content():
                    raise AssertionError(('Disabled leaderboard message missing', width))
                if page.locator('.panel_multi_body').is_visible() or page.locator('#leaderboard_refresh').is_visible():
                    raise AssertionError(('Disabled leaderboard controls visible', width))
                if leaderboard_requests:
                    raise AssertionError(('Disabled leaderboard sent requests', leaderboard_requests))
                page.screenshot(path=str(ROOT / 'build' / ('leaderboard-ui-' + str(width) + '.png')), full_page=True)
                page.locator('#menu_button_multi').click()
                page.locator('#menu_button_settings').click()
                page.locator('.btn_menu_settings[menu="4"]').click()
                if not page.locator('#close_nav').is_visible() or not page.locator('#close_app').is_visible():
                    raise AssertionError(('Settings buttons unavailable', width))
                page.screenshot(path=str(ROOT / 'build' / ('settings-ui-' + str(width) + '.png')), full_page=True)
                page.locator('#menu_button_settings').click()
                information = page.locator('#information_panel')
                page.locator('#menu_button_information').click()
                if not information.is_visible() or information.locator('.faq-item').count() != 17:
                    raise AssertionError(('Information FAQ unavailable', width))
                information.locator('.faq-item summary').first.click()
                if not information.locator('.faq-item p').first.is_visible():
                    raise AssertionError(('FAQ answer did not open', width))
                for code in ['eng','deu','ita','spaes','spaar','por','pol','rus','jap','kor','chi','zht','tha','ara']:
                    page.evaluate('(code) => launchLanguages(code)', code)
                    if information.locator('.faq-item summary').first.text_content() != page.evaluate('(code) => ELDEN_UI_PACKS[code].modern.faq_q_01', code):
                        raise AssertionError(('FAQ language did not change', width, code))
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
            browser.close()
    finally:
        # A Windows venv launcher can have a child interpreter holding SQLite files.
        subprocess.run(['taskkill', '/PID', str(server.pid), '/T', '/F'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        server.wait(timeout=10)
        time.sleep(.5)
