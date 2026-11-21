"""Build a compact offline PNG atlas from the bundled flag-icons SVGs.

Run with the development Playwright/Chrome installation; the tracker itself
needs only Pillow and the resulting image. The original MIT license remains
in static/flags/LICENSE.txt and is also embedded in the generated PNG.
"""
import base64
import json
import os
from io import BytesIO
from pathlib import Path

from PIL import Image, PngImagePlugin
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
FLAGS = ROOT / 'static' / 'flags'
OUTPUT = ROOT / 'static' / 'overlay-country-flags.png'
CELL_WIDTH, CELL_HEIGHT, COLUMNS = 48, 36, 16
CHROME = Path(os.environ.get('ProgramFiles', r'C:\Program Files')) / 'Google/Chrome/Application/chrome.exe'


def main():
    paths = sorted(path for path in FLAGS.glob('*.svg')
                   if len(path.stem) == 2 and path.stem.isascii() and path.stem.isalpha())
    codes = [path.stem.upper() for path in paths]
    atlas = Image.new('RGBA', (COLUMNS * CELL_WIDTH, ((len(paths) + COLUMNS - 1) // COLUMNS) * CELL_HEIGHT))
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=str(CHROME), headless=True)
        try:
            page = browser.new_page()
            page.route('**/*', lambda route: route.abort())
            for index, path in enumerate(paths):
                encoded = page.evaluate('''async ({svg, width, height}) => {
                    const image = new Image();
                    const url = URL.createObjectURL(new Blob([svg], {type: 'image/svg+xml'}));
                    try {
                        await new Promise((resolve, reject) => {
                            image.onload = resolve; image.onerror = reject; image.src = url;
                        });
                        const canvas = document.createElement('canvas');
                        canvas.width = width; canvas.height = height;
                        canvas.getContext('2d').drawImage(image, 0, 0, width, height);
                        return canvas.toDataURL('image/png').split(',')[1];
                    } finally { URL.revokeObjectURL(url); }
                }''', {'svg':path.read_text(encoding='utf-8'), 'width':CELL_WIDTH, 'height':CELL_HEIGHT})
                with Image.open(BytesIO(base64.b64decode(encoded))) as flag:
                    atlas.paste(flag.convert('RGBA'), ((index % COLUMNS) * CELL_WIDTH, (index // COLUMNS) * CELL_HEIGHT))
        finally:
            browser.close()
    info = PngImagePlugin.PngInfo()
    info.add_text('country_codes', json.dumps(codes, separators=(',', ':')))
    info.add_text('license', (FLAGS / 'LICENSE.txt').read_text(encoding='utf-8'))
    atlas.save(OUTPUT, pnginfo=info, optimize=True)
    print(f'{len(codes)} flags: {OUTPUT} ({OUTPUT.stat().st_size} bytes)')


if __name__ == '__main__':
    main()
