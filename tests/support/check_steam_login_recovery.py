"""Verify a failed status check still reaches explicit Steam login, without network access."""
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
with tempfile.TemporaryDirectory(prefix='tracker-steam-login-test-', ignore_cleanup_errors=True) as directory:
    env = os.environ.copy()
    env.update(APPDATA=directory, TRACKER_TEST_PORT=str(port))
    server = subprocess.Popen([sys.executable, str(ROOT / 'tests/support/browser_server.py')], cwd=ROOT, env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        url = f'http://127.0.0.1:{port}'
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
            context = browser.new_context()
            context.route('**/*', lambda route: route.continue_() if route.request.url.startswith(url + '/') else route.abort())
            state = {'login': 0, 'status': 0}
            context.route('**/online-leaderboard/settings', lambda route: route.fulfill(json={
                'enabled': True, 'configured': True, 'state': 'steam_login_required',
                'steam_status_observe': True, 'steam_consent': False}))
            def status(route):
                state['status'] += 1
                if state['login']:
                    route.fulfill(json={'connected': False, 'confirmation_pending': True})
                else:
                    route.fulfill(status=503, json={'error':'unavailable'})
            def login(route):
                state['login'] += 1
                route.fulfill(json={'url':'https://steamcommunity.com/openid/login?state=fixture'})
            context.route('**/online-leaderboard/steam-status?**', status)
            context.route('**/online-leaderboard/steam-login', login)
            page = context.new_page()
            page.add_init_script("window.open = () => ({closed:false, close(){this.closed=true}, location:{href:''}})")
            page.goto(url, wait_until='load')
            page.wait_for_function("() => document.querySelector('#online_enabled') && document.querySelector('#online_steam_state').dataset.state === 'unavailable'", timeout=20000)
            page.evaluate("() => document.querySelector('#online_enabled').dispatchEvent(new Event('change'))")
            page.locator('dialog.online-dialog[open]').wait_for(state='visible')
            page.locator('#online_accept').click()
            page.wait_for_function("() => document.querySelector('dialog.online-dialog').dataset.step === 'code'", timeout=10000)
            assert state['status'] >= 2 and state['login'] == 1, state
            print('Failed status check reaches explicit login and code confirmation.')
            context.close()
            # A modern server confirms the local proof without asking for a code.
            context = browser.new_context()
            context.route('**/*', lambda route: route.continue_() if route.request.url.startswith(url + '/') else route.abort())
            state = {'login': 0, 'confirm': 0}
            context.route('**/online-leaderboard/settings', lambda route: route.fulfill(json={
                'enabled': True, 'configured': True, 'state': 'steam_login_required',
                'steam_status_observe': True, 'steam_consent': False}))
            context.route('**/online-leaderboard/steam-status?**', lambda route: route.fulfill(json={
                'connected': False, 'confirmation_pending': bool(state['login'])}))
            def auto_login(route):
                state['login'] += 1
                route.fulfill(json={'url':'https://steamcommunity.com/openid/login?state=fixture', 'automatic':True})
            def auto_confirm(route):
                state['confirm'] += 1
                route.fulfill(json={'connected':True})
            context.route('**/online-leaderboard/steam-login', auto_login)
            context.route('**/online-leaderboard/steam-auto-confirm', auto_confirm)
            context.route('**/online-leaderboard/sync', lambda route: route.fulfill(json={'state':'success'}))
            page = context.new_page()
            page.add_init_script("window.open = () => ({closed:false, close(){this.closed=true}, location:{href:''}})")
            page.goto(url, wait_until='load')
            page.wait_for_function("() => document.querySelector('#online_enabled') && document.querySelector('#online_steam_state').dataset.state === 'disconnected'", timeout=20000)
            page.evaluate("() => document.querySelector('#online_enabled').dispatchEvent(new Event('change'))")
            page.locator('dialog.online-dialog[open]').wait_for(state='visible')
            page.locator('#online_accept').click()
            page.wait_for_function("() => document.querySelector('dialog.online-dialog').dataset.step === 'success'", timeout=10000)
            assert state == {'login':1, 'confirm':1}, state
            assert page.locator('#online_steam_code').is_hidden()
            print('Automatic confirmation completes without a code.')
            context.close()
            # Show the safe diagnostic returned by the tracker, in each language.
            context = browser.new_context()
            context.route('**/*', lambda route: route.continue_() if route.request.url.startswith(url + '/') else route.abort())
            context.route('**/online-leaderboard/settings', lambda route: route.fulfill(json={
                'enabled': True, 'configured': True, 'state': 'steam_login_required',
                'steam_status_observe': True, 'steam_consent': False}))
            context.route('**/online-leaderboard/steam-status?**', lambda route: route.fulfill(status=503, json={'error':'unavailable'}))
            context.route('**/online-leaderboard/steam-login', lambda route: route.fulfill(status=503, json={
                'error':'unavailable', 'stage':'login', 'reason':'http', 'http_status':502, 'log_saved':True}))
            page = context.new_page()
            page.add_init_script("window.open = () => ({closed:false, close(){this.closed=true}, location:{href:''}})")
            page.goto(url, wait_until='load')
            page.wait_for_function("() => document.querySelector('#online_enabled') && document.querySelector('#online_steam_state').dataset.state === 'unavailable'", timeout=20000)
            page.evaluate("() => document.querySelector('#online_enabled').dispatchEvent(new Event('change'))")
            page.locator('#online_accept').click()
            page.wait_for_function("() => document.querySelector('dialog.online-dialog').dataset.step === 'offline'", timeout=10000)
            for language in ['fra','eng','deu','ita','spaes','spaar','por','pol','rus','jap','kor','chi','zht','tha','ara']:
                page.evaluate('(language) => launchLanguages(language)', language)
                page.wait_for_timeout(100)
                detail = page.locator('#online_dialog_text').text_content()
                assert 'HTTP 502' in detail and 'tracker-errors.log' in detail, (language, detail)
                if language != 'fra':
                    expected = page.evaluate("ELDEN_UI_PACKS[uiCurrentLanguage()].modern.steam_diag_stage_login")
                    assert expected in detail, (language, detail, expected)
            print('Safe diagnostic is visible in all 15 languages.')
            context.close()
            browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()
