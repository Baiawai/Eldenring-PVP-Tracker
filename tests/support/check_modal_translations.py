"""Check guide and leaderboard dialog translations in an isolated browser."""
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

from playwright.sync_api import sync_playwright

from check_online_profile_notice import CHROME, ROOT

LANGUAGES = ['fra', 'eng', 'deu', 'ita', 'spaes', 'spaar', 'por', 'pol',
             'rus', 'jap', 'kor', 'chi', 'zht', 'tha', 'ara']
CONSENT_KEYS = ['online_consent_text', 'online_steam_login_required',
                'online_steam_identity_consent', 'online_event_notice',
                'online_event_new_only', 'online_player_content_risk']


def change_language(page, language):
    page.evaluate('''async language => {
        launchLanguages(language);
        await new Promise(resolve => setTimeout(resolve, 10));
    }''', language)


def check_consent(page):
    page.wait_for_selector('#online_enabled', state='attached')
    page.evaluate("() => document.getElementById('online_enabled').dispatchEvent(new Event('change'))")
    dialog = page.locator('.online-dialog')
    dialog.wait_for(state='visible')
    assert dialog.get_attribute('data-action') == 'participation'
    french = {
        'title': page.locator('#online_dialog_title').text_content(),
        'body': page.locator('#online_dialog_text').text_content(),
        'cancel': page.locator('#online_cancel').text_content(),
        'accept': page.locator('#online_accept').text_content(),
    }
    # Simulate an in-flight action and a retained code: translation must not
    # reset them, reopen the dialog, or change its action or nonce.
    page.evaluate('''() => {
        document.getElementById('online_accept').disabled = true;
        document.getElementById('online_steam_code').value = '12345678';
        document.querySelector('.online-dialog').dataset.transitionNonce = 'fixture';
    }''')
    for language in LANGUAGES:
        change_language(page, language)
        actual = [page.locator('#online_dialog_title').text_content(),
                  page.locator('#online_dialog_text').text_content(),
                  page.locator('#online_cancel').text_content(),
                  page.locator('#online_accept').text_content()]
        if language == 'fra':
            expected = [french['title'], french['body'], french['cancel'], french['accept']]
        else:
            expected = page.evaluate('''([language, keys]) => {
                const words = ELDEN_UI_PACKS[language].modern;
                return [words.online_consent_title, keys.map(key => words[key]).join(' '),
                        words.online_cancel, words.online_accept];
            }''', [language, CONSENT_KEYS])
        assert actual == expected, (language, actual, expected)
        assert dialog.is_visible() and dialog.get_attribute('data-action') == 'participation'
        assert dialog.get_attribute('data-transition-nonce') == 'fixture'
        assert page.locator('#online_accept').is_disabled()
        assert page.locator('#online_steam_code').input_value() == '12345678'

    # Revalidation uses the same consent copy but a different action.
    page.evaluate("() => document.querySelector('.online-dialog').dataset.action = 'revalidate'")
    change_language(page, 'eng')
    assert dialog.get_attribute('data-action') == 'revalidate'
    assert page.locator('#online_dialog_title').text_content() == page.evaluate("ELDEN_UI_PACKS.eng.modern.online_consent_title")
    assert page.locator('#online_accept').is_disabled()

    # Exercise the recovery rendering branch without contacting Steam.  The
    # selected installation, typed code and disabled state must survive.
    page.evaluate('''() => {
        const dialog = document.querySelector('.online-dialog');
        dialog.dataset.action = 'steam'; dialog.dataset.step = 'recovery_choose';
        const select = document.getElementById('online_recovery_select');
        select.hidden = false;
        select.replaceChildren(new Option('Choisir une installation', ''), new Option('Fixture', 'one'));
        select.value = 'one';
    }''')
    for language in LANGUAGES:
        change_language(page, language)
        select = page.locator('#online_recovery_select')
        label = page.evaluate('''language => ELDEN_UI_PACKS[language]?.modern.online_recovery_placeholder
                                    || 'Choisir une installation' ''', language)
        assert select.get_attribute('aria-label') == label, language
        assert select.locator('option[value=""]').text_content() == label, language
        assert select.input_value() == 'one'
        assert page.locator('#online_steam_code').input_value() == '12345678'
        assert page.locator('#online_accept').is_disabled()
    page.evaluate("() => document.querySelector('.online-dialog').close()")


