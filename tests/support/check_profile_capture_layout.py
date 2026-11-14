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
    env.update(APPDATA=directory, TRACKER_TEST_PORT=str(port))
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
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=str(CHROME), headless=True)
            try:
                for width, height in [(1440,900), (390,844)]:
                    context, page, _, errors = scenario(browser, url, viewport={'width':width, 'height':height})
                    try:
                        page.wait_for_selector('.sprit', state='detached', timeout=30000)
                        ready = [False]
                        saves = []
                        def capture(route):
                            payload = urllib.parse.parse_qs(route.request.post_data or '')
                            action = payload.get('action', [''])[0]
                            if action == 'read':
                                route.fulfill(json={'request':'success', 'token':'fixture-token', 'profile':profile} if ready[0] else {'request':'waiting'})
                            elif action == 'save':
                                saves.append(payload.get('token', [''])[0])
                                route.fulfill(json={'request':'success', 'profile':profile})
                            else:
                                route.fulfill(json={'request':'waiting'})
                        page.route('**/profile-capture', capture)
                        page.evaluate('window.openProfileCapture()')
                        panel = page.locator('#profile_capture_panel')
                        panel.wait_for(state='visible')
                        assert page.locator('#profile_capture_cancel').is_visible()
                        assert page.locator('#profile_capture_save').is_hidden()
                        ready[0] = True
                        page.locator('#profile_capture_preview').wait_for(state='visible', timeout=7000)
                        cancel, save = page.locator('#profile_capture_cancel'), page.locator('#profile_capture_save')
                        assert save.is_visible() and cancel.is_visible()
                        c, s = cancel.bounding_box(), save.bounding_box()
                        assert abs(c['y'] - s['y']) < 2, (width, 'actions not aligned', c, s)
                        assert c['y'] > page.locator('.profile-capture-content').bounding_box()['y']
                        assert page.locator('#profile_capture_name').inner_text() == profile['name']
                        assert page.locator('#profile_capture_level').inner_text() == str(profile['level'])
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
                        cancel.click()
                        assert panel.is_hidden() and not saves
                        page.evaluate('window.openProfileCapture()')
                        page.locator('#profile_capture_preview').wait_for(state='visible', timeout=7000)
                        save.click()
                        panel.wait_for(state='hidden', timeout=7000)
                        assert panel.is_hidden() and saves == ['fixture-token']
                        assert page.locator('.sidebar-profile-name').text_content() == profile['name'], page.locator('.sidebar-profile-name').text_content()
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
                assert instructions.get_attribute('data-i18n') == 'profile_step_menu'
                for language in ['eng','deu','ita','spaes','spaar','por','pol','rus','jap','kor','chi','zht','tha','ara']:
                    cached.evaluate('(code) => uiApplyLanguage(code)', language)
                    expected = cached.evaluate('(code) => ELDEN_UI_PACKS[code].modern.profile_step_menu', language)
                    assert instructions.text_content() == expected, language
                cached.evaluate("uiApplyLanguage('fra')")
                assert 'Quitter la partie' in instructions.text_content()
                cached.close()
            finally:
                browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)
