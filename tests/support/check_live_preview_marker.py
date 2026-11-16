"""Test that each live marker follows only its corresponding synthetic frame."""
import base64
from io import BytesIO
from pathlib import Path
from PIL import Image
from playwright.sync_api import sync_playwright
ROOT = Path(__file__).resolve().parents[2]
source = (ROOT / 'static/app.js').read_text(encoding='utf-8')
start = source.index('let previewImageRequest = 0;')
end = source.index('\nfunction startPreviewPolling()', start)
script = source[start:end]
def image(color):
    output = BytesIO()
    Image.new('RGB', (160, 90), color).save(output, 'JPEG')
    return base64.b64encode(output.getvalue()).decode()
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe')
    page = browser.new_page()
    page.set_content('<style>.live-preview{position:relative;width:320px;height:180px}.live-preview img{width:100%;height:100%;object-fit:contain}.live-preview-notification{position:absolute;border:1px solid gold}.live-preview-notification[hidden]{display:none}</style><div class="live-preview"><img></div>')
    page.add_script_tag(content=script)
    first, second = image('red'), image('blue')
    page.evaluate('v => updateLivePreview(v, true, 1, {frame:1, box:[.1,.2,.8,.65]})', first)
    page.wait_for_function("document.querySelector('.live-preview-notification').hidden === false")
    page.evaluate('v => updateLivePreview(v, true, 2, null)', second)
    page.wait_for_function("document.querySelector('.live-preview img').dataset.previewRevision === '2'")
    assert page.locator('.live-preview-notification').is_hidden()
    assert page.locator('.live-preview img').get_attribute('src').endswith(second)
    page.evaluate('v => updateLivePreview(v, true, 3, {frame:3, box:[.2,.3,.7,.6]})', first)
    page.wait_for_function("document.querySelector('.live-preview-notification').hidden === false")
    page.evaluate('() => updateLivePreview("", false, 4, null)')
    assert page.locator('.live-preview-notification').is_hidden()
    browser.close()
print('Le cadre suit son image et disparaît immédiatement sur une image sans détection.')
