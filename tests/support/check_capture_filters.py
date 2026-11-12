"""Browser checks for capture result filters and leaderboard navigation.

Uses a temporary APPDATA and an isolated image directory; no live tracker data.
Run with Playwright installed: python tests/support/check_capture_filters.py
"""
import base64
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

root = Path(__file__).resolve().parents[2]
chrome = Path(os.environ.get('ProgramFiles', r'C:\Program Files')) / 'Google/Chrome/Application/chrome.exe'
with socket.socket() as sock:
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
with tempfile.TemporaryDirectory(prefix='tracker-capture-ui-', ignore_cleanup_errors=True) as directory:
    env = os.environ.copy()
    env.update(APPDATA=directory, TRACKER_TEST_PORT=str(port))
    seed = '''from flask import Flask
app=Flask(__name__)
from application.init import create_tables, add_capture
create_tables()
cases=[('Arena',1,0,0),('Arena',0,1,0),('Arena',0,0,1),('Invasion',1,0,0),('Invasion',0,1,0),('Defense',1,0,0)]
for n in range(72):
 mode,v,d,e=cases[n%len(cases)]
 add_capture('Player '+str(n),v,d,e,15,'01/01/2025',mode,'aW1hZ2U=')
'''
    py = sys.executable
    subprocess.run([str(py), '-c', seed], cwd=root, env=env, check=True, capture_output=True)
    server = subprocess.Popen([str(py), str(root / 'tests/support/browser_server.py')], cwd=root, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        url = f'http://127.0.0.1:{port}'
        for _ in range(100):
            try:
                urllib.request.urlopen(url, timeout=1).close()
                break
            except OSError:
                time.sleep(.1)
        else:
            raise RuntimeError('Isolated server did not start')
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=str(chrome), headless=True)
            for width, height in [(1440,900), (390,844)]:
                page = browser.new_page(viewport={'width':width,'height':height})
                errors, sync_requests, next_requests = [], [], []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.on('request', lambda request: sync_requests.append(request.url) if '/syncMulti' in request.url else None)
                page.on('request', lambda request: next_requests.append(request.url) if '/nextCaptures' in request.url else None)
                page.goto(url, wait_until='load')
                page.wait_for_selector('.sprit', state='detached', timeout=15000)
                page.wait_for_function("() => document.querySelectorAll('.capture-scroll .para_capture').length === 50")
                page.evaluate("document.getElementById('menu_button_captures').click()")
                page.wait_for_function("() => getComputedStyle(document.querySelector('.capture-toolbar')).display !== 'none'")
                result = page.locator('#capture_result')
                assert result.count() == 1 and page.locator('.choice_capture').count() == 0
                page.evaluate("launchLanguages('chi')")
                assert result.locator('option[value=all]').text_content() == '所有结果'
                assert result.locator('option[value=victory_text]').text_content() == page.evaluate("ELDEN_UI_PACKS.chi.modern.victories")
                result.select_option('victory_text')
                page.wait_for_function("() => document.querySelectorAll('.capture-scroll .para_capture').length === 36")
                assert page.locator('.capture-scroll .para_capture:not(.victory_text)').count() == 0
                page.locator('#capture_mode').select_option('Invasion')
                page.wait_for_function("() => document.querySelectorAll('.capture-scroll .para_capture').length === 12")
                assert result.input_value() == 'victory_text'
                assert result.locator('option[value=egality_text]').get_attribute('disabled') is not None
                result.select_option('all')
                page.wait_for_function("() => document.querySelectorAll('.capture-scroll .para_capture').length === 24")
                page.locator('#capture_mode').select_option('Arena')
                result.select_option('egality_text')
                page.wait_for_function("() => document.querySelectorAll('.capture-scroll .para_capture').length === 12 && document.querySelectorAll('.capture-scroll .para_capture:not(.egality_text)').length === 0")
                page.locator('#capture_mode').select_option('Invasion')
                page.wait_for_function("() => document.querySelector('#capture_result').value === 'all' && document.querySelectorAll('.capture-scroll .para_capture').length === 24")
                page.locator('#capture_mode').select_option('all')
                page.wait_for_function("() => document.querySelectorAll('.capture-scroll .para_capture').length === 72")
                page.locator('.capture-scroll').evaluate('(el) => { el.scrollTop = el.scrollHeight; el.dispatchEvent(new Event("scroll")); }')
                page.wait_for_timeout(300)
                assert len(next_requests) == 0, next_requests
                assert page.locator('.capture-scroll .para_capture').count() == 72
                page.locator('.capture-scroll .para_capture').last.click()
                assert page.locator('#capture_viewer_overlay').is_visible()
                page.locator('.capture-viewer-close').click()
                toolbar=page.locator('.capture-toolbar')
                assert toolbar.evaluate('el => el.scrollWidth <= el.clientWidth + 1')
                page.screenshot(path=str(root/'build'/f'capture-filter-{width}.png'))
                page.evaluate("document.getElementById('menu_button_multi').click()")
                assert page.locator('.panel_multi_body').is_visible()
                assert page.locator('#leaderboard_content_toggle').count() == 0
                assert not sync_requests, sync_requests
                page.evaluate("document.body.dataset.storeBuild = 'true'")
                assert page.locator('#menu_button_multi').is_visible()
                assert not errors, errors
                print('Capture filters and leaderboard navigation OK:',width,flush=True)
                page.close()
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)
        time.sleep(1)
