"""Check translated ranking headers after DataTables reinitialization.

The browser server uses isolated APPDATA and runtime images on an ephemeral port.
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

from check_online_profile_notice import CHROME, LANGUAGES, scenario

ROOT = Path(__file__).resolve().parents[2]
HEADINGS = [
    ('tb-1', 'leaderboard_rank', 'Rang'),
    ('tb-11', 'game_language', 'Langue du jeu'),
    ('tb-3', 'online_name', 'Pseudo'),
    ('tb-2', 'leaderboard_avatar', 'Avatar'),
    ('tb-4', 'leaderboard_level', 'Niveau'),
    ('tb-5', 'stats_score', 'Score'),
    ('tb-6', 'victories', 'Victoires'),
    ('tb-7', 'defeats', 'Défaites'),
    ('tb-8', 'draw', 'Égalité'),
    ('tb-9', 'stats_win_rate', 'Taux de victoire'),
    ('tb-10', 'fights', 'Combats'),
]


def check(browser, url):
    context, page, _, errors = scenario(browser, url, state='success')
    try:
        page.locator('#menu_button_multi').click()
        page.wait_for_function("() => !!window.jQuery && $.fn.DataTable.isDataTable('#table_multi')")
        for language in LANGUAGES:
            page.evaluate('(code) => launchLanguages(code)', language)
            # setLeaderboardLanguage fetches the DataTables locale before
            # destroying and rebuilding the table asynchronously.
            page.wait_for_timeout(400)
            assert page.evaluate("() => $.fn.DataTable.isDataTable('#table_multi')")
            for class_name, key, french in HEADINGS:
                expected = french if language == 'fra' else page.evaluate(
                    '([code, key]) => ELDEN_UI_PACKS[code].modern[key]', [language, key])
                assert expected, (language, key)
                actual = page.locator('#table_multi thead .' + class_name).inner_text().strip()
                assert actual == expected, (language, class_name, actual, expected)
        assert not errors, errors
    finally:
        context.close()


def main():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix='tracker-ranking-headers-', ignore_cleanup_errors=True) as directory:
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
            print('Ranking headers translated after DataTables rebuild in all languages.')
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
