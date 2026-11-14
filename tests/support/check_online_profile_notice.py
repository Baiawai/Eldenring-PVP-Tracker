"""Browser checks for profile-required notices with isolated data and no network.

Run from the project root with its virtual-environment Python. The test server
uses a private APPDATA, temporary runtime images, and a separate ephemeral port.
"""
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
LANGUAGES = ['fra', 'eng', 'deu', 'ita', 'spaes', 'spaar', 'por', 'pol',
             'rus', 'jap', 'kor', 'chi', 'zht', 'tha', 'ara']


def scenario(browser, url, state='profile_required', viewport=None):
    context = browser.new_context(viewport=viewport or {'width': 1440, 'height': 900})
    context.route('**/*', lambda route: route.continue_()
                  if route.request.url.startswith(url + '/') else route.abort())
    payload = {'enabled': True, 'configured': True, 'state': state,
               'steam_status_observe': False, 'steam_consent': False}
    context.route('**/online-leaderboard/settings', lambda route: route.fulfill(json=payload))
    context.route('**/online-leaderboard/sync', lambda route: route.fulfill(json={'state': state}))
    context.route('**/online-leaderboard/status', lambda route: route.fulfill(json={'state': state}))
    context.route('**/online-leaderboard/entries?**', lambda route: route.fulfill(json={
        'mode': 'Arena', 'entries': [], 'page': 1, 'per_page': 5, 'total': 0, 'filtered_total': 0}))
    reads = []

    def profile(route):
        reads.append(route.request.post_data)
        route.fulfill(json={'request': 'waiting'})

    context.route('**/profile-capture', profile)
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(url, wait_until='load')
    page.wait_for_function("() => document.querySelector('.online-main-status') !== null")
    page.wait_for_timeout(1800)
    return context, page, reads, errors


def check(browser, url):
    context, page, reads, errors = scenario(browser, url)
    try:
        notice = page.locator('.online-main-status')
        action = notice.locator('.online-profile-action')
        action.wait_for(state='visible')
        for language in LANGUAGES:
            page.evaluate('(code) => launchLanguages(code)', language)
            expected = page.evaluate('''code => code === 'fra'
                ? ['Ajoute un pseudo dans ton profil avant la synchronisation.', 'Récupérer mon profil']
                : [ELDEN_UI_PACKS[code].modern.online_profile_required,
                   ELDEN_UI_PACKS[code].modern.profile_capture_start]''', language)
            assert expected[0] in notice.inner_text(), (language, notice.inner_text(), expected)
            assert action.inner_text() == expected[1], (language, action.inner_text(), expected)
        page.evaluate("() => launchLanguages('fra')")
        assert action.evaluate('(el) => getComputedStyle(el).pointerEvents') == 'auto'
        action.focus()
        assert action.evaluate('(el) => document.activeElement === el')
        page.keyboard.press('Enter')
        page.locator('.settings-panel').wait_for(state='visible')
        assert page.locator('.btn_menu_settings[menu="3"]').evaluate('(e) => e.classList.contains("active_setting")')
        assert page.locator('#profile_capture_panel').is_visible()
        page.wait_for_function('() => !document.querySelector("#profile_capture_instructions").hidden')
        assert reads and 'action=read' in reads[0], reads
        assert not errors, errors
    finally:
        context.close()

    # An already-running capture must not be restarted when following the
    # notice again; the next poll is scheduled two seconds after the first.
    context, page, reads, errors = scenario(browser, url, viewport={'width': 390, 'height': 844})
    try:
        page.locator('.online-profile-action').click()
        page.locator('#profile_capture_panel').wait_for(state='visible')
        assert len(reads) == 1, reads
        page.locator('.btn_menu_settings[menu="7"]').click()
        page.locator('.online-profile-action').click()
        assert len(reads) == 1, ('Existing capture restarted', reads)
        assert page.locator('#profile_capture_panel').is_visible()
        assert not errors, errors
    finally:
        context.close()

    # Unrelated errors must remain plain status messages.
    context, page, _, errors = scenario(browser, url, state='offline')
    try:
        page.wait_for_function("() => !!document.querySelector('.online-main-status').textContent")
        assert page.locator('.online-main-status .online-profile-action').count() == 0
        assert not errors, errors
    finally:
        context.close()

    # A refresh countdown takes precedence over a profile-required message.
    context, page, _, errors = scenario(browser, url)
    try:
        page.locator('#menu_button_multi').click()
        page.wait_for_timeout(500)
        page.locator('#leaderboard_refresh').click()
        page.wait_for_function("() => document.querySelector('.online-main-status').textContent.includes('refresh') || document.querySelector('.online-main-status').textContent.includes('actualisation')")
        assert page.locator('.online-main-status .online-profile-action').count() == 0
        assert not errors, errors
    finally:
        context.close()


def main():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix='tracker-profile-notice-', ignore_cleanup_errors=True) as directory:
        env = os.environ.copy()
        env.update(APPDATA=directory, TRACKER_TEST_PORT=str(port))
        server = subprocess.Popen([sys.executable, str(ROOT / 'tests/support/browser_server.py')],
                                  cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
                    check(browser, url)
                finally:
                    browser.close()
            print('Online profile notice browser checks passed.')
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
