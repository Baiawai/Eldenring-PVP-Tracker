"""Create localized draft Store screenshots using the isolated browser server.

No game, Steam account, real profile or history is used. Images show the real
development UI with a fresh temporary profile, not an installed Store package.
"""
import argparse
import hashlib
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
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from application.version import APP_VERSION

CHROME = Path(os.environ.get('ProgramFiles', r'C:\Program Files')) / 'Google/Chrome/Application/chrome.exe'
PACKS = json.loads((ROOT / 'application/locales/ui_packs.json').read_text(encoding='utf-8'))
LANGUAGES = ['fra', *PACKS]
SOURCES = ('application/version.py', 'templates/index.html', 'static/app.js',
           'static/ui-packs.js', 'static/ui-i18n.js', 'static/overlay-settings.js',
           'static/style.css', 'static/stats-page.css')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--version', default=APP_VERSION, help='Version expected in the source UI')
    parser.add_argument('--output', type=Path, help='New empty output directory')
    parser.add_argument('--languages', nargs='+', choices=LANGUAGES, default=LANGUAGES)
    args = parser.parse_args()
    if args.version != APP_VERSION:
        parser.error('Requested version does not match application/version.py')
    if args.output is None:
        args.output = ROOT / 'release/store' / ('screenshots-' + args.version)
    if args.output.exists() and any(args.output.iterdir()):
        parser.error('Output directory must be empty; existing screenshots are never overwritten')
    source_hashes = {name: digest(ROOT / name) for name in SOURCES}
    args.output.mkdir(parents=True, exist_ok=True)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    url = f'http://127.0.0.1:{port}'
    with tempfile.TemporaryDirectory(prefix='tracker-store-screenshots-', ignore_cleanup_errors=True) as temp:
        env = os.environ.copy()
        env.update(APPDATA=temp, LOCALAPPDATA=temp, TRACKER_TEST_PORT=str(port), TRACKER_TEST_NO_STEAM='1')
        server = subprocess.Popen([sys.executable, str(ROOT / 'tests/support/browser_server.py')], cwd=ROOT, env=env,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(100):
                try:
                    urllib.request.urlopen(url, timeout=1).close()
                    break
                except OSError:
                    if server.poll() is not None:
                        raise RuntimeError('Isolated server exited')
                    time.sleep(.1)
            else:
                raise RuntimeError('Isolated server failed to start')
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(executable_path=str(CHROME), headless=True)
                try:
                    context = browser.new_context(viewport={'width':1920, 'height':1080}, device_scale_factor=1)
                    context.route('**/*', lambda route: route.continue_() if route.request.url.startswith(url + '/') else route.abort())
                    context.route('**/onboarding-status', lambda route: route.fulfill(json={'first_capture':False, 'first_event':False}))
                    context.route('**/steam-peers', lambda route: route.fulfill(json={'enabled':False, 'status':'disabled', 'peers':[]}))
                    context.route('**/online-leaderboard/settings', lambda route: route.fulfill(json={'enabled':False, 'configured':False, 'state':'idle'}))
                    page = context.new_page()
                    errors = []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    for language in args.languages:
                        folder = args.output / language
                        folder.mkdir(parents=True, exist_ok=True)
                        page.goto(url, wait_until='load')
                        page.wait_for_selector('.sprit', state='detached', timeout=30000)
                        page.locator('#menu_button_settings').click()
                        page.locator('.btn_menu_settings[menu="0"]').click()
                        page.wait_for_function("() => !document.querySelector('#interface_language').disabled")
                        page.locator('#interface_language').select_option(language)
                        page.wait_for_function('(code) => window.uiCurrentLanguage() === code && !document.querySelector("#interface_language").disabled', arg=language)
                        # Reload the isolated profile so every guide screenshot
                        # starts on the home page and the selector reflects it.
                        page.goto(url, wait_until='load')
                        page.wait_for_selector('.sprit', state='detached', timeout=30000)
                        page.wait_for_selector('.onboarding-card:not([hidden])', state='visible', timeout=10000)
                        page.wait_for_function('(code) => window.uiCurrentLanguage() === code', arg=language)
                        if page.locator('.version').text_content().strip() != args.version:
                            raise AssertionError(f'Incorrect displayed version: {language}')

                        # Real translated tutorial, with the normal empty-profile state.
                        page.locator('.onboarding-card').click()
                        page.locator('.onboarding-dialog').wait_for(state='visible')
                        page.screenshot(path=str(folder / '01-guide.png'), animations='disabled')
                        page.locator('.onboarding-close').click()

                        page.locator('#menu_button_settings').click()
                        page.locator('.btn_menu_settings[menu="8"]').click()
                        page.wait_for_function("() => !document.querySelector('#overlay_custom_background_opacity').disabled")
                        page.locator('.overlay-custom-group').first.evaluate('(el) => { el.open = true; }')
                        page.screenshot(path=str(folder / '02-overlay-settings.png'), animations='disabled')

                        page.locator('.btn_menu_settings[menu="0"]').click()
                        page.wait_for_function('(code) => document.querySelector("#interface_language").value === code', arg=language)
                        page.wait_for_function("() => !document.querySelector('#game_language').disabled")
                        if page.locator('#game_language').input_value() != 'engus':
                            raise AssertionError('The isolated game language must be the English fixture')
                        page.screenshot(path=str(folder / '03-language-settings.png'), animations='disabled')

                        page.locator('#menu_button_info').click()
                        page.wait_for_timeout(300)
                        page.screenshot(path=str(folder / '04-statistics.png'), animations='disabled')
                        print(f'{language}: 4 screenshots', flush=True)
                    if errors:
                        raise AssertionError('Browser errors: ' + '; '.join(errors))
                    context.close()
                finally:
                    browser.close()
        finally:
            subprocess.run(['taskkill', '/PID', str(server.pid), '/T', '/F'], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, check=False)
            server.wait(timeout=10)
    if source_hashes != {name: digest(ROOT / name) for name in SOURCES}:
        raise RuntimeError('UI sources changed while screenshots were being generated')
    screenshot_hashes = []
    for language in args.languages:
        for filename in ('01-guide.png', '02-overlay-settings.png', '03-language-settings.png', '04-statistics.png'):
            path = args.output / language / filename
            with Image.open(path) as screenshot:
                if screenshot.format != 'PNG' or screenshot.size != (1920, 1080):
                    raise AssertionError(f'Invalid screenshot: {language}/{filename}')
                screenshot.verify()
            screenshot_hashes.append((language + '/' + filename, digest(path)))
    (args.output / 'MANIFEST.md').write_text(
        '# Localized Store screenshot drafts\n\n'
        'Version: `' + args.version + '`. Generated from the development app with a private temporary profile at 1920 × 1080. '
        'There are no real accounts, player names, captures, or match results. '
        'The game and Steam were not accessed; external network requests were blocked. '
        'The guide, overlay settings, language settings and empty statistics are real UI views. '
        'These are draft images for visual and Store compliance review; they are not screenshots '
        'of a built or installed MSIX and are not submitted to the Store. '
        'Game-language detection is mocked to English; all interface languages '
        'are selected through the normal local settings UI.\n\n'
        'Each directory contains `01-guide.png`, `02-overlay-settings.png`, '
        '`03-language-settings.png`, and `04-statistics.png`. Review each image '
        'and map these interface locales to the Store listings actually enabled '
        'in Partner Center before submission.\n\n'
        '| Directory | Interface locale |\n| --- | --- |\n' +
        ''.join('| ' + language + ' | ' + ('fr' if language == 'fra' else PACKS[language]['html_lang']) + ' |\n'
                for language in args.languages) +
        '\n## Source file SHA-256\n\n' + ''.join('- `' + name + '`: `' + value + '`\n' for name, value in source_hashes.items()) +
        '\n## Screenshot SHA-256\n\n' + ''.join('- `' + name + '`: `' + value + '`\n' for name, value in screenshot_hashes),
        encoding='utf-8')


if __name__ == '__main__':
    main()
