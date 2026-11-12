"""Browser checks for the optional leaderboard invitation, using isolated data.

Run this from an isolated project copy so generated images cannot touch a real
installation. The server has a temporary APPDATA and never contacts the API.
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
NOTICE = '.sidebar-guidance .carde_info[info="online-leaderboard"]'
LANGUAGES = ['fra', 'eng', 'deu', 'ita', 'spaes', 'spaar', 'por', 'pol',
             'rus', 'jap', 'kor', 'chi', 'zht', 'tha', 'ara']


def scenario(browser, url, response, visible):
    """Start fresh with a controlled settings response and no external calls."""
    context = browser.new_context(viewport={'width': 1440, 'height': 900})
    context.route('**/*', lambda route: route.continue_()
                  if route.request.url.startswith(url + '/') else route.abort())
    reads, posts = [], []
    state = dict(response) if response is not None else None

    def settings(route):
        if route.request.method == 'POST':
            posts.append(route.request.post_data_json)
            state['enabled'] = bool(posts[-1]['enabled'])
        reads.append(route.request.method)
        if state is None:
            route.fulfill(status=503, json={'error': 'unavailable'})
        else:
            route.fulfill(json=state)

    context.route('**/online-leaderboard/settings', settings)
    def init(route):
        response = route.fetch()
        payload = response.json()
        payload['language_default'] = True
        payload['user'][1] = ''
        route.fulfill(response=response, json=payload)

    context.route('**/init', init)
    context.route('**/online-leaderboard/steam-status**',
                  lambda route: route.fulfill(json={'connected': False}))
    context.route('**/online-leaderboard/steam-login',
                  lambda route: route.fulfill(json={'url': 'https://steamcommunity.com/'}))
    context.route('https://steamcommunity.com/**',
                  lambda route: route.fulfill(status=200, body='Steam test'))
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(url, wait_until='load')
    page.wait_for_function("() => document.querySelector('" + NOTICE.replace('"', '\\"') + "') !== null")
    for _ in range(100):
        if reads:
            break
        page.wait_for_timeout(50)
    if not reads:
        raise AssertionError('Settings were not loaded')
    # The legacy startup settings request can set the initial UI language
    # after the ranking request finishes. Let that initialization complete.
    page.wait_for_timeout(1500)
    card = page.locator(NOTICE)
    page.wait_for_function('(args) => document.querySelector(args.selector).hidden !== args.visible',
                           arg={'selector': NOTICE, 'visible': visible})
    if card.is_visible() != visible:
        raise AssertionError(('Unexpected invitation visibility', response, card.is_visible()))
    return context, page, card, posts, errors


def check(browser, url):
    base = {'enabled': False, 'configured': True, 'state': 'idle', 'steam_status_observe': True}
    context, page, card, posts, errors = scenario(browser, url, base, True)
    try:
        ranking_reads = []
        page.on('request', lambda request: ranking_reads.append(request.url)
                if '/online-leaderboard/entries?' in request.url else None)
        page.route('**/online-leaderboard/entries?**', lambda route: route.fulfill(json={
            'mode': 'Arena', 'entries': [{'rank': 1, 'name': 'Test player', 'level': 1, 'score': 1, 'stats': {}}],
            'page': 1, 'per_page': 5, 'total': 1, 'filtered_total': 1}))
        page.locator('#menu_button_multi').click()
        if not page.locator('#leaderboard_content').is_visible() or not page.locator('#leaderboard_status').is_visible():
            raise AssertionError('The empty table and participation message must be visible before consent')
        if ranking_reads or page.locator('#leaderboard_content_toggle').count():
            raise AssertionError(('Player content fetched or separate display button present before consent', ranking_reads))
        if page.locator('.leaderboard-report').get_attribute('href') != 'https://discord.gg/y79z83D2Ua':
            raise AssertionError('The report action must open Discord')
        page.locator('#menu_button_multi').click()
        if card.get_attribute('role') != 'button' or card.get_attribute('tabindex') != '0':
            raise AssertionError('Invitation is not keyboard accessible')
        if card.locator('img').get_attribute('src') != '/static/page-icon-ranking.png':
            raise AssertionError('Invitation does not use the ranking icon')
        wrong_cursors = page.locator('.sidebar-guidance .carde_info[role="button"]').evaluate_all('''cards =>
            cards.flatMap(card => [card, ...card.querySelectorAll('*')]
                .filter(node => getComputedStyle(node).cursor !== 'pointer')
                .map(node => [card.getAttribute('info'), node.tagName, getComputedStyle(node).cursor]))''')
        if wrong_cursors:
            raise AssertionError(('Guidance elements do not show a pointer', wrong_cursors))
        for language in LANGUAGES:
            page.evaluate('(code) => launchLanguages(code)', language)
            expected = page.evaluate('''code => code === 'fra'
                ? ['Classement en ligne', 'Rejoins le classement en ligne et compare tes résultats avec les autres joueurs.', 'Clique dans le cadre pour accéder à cette option.']
                : [ELDEN_UI_PACKS[code].modern.online_title, ELDEN_UI_PACKS[code].modern.online_invitation_action, ELDEN_UI_PACKS[code].modern.sidebar_guidance_hint]''', language)
            actual = [card.locator('[data-online="online_title"]').inner_text(),
                      card.locator('[data-online="online_invitation_action"]').inner_text(),
                      card.locator('[data-online="sidebar_guidance_hint"]').inner_text()]
            if actual != expected:
                raise AssertionError(('Invitation translation', language, expected, actual))
            for hint in page.locator('.sidebar-guidance [data-i18n="sidebar_guidance_hint"]').all():
                if hint.inner_text() != expected[2]:
                    raise AssertionError(('Guidance hint translation', language, hint.inner_text(), expected[2]))
            card.click()
            page.locator('.online-dialog').wait_for(state='visible')
            risk = page.evaluate('''code => code === 'fra'
                ? 'Les pseudonymes et avatars sont fournis par les joueurs. Malgré une modération manuelle, des contenus choquants ou inappropriés peuvent apparaître. La nudité et la violence explicite sont interdites ; signale tout contenu sur Discord.'
                : ELDEN_UI_PACKS[code].modern.online_player_content_risk''', language)
            if risk not in page.locator('#online_dialog_text').inner_text():
                raise AssertionError(('Consent risk warning not translated', language))
            page.locator('#online_cancel').click()
        page.evaluate("() => launchLanguages('fra')")
        for kind in ('languages', 'profile'):
            guidance = page.locator(f'.sidebar-guidance .carde_info[info="{kind}"]')
            if guidance.get_attribute('role') != 'button' or guidance.get_attribute('tabindex') != '0':
                raise AssertionError(('Guidance is not keyboard accessible', kind))
            # Observe the card activation without launching an actual profile capture.
            guidance.evaluate('''node => node.addEventListener('click', event => {
                event.preventDefault(); event.stopImmediatePropagation();
                node.dataset.testClicks = String(Number(node.dataset.testClicks || 0) + 1);
            }, true)''')
            guidance.click(position={'x': 5, 'y': 5})
            guidance.focus()
            page.keyboard.press('Enter')
            page.keyboard.press('Space')
            if guidance.get_attribute('data-test-clicks') != '3':
                raise AssertionError(('Guidance activation failed', kind))
        card.click()
        dialog = page.locator('.online-dialog')
        dialog.wait_for(state='visible')
        if posts:
            raise AssertionError(('Opening the invitation changed participation', posts))
        text = page.locator('#online_dialog_text').inner_text()
        for detail in ('pseudo', 'Steam', 'résultats des combats', 'modération manuelle', 'contenus choquants', 'Discord'):
            if detail not in text:
                raise AssertionError(('Consent information missing', detail, text))
        page.locator('#online_cancel').click()
        if dialog.is_visible() or posts or not card.is_visible():
            raise AssertionError(('Cancellation changed participation or hid invitation', posts))
        card.focus()
        page.keyboard.press('Enter')
        dialog.wait_for(state='visible')
        page.locator('#online_cancel').click()
        card.focus()
        page.keyboard.press('Space')
        dialog.wait_for(state='visible')
        if posts:
            raise AssertionError(('Keyboard activation changed participation', posts))
        with page.expect_popup() as popup:
            page.locator('#online_accept').click()
        popup.value.wait_for_load_state('domcontentloaded')
        page.wait_for_function('(selector) => document.querySelector(selector).hidden', arg=NOTICE)
        if len(posts) != 1 or not all(posts[0].get(key) is True for key in
                                      ('enabled', 'consent', 'event_consent')):
            raise AssertionError(('Acceptance did not explicitly enable participation', posts))
        # Close only the mocked Steam dialog so the newly accepted view can be tested.
        page.locator('.online-dialog').evaluate('node => node.close()')
        page.locator('#menu_button_multi').click()
        page.wait_for_function("() => document.querySelector('#table_multi tbody')?.textContent.includes('Test player')")
        if not ranking_reads or page.locator('#leaderboard_status').is_visible():
            raise AssertionError(('Accepted participation did not display the players', ranking_reads))
        page.route('**/online-leaderboard/steam-status**', lambda route: route.fulfill(json={
            'connected': True, 'confirmation_pending': False}))
        page.evaluate("() => window.dispatchEvent(new Event('focus'))")
        page.wait_for_function("() => document.querySelector('#online_steam_state').dataset.state === 'connected'")
        page.locator('#menu_button_settings').click()
        page.locator('.online-ranking-tab').click()
        page.locator('#online_enabled').evaluate("node => { node.checked = false; node.dispatchEvent(new Event('change')); }")
        page.locator('#online_keep').click()
        page.wait_for_function("() => document.querySelector('#online_enabled').checked === false")
        page.locator('#menu_button_settings').click()
        page.locator('#menu_button_multi').click()
        if 'Test player' in page.locator('#table_multi tbody').inner_text() or not page.locator('#leaderboard_status').is_visible():
            raise AssertionError('Disabling participation must clear player content')
        count = len(ranking_reads)
        page.wait_for_timeout(300)
        if len(ranking_reads) != count:
            raise AssertionError('Player content was requested after participation was disabled')
        if errors:
            raise AssertionError(('JavaScript errors', errors))
    finally:
        context.close()

    for response in (
        {'enabled': True, 'configured': True, 'state': 'idle'},
        {'enabled': False, 'configured': False, 'state': 'idle'},
        {'enabled': False, 'configured': True, 'state': 'delete_pending'},
        {'enabled': False, 'configured': True, 'state': 'syncing'},
        {'enabled': False, 'configured': True, 'state': 'steam_cancel_pending'},
        {'enabled': False, 'configured': True, 'state': 'idle', 'migration_available': True},
        {'enabled': False, 'configured': True, 'state': 'idle', 'partial_identity': True},
        {'enabled': False, 'configured': True, 'state': 'idle', 'transition_blocked': True},
        {'enabled': False, 'configured': True, 'state': 'idle', 'server_consent_required': True},
        None,
    ):
        context, page, card, posts, errors = scenario(browser, url, response, False)
        try:
            if posts or errors:
                raise AssertionError(('Blocked invitation made a change or caused an error', response, posts, errors))
        finally:
            context.close()


def main():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix='tracker-invitation-test-', ignore_cleanup_errors=True) as directory:
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
            print('Leaderboard invitation browser checks passed (15 languages).')
        finally:
            # On Windows the venv launcher can spawn a second Python process;
            # terminate its own process tree, not the running user tracker.
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