def check_disabling(page):
    page.wait_for_function("() => document.getElementById('online_enabled')?.checked === true")
    change_language(page, 'fra')
    page.evaluate("() => document.getElementById('online_enabled').dispatchEvent(new Event('change'))")
    dialog = page.locator('.online-dialog')
    dialog.wait_for(state='visible')
    assert dialog.get_attribute('data-disabling') == '1'
    french = [page.locator('#online_dialog_title').text_content(),
              page.locator('#online_dialog_text').text_content(),
              page.locator('#online_cancel').text_content(),
              page.locator('#online_keep').text_content(),
              page.locator('#online_accept').text_content()]
    page.evaluate("() => document.getElementById('online_accept').disabled = true")
    for language in LANGUAGES:
        change_language(page, language)
        actual = [page.locator('#online_dialog_title').text_content(),
                  page.locator('#online_dialog_text').text_content(),
                  page.locator('#online_cancel').text_content(),
                  page.locator('#online_keep').text_content(),
                  page.locator('#online_accept').text_content()]
        expected = french if language == 'fra' else page.evaluate('''language => {
            const words = ELDEN_UI_PACKS[language].modern;
            return [words.online_disable_title, words.online_disable_text, words.online_cancel,
                    words.online_keep, words.online_remove];
        }''', language)
        assert actual == expected, (language, actual, expected)
        assert dialog.is_visible() and dialog.get_attribute('data-disabling') == '1'
        assert page.locator('#online_accept').is_disabled()
        assert not page.locator('#online_keep').is_hidden()
    page.evaluate("() => document.querySelector('.online-dialog').close()")


def check_guide(page):
    change_language(page, 'fra')
    page.wait_for_selector('.onboarding-card:not([hidden])', state='attached')
    page.evaluate("() => document.querySelector('.onboarding-card').click()")
    dialog = page.locator('.onboarding-dialog')
    dialog.wait_for(state='visible')
    keys = ['onboarding_profile', 'onboarding_steam', 'onboarding_duel']
    titles = ['profile_capture_title', 'online_title', 'arena']
    for index, key in enumerate(keys):
        change_language(page, 'fra')
        french = {
            'description': dialog.locator('.onboarding-description').text_content(),
            'title': dialog.locator('h3').text_content(),
            'previous': dialog.locator('.onboarding-previous').text_content(),
            'next': dialog.locator('.onboarding-next').text_content(),
            'close': dialog.locator('.onboarding-close').get_attribute('aria-label'),
        }
        for language in LANGUAGES:
            change_language(page, language)
            actual = [dialog.locator('.onboarding-description').text_content(),
                      dialog.locator('h3').text_content(),
                      dialog.locator('.onboarding-previous').text_content(),
                      dialog.locator('.onboarding-next').text_content(),
                      dialog.locator('.onboarding-close').get_attribute('aria-label')]
            if language == 'fra':
                expected = list(french.values())
            else:
                expected = page.evaluate('''([language, key, title, last]) => {
                    const words = ELDEN_UI_PACKS[language].modern;
                    return [words[key], words[title], words.online_previous,
                            words[last ? 'initialization_close' : 'online_next'], words.initialization_close];
                }''', [language, key, titles[index], index == 2])
            assert actual == expected, (index, language, actual, expected)
            assert dialog.is_visible()
            assert dialog.get_attribute('dir') == ('rtl' if language == 'ara' else 'ltr')
        if index < 2:
            page.evaluate("() => document.querySelector('.onboarding-next').click()")
    page.evaluate("() => document.querySelector('.onboarding-close').click()")


def main():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix='tracker-modal-i18n-', ignore_cleanup_errors=True) as directory:
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
                    for width, height in [(1440, 900), (390, 844)]:
                        context = browser.new_context(viewport={'width': width, 'height': height})
                        context.route('**/*', lambda route: route.continue_() if route.request.url.startswith(url + '/') else route.abort())
                        context.route('**/onboarding-status', lambda route: route.fulfill(json={'first_capture': False, 'first_event': False}))
                        context.route('**/online-leaderboard/settings', lambda route: route.fulfill(json={'enabled': False, 'configured': True, 'state': 'idle', 'steam_status_observe': False}))
                        page = context.new_page()
                        errors = []
                        page.on('pageerror', lambda error: errors.append(str(error)))
                        page.goto(url, wait_until='load')
                        page.wait_for_selector('.onboarding-card:not([hidden])', state='attached', timeout=10000)
                        page.wait_for_selector('.sprit', state='detached', timeout=30000)
                        change_language(page, 'fra')
                        check_consent(page)
                        check_guide(page)
                        assert not errors, errors
                        print(f'{width}x{height}: consent and guide translated in all 15 languages')
                        context.close()

                        context = browser.new_context(viewport={'width': width, 'height': height})
                        context.route('**/*', lambda route: route.continue_() if route.request.url.startswith(url + '/') else route.abort())
                        context.route('**/online-leaderboard/settings', lambda route: route.fulfill(json={'enabled': True, 'configured': True, 'state': 'success', 'steam_status_observe': False}))
                        page = context.new_page()
                        page.goto(url, wait_until='load')
                        page.wait_for_selector('.sprit', state='detached', timeout=30000)
                        check_disabling(page)
                        print(f'{width}x{height}: disable dialog translated in all 15 languages')
                        context.close()
                finally:
                    browser.close()
        finally:
            if os.name == 'nt':
                subprocess.run(['taskkill', '/PID', str(server.pid), '/T', '/F'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            else:
                server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()


if __name__ == '__main__':
    main()
