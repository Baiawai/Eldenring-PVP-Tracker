"""Check Store ping UI on a temporary server, with no Steam or real data."""
import os
import re
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


def check(browser, url, store):
    context = browser.new_context(viewport={'width': 1440, 'height': 900})
    context.route('**/*', lambda route: route.continue_() if route.request.url.startswith(url + '/') else route.abort())

    def document(route):
        response = route.fetch()
        html = re.sub(r'data-store-build="(?:true|false)"',
                      'data-store-build="' + str(store).lower() + '"', response.text())
        route.fulfill(response=response, body=html)

    context.route(url + '/', document)
    ping = {'mode': 'admin_required'}
    context.route('**/steam-peers', lambda route: route.fulfill(json={
        'status': 'active', 'enabled': True, 'ping_mode': ping['mode'], 'peers': []}))
    context.route('**/steam-ping', lambda route: route.fulfill(json={'request': 'success'}))
    page = context.new_page()
    try:
        page.goto(url, wait_until='load')
        page.wait_for_selector('.sprit', state='detached', timeout=30000)
        page.locator('#menu_button_settings').click()
        page.locator('.btn_menu_settings[menu="5"]').click()
        button = page.locator('#steam_ping_activate')
        help_text = page.locator('#steam_ping_help')
        status = page.locator('#steam_ping_status')
        if store:
            assert button.is_hidden()
            assert help_text.get_attribute('hidden') is not None
            page.wait_for_function("() => document.querySelector('#steam_ping_status').textContent.includes('Steam')")
            assert 'administrateur' not in status.text_content().lower()
            # A stale page can dispatch an old manual action even though the
            # Store button is hidden. The next steam_only update must clear
            # the pending admin prompt without waiting for the 30 s timeout.
            ping['mode'] = 'steam_only'
            button.evaluate("node => node.dispatchEvent(new MouseEvent('click', {bubbles:true}))")
            page.wait_for_function("() => document.querySelector('#steam_ping_status').textContent === window.uiT('steam_ping_requesting', 'Confirme la demande administrateur Windows.')")
            page.wait_for_function("() => document.querySelector('#steam_ping_status').textContent === window.uiT('steam_ping_steam_only', 'Le ping Steam est affiché lorsqu’il est disponible.')", timeout=10000)
        else:
            assert button.is_visible()
            assert help_text.get_attribute('hidden') is None
        print('Store ping UI:' if store else 'Development ping UI:', 'passed')
    finally:
        context.close()


def main():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    url = 'http://127.0.0.1:' + str(port)
    with tempfile.TemporaryDirectory(prefix='tracker-store-ping-', ignore_cleanup_errors=True) as directory:
        env = os.environ.copy()
        env.update(APPDATA=directory, LOCALAPPDATA=directory, TRACKER_TEST_PORT=str(port))
        server = subprocess.Popen([sys.executable, str(ROOT / 'tests/support/browser_server.py')],
                                  cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
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
                try:
                    check(browser, url, True)
                    check(browser, url, False)
                finally:
                    browser.close()
        finally:
            if os.name == 'nt':
                subprocess.run(['taskkill', '/PID', str(server.pid), '/T', '/F'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            else:
                server.terminate()
            server.wait(timeout=10)


if __name__ == '__main__':
    main()
