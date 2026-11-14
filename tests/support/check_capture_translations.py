"""Check capture captions across languages without using real tracker data."""
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

from check_online_profile_notice import CHROME

ROOT = Path(__file__).resolve().parents[2]


def check_captions(page, code):
    page.wait_for_timeout(150)
    errors = page.evaluate('''(code) => {
        const french = {victory:'Victoire', defeat:'Défaite', draw:'Égalité', capture_duel:'Duel',
                        invasion:'Invasions', defense:'Monde envahi', time:'Temps'};
        const words = code === 'fra' ? french : ELDEN_UI_PACKS[code].modern;
        return Array.from(document.querySelectorAll('.para_capture[data-capture-caption]')).flatMap(card => {
            const parts = [];
            parts.push(words[card.dataset.captureMode === 'Arena' ? 'capture_duel' : card.dataset.captureMode === 'Defense' ? 'defense' : 'invasion']);
            if (card.dataset.captureResult) parts.push(words[card.dataset.captureResult]);
            if (card.dataset.captureOpponent) parts.push(card.dataset.captureOpponent);
            const actual = card.querySelector(':scope > span > b').textContent;
            const time = card.querySelector('.capture-duration-label');
            return actual !== parts.join(' · ') || !time || time.textContent !== words.time
                ? [{actual, expected:parts.join(' · '), time:time && time.textContent, expectedTime:words.time}]
                : [];
        });
    }''', code)
    assert not errors, (code, errors)


