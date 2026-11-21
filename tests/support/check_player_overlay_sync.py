"""Playwright checks: player-card visibility follows saved overlay options.

The server uses private APPDATA and redirected runtime images. Steam peers,
avatars and profile actions are synthetic, and external requests are blocked.
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
FIELDS = {
    'show_avatars': '.steam-peer-avatar',
    'show_player_name': '.steam-peer-name',
    'show_role': '.steam-peer-role',
    'show_steam_id': '.steam-peer-id',
    'show_country': '.steam-peer-country',
    'show_ping': '.steam-peer-ping',
    'show_ping_average': '.steam-peer-ping-detail',
    'show_jitter': '.steam-peer-jitter',
    'show_quality': '.steam-peer-quality',
    'show_duration': '.steam-peer-duration',
    'show_player_stats': '.steam-peer-encounters',
}


def options(page):
    return page.evaluate("async () => (await (await fetch('/overlay-settings')).json()).options")


def set_option(page, name, value):
    page.locator('#overlay_custom_' + name).evaluate('''(node, value) => {
        node.checked = value;
        node.dispatchEvent(new Event('change', {bubbles:true}));
    }''', value)
    page.wait_for_function('''async ([name, value]) =>
        (await (await fetch('/overlay-settings', {cache:'no-store'})).json()).options[name] === value''',
        arg=[name, value])


def field_is_visible(card, selector):
    """Respect visibility up to the card, even while its page panel is inactive."""
    node = card.locator(selector)
    assert node.count() == 1, (selector, node.count())
    return node.evaluate("""element => {
        const card = element.closest('.steam-peer-item');
        for (let node = element; node && node !== card.parentElement; node = node.parentElement) {
            const style = getComputedStyle(node);
            if (node.hidden || style.display === 'none' || style.visibility === 'hidden') return false;
        }
        return true;
    }""")


def run(browser, base, width, height):
    context = browser.new_context(viewport={'width': width, 'height': height})
    external = []
    def restrict(route):
        if route.request.url.startswith(base + '/'):
            route.continue_()
        else:
            external.append(route.request.url)
            route.abort()
    context.route('**/*', restrict)
    peer_id = '76561198000000001'
    peer = {'id': peer_id, 'name': 'Player Test', 'ping': 42, 'average_ping': 47,
            'jitter': 4, 'quality': .93, 'connected_seconds': 123, 'avatar_available': False,
            'country_code': 'FR', 'role': 'hunter', 'encounters': 8}
    calls = {'profile': [], 'peer': dict(peer)}
    def steam(route):
        route.fulfill(json={'status': 'active', 'enabled': True, 'ping_mode': 'steam_only',
                            'mode_id': 'Arena', 'world_host': None, 'peers': [calls['peer']]})
    def profile(route):
        calls['profile'].append(route.request.post_data)
        route.fulfill(json={'request': 'success'})
    context.route('**/steam-peers', steam)
    context.route('**/steam-profile', profile)
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    try:
        page.goto(base, wait_until='load')
        page.wait_for_selector('.sprit', state='detached', timeout=30000)
        page.evaluate("""() => {
            document.querySelector('.presentation').style.display = 'none';
            document.querySelector('.live').style.display = 'block';
            launchLanguages('fra');
        }""")
        page.wait_for_selector('.steam-peer-item', state='attached')
        page.locator('#menu_button_settings').click()
        page.locator('.btn_menu_settings[menu="8"]').click()
        page.wait_for_function("() => !document.querySelector('#overlay_custom_show_avatars').disabled")
        page.locator('.overlay-custom-group').evaluate_all('(groups) => groups.forEach(group => group.open = true)')
        card = page.locator('.steam-peer-item').first
        assert page.locator('#overlay_custom_show_rank').count() == 0
        assert card.locator('.steam-peer-rank').count() == 0
        # The full synthetic peer must make every configurable field available.
        for name in FIELDS:
            set_option(page, name, True)
        for name, selector in FIELDS.items():
            assert field_is_visible(card, selector), (width, name, 'not shown')
        # Both interfaces should present the same data in this sequence. Keep
        # the expectations literal so a changed translation or format cannot
        # silently mask a divergence from the overlay.
        expected_fields = [
            ('.steam-peer-name', 'Player Test'),
            ('.steam-peer-ping', '42 ms'),
            ('.steam-peer-role', 'Chasseur'),
            ('.steam-peer-id', 'SteamID : ' + peer_id),
            ('.steam-peer-duration', 'Connexion : 00:02:03'),
            ('.steam-peer-ping-detail', 'Ping moyen : 47 ms'),
            ('.steam-peer-jitter', 'Jitter : 4 ms'),
            ('.steam-peer-quality', 'Qualité de connexion : 93 %'),
            ('.steam-peer-encounters', 'Nombre de rencontres : 8'),
            ('.steam-peer-country', 'France'),
        ]
        for selector, expected in expected_fields:
            actual = card.locator(selector).text_content().strip()
            assert actual == expected, (width, selector, actual, expected)
        for (previous, _), (following, _) in zip(expected_fields, expected_fields[1:]):
            ordered = card.evaluate('''(card, [previous, following]) =>
                !!(card.querySelector(previous).compareDocumentPosition(card.querySelector(following))
                   & Node.DOCUMENT_POSITION_FOLLOWING)''', [previous, following])
            assert ordered, (width, previous, following, 'unexpected field order')
        initial = options(page)
        # General overlay visibility and enabling it are separate settings:
        # neither should suppress player details in the application.
        set_option(page, 'show_peers', False)
        assert all(field_is_visible(card, selector) for selector in FIELDS.values())
        set_option(page, 'show_peers', True)
        page.locator('#game_overlay_enabled').evaluate('''node => {
            node.checked = false; node.dispatchEvent(new Event('change', {bubbles:true}));
        }''')
        page.wait_for_function("async () => !(await (await fetch('/overlay-settings')).json()).enabled")
        assert all(field_is_visible(card, selector) for selector in FIELDS.values())
        page.locator('#game_overlay_enabled').evaluate('''node => {
            node.checked = true; node.dispatchEvent(new Event('change', {bubbles:true}));
        }''')
        page.wait_for_function("async () => (await (await fetch('/overlay-settings')).json()).enabled")
        # Each setting controls only its field, and the change is persisted.
        for name, selector in FIELDS.items():
            set_option(page, name, False)
            assert not field_is_visible(card, selector), (width, name, 'not hidden')
            for other, other_selector in FIELDS.items():
                if other != name:
                    assert field_is_visible(card, other_selector), (width, name, 'also hid', other)
            set_option(page, name, True)
            assert field_is_visible(card, selector), (width, name, 'not restored')

        # Old display settings remain respected as additional restrictions.
        for body_class, selector in [('hide-steam-name', '.steam-peer-name'),
                                     ('hide-steam-ping', '.steam-peer-ping'),
                                     ('hide-steam-country', '.steam-peer-country')]:
            page.evaluate('(name) => document.body.classList.add(name)', body_class)
            assert not field_is_visible(card, selector), (width, body_class)
            page.evaluate('(name) => document.body.classList.remove(name)', body_class)
            assert field_is_visible(card, selector), (width, body_class)

        # Changes are reflected immediately, before the server confirms the save.
        page.evaluate('''() => {
            window.__originalTestFetch = window.fetch;
            window.__releaseTestSave = null;
            window.fetch = async function(input, init) {
                if (input === '/overlay-settings' && init?.method === 'POST' && init?.headers?.['Content-Type'] === 'application/json') {
                    await new Promise(resolve => { window.__releaseTestSave = resolve; });
                }
                return window.__originalTestFetch.call(this, input, init);
            };
        }''')
        page.locator('#overlay_custom_show_role').evaluate('''node => {
            node.checked = false; node.dispatchEvent(new Event('change', {bubbles:true}));
        }''')
        page.wait_for_function('() => window.__releaseTestSave !== null')
        assert not field_is_visible(card, FIELDS['show_role']), (width, 'not applied before save')
        assert options(page)['show_role'] is True
        page.evaluate('() => window.__releaseTestSave()')
        page.wait_for_function("async () => !(await (await fetch('/overlay-settings')).json()).options.show_role")
        page.evaluate('() => { window.fetch = window.__originalTestFetch; }')
        set_option(page, 'show_role', True)
        assert field_is_visible(card, FIELDS['show_role'])

        # A failed save restores both the control and the player card.
        page.evaluate('''() => {
            window.__originalTestFetch = window.fetch;
            window.fetch = async function(input, init) {
                if (input === '/overlay-settings' && init?.method === 'POST' && init?.headers?.['Content-Type'] === 'application/json') {
                    return new Response('{}', {status:503, headers:{'Content-Type':'application/json'}});
                }
                return window.__originalTestFetch.call(this, input, init);
            };
        }''')
        page.locator('#overlay_custom_show_ping').evaluate('''node => {
            node.checked = false; node.dispatchEvent(new Event('change', {bubbles:true}));
        }''')
        page.wait_for_function("() => document.querySelector('.overlay-custom-status').textContent.length > 0")
        assert page.locator('#overlay_custom_show_ping').is_checked()
        assert field_is_visible(card, FIELDS['show_ping'])
        assert options(page)['show_ping'] is True
        page.evaluate('() => { window.fetch = window.__originalTestFetch; }')

        # A persisted mixture is restored on reload, not reset by the peer poll.
        for name in ('show_avatars', 'show_ping', 'show_jitter', 'show_player_stats'):
            set_option(page, name, False)
        saved = options(page)
        page.reload(wait_until='load')
        page.wait_for_selector('.sprit', state='detached', timeout=30000)
        page.wait_for_selector('.steam-peer-item', state='attached')
        page.wait_for_function("() => !document.querySelector('#overlay_custom_show_avatars').disabled")
        card = page.locator('.steam-peer-item').first
        for name, selector in FIELDS.items():
            assert field_is_visible(card, selector) == saved[name], (width, name, 'reload')
        assert options(page) == saved
        assert all(initial[key] == saved[key] for key in initial if key not in
                   ('show_avatars', 'show_ping', 'show_jitter', 'show_player_stats'))

        # An unavailable observation must never fabricate values. Role is
        # omitted; quality and encounter count indicate they are unavailable.
        calls['peer'] = {'id': peer_id, 'name': 'Player Test', 'ping': None,
                         'average_ping': None, 'jitter': None, 'quality': None,
                         'connected_seconds': None, 'avatar_available': False, 'country_code': None}
        page.reload(wait_until='load')
        page.wait_for_selector('.steam-peer-item', state='attached')
        page.wait_for_function("() => !document.querySelector('#overlay_custom_show_avatars').disabled")
        card = page.locator('.steam-peer-item').first
        assert not field_is_visible(card, FIELDS['show_role'])
        assert card.locator('.steam-peer-rank').count() == 0
        assert field_is_visible(card, FIELDS['show_quality'])
        quality_fallback = page.evaluate("() => window.uiT('steam_peer_quality_unknown', 'Qualité de connexion indisponible')")
        assert card.locator(FIELDS['show_quality']).text_content() == quality_fallback
        assert not field_is_visible(card, FIELDS['show_player_stats'])  # saved as off above
        set_option(page, 'show_player_stats', True)
        assert field_is_visible(card, FIELDS['show_player_stats'])
        count_label = page.evaluate("() => window.uiT('overlay_encounter_count', 'Nombre de rencontres')")
        assert card.locator(FIELDS['show_player_stats']).text_content() == count_label + ' : —'
        # Zero is a known value and must not be treated as unavailable.
        calls['peer']['encounters'] = 0
        page.reload(wait_until='load')
        page.wait_for_selector('.steam-peer-item', state='attached')
        page.wait_for_function("() => !document.querySelector('#overlay_custom_show_avatars').disabled")
        card = page.locator('.steam-peer-item').first
        assert field_is_visible(card, FIELDS['show_player_stats'])
        assert card.locator(FIELDS['show_player_stats']).text_content() == count_label + ' : 0'
        assert not errors, errors
        assert not external, external
        print('Player overlay settings passed:', width, flush=True)
    finally:
        context.close()


def main():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    base = 'http://127.0.0.1:' + str(port)
    with tempfile.TemporaryDirectory(prefix='tracker-player-options-', ignore_cleanup_errors=True) as directory:
        environment = os.environ.copy()
        environment.update(APPDATA=directory, LOCALAPPDATA=directory, TRACKER_TEST_PORT=str(port))
        server = subprocess.Popen([sys.executable, str(ROOT / 'tests/support/browser_server.py')], cwd=ROOT,
                                  env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(100):
                try:
                    urllib.request.urlopen(base, timeout=1).close()
                    break
                except OSError:
                    if server.poll() is not None:
                        raise RuntimeError('isolated server exited')
                    time.sleep(.1)
            else:
                raise RuntimeError('isolated server failed')
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(executable_path=str(CHROME), headless=True)
                try:
                    for width, height in ((1440, 900), (390, 844)):
                        run(browser, base, width, height)
                finally:
                    browser.close()
        finally:
            subprocess.run(['taskkill', '/PID', str(server.pid), '/T', '/F'], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, check=False)
            server.wait(timeout=10)


if __name__ == '__main__':
    main()
