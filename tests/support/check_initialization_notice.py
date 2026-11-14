"""Check first-run notices in a browser with isolated data and no game."""
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
CHROME = Path(os.environ.get('ProgramFiles', r'C:\Program Files')) / 'Google/Chrome/Application/chrome.exe'
with socket.socket() as sock:
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
with tempfile.TemporaryDirectory(prefix='tracker-initial-notice-', ignore_cleanup_errors=True) as directory:
    env = os.environ.copy()
    env.update(APPDATA=directory, TRACKER_TEST_PORT=str(port))
    server = subprocess.Popen([sys.executable, str(ROOT / 'tests/support/browser_server.py')], cwd=ROOT, env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        url = 'http://127.0.0.1:' + str(port)
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
            page = browser.new_page(viewport={'width':1440, 'height':900})
            page.route('**/initialization-notice', lambda route: route.fulfill(json={'notice':{'state':'ready', 'log_available':False}}))
            page.route('**/online-leaderboard/settings', lambda route: route.fulfill(json={'enabled':True, 'configured':True, 'state':'profile_required'}))
            page.route('**/online-leaderboard/sync', lambda route: route.fulfill(json={'state':'profile_required'}))
            page.route('**/online-leaderboard/status', lambda route: route.fulfill(json={'state':'profile_required'}))
            def slow_init(route):
                time.sleep(6)  # A slow startup must not consume the notice behind the splash.
                route.continue_()
            page.route('**/init', slow_init)
            page.goto(url, wait_until='load')
            page.wait_for_selector('.sprit', state='detached', timeout=30000)
            page.wait_for_function("['initialization', 'initialisation'].some(word => (document.querySelector('.online-main-status')?.textContent || '').toLowerCase().includes(word))", timeout=10000)
            assert page.locator('.initialization-notice').count() == 0
            page.evaluate("launchLanguages('fra')")
            assert 'Initialisation terminée' in page.locator('.online-main-status').inner_text()
            assert page.locator('.online-main-status .online-profile-action').count() == 0
            page.evaluate('''() => {
                const node = document.querySelector('.online-main-status');
                window.initializationFaded = node.classList.contains('is-leaving');
                new MutationObserver(() => {
                    if (node.classList.contains('is-leaving')) window.initializationFaded = true;
                }).observe(node, {attributes:true, attributeFilter:['class']});
            }''')
            page.wait_for_function('window.initializationFaded === true', timeout=8000)
            page.wait_for_function("document.querySelector('.online-main-status .online-profile-action') !== null", timeout=3000)
            assert 'profil' in page.locator('.online-main-status').inner_text().lower()
            page.close()

            page = browser.new_page(viewport={'width':1440, 'height':900})
            page.route('**/initialization-notice', lambda route: route.fulfill(json={'notice':{'state':'failed', 'log_available':True}}))
            page.route('**/initialization-error-log', lambda route: route.fulfill(json={'opened':True}))
            page.route('**/online-leaderboard/settings', lambda route: route.fulfill(json={'enabled':False, 'configured':True, 'state':'idle'}))
            page.goto(url, wait_until='load')
            panel = page.locator('.initialization-notice')
            panel.wait_for(state='visible', timeout=10000)
            assert panel.get_attribute('role') == 'alert'
            assert panel.locator('button').count() == 2
            with page.expect_response('**/initialization-error-log'):
                panel.locator('button').first.click()
            assert panel.is_visible()
            page.close()
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)
