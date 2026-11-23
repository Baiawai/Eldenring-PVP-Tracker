"""Exercise live app status translation with isolated data and mocked failures."""
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

from check_online_profile_notice import CHROME, scenario

ROOT = Path(__file__).resolve().parents[2]
LANGUAGES = list(json.loads((ROOT / 'application/locales/ui_packs.json').read_text(encoding='utf-8')))


def check(browser, url):
    context, page, _, errors = scenario(browser, url, state='offline')
    try:
        # Simulate a cached template with legacy-only labels. The usual test
        # profile has already selected a language, so its card was removed.
        page.evaluate('''async () => {
            const parent = document.querySelector('.sidebar-guidance');
            if (!parent.querySelector('.carde_info[info="languages"]')) {
                parent.insertAdjacentHTML('afterbegin', '<div class="carde_info" info="languages"><h5 class="btr_1">Ancien titre</h5><p class="btr_2">Ancienne aide</p></div>');
            }
            const card = parent.querySelector('.carde_info[info="languages"]');
            card.querySelectorAll('[data-i18n]').forEach(node => { delete node.dataset.i18n; delete node.dataset.i18nFr; });
            (0, eval)(await (await fetch('/static/ui-i18n.js')).text());
        }''')
        # The sidebar link chooses the game language independently of the UI.
        title = page.locator('.sidebar-guidance .carde_info[info="languages"] h5')
        description = page.locator('.sidebar-guidance .carde_info[info="languages"] p').first
        for code in LANGUAGES:
            page.evaluate('(code) => launchLanguages(code)', code)
            assert title.text_content() == page.evaluate('(code) => ELDEN_UI_PACKS[code].modern.game_language_label', code)
            assert description.text_content() == page.evaluate('(code) => ELDEN_UI_PACKS[code].modern.help_game_language', code)
        page.evaluate("() => launchLanguages('fra')")
        assert title.text_content() == 'Langue du jeu'
        assert description.text_content() == 'Choisit la langue utilisée pour reconnaître les messages du jeu sans modifier ses réglages.'
        page.locator('.sidebar-guidance .carde_info[info="languages"]').evaluate('(node) => node.remove()')

        # Until session data arrives, the empty last-combat label must still
        # follow the selected language.
        page.evaluate("() => { sidebarSession = null; launchLanguages('jap'); }")
        assert page.locator('#sidebar_last_combat').inner_text() == page.evaluate(
            "() => ELDEN_UI_PACKS.jap.modern.last_combat_empty")
        page.evaluate("() => launchLanguages('fra')")

        # A detected mode remains visible and translated even when the user
        # changes language while the monitor is stopped.
        page.evaluate("() => { detected_stats_mode = 'Defense'; }")
        for code in LANGUAGES:
            page.evaluate('(code) => launchLanguages(code)', code)
            assert page.locator('#stats_mode_choice option[value="auto"]').text_content() == page.evaluate(
                '(code) => ELDEN_UI_PACKS[code].modern.automatic + " · " + ELDEN_UI_PACKS[code].modern.defense', code)
        page.evaluate("() => { detected_stats_mode = null; launchLanguages('fra'); }")

        # Failed saves are simulated: no user's legend is read or changed.
        page.route('**/profile-legend', lambda route: route.fulfill(status=500, body='error'))
        page.locator('#menu_button_settings').click()
        page.locator('.btn_menu_settings[menu="3"]').click()
        legend = page.locator('#profile_legend')
        legend.fill('temporary test')
        legend.blur()
        status = page.locator('#profile_legend_status')
        page.wait_for_function("() => document.querySelector('#profile_legend_status').dataset.i18n === 'profile_legend_error'")
        for code in LANGUAGES:
            page.evaluate('(code) => launchLanguages(code)', code)
            assert status.inner_text() == page.evaluate(
                '(code) => ELDEN_UI_PACKS[code].modern.profile_legend_error', code)
        legend.fill('')
        assert status.inner_text() == '' and status.get_attribute('data-i18n') is None

        # Mode and chart errors also retain their key across language changes.
        page.route('**/modeStats?**', lambda route: route.fulfill(status=500, body='error'))
        page.route('**/allCapturesChart?**', lambda route: route.fulfill(status=500, body='error'))
        page.locator('#menu_button_settings').click()
        page.locator('#menu_button_info').click()
        page.wait_for_function("() => document.querySelector('#stats_mode_error').dataset.i18n === 'stats_unavailable'")
        page.wait_for_function("() => document.querySelector('#stats_panel .chart-status').dataset.i18n === 'stats_chart_error'")
        for code in LANGUAGES:
            page.evaluate('(code) => launchLanguages(code)', code)
            assert page.locator('#stats_mode_error').inner_text() == page.evaluate(
                '(code) => ELDEN_UI_PACKS[code].modern.stats_unavailable', code)
            page.wait_for_function("() => document.querySelector('#stats_panel .chart-status').dataset.i18n === 'stats_chart_error'")
            assert page.locator('#stats_panel .chart-status').inner_text() == page.evaluate(
                '(code) => ELDEN_UI_PACKS[code].modern.stats_chart_error', code)
        assert not errors, errors
    finally:
        context.close()


def main():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix='tracker-app-status-', ignore_cleanup_errors=True) as directory:
        env = os.environ.copy()
        env.update(APPDATA=directory, LOCALAPPDATA=directory, TRACKER_TEST_PORT=str(port))
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
            print('Live app statuses follow language changes and clear correctly.')
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
