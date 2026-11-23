"""Exercise the P2P diagnostic with simulated Steam and isolated app data."""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright
from check_online_profile_notice import CHROME, ROOT, scenario


def check(browser, url, width, screenshots):
    context, page, _, errors = scenario(browser, url, viewport={'width': width, 'height': 900 if width > 600 else 844})
    try:
        page.wait_for_selector('.sprit', state='detached', timeout=30000)
        state = {'status': 'waiting_log', 'enabled': True, 'ping_mode': 'admin_required', 'peers': [],
                 'diagnostic': {'log': 'missing', 'auto': 'requested'}}
        attempts = []
        page.route('**/steam-peers', lambda route: route.fulfill(json=state))
        def retry(route):
            attempts.append(route.request.method)
            route.fulfill(json={'request': 'success', 'state': 'queued'})
        page.route('**/steam-log-auto/retry', retry)
        page.evaluate('''() => {
            uiApplyLanguage('fra');
            document.getElementById('menu_button_settings').click();
            document.querySelector('.btn_menu_settings[menu="5"]').click();
        }''')
        assert page.locator('.steam-log-diagnostic').count() == 0
        page.wait_for_function("() => document.querySelector('#steam_peer_status').textContent === 'Journal Steam : Fichier introuvable.'", timeout=8000)
        assert page.locator('#steam_peer_enabled').is_visible()
        assert page.locator('#steam_log_auto').count() == 1
        manual = page.locator('#steam_manual_setup')
        assert manual.is_visible()
        manual.locator('summary').click()
        assert manual.evaluate('(node) => node.open')
        assert page.locator('#steam_copy_command').is_visible()
        assert page.locator('#steam_command').text_content() == 'log_ipc "BeginAuthSession,EndAuthSession,LeaveLobby,SendClanChatMessage"'
        languages = ['fra'] if os.environ.get('TRACKER_STEAM_DIAG_QUICK') == '1' else [
            'fra', *json.loads((ROOT / 'application/locales/ui_packs.json').read_text(encoding='utf-8'))]
        for code in languages:
            page.evaluate('(code) => uiApplyLanguage(code)', code)
            if code != 'fra':
                expected = page.evaluate('code => ELDEN_UI_PACKS[code].modern', code)
                assert page.locator('#steam_peer_status').text_content() == expected['steam_diag_log_label'] + ' : ' + expected['steam_diag_log_missing'], code
        page.evaluate("() => uiApplyLanguage('fra')")
        if screenshots:
            manual.screenshot(path=str(Path(screenshots) / ('steam-manual-' + str(width) + '.png')))
        assert attempts == [], attempts
        for log, text in [('unreadable', 'Le tracker ne peut pas vérifier le fichier avec ses droits actuels.'),
                          ('waiting', 'Aucune mise à jour récente du fichier observée.')]:
            state['diagnostic']['log'] = log
            page.wait_for_function('(value) => document.querySelector("#steam_peer_status").textContent === "Journal Steam : " + value', arg=text, timeout=8000)
        state['diagnostic']['log'] = 'receiving'
        page.wait_for_function("() => document.querySelector('#steam_peer_status').textContent === 'En attente du journal Steam…'", timeout=8000)
        state['diagnostic']['auto'] = 'refused'
        state.pop('diagnostic')
        page.wait_for_timeout(3200)
        assert page.locator('#steam_peer_status').text_content() == 'En attente du journal Steam…'
        assert attempts == [], attempts
        assert not errors, errors
    finally:
        context.close()


def main():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix='tracker-steam-diag-', ignore_cleanup_errors=True) as directory:
        env = os.environ.copy()
        env.update(APPDATA=directory, LOCALAPPDATA=directory, TRACKER_TEST_PORT=str(port), TRACKER_TEST_NO_STEAM='1')
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
                        raise RuntimeError('Isolated server exited')
                    time.sleep(.1)
            else:
                raise RuntimeError('Isolated server did not start')
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(executable_path=str(CHROME), headless=True)
                try:
                    for width in (1440, 390):
                        check(browser, url, width, os.environ.get('TRACKER_STEAM_DIAG_SCREENSHOTS'))
                finally:
                    browser.close()
            print('Steam diagnostic browser checks passed.')
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
