"""Check the development marker using isolated data and mocked initialization."""
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


def check(browser, url, viewport, development_build, store_build, expect_badge):
    context = browser.new_context(viewport=viewport)
    context.route('**/*', lambda route: route.continue_() if route.request.url.startswith(url + '/') else route.abort())

    def document(route):
        response = route.fetch()
        html = re.sub(r'data-store-build="(?:true|false)"',
                      'data-store-build="' + str(store_build).lower() + '"', response.text())
        route.fulfill(response=response, body=html)

    context.route(url + '/', document)

    def init(route):
        response = route.fetch()
        payload = response.json()
        payload['user'][1] = 'Tarnished'
        if development_build is None:
            payload.pop('development_build', None)
        else:
            payload['development_build'] = development_build
        route.fulfill(response=response, json=payload)

    context.route('**/init', init)
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    try:
        page.goto(url, wait_until='load')
        page.wait_for_selector('.sprit', state='detached', timeout=30000)
        name = page.locator('.sidebar-profile-name')
        badge = name.locator('.sidebar-profile-dev')
        page.wait_for_function("() => document.querySelector('.sidebar-profile-name')?.textContent.includes('Tarnished')")
        if expect_badge:
            assert name.text_content() == 'Tarnished (dev)', (development_build, store_build, name.text_content())
            assert badge.count() == 1 and badge.text_content().strip() == '(dev)'
            colors = badge.evaluate('(node) => [getComputedStyle(node).color, getComputedStyle(node.parentElement).color]')
            assert colors[0] != colors[1], colors
        else:
            assert name.text_content() == 'Tarnished', (development_build, store_build, name.text_content())
            assert badge.count() == 0
        page.evaluate("() => window.updateSidebarProfile('Second', 120)")
        assert name.text_content() == ('Second (dev)' if expect_badge else 'Second')
        assert page.locator('.sidebar-profile-level-value').text_content() == '120'
        page.evaluate("() => window.updateSidebarProfile('Second (dev)', 120)")
        assert name.text_content() == 'Second (dev)'
        assert badge.count() == (1 if expect_badge else 0)
        page.evaluate("() => window.updateSidebarProfile('<img src=x onerror=alert(1)>', 120)")
        assert '<img src=x onerror=alert(1)>' in name.text_content()
        assert name.locator('img').count() == 0
        assert badge.count() == (1 if expect_badge else 0)
        page.evaluate("() => window.updateSidebarProfile('', 120)")
        assert badge.count() == 0
        assert 'dev' not in name.text_content().lower()
        assert not errors, errors
    finally:
        context.close()


def main():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix='tracker-sidebar-dev-', ignore_cleanup_errors=True) as directory:
        env = os.environ.copy()
        env.update(APPDATA=directory, TRACKER_TEST_PORT=str(port))
        server = subprocess.Popen([sys.executable, str(ROOT / 'tests/support/browser_server.py')], cwd=ROOT, env=env,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        url = 'http://127.0.0.1:' + str(port)
        try:
            for _ in range(100):
                try:
                    urllib.request.urlopen(url, timeout=1).close()
                    break
                except OSError:
                    if server.poll() is not None:
                        raise RuntimeError('Isolated browser server exited')
                    time.sleep(.1)
            else:
                raise RuntimeError('Isolated browser server did not start')
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(executable_path=str(CHROME), headless=True)
                try:
                    for viewport in ({'width': 1440, 'height': 900}, {'width': 390, 'height': 844}):
                        for development, store, expected in ((True, True, True), (False, False, False),
                                                              (None, False, True), (None, True, False)):
                            check(browser, url, viewport, development, store, expected)
                finally:
                    browser.close()
            print('Development badge: initialization, profile updates and responsive colors passed.')
        finally:
            if os.name == 'nt':
                subprocess.run(['taskkill', '/PID', str(server.pid), '/T', '/F'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            else:
                server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()


if __name__ == '__main__':
    main()
