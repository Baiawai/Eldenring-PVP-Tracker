"""Exercise translated temporary statuses with simulated local responses.

The browser server uses private APPDATA and runtime images. Requests that
would change settings, test OCR, or purge history are fulfilled by Playwright.
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

from check_online_profile_notice import CHROME, ROOT, scenario


def check(browser, url):
    context, page, _, errors = scenario(browser, url)
    try:
        page.evaluate("() => uiApplyLanguage('fra')")

        def check_status(selector, key, french):
            node = page.locator(selector)
            page.wait_for_function("([selector, key]) => document.querySelector(selector).dataset.i18n === key", arg=[selector, key])
            assert node.text_content() == french, (selector, node.text_content())
            page.evaluate("() => uiApplyLanguage('eng')")
            english = page.evaluate('(key) => ELDEN_UI_PACKS.eng.modern[key]', key)
            assert node.text_content() == english, (selector, node.text_content(), english)
            page.evaluate("() => uiApplyLanguage('fra')")
            assert node.text_content() == french, (selector, node.text_content())

        # Opening and cancelling a pending profile capture must translate and
        # then clear its status without making another real capture request.
        page.evaluate("() => document.getElementById('profile_capture_start').click()")
        check_status('#profile_capture_status', 'profile_capture_wait',
                     'Laisse le jeu au premier plan sur cet écran pendant la lecture.')
        page.evaluate("() => document.getElementById('profile_capture_cancel').click()")
        page.evaluate("() => uiApplyLanguage('eng')")
        assert page.locator('#profile_capture_status').text_content() == ''
        assert page.locator('#profile_capture_status').get_attribute('data-i18n') is None
        page.evaluate("() => uiApplyLanguage('fra')")

        # The recognized OCR text is user/game data, not interface copy.
        raw_ocr = 'Texte OCR personnalisé : テスト'
        page.route('**/notification-region', lambda route: route.fulfill(json={
            'manual': False, 'locked': False, 'can_lock': True, 'top': .4, 'bottom': 1,
            'preview': 'AA==', 'preview_id': 'fixture'}))
        page.route('**/notification-ocr-test', lambda route: route.fulfill(json={
            'matched': True, 'text': raw_ocr}))
        page.evaluate('() => window.initNotificationRegion()')
        page.wait_for_function("() => !document.getElementById('notification_ocr_test').disabled")
        page.evaluate("() => document.getElementById('notification_ocr_test').click()")
        check_status('#notification_ocr_status', 'notification_ocr_matched',
                     'Message reconnu comme événement de suivi.')
        assert page.locator('#notification_ocr_result').text_content() == raw_ocr

        # Simulated failed and successful saves test both retained and cleared
        # translation keys. No request reaches the tracker or its settings.
        fail_speed = {'value': True}
        page.route('**/capture-speed', lambda route: route.fulfill(
            status=503, json={'error': 'fixture'}) if fail_speed['value'] else
            route.fulfill(json={'interval': 0}))
        page.evaluate("() => document.getElementById('capture_speed').dispatchEvent(new Event('change'))")
        check_status('#capture_speed_status', 'capture_interval_error', 'Impossible d’enregistrer le réglage.')
        fail_speed['value'] = False
        page.evaluate("() => document.getElementById('capture_speed').dispatchEvent(new Event('change'))")
        page.wait_for_function("() => !document.getElementById('capture_speed_status').hasAttribute('data-i18n')")
        page.evaluate("() => { uiApplyLanguage('eng'); uiApplyLanguage('fra'); }")
        assert page.locator('#capture_speed_status').text_content() == ''

        page.route('**/auto-game-start', lambda route: route.fulfill(status=503, json={'error': 'fixture'}))
        page.evaluate("() => document.getElementById('auto_game_start').dispatchEvent(new Event('change'))")
        check_status('#auto_game_start_status', 'auto_game_start_error', 'Impossible d’enregistrer ce réglage.')

        page.route('**/tracking-notifications', lambda route: route.fulfill(status=503, json={'error': 'fixture'}))
        page.evaluate("() => document.getElementById('notify_monitor_error').dispatchEvent(new Event('change'))")
        check_status('#tracking_notifications_status', 'notification_settings_error', 'Impossible de modifier les notifications.')

        page.route('**/steam-log-auto', lambda route: route.fulfill(status=503, json={'error': 'fixture'}))
        page.evaluate("() => document.getElementById('steam_log_auto').dispatchEvent(new Event('change'))")
        check_status('#steam_log_auto_status', 'auto_game_start_error', 'Impossible d’enregistrer ce réglage.')

        page.route('**/retention-settings', lambda route: route.fulfill(json={'settings': {'captures': 0, 'steam': 0}}))
        page.evaluate("() => document.getElementById('retention_captures').dispatchEvent(new Event('change'))")
        check_status('#retention_captures_status', 'retention_saved', 'Réglage enregistré.')

        # Purge is only a simulated response on the private browser session.
        page.route('**/history-storage', lambda route: route.fulfill(json={
            'request': 'success', 'history': {'events': 1, 'bytes': 100, 'estimated': False},
            'archives': [], 'monitor_running': False}))
        page.route('**/detection-history?**', lambda route: route.fulfill(json={
            'request': 'success', 'events': [], 'has_more': False}))
        page.route('**/history-purge', lambda route: route.fulfill(json={'request': 'success'}))
        page.evaluate("() => document.getElementById('menu_button_history').click()")
        page.wait_for_function("() => !document.getElementById('history_purge').disabled")
        page.once('dialog', lambda dialog: dialog.accept())
        page.evaluate("() => document.getElementById('history_purge').click()")
        check_status('#history_action_status', 'history_purge_done', 'Historique actif purgé.')

        # Player records use translated labels rather than French-only V/D/E.
        page.route('**/players', lambda route: route.fulfill(json={
            'players': [{'name': 'Fixture', 'steam': None, 'relations': ['opponent'],
                         'roles': [], 'total': 3, 'victories': 1, 'defeats': 1,
                         'draws': 1, 'sightings': 0, 'last_seen': '2026-01-01',
                         'history': [{'mode': 'Arena', 'outcome': 'draw', 'date': '2026-01-01'}]}],
            'unnamed_captures': 0}))
        page.evaluate("() => document.getElementById('menu_button_players').click()")
        page.wait_for_selector('.player-record .draw')
        for language in ['fra', 'eng', 'deu', 'ita', 'spaes', 'spaar', 'por', 'pol',
                         'rus', 'jap', 'kor', 'chi', 'zht', 'tha', 'ara']:
            page.evaluate('(language) => uiApplyLanguage(language)', language)
            expected = page.evaluate('''language => {
                const words = ELDEN_UI_PACKS[language]?.modern;
                return ['1 ' + (words?.victories || 'Victoires'),
                        '1 ' + (words?.defeats || 'Défaites'),
                        '1 ' + (words?.draw || 'Égalités')];
            }''', language)
            assert page.locator('.player-record span').all_text_contents() == expected, language

        assert page.locator('#notification_ocr_result').text_content() == raw_ocr
        assert not errors, errors
    finally:
        context.close()


def main():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix='tracker-status-i18n-', ignore_cleanup_errors=True) as directory:
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
            print('Temporary status translations and OCR preservation passed.')
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
