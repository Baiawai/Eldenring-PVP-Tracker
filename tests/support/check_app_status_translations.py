"""Exercise live app status translation with isolated data and mocked failures."""
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


def check(browser, url):
    context, page, _, errors = scenario(browser, url, state='offline')
    try:
        # Until session data arrives, the empty last-combat label must still
        # follow the selected language.
        page.evaluate("() => { sidebarSession = null; launchLanguages('jap'); }")
        assert page.locator('#sidebar_last_combat').inner_text() == page.evaluate(
            "() => ELDEN_UI_PACKS.jap.modern.last_combat_empty")
        page.evaluate("() => launchLanguages('fra')")

        # A detected mode remains visible and translated even when the user
        # changes language while the monitor is stopped.
        page.evaluate("() => { detected_stats_mode = 'Defense'; }")
        for code in ['eng', 'deu', 'ita', 'spaes', 'spaar', 'por', 'pol',
                     'rus', 'jap', 'kor', 'chi', 'zht', 'tha', 'ara']:
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
        for code in ['eng', 'jap', 'ara']:
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
        for code in ['eng', 'jap', 'ara']:
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
