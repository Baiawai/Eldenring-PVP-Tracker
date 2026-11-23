"""Optional Playwright smoke test on an isolated server and temporary data."""
import os
import re
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


def open_settings(page):
    page.goto(page.url or BASE_URL, wait_until='load')
    page.wait_for_selector('.sprit', state='detached', timeout=30000)
    page.locator('#menu_button_settings').click()
    page.locator('.btn_menu_settings[menu="8"]').click()
    page.wait_for_function("() => !document.querySelector('#overlay_custom_background_opacity').disabled")
    page.locator('.overlay-custom-group').evaluate_all('(groups) => groups.forEach(group => group.open = true)')


def get_options(page):
    return page.evaluate("async () => (await (await fetch('/overlay-settings')).json()).options")


def wait_option(page, key, value):
    page.wait_for_function("async ([key, value]) => (await (await fetch('/overlay-settings')).json()).options[key] === value", arg=[key, value])


with socket.socket() as sock:
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
BASE_URL = 'http://127.0.0.1:' + str(port)
with tempfile.TemporaryDirectory(prefix='overlay-custom-ui-', ignore_cleanup_errors=True) as directory:
    env = os.environ.copy()
    env.update(APPDATA=directory, LOCALAPPDATA=directory, TRACKER_TEST_PORT=str(port), TRACKER_TEST_NO_STEAM='1')
    server = subprocess.Popen([sys.executable, str(ROOT / 'tests/support/browser_server.py')], cwd=ROOT, env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(BASE_URL, timeout=1).close()
                break
            except OSError:
                if server.poll() is not None:
                    raise RuntimeError('isolated server exited')
                time.sleep(.1)
        else:
            raise RuntimeError('isolated server failed')
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=str(CHROME), headless=True)
            for width, height in ((1440, 900), (390, 844)):
                context = browser.new_context(viewport={'width':width, 'height':height})
                context.route('**/*', lambda route: route.continue_() if route.request.url.startswith(BASE_URL + '/') else route.abort())
                page = context.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(BASE_URL)
                open_settings(page)
                panel = page.locator('.contente_settings[setting="8"]')
                assert panel.is_visible()
                assert page.locator('#overlay_custom_show_rank').count() == 0
                # Every visible overlay setting shares the same information
                # control, including the master switch and the grouped rows.
                rows = panel.locator('.overlay-custom-row')
                assert rows.count() == 36
                master_row = page.locator('#game_overlay_enabled').locator('xpath=ancestor::div[contains(@class,"form_single")]')
                assert master_row.locator(':scope > .settings-info .settings-info-trigger').count() == 1
                for row in rows.all():
                    trigger = row.locator(':scope > .settings-info .settings-info-trigger')
                    assert trigger.count() == 1
                    tooltip_id = trigger.get_attribute('aria-describedby')
                    assert tooltip_id and row.locator('[role="tooltip"]').get_attribute('id') == tooltip_id
                    assert row.locator('[role="tooltip"] p').count() >= 1
                    assert row.locator('[role="tooltip"] p').first.text_content().strip()
                # Keyboard focus must show a reachable tooltip at both desktop
                # and narrow sizes, including rows in the last collapsed group.
                for index in (0, 1, 11, 16, 28, 33):
                    trigger = rows.nth(index).locator('.settings-info-trigger')
                    trigger.scroll_into_view_if_needed()
                    trigger.focus()
                    tip = rows.nth(index).locator('[role="tooltip"]')
                    assert tip.is_visible(), (width, index, 'tooltip not visible on focus')
                    bounds = tip.bounding_box()
                    assert bounds['x'] >= -1 and bounds['x'] + bounds['width'] <= width + 1, (width, index, bounds)
                    assert bounds['y'] >= -1 and bounds['y'] + bounds['height'] <= height + 1, (width, index, bounds)
                if width == 1440:
                    # Exercise the actual language switch on the dynamic overlay
                    # section, including choices and the common Yes/No widget.
                    # The synthetic profile and browser are isolated from the user.
                    issues = page.evaluate('''() => {
                        const problems = [];
                        const panel = document.querySelector('.contente_settings[setting="8"]');
                        for (const language of ['fra', ...Object.keys(window.ELDEN_UI_PACKS)]) {
                            window.launchLanguages(language);
                            const pack = window.ELDEN_UI_PACKS[language];
                            for (const node of panel.querySelectorAll('[data-i18n]')) {
                                const key = node.dataset.i18n;
                                const translated = pack && pack.modern && pack.modern[key];
                                if (language !== 'fra' && !translated) {
                                    problems.push(language + ': missing ' + key);
                                    continue;
                                }
                                const expected = translated || node.dataset.i18nFr;
                                if (expected && node.textContent !== expected)
                                    problems.push(language + ': incorrect ' + key);
                            }
                            for (const checkbox of panel.querySelectorAll('input[type="checkbox"][data-yes-no-ready="1"]')) {
                                const value = checkbox.nextElementSibling.querySelector('span');
                                const choices = pack && pack.legacy ? [pack.legacy[44], pack.legacy[45]] : ['Non', 'Oui'];
                                if (!value || value.textContent !== choices[checkbox.checked ? 1 : 0])
                                    problems.push(language + ': incorrect Yes/No ' + checkbox.id);
                            }
                        }
                        window.launchLanguages('fra');
                        return problems;
                    }''')
                    assert not issues, issues
                    assert page.locator('#overlay_custom_show_jitter_label').inner_text() == 'Variation du ping'
                    assert page.locator('#overlay_custom_visibility_mode').input_value() == 'game_visible'
                    assert page.locator('#overlay_custom_width_percent').input_value() == '80'
                    # The separate master switch is saved and restored too.
                    master = page.locator('#game_overlay_enabled')
                    master_row = master.locator('xpath=ancestor::div[contains(@class,"form_single")]')
                    initial_master = master.is_checked()
                    master_row.locator('.yes-no-control button').first.click()
                    page.wait_for_function('''async expected =>
                        (await (await fetch('/overlay-settings', {cache:'no-store'})).json()).enabled === expected''',
                        arg=not initial_master)
                    page.reload(wait_until='load')
                    open_settings(page)
                    assert page.locator('#game_overlay_enabled').is_checked() is (not initial_master)
                    master_row = page.locator('#game_overlay_enabled').locator('xpath=ancestor::div[contains(@class,"form_single")]')
                    master_row.locator('.yes-no-control button').first.click()
                    page.wait_for_function('''async expected =>
                        (await (await fetch('/overlay-settings', {cache:'no-store'})).json()).enabled === expected''',
                        arg=initial_master)
                for percentage in (60, 100, 75):
                    slider = page.locator('#overlay_custom_width_percent')
                    slider.fill(str(percentage))
                    wait_option(page, 'width_percent', percentage)
                    assert page.locator('#overlay_custom_width_percent_value').inner_text() == f'{percentage} %'
                border = page.locator('#overlay_custom_show_overlay_border')
                if width == 1440:
                    assert not border.is_checked()
                border_row = border.locator('xpath=ancestor::div[contains(@class,"form_single")]')
                initial_border = border.is_checked()
                border_row.locator('.yes-no-control button').first.click()
                wait_option(page, 'show_overlay_border', not initial_border)
                for visibility in ('always', 'capture', 'game_visible'):
                    page.locator('#overlay_custom_visibility_mode').select_option(visibility)
                    wait_option(page, 'visibility_mode', visibility)
                for language in ('fra', 'eng'):
                    page.evaluate('(language) => launchLanguages(language)', language)
                    for visibility in ('capture', 'game_visible', 'always'):
                        select = page.locator('#overlay_custom_visibility_mode')
                        select.select_option(visibility)
                        fits = select.evaluate('''node => {
                            const style = getComputedStyle(node);
                            const canvas = document.createElement('canvas');
                            const context = canvas.getContext('2d');
                            context.font = `${style.fontStyle} ${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
                            const text = node.selectedOptions[0].textContent;
                            return context.measureText(text).width <= node.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
                        }''')
                        full_value = page.locator('#overlay_custom_visibility_mode_selected')
                        if not fits:
                            assert full_value.is_visible(), f'visibility option clipped: {language} / {visibility} / {width}'
                            assert full_value.inner_text() == select.locator('option:checked').inner_text()
                            assert full_value.evaluate('node => node.scrollWidth <= node.clientWidth')
                page.evaluate("() => launchLanguages('fra')")
                count_row = page.locator('#overlay_custom_show_player_stats').locator('xpath=ancestor::div[contains(@class,"form_single")]')
                assert count_row.locator('.form_single_left').inner_text() == 'Nombre de rencontres'
                page.locator('#overlay_custom_visibility_mode').select_option('game_visible')
                wait_option(page, 'visibility_mode', 'game_visible')
                assert page.locator('#overlay_custom_background_opacity_value').inner_text().endswith('%')
                for transparency in (0, 100, 30):
                    slider = page.locator('#overlay_custom_background_opacity')
                    slider.fill(str(transparency))
                    wait_option(page, 'background_opacity', 100 - transparency)
                    assert page.locator('#overlay_custom_background_opacity_value').inner_text() == f'{transparency} %'
                for transparency in (0, 100, 35):
                    slider = page.locator('#overlay_custom_text_opacity')
                    slider.fill(str(transparency))
                    wait_option(page, 'text_opacity', 100 - transparency)
                    assert page.locator('#overlay_custom_text_opacity_value').inner_text() == f'{transparency} %'
                for radius in (0, 30, 12):
                    page.locator('#overlay_custom_border_radius').select_option(str(radius))
                    wait_option(page, 'border_radius', radius)
                for name, value in (('background_color','#3567aa'), ('text_color','#eeddbb'), ('border_color','#a76b40')):
                    page.locator('#overlay_custom_' + name).fill(value)
                    wait_option(page, name, value)
                for font_size in ('12', '32'):
                    page.locator('#overlay_custom_font_size').select_option(font_size)
                    wait_option(page, 'font_size', int(font_size))
                for position in ('top_left', 'top_right', 'bottom_left', 'bottom_right'):
                    page.locator('#overlay_custom_position').select_option(position)
                    wait_option(page, 'position', position)
                for name in ('show_status','show_mode','show_peers','show_event', 'show_player_count',
                             'show_avatars', 'show_player_name', 'show_role', 'show_steam_id', 'show_country', 'show_ping',
                             'show_ping_average', 'show_jitter', 'show_quality', 'show_duration',
                             'show_player_stats', 'show_player_tags', 'show_player_favourite'):
                    control = page.locator('#overlay_custom_' + name)
                    before = control.is_checked()
                    row = control.locator('xpath=ancestor::div[contains(@class,"form_single")]')
                    row.locator('.yes-no-control button').first.scroll_into_view_if_needed()
                    row.locator('.yes-no-control button').first.click()
                    wait_option(page, name, not before)
                # All controls, including the last one, can be reached by scrolling.
                last = page.locator('#overlay_custom_show_event').locator('xpath=ancestor::div[contains(@class,"form_single")]')
                last.locator('.yes-no-control button').first.scroll_into_view_if_needed()
                assert last.locator('.yes-no-control button').first.is_visible()
                for name, value in (('avatar_size', '64'), ('card_size', '100'), ('card_spacing', '16')):
                    page.locator('#overlay_custom_' + name).select_option(value)
                    wait_option(page, name, int(value))
                for name, value in (('ping_good_color','#135799'), ('ping_medium_color','#aadd11'), ('ping_bad_color','#ff9911')):
                    page.locator('#overlay_custom_' + name).fill(value)
                    wait_option(page, name, value)
                saved = get_options(page)
                page.reload(wait_until='load')
                open_settings(page)
                assert page.locator('#overlay_custom_background_opacity').input_value() == '30'
                assert page.locator('#overlay_custom_background_color').input_value() == '#3567aa'
                assert page.locator('#overlay_custom_text_color').input_value() == '#eeddbb'
                assert page.locator('#overlay_custom_border_color').input_value() == '#a76b40'
                assert page.locator('#overlay_custom_border_radius').input_value() == '12'
                assert page.locator('#overlay_custom_text_opacity').input_value() == '35'
                assert page.locator('#overlay_custom_font_size').input_value() == '32'
                assert page.locator('#overlay_custom_width_percent').input_value() == '75'
                assert page.locator('#overlay_custom_show_overlay_border').is_checked() == saved['show_overlay_border']
                assert page.locator('#overlay_custom_position').input_value() == 'bottom_right'
                assert page.locator('#overlay_custom_visibility_mode').input_value() == 'game_visible'
                assert all(page.locator('#overlay_custom_' + name).is_checked() == saved[name]
                           for name in ('show_status', 'show_mode', 'show_peers', 'show_event', 'show_player_count',
                                        'show_avatars', 'show_player_name', 'show_role', 'show_steam_id',
                                        'show_country', 'show_ping', 'show_ping_average', 'show_jitter',
                                        'show_quality', 'show_duration', 'show_player_stats', 'show_player_tags', 'show_player_favourite'))
                for name in ('avatar_size', 'card_size', 'card_spacing', 'ping_good_color',
                             'ping_medium_color', 'ping_bad_color'):
                    assert page.locator('#overlay_custom_' + name).input_value() == str(saved[name]), name
                page.evaluate("launchLanguages('eng')")
                assert page.locator('label[for="overlay_custom_background_color"]').inner_text() == page.evaluate("ELDEN_UI_PACKS.eng.modern.overlay_custom_background_color")
                assert page.locator('#overlay_custom_position option[value="bottom_right"]').inner_text() == page.evaluate("ELDEN_UI_PACKS.eng.modern.overlay_position_bottom_right")
                page.evaluate("launchLanguages('fra')")
                # Reject a save and check that the control returns to its saved value.
                def fail_option(route):
                    if route.request.method == 'POST' and route.request.headers.get('content-type','').startswith('application/json'):
                        route.fulfill(status=503, json={'request':'error'})
                    else:
                        route.continue_()
                page.route('**/overlay-settings', fail_option)
                page.locator('#overlay_custom_font_size').select_option('24')
                page.wait_for_function("() => document.querySelector('.overlay-custom-status').textContent.length > 0")
                assert page.locator('#overlay_custom_font_size').input_value() == '32'
                assert page.locator('#overlay_custom_width_percent').input_value() == '75'
                assert page.locator('#overlay_custom_show_overlay_border').is_checked() == saved['show_overlay_border']
                assert not errors, errors
                page.screenshot(path=str(Path(os.environ['TEMP']) / ('overlay-custom-' + str(width) + '.png')))
                context.close()
                print('Passed viewport', width, flush=True)
            # Earlier servers may still have a cached template from before the
            # section existed. Exercise the fallback with and without its row.
            for old_row in (True, False):
                context = browser.new_context(viewport={'width':1440, 'height':900})
                context.route('**/*', lambda route: route.continue_() if route.request.url.startswith(BASE_URL + '/') else route.abort())
                page = context.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                def old_template(route):
                    response = route.fetch()
                    html = response.text()
                    html = re.sub(r'<button[^>]+menu="8"[^>]*>.*?</button>', '', html, count=1, flags=re.S)
                    match = re.search(r'<section class="contente_settings hide overlay-settings"[^>]*>(.*?)</section>', html, flags=re.S)
                    assert match
                    row = match.group(1)
                    html = html[:match.start()] + html[match.end():]
                    if old_row:
                        marker = '<div class="contente_settings" setting="0">'
                        html = html.replace(marker, marker + row, 1)
                    else:
                        html = re.sub(r'<script[^>]+src="/static/overlay-settings.js"[^>]*></script>', '', html, count=1)
                    route.fulfill(response=response, body=html)
                page.route(BASE_URL + '/', old_template)
                page.goto(BASE_URL)
                open_settings(page)
                assert page.locator('#overlay_custom_background_opacity').count() == 1
                assert page.locator('#overlay_custom_show_event').count() == 1
                assert page.locator('#overlay_custom_background_opacity').input_value() == '30'
                assert page.locator('#overlay_custom_font_size').input_value() == '32'
                assert not errors, errors
                context.close()
                print('Passed cached template:', old_row, flush=True)
            browser.close()
    finally:
        subprocess.run(['taskkill', '/PID', str(server.pid), '/T', '/F'], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, check=False)
        server.wait(timeout=10)
print('Overlay customization checks passed')
