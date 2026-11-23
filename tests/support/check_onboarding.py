"""Exercise the guide in a headless browser with an isolated test server."""
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

ROOT = Path(__file__).resolve().parents[2]
CHROME = Path(os.environ.get('ProgramFiles', r'C:\Program Files')) / 'Google/Chrome/Application/chrome.exe'
with socket.socket() as sock:
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
with tempfile.TemporaryDirectory(prefix='tracker-onboarding-browser-', ignore_cleanup_errors=True) as directory:
    env = os.environ.copy()
    env.update(APPDATA=directory, LOCALAPPDATA=directory, TRACKER_TEST_PORT=str(port), TRACKER_TEST_NO_STEAM='1')
    server = subprocess.Popen([sys.executable, str(ROOT / 'tests/support/browser_server.py')], cwd=ROOT, env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        url = 'http://127.0.0.1:' + str(port)
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
            sizes = ([(390, 844)] if os.environ.get('TRACKER_GUIDE_MOBILE') else
                     [(1440, 900)] if os.environ.get('TRACKER_GUIDE_QUICK') else [(1440, 900), (390, 844)])
            for width, height in sizes:
                page = browser.new_page(viewport={'width':width, 'height':height})
                state = {'first_capture':False, 'first_event':False}
                page.route('**/onboarding-status', lambda route: route.fulfill(json=state))
                page.route('**/online-leaderboard/settings', lambda route: route.fulfill(json={'enabled':False, 'configured':True, 'state':'idle'}))
                page.route('**/profile-capture', lambda route: route.fulfill(json={'request':'pending'}))
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(url, wait_until='load')
                page.wait_for_selector('.onboarding-card:not([hidden])', timeout=10000)
                page.wait_for_selector('.sprit', state='detached', timeout=30000)
                assert page.locator('.sidebar-scoreboard').is_hidden()
                assert page.locator('.sidebar-last').is_hidden()
                assert page.locator('.sidebar-summary').is_hidden()
                assert page.locator('.profile-card').evaluate("node => parseFloat(getComputedStyle(node).paddingBottom)") == 0
                if not page.locator('body').evaluate("element => element.classList.contains('profile-sidebar-open')"):
                    page.locator('#sidebar_toggle').click()
                bounds = page.locator('.onboarding-card').bounding_box()
                assert bounds and bounds['y'] >= 0 and bounds['y'] + bounds['height'] <= height + 1, (width, 'card outside viewport', bounds)
                card = page.locator('.onboarding-card')
                initial_opacity = float(card.evaluate('node => getComputedStyle(node).opacity'))
                card.hover()
                page.wait_for_timeout(250)
                assert float(card.evaluate('node => getComputedStyle(node).opacity')) > initial_opacity
                assert card.evaluate('node => getComputedStyle(node).outlineStyle') == 'none'
                for selector in ('.onboarding-card', '.onboarding-card strong', '.onboarding-card span'):
                    assert page.locator(selector).evaluate('node => getComputedStyle(node).cursor') == 'pointer', (width, selector)
                initial_angle = card.evaluate("node => getComputedStyle(node, '::before').getPropertyValue('--onboarding-glow-angle')")
                page.wait_for_timeout(250)
                next_angle = card.evaluate("node => getComputedStyle(node, '::before').getPropertyValue('--onboarding-glow-angle')")
                assert initial_angle != next_angle, ('glow did not rotate', width, initial_angle, next_angle)
                page.emulate_media(reduced_motion='reduce')
                initial_angle = card.evaluate("node => getComputedStyle(node, '::before').getPropertyValue('--onboarding-glow-angle')")
                page.wait_for_timeout(250)
                next_angle = card.evaluate("node => getComputedStyle(node, '::before').getPropertyValue('--onboarding-glow-angle')")
                assert initial_angle != next_angle, ('glow stopped with reduced motion', width)
                page.emulate_media(reduced_motion='no-preference')
                profile_notice = page.locator('.carde_info[info="profile"]')
                if profile_notice.count():
                    page.locator('.profile-card').hover()
                    assert float(profile_notice.evaluate('node => getComputedStyle(node).opacity')) == 1
                    profile_card = page.locator('.profile-card')
                    assert profile_card.get_attribute('role') == 'button'
                    assert profile_card.get_attribute('tabindex') == '0'
                    for selector in ('.profile-card', '.profile-card-header', '.sidebar-profile-name', '.fakeImageuser'):
                        assert page.locator(selector).evaluate('node => getComputedStyle(node).cursor') == 'pointer', (width, selector)
                    sidebar_preference = page.evaluate("localStorage.getItem('trackerProfileSidebarOpen')")
                    profile_card.click()
                    assert page.locator('#profile_capture_panel').is_visible()
                    if width <= 760:
                        assert page.evaluate("localStorage.getItem('trackerProfileSidebarOpen')") == sidebar_preference
                    page.locator('#profile_capture_cancel').click()
                    page.locator('#menu_button_settings').click()
                    if not page.locator('body').evaluate("element => element.classList.contains('profile-sidebar-open')"):
                        page.locator('#sidebar_toggle').click()
                    profile_card.focus()
                    page.keyboard.press('Enter')
                    assert page.locator('#profile_capture_panel').is_visible()
                    page.locator('#profile_capture_cancel').click()
                    page.locator('#menu_button_settings').click()
                    if not page.locator('body').evaluate("element => element.classList.contains('profile-sidebar-open')"):
                        page.locator('#sidebar_toggle').click()
                page.evaluate("window.updateSidebarProfile('Tarnished', 0)")
                assert page.locator('.sidebar-profile-name').inner_text() == 'Tarnished (dev)'
                assert page.locator('.sidebar-profile-level-label').is_hidden()
                page.evaluate("window.updateSidebarProfile('', 170)")
                assert page.locator('.sidebar-profile-level-value').inner_text() == '170'
                assert not page.locator('.sidebar-profile-level-label').is_hidden()
                page.evaluate("window.updateSidebarProfile('', 0)")
                languages = (['fra'] if os.environ.get('TRACKER_GUIDE_QUICK') else
                             ['fra', *json.loads((ROOT / 'application/locales/ui_packs.json').read_text(encoding='utf-8'))])
                for code in languages:
                    page.evaluate('(language) => launchLanguages(language)', code)
                    page.wait_for_timeout(150)
                    if code != 'fra':
                        expected = page.evaluate("window.ELDEN_UI_PACKS[window.uiCurrentLanguage()].modern.sidebar_profile_missing")
                        assert page.locator('.sidebar-profile-name').inner_text() == expected, (width, code)
                        expected = page.evaluate("window.ELDEN_UI_PACKS[window.uiCurrentLanguage()].modern.sidebar_level_missing")
                        assert page.locator('.sidebar-profile-level-value').inner_text() == expected, (width, code)
                    if os.environ.get('TRACKER_GUIDE_SCREENSHOT_DIR'):
                        page.screenshot(path=str(Path(os.environ['TRACKER_GUIDE_SCREENSHOT_DIR']) / 'page-before.png'))
                    page.locator('.onboarding-card').click(timeout=10000)
                    for index, key in enumerate(['onboarding_profile','onboarding_steam','onboarding_duel']):
                        dialog = page.locator('.onboarding-dialog')
                        assert dialog.is_visible(), (width, code, index)
                        assert dialog.locator('h2').count() == 0
                        progress = dialog.locator('.onboarding-progress')
                        assert progress.text_content() == f'{index + 1} / 3', (width, code, index)
                        assert progress.evaluate('node => getComputedStyle(node).direction') == 'ltr', (width, code, index)
                        assert float(dialog.locator('.onboarding-progress').evaluate('node => parseFloat(getComputedStyle(node).fontSize)')) >= 24
                        assert float(dialog.locator('.onboarding-close').evaluate('node => parseFloat(getComputedStyle(node).borderTopWidth)')) == 0
                        nav = dialog.locator('nav')
                        before_scroll = nav.bounding_box()
                        dialog_bounds = dialog.bounding_box()
                        assert before_scroll['y'] + before_scroll['height'] <= dialog_bounds['y'] + dialog_bounds['height'], (width, code, index, 'navigation clipped')
                        for button in nav.locator('button').all():
                            bounds = button.bounding_box()
                            assert bounds['x'] >= dialog_bounds['x'] and bounds['x'] + bounds['width'] <= dialog_bounds['x'] + dialog_bounds['width'] + 1, (width, code, index, 'button clipped')
                        dialog.locator('.onboarding-body').evaluate('node => node.scrollTop = node.scrollHeight')
                        after_scroll = nav.bounding_box()
                        assert abs(before_scroll['y'] - after_scroll['y']) < 1, (width, code, index, 'navigation moved')
                        dialog.locator('.onboarding-body').evaluate('node => node.scrollTop = 0')
                        if code != 'fra':
                            expected = page.evaluate('(key) => window.ELDEN_UI_PACKS[window.uiCurrentLanguage()].modern[key]', key)
                            assert dialog.locator('.onboarding-description').text_content() == expected, (width, code, index)
                            visual_key = ['profile_capture_title', 'online_participate', None][index]
                            if visual_key:
                                visual_text = page.evaluate('(key) => window.ELDEN_UI_PACKS[window.uiCurrentLanguage()].modern[key]', visual_key)
                                assert visual_text in dialog.locator('.onboarding-visual').inner_text(), (width, code, index, visual_text)
                        assert dialog.locator('.onboarding-visual').locator('li, .form_single').count() > 0, (width, code, index)
                        assert dialog.locator('.onboarding-visual').evaluate('(node) => node.scrollWidth <= node.clientWidth + 2'), (width, code, index, 'overflow')
                        screenshot_dir = os.environ.get('TRACKER_GUIDE_SCREENSHOT_DIR')
                        if screenshot_dir:
                            dialog.screenshot(path=str(Path(screenshot_dir) / f'guide-{width}-{code}-{index + 1}.png'))
                        if index < 2:
                            dialog.locator('.onboarding-next').click()
                    page.locator('.onboarding-close').click()
                state['first_event'] = True
                page.wait_for_selector('.sidebar-scoreboard:not([hidden])', timeout=10000)
                assert page.locator('.profile-card').evaluate("node => parseFloat(getComputedStyle(node).paddingBottom)") > 0
                assert not page.locator('.onboarding-card').is_hidden()
                assert not page.locator('.sidebar-last').is_hidden()
                assert not page.locator('.sidebar-summary').is_hidden()
                state['first_capture'] = True
                page.wait_for_selector('.onboarding-card[hidden]', state='attached', timeout=10000)
                assert not page.locator('.onboarding-card').is_visible()
                if profile_notice.count():
                    profile_notice.evaluate('node => node.remove()')
                    page.wait_for_function("!document.querySelector('.profile-card').classList.contains('profile-actionable')")
                    assert page.locator('.profile-card').get_attribute('role') is None
                    assert page.locator('.profile-card').get_attribute('tabindex') is None
                    assert page.locator('.profile-card-header').evaluate('node => getComputedStyle(node).cursor') != 'pointer'
                assert not errors, errors
                page.close()
            if not os.environ.get('TRACKER_GUIDE_QUICK'):
                # A tracker already running before the update has no new endpoint.
                page = browser.new_page(viewport={'width':1440, 'height':900})
                old_state = {'won':False, 'event':False}
                page.route('**/onboarding-status', lambda route: route.fulfill(status=404))
                def old_captures(route):
                    row = [1, '', '1' if old_state['won'] else '0', '0', '0' if old_state['won'] else '1', '', '', 'Arena']
                    route.fulfill(json={'captures':[row]})
                page.route('**/allCapturesChart*', old_captures)
                page.route('**/detection-history*', lambda route: route.fulfill(json={'events':[{'kind':'detection', 'mode':'Arena'}] if old_state['event'] else []}))
                page.goto(url, wait_until='load')
                page.wait_for_selector('.sprit', state='detached', timeout=30000)
                page.wait_for_selector('.onboarding-card:not([hidden])', timeout=10000)
                assert not page.locator('.sidebar-scoreboard').is_hidden()  # A draw is still a game event.
                old_state['won'] = True
                page.wait_for_selector('.onboarding-card[hidden]', state='attached', timeout=22000)
                page.close()
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)
