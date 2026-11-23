"""Review and cancel a simulated profile capture on isolated browser data."""
import base64
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright
from check_online_profile_notice import CHROME, ROOT, scenario

with socket.socket() as sock:
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
with tempfile.TemporaryDirectory(prefix='tracker-profile-layout-', ignore_cleanup_errors=True) as directory:
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
        avatar = base64.b64encode((ROOT / 'static/loader-classic-eye.png').read_bytes()).decode('ascii')
        profile = {'name':'Tarnished', 'level':170, 'avatar':avatar}
        old_avatar = base64.b64encode((ROOT / 'static/icon-edit-profile-bronze.png').read_bytes()).decode('ascii')
        saved_profile = {'name':'Previously saved', 'level':85, 'avatar':old_avatar}
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=str(CHROME), headless=True)
            try:
                for width, height in [(1440,900), (390,844)]:
                    context, page, _, errors = scenario(browser, url, viewport={'width':width, 'height':height})
                    try:
                        page.wait_for_selector('.sprit', state='detached', timeout=30000)
                        page.evaluate("() => { document.getElementById('menu_button_settings').click(); document.querySelector('.btn_menu_settings[menu=\"3\"]').click(); }")
                        assert page.locator('#saved_profile_preview').is_hidden(), 'An empty profile must not show a saved preview'
                        # Revisit with a synthetic saved profile so startup reads
                        # the normal /init response without changing real data.
                        def initial_profile(route):
                            response = route.fetch()
                            payload = response.json()
                            payload['user'][1] = saved_profile['name']
                            payload['user'][6] = saved_profile['avatar']
                            payload['user'][19] = saved_profile['level']
                            route.fulfill(response=response, json=payload)
                        page.route('**/init', initial_profile)
                        page.reload(wait_until='load')
                        page.wait_for_selector('.sprit', state='detached', timeout=30000)
                        ready = [False]
                        fail_save = [False]
                        saves = []
                        def capture(route):
                            payload = urllib.parse.parse_qs(route.request.post_data or '')
                            action = payload.get('action', [''])[0]
                            if action == 'read':
                                route.fulfill(json={'request':'success', 'token':'fixture-token', 'profile':profile} if ready[0] else {'request':'waiting'})
                            elif action == 'save':
                                saves.append(payload.get('token', [''])[0])
                                if fail_save[0]:
                                    route.fulfill(status=500, body='error')
                                else:
                                    route.fulfill(json={'request':'success', 'profile':profile})
                            else:
                                route.fulfill(json={'request':'waiting'})
                        page.route('**/profile-capture', capture)
                        page.evaluate('window.openProfileCapture()')
                        panel = page.locator('#profile_capture_panel')
                        panel.wait_for(state='visible')
                        saved = page.locator('#saved_profile_preview')
                        assert saved.is_visible()
                        assert page.locator('#saved_profile_title').evaluate('(node) => getComputedStyle(node).paddingTop') == '0px'
                        assert page.locator('#saved_profile_name').inner_text() == saved_profile['name']
                        assert page.locator('#saved_profile_level').inner_text() == str(saved_profile['level'])
                        assert page.locator('#saved_profile_avatar').get_attribute('src').endswith(saved_profile['avatar'])
                        assert page.locator('#profile_capture_cancel').is_visible()
                        assert page.locator('#profile_capture_save').is_hidden()
                        guide = page.locator('#profile_capture_instructions.profile-capture-guide')
                        assert guide.is_visible()
                        steps = guide.locator('ol.profile-guide-steps > li')
                        assert steps.count() == 5
                        figures = guide.locator('figure.profile-guide-visual')
                        captions = figures.locator('figcaption')
                        assert figures.count() == 2 and captions.count() == 2
                        assert all(caption.is_visible() for caption in captions.all())
                        assert page.locator('#profile_capture_status').inner_text().strip()
                        languages = ['fra'] + page.evaluate('() => Object.keys(window.ELDEN_UI_PACKS)')
                        assert len(languages) == 30 and len(set(languages)) == 30
                        keys = ['profile_guide_step_' + str(number) for number in range(1, 6)] + ['profile_guide_menu_visual_label', 'profile_guide_profile_visual_label']
                        for language in languages:
                            page.evaluate('(code) => uiApplyLanguage(code)', language)
                            expected = page.evaluate('''([code, keys]) => keys.map(key => code === 'fra'
                                ? document.querySelector('#profile_capture_instructions [data-i18n="' + key + '"]').dataset.i18nFr
                                : window.ELDEN_UI_PACKS[code].modern[key])''', [language, keys])
                            actual = steps.all_text_contents() + captions.all_text_contents()
                            assert all(isinstance(value, str) and value.strip() for value in expected), (width, language, expected)
                            assert [value.strip() for value in actual] == [value.strip() for value in expected], (width, language, actual, expected)
                            assert guide.evaluate('(node) => node.scrollWidth <= node.clientWidth + 2'), (width, language, 'guide overflow')
                            for step in steps.all():
                                assert step.evaluate('(node) => parseFloat(getComputedStyle(node).fontSize)') >= 18, (width, language)
                        page.evaluate("uiApplyLanguage('fra')")
                        screenshot_dir = os.environ.get('TRACKER_PROFILE_SCREENSHOT_DIR')
                        if screenshot_dir:
                            guide.screenshot(path=str(Path(screenshot_dir) / ('profile-guide-' + str(width) + '.png')))
                        for index, caption in enumerate(captions.all(), start=1):
                            caption.scroll_into_view_if_needed()
                            assert caption.evaluate('''node => {
                                const rect = node.getBoundingClientRect();
                                if (rect.top < 0 || rect.bottom > innerHeight) return false;
                                for (let parent = node.parentElement; parent; parent = parent.parentElement) {
                                    if (/(auto|scroll|hidden|clip)/.test(getComputedStyle(parent).overflowY)) {
                                        const bounds = parent.getBoundingClientRect();
                                        if (rect.top < bounds.top - 1 || rect.bottom > bounds.bottom + 1) return false;
                                    }
                                }
                                return true;
                            }'''), (width, index, 'The visual caption cannot be reached by scrolling')
                            assert figures.nth(index - 1).locator('svg').count() == 1
                            if screenshot_dir:
                                figures.nth(index - 1).screenshot(
                                    path=str(Path(screenshot_dir) / ('profile-guide-visual-' + str(index) + '-' + str(width) + '.png')))
                        ready[0] = True
                        page.locator('#profile_capture_preview').wait_for(state='visible', timeout=7000)
                        assert guide.is_hidden(), 'The instructions must not obscure the review'
                        cancel, save = page.locator('#profile_capture_cancel'), page.locator('#profile_capture_save')
                        assert save.is_visible() and cancel.is_visible()
                        c, s = cancel.bounding_box(), save.bounding_box()
                        assert abs(c['y'] - s['y']) < 2, (width, 'actions not aligned', c, s)
                        assert c['y'] > page.locator('.profile-capture-content').bounding_box()['y']
                        assert page.locator('#profile_capture_name').inner_text() == profile['name']
                        assert page.locator('#profile_capture_level').inner_text() == str(profile['level'])
                        assert page.locator('#saved_profile_name').inner_text() == saved_profile['name']
                        assert page.locator('#saved_profile_avatar').get_attribute('src').endswith(saved_profile['avatar'])
                        screenshot_dir = os.environ.get('TRACKER_PROFILE_SCREENSHOT_DIR')
                        if screenshot_dir:
                            panel.screenshot(path=str(Path(screenshot_dir) / ('profile-review-' + str(width) + '.png')))
                        for language in ['fra','eng','deu','ita','spaes','spaar','por','pol','rus','jap','kor','chi','zht','tha','ara']:
                            page.evaluate('(code) => launchLanguages(code)', language)
                            if language != 'fra':
                                words = page.evaluate('''code => [ELDEN_UI_PACKS[code].modern.profile_capture_cancel,
                                                                 ELDEN_UI_PACKS[code].modern.profile_legend_save]''', language)
                                assert [cancel.inner_text(), save.inner_text()] == words, (width, language)
                                labels = page.evaluate('''code => [ELDEN_UI_PACKS[code].legacy[52],
                                                                  ELDEN_UI_PACKS[code].legacy[54],
                                                                  ELDEN_UI_PACKS[code].modern.profile_capture_review]''', language)
                                actual = [page.locator('.profile-capture-fields .vt_pseudo_tr').inner_text(),
                                          page.locator('.profile-capture-fields .vt_niveau_tr').inner_text(),
                                          page.locator('#profile_capture_preview [data-i18n="profile_capture_review"]').inner_text()]
                                assert actual == labels, (width, language, actual, labels)
                                saved_labels = page.evaluate('''code => [ELDEN_UI_PACKS[code].modern.profile_saved_preview,
                                                                        ELDEN_UI_PACKS[code].modern.online_name,
                                                                        ELDEN_UI_PACKS[code].modern.leaderboard_level]''', language)
                                actual_saved = [page.locator('#saved_profile_title').inner_text(),
                                                saved.locator('[data-i18n="online_name"]').inner_text(),
                                                saved.locator('[data-i18n="leaderboard_level"]').inner_text()]
                                assert actual_saved == saved_labels, (width, language, actual_saved, saved_labels)
                                assert saved.evaluate('(node) => node.scrollWidth <= node.clientWidth + 1'), (width, language)
                        page.evaluate("launchLanguages('fra')")
                        cancel.click()
                        assert panel.is_hidden() and not saves
                        assert page.locator('#saved_profile_name').inner_text() == saved_profile['name']
                        assert page.locator('#saved_profile_level').inner_text() == str(saved_profile['level'])
                        if screenshot_dir:
                            page.locator('.contente_settings[setting="3"]').screenshot(
                                path=str(Path(screenshot_dir) / ('profile-saved-' + str(width) + '.png')))
                        ready[0] = False
                        page.evaluate('window.openProfileCapture()')
                        assert guide.is_visible() and save.is_hidden(), 'Restart must restore the guide before a capture'
                        ready[0] = True
                        page.locator('#profile_capture_preview').wait_for(state='visible', timeout=7000)
                        fail_save[0] = True
                        save.click()
                        page.wait_for_function("() => !document.querySelector('#profile_capture_save').disabled")
                        assert panel.is_visible() and page.locator('#saved_profile_name').inner_text() == saved_profile['name']
                        fail_save[0] = False
                        save.click()
                        panel.wait_for(state='hidden', timeout=7000)
                        assert panel.is_hidden() and saves == ['fixture-token', 'fixture-token']
                        assert saved.is_visible()
                        assert page.locator('#saved_profile_name').inner_text() == profile['name']
                        assert page.locator('#saved_profile_level').inner_text() == str(profile['level'])
                        assert page.locator('#saved_profile_avatar').get_attribute('src').endswith(profile['avatar'])
                        assert page.locator('.sidebar-profile-name').text_content() == profile['name'] + ' (dev)', page.locator('.sidebar-profile-name').text_content()
                        # Partially completed profiles retain the available
                        # fields and hide missing ones without inventing data.
                        page.evaluate("() => window.updateSavedProfilePreview({name:'Only name', level:0, avatar:''})")
                        assert saved.is_visible() and page.locator('#saved_profile_name').inner_text() == 'Only name'
                        assert page.locator('#saved_profile_level').locator('..').is_hidden()
                        assert page.locator('#saved_profile_avatar').is_hidden()
                        page.evaluate("() => window.updateSavedProfilePreview({name:'', level:42, avatar:''})")
                        assert saved.is_visible() and page.locator('#saved_profile_name').locator('..').is_hidden()
                        assert page.locator('#saved_profile_level').inner_text() == '42'
                        page.evaluate('(avatar) => window.updateSavedProfilePreview({name:"", level:0, avatar})', avatar)
                        assert saved.is_visible() and page.locator('#saved_profile_avatar').is_visible()
                        assert page.locator('#saved_profile_name').locator('..').is_hidden()
                        assert page.locator('#saved_profile_level').locator('..').is_hidden()
                        page.evaluate("() => window.updateSavedProfilePreview({name:'', level:0, avatar:''})")
                        assert saved.is_hidden()
                        assert not errors, errors
                    finally:
                        context.close()
                # The running server may still return the previous cached HTML.
                cached = browser.new_page()
                cached.set_content('''<button id="profile_capture_start"></button>
                    <div id="profile_capture_panel" hidden><p id="profile_capture_instructions"></p>
                    <p id="profile_capture_success" hidden></p><p id="profile_capture_status"></p>
                    <button id="profile_capture_cancel">Cancel</button><div id="profile_capture_preview" hidden>
                    <img id="profile_capture_avatar"><p>Name: <strong id="profile_capture_name"></strong></p>
                    <p>Level: <strong id="profile_capture_level"></strong></p><p>Review</p>
                    <button id="profile_capture_save">Save</button></div></div>''')
                cached.add_script_tag(path=str(ROOT / 'static/profile-capture.js'))
                assert cached.locator('.profile-capture-content #profile_capture_avatar').count() == 1
                assert cached.locator('.profile-capture-fields #profile_capture_name').count() == 1
                assert cached.locator('.profile-capture-fields #profile_capture_level').count() == 1
                assert cached.locator('.profile-capture-actions > button').evaluate_all('(nodes) => nodes.map(n => n.id)') == ['profile_capture_cancel', 'profile_capture_save']
                assert cached.locator('#profile_capture_save').get_attribute('hidden') is not None
                # Older cached templates may lack the translation attribute.
                cached.add_script_tag(path=str(ROOT / 'static/ui-packs.js'))
                cached.add_script_tag(path=str(ROOT / 'static/ui-i18n.js'))
                instructions = cached.locator('#profile_capture_instructions')
                assert instructions.locator('ol.profile-guide-steps > li').count() == 5
                assert instructions.locator('figure.profile-guide-visual').count() == 2
                for language in cached.evaluate('() => Object.keys(window.ELDEN_UI_PACKS)'):
                    cached.evaluate('(code) => uiApplyLanguage(code)', language)
                    for key in ['profile_guide_step_' + str(number) for number in range(1, 6)] + ['profile_guide_menu_visual_label', 'profile_guide_profile_visual_label']:
                        expected = cached.evaluate('([code, key]) => ELDEN_UI_PACKS[code].modern[key]', [language, key])
                        assert instructions.locator('[data-i18n="' + key + '"]').text_content() == expected, (language, key)
                cached.evaluate("uiApplyLanguage('fra')")
                assert instructions.locator('ol.profile-guide-steps > li').count() == 5
                cached.close()
            finally:
                browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)