def check(browser, url, viewport):
    context = browser.new_context(viewport=viewport)
    context.route('**/*', lambda route: route.continue_() if route.request.url.startswith(url + '/') else route.abort())
    # A running tracker can serve an old template without the viewer arrows.
    def cached_template(route):
        response = route.fetch()
        text = re.sub(r'<button[^>]+class="capture-viewer-nav capture-viewer-(?:prev|next)"[^>]*>.*?</button>', '', response.text())
        route.fulfill(response=response, body=text)
    context.route(url + '/', cached_template)
    page = context.new_page()
    errors, capture_requests = [], []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('request', lambda request: capture_requests.append(request.url)
            if any(path in request.url for path in ['/allCaptures?', '/nextCaptures', '/capture?']) else None)
    try:
        page.goto(url, wait_until='load')
        page.wait_for_selector('.sprit', state='detached', timeout=15000)
        page.wait_for_function("() => document.querySelectorAll('.capture-scroll .para_capture').length === 50")
        page.evaluate("document.getElementById('menu_button_captures').click()")
        page.wait_for_function("() => getComputedStyle(document.querySelector('.capture-toolbar')).display !== 'none'")
        page.evaluate("launchLanguages('fra')")
        check_captions(page, 'fra')
        before = page.locator('.capture-scroll .para_capture').evaluate_all('es => es.map(e => [e.querySelector(".posted").textContent, e.querySelector(".datePosted").textContent, e.querySelector("img").src])')
        requests = len(capture_requests)
        page.evaluate("launchLanguages('eng')")
        check_captions(page, 'eng')
        assert page.locator('.capture-scroll .para_capture').evaluate_all('es => es.map(e => [e.querySelector(".posted").textContent, e.querySelector(".datePosted").textContent, e.querySelector("img").src])') == before
        assert len(capture_requests) == requests, 'Changing language reloaded capture data'

        # Scroll-paginated cards are localized in place too.
        page.locator('.capture-scroll').evaluate('(el) => { el.scrollTop = el.scrollHeight; el.dispatchEvent(new Event("scroll")); }')
        page.wait_for_function("() => document.querySelectorAll('.capture-scroll .para_capture').length === 72")
        for code in ['fra', 'eng', 'deu', 'ita', 'spaes', 'spaar', 'por', 'pol',
                     'rus', 'jap', 'kor', 'chi', 'zht', 'tha', 'ara']:
            page.evaluate('(code) => launchLanguages(code)', code)
            check_captions(page, code)
        duration = page.locator('.capture-scroll .capture-duration-label').first
        assert duration.evaluate('(e) => { const s=getComputedStyle(e); return s.position === "static" && s.fontStyle === "normal"; }')
        assert '15 s' in duration.locator('..').inner_text()

        # The viewer copy keeps the same metadata, including its translated
        # duration and accessible labels, even with an old cached template.
        page.locator('.capture-scroll .para_capture').last.click()
        assert page.locator('#capture_viewer_overlay').is_visible()
        page.evaluate("launchLanguages('eng')")
        check_captions(page, 'eng')
        for selector, key in [('.capture-viewer-prev', 'previous_capture'), ('.capture-viewer-next', 'next_capture')]:
            assert page.locator(selector).get_attribute('aria-label') == page.evaluate(
                '(key) => ELDEN_UI_PACKS.eng.modern[key]', key)
        page.locator('.capture-viewer-close').click()

        # Result/mode filtering remains intact and does not change selection
        # or request a reload when the language changes.
        page.locator('#capture_result').select_option('victory_text')
        page.wait_for_function("() => document.querySelectorAll('.capture-scroll .para_capture').length === 36")
        page.locator('#capture_mode').select_option('Invasion')
        page.wait_for_function("() => document.querySelectorAll('.capture-scroll .para_capture').length === 12")
        requests = len(capture_requests)
        page.evaluate("launchLanguages('deu')")
        check_captions(page, 'deu')
        assert page.locator('#capture_result').input_value() == 'victory_text'
        assert page.locator('#capture_mode').input_value() == 'Invasion'
        assert len(capture_requests) == requests

        # Newly captured results use the same metadata, including their
        # original localized duration label, without touching real screenshots.
        page.locator('#capture_mode').select_option('all')
        page.locator('#capture_result').select_option('all')
        page.wait_for_function("() => document.querySelectorAll('.capture-scroll .para_capture').length === 72")
        page.evaluate("launchLanguages('fra')")
        page.route('**/capture', lambda route: route.fulfill(json={'request':'success', 'datas':'aW1hZ2U=', 'mode':'Defense', 'opponent':'Example', 'date':'01/01/2025'}))
        page.evaluate("getCapture('Victory', '<br> Temps: 17 s')")
        page.wait_for_function("() => document.querySelectorAll('.capture-scroll .para_capture').length === 73")
        live = page.locator('.capture-scroll .para_capture').first
        assert 'Example' in live.inner_text() and '17 s' in live.inner_text()
        requests = len(capture_requests)
        page.evaluate("launchLanguages('eng')")
        check_captions(page, 'eng')
        assert 'Example' in live.inner_text() and '17 s' in live.inner_text()
        assert len(capture_requests) == requests
        assert not errors, errors
    finally:
        context.close()


def main():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix='tracker-capture-translations-', ignore_cleanup_errors=True) as directory:
        env = os.environ.copy()
        env.update(APPDATA=directory, TRACKER_TEST_PORT=str(port))
        seed = '''from flask import Flask
app=Flask(__name__)
from application.init import create_tables, add_capture
create_tables()
cases=[('Arena',1,0,0),('Arena',0,1,0),('Arena',0,0,1),('Invasion',1,0,0),('Invasion',0,1,0),('Defense',1,0,0)]
for n in range(72):
 mode,v,d,e=cases[n%len(cases)]
 add_capture('Player '+str(n),v,d,e,15,'01/01/2025',mode,'aW1hZ2U=')
'''
        subprocess.run([sys.executable, '-c', seed], cwd=ROOT, env=env, check=True, capture_output=True)
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
                    check(browser, url, {'width':1440, 'height':900})
                    check(browser, url, {'width':390, 'height':844})
                finally:
                    browser.close()
            print('Capture captions, viewer, filtering and pagination follow language changes.')
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
