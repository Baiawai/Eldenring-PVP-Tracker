"""Browser checks with synthetic data. Run with the project Python and Chrome."""
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright
from check_online_profile_notice import CHROME

ROOT = Path(__file__).resolve().parents[2]


def check(browser, url, viewport):
    context = browser.new_context(viewport=viewport)
    context.route('**/*', lambda route: route.continue_() if route.request.url.startswith(url + '/') else route.abort())
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    try:
        page.goto(url, wait_until='load')
        page.wait_for_selector('.sprit', state='detached', timeout=15000)
        page.wait_for_function("() => document.querySelectorAll('.capture-scroll .para_capture').length === 50")
        page.evaluate("document.getElementById('menu_button_captures').click(); launchLanguages('fra')")
        arena = page.locator('.capture-scroll .para_capture[data-capture-steam-name="Arena Steam"]')
        arena_without_name = page.locator('.capture-scroll .para_capture[data-capture-mode="Arena"][data-capture-steam-name=""][data-capture-opponent=""]')
        defense = page.locator('.capture-scroll .para_capture[data-capture-steam-name="Defense Steam"]')
        assert arena.count() == defense.count() == 1
        assert arena_without_name.count() == 1
        assert arena.locator('b').inner_text() == 'Duel · Victoire · Arena Steam'
        assert arena_without_name.locator('b').inner_text() == 'Duel · Défaite'
        assert defense.locator('b').inner_text() == 'Monde envahi · Victoire · Profil Steam : Defense Steam'
        hostile = page.locator('.capture-scroll .para_capture[data-capture-steam-name^="<img"]')
        assert '<img' in hostile.locator('b').inner_text() and hostile.locator('b img').count() == 0
        page.evaluate("launchLanguages('eng')")
        assert arena.locator('b').inner_text() == 'Duel · Victory · Arena Steam'
        assert arena_without_name.locator('b').inner_text() == 'Duel · Defeat'
        assert 'Steam profile : Defense Steam' in defense.locator('b').inner_text()
        arena.evaluate('(el) => el.click()')
        assert page.locator('#capture_viewer_overlay').is_visible()
        assert 'Duel · Victory · Arena Steam' in page.locator('#capture_viewer_overlay').inner_text()
        page.locator('.capture-viewer-close').click()

        # The second page comes from /nextCaptures, and the filtered list from
        # /allCaptures; both must preserve names and character-name priority.
        page.locator('.capture-scroll').evaluate('(el) => { el.scrollTop = el.scrollHeight; el.dispatchEvent(new Event("scroll")); }')
        page.wait_for_function("() => document.querySelectorAll('.capture-scroll .para_capture').length === 53")
        older = page.locator('.capture-scroll .para_capture[data-capture-steam-name="Older Steam"]')
        assert 'Older Steam' in older.locator('b').inner_text()
        character = page.locator('.capture-scroll .para_capture[data-capture-steam-name="Hidden Steam"]')
        assert 'Game character' in character.locator('b').inner_text() and 'Hidden Steam' not in character.locator('b').inner_text()
        page.locator('#capture_mode').select_option('Arena')
        page.wait_for_function("() => document.querySelectorAll('.capture-scroll .para_capture').length === 5")
        assert page.locator('.capture-scroll .para_capture[data-capture-steam-name="Older Steam"]').count() == 1
        page.locator('#capture_mode').select_option('all')
        page.wait_for_function("() => document.querySelectorAll('.capture-scroll .para_capture').length === 53")

        # Test the live route while keeping the original journal message intact.
        page.evaluate("launchLanguages('fra')")
        page.route('**/capture', lambda route: route.fulfill(json={'request':'success', 'datas':'aW1hZ2U=', 'mode':'Defense', 'opponent':'', 'steam_name':'Live Steam', 'date':'01/01/2025'}))
        page.evaluate('''() => {
            const journal = document.createElement('div'); journal.id = 'synthetic-journal';
            journal.innerHTML = '<br> Temps: 17 s<br><span class="victory-opponent-detail">Profil Steam : Live Steam</span>';
            document.body.appendChild(journal); getCapture('Victory', journal.innerHTML);
        }''')
        live = page.locator('.capture-scroll .para_capture').first
        page.wait_for_function("() => document.querySelector('.capture-scroll .para_capture')?.dataset.captureSteamName === 'Live Steam'")
        assert live.locator('b').inner_text() == 'Monde envahi · Victoire · Profil Steam : Live Steam'
        assert '17 s' in live.inner_text() and live.locator('.victory-opponent-detail').count() == 0
        assert page.locator('#synthetic-journal .victory-opponent-detail').count() == 1
        sanitized = page.evaluate('''() => captureTimeWithoutOpponentDetail(
            '<!----><span class="combat-result-text">Vous remportez la victoire contre Test !</span><br> Temps: 17 s')''')
        assert '17 s' in sanitized and 'contre Test' not in sanitized and '<!---->' not in sanitized
        assert not errors, errors
    finally:
        context.close()


def main():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix='tracker-capture-steam-browser-', ignore_cleanup_errors=True) as directory:
        env = os.environ.copy()
        env.update(APPDATA=directory, TRACKER_TEST_PORT=str(port))
        seed = '''from flask import Flask
app=Flask(__name__)
from application.init import create_tables, add_capture
create_tables()
add_capture('',1,0,0,15,'2026-11-10','Arena','aW1hZ2U=',steam_name='Older Steam')
add_capture('Game character',1,0,0,15,'2026-11-10','Arena','aW1hZ2U=',steam_name='Hidden Steam')
for n in range(47): add_capture('',1,0,0,15,'2026-11-10','Invasion','aW1hZ2U=')
add_capture('',0,1,0,15,'2026-11-10','Arena','aW1hZ2U=')
add_capture('',1,0,0,15,'2026-11-10','Arena','aW1hZ2U=',steam_name='<img src=x onerror=alert(1)>')
add_capture('',1,0,0,15,'2026-11-10','Defense','aW1hZ2U=',steam_name='Defense Steam')
add_capture('',1,0,0,15,'2026-11-10','Arena','aW1hZ2U=',steam_name='Arena Steam')
'''
        subprocess.run([sys.executable, '-c', seed], cwd=ROOT, env=env, check=True, capture_output=True)
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
                    for viewport in [{'width': 1440, 'height': 900}, {'width': 390, 'height': 844}]:
                        check(browser, url, viewport)
                finally:
                    browser.close()
            print('Capture Steam name browser checks passed.')
        finally:
            if os.name == 'nt':
                subprocess.run(['taskkill', '/PID', str(server.pid), '/T', '/F'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            else:
                server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()


if __name__ == '__main__':
    main()
