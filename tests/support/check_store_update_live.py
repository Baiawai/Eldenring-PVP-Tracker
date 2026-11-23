"""Check that a running interface opens the mandatory Store update screen."""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from flask import Flask, request
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from application import store_update


def update_page():
    app = Flask(__name__, template_folder=str(ROOT / 'templates'), static_folder=str(ROOT / 'static'))
    packs = json.loads((ROOT / 'application/locales/ui_packs.json').read_text(encoding='utf-8'))
    app.before_request(lambda: store_update.gate_response(request, lambda: 'fra', lambda: packs))
    app.add_url_rule('/', 'index', lambda: 'tracker')
    try:
        store_update._REQUIRED = True
        with app.test_client() as client:
            response = client.get('/')
            assert response.status_code == 200
            return response.get_data(as_text=True)
    finally:
        store_update._REQUIRED = False


def main():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    chrome = Path(os.environ.get('ProgramFiles', r'C:\Program Files')) / 'Google/Chrome/Application/chrome.exe'
    with tempfile.TemporaryDirectory(prefix='tracker-update-browser-', ignore_cleanup_errors=True) as directory:
        env = os.environ.copy()
        env.update(APPDATA=directory, LOCALAPPDATA=directory, TRACKER_TEST_PORT=str(port), TRACKER_TEST_NO_STEAM='1')
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
            html = update_page()
            state = {'required': False, 'blocked_polls': 0, 'exit_requests': [], 'version_polls': 0}
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(executable_path=str(chrome), headless=True)
                page = browser.new_page(viewport={'width': 1440, 'height': 900})

                def intercept_status(route):
                    if state['required']:
                        state['blocked_polls'] += 1
                        route.fulfill(status=423, json={'error': 'store_update_required'})
                    else:
                        route.continue_()

                def intercept_home(route):
                    if state['required'] and route.request.is_navigation_request():
                        route.fulfill(status=200, content_type='text/html; charset=utf-8', body=html)
                    else:
                        route.continue_()

                def intercept_exit(route):
                    state['exit_requests'].append(route.request.method)
                    route.fulfill(status=200, json={'success': True})

                def intercept_update_status(route):
                    state['version_polls'] += 1
                    if state['version_polls'] == 1:
                        route.fulfill(json={'available_version': None, 'version_source': None, 'lookup_pending': True})
                    else:
                        route.fulfill(json={'available_version': '1.0.12.0', 'version_source': 'site', 'lookup_pending': False})

                page.route('**/monitor-status', intercept_status)
                page.route('**/exit', intercept_exit)
                page.route('**/store-update-status', intercept_update_status)
                page.route(url + '/', intercept_home)
                page.goto(url + '/', wait_until='load')
                page.wait_for_selector('#start', timeout=15000)
                assert page.locator('.update-panel').count() == 0
                state['required'] = True
                page.wait_for_selector('.update-panel', timeout=12000)
                assert state['blocked_polls'] > 0
                assert page.locator('.update-panel h1').text_content().strip() == 'Mise à jour requise'
                assert page.locator('.update-button').get_attribute('href') == store_update.STORE_URL
                assert 'ferme le tracker' in page.locator('.update-instruction').inner_text().lower()
                page.wait_for_function("document.querySelector('#update-available-version')?.textContent.trim() === '1.0.12.0'", timeout=8000)
                assert 'indicative' in page.locator('#update-available-label').inner_text().lower()
                assert state['version_polls'] == 2
                # Prevent only the external OS protocol during the test; the
                # application's click handler must not cancel it in production.
                page.evaluate("""() => {
                    const original = window.fetch;
                    window.fetch = (...args) => {
                        if (args[0] === '/exit') window.testExitOptions = args[1];
                        return original(...args);
                    };
                    document.addEventListener('click', event => {
                        if (event.target.closest('.update-button')) event.preventDefault();
                    });
                }""")
                page.locator('.update-button').click()
                page.locator('.update-button').click()
                page.wait_for_timeout(800)
                assert state['exit_requests'] == ['POST'], state['exit_requests']
                assert page.evaluate("window.testExitOptions.credentials") == 'same-origin'
                assert page.evaluate("window.testExitOptions.keepalive") is True
                assert not page.is_closed()
                assert page.locator('.update-panel').is_visible()

                # A late site result must never replace an actual Store value.
                second = browser.new_page(viewport={'width': 390, 'height': 844})
                late = {'calls': 0}

                def intercept_late_status(route):
                    late['calls'] += 1
                    if late['calls'] == 1:
                        route.fulfill(json={'available_version': '1.0.13.0', 'version_source': 'store', 'lookup_pending': True})
                    else:
                        route.fulfill(json={'available_version': '1.0.99.0', 'version_source': 'site', 'lookup_pending': False})

                second.route(url + '/', lambda route: route.fulfill(status=200, content_type='text/html; charset=utf-8', body=html))
                second.route('**/store-update-status', intercept_late_status)
                second.goto(url + '/', wait_until='load')
                second.wait_for_function("document.querySelector('#update-available-version')?.textContent.trim() === '1.0.13.0'", timeout=8000)
                second.wait_for_timeout(2200)
                assert late['calls'] == 2
                assert second.locator('#update-available-version').text_content().strip() == '1.0.13.0'
                assert 'indicative' not in second.locator('#update-available-label').inner_text().lower()
                assert second.locator('body').evaluate('(node) => node.scrollWidth <= node.clientWidth + 1')
                second.close()
                browser.close()
            print('The update screen opens and requests one tracker shutdown without closing its tab.')
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()


if __name__ == '__main__':
    main()
