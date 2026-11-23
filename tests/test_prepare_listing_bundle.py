"""Exercise a Store import bundle entirely with temporary synthetic data."""
import csv
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from PIL import Image
from store import prepare_listing_csv as listing


class PrepareListingBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='tracker-listing-bundle-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'export.csv'
        self.destination = self.root / 'StoreDraft'
        self.screenshots = self.root / 'screenshots'
        self.descriptions = self.root / 'descriptions.md'
        self.notes = self.root / 'notes.md'
        for path, label in ((self.descriptions, 'Description'), (self.notes, 'Release')):
            path.write_text(''.join(f'## Example ({code})\n\n{label} {code}\n\n'
                                    for code in listing.LOCALES), encoding='utf-8')
        header = ['Field', 'ID', 'Type (Type)', 'default', 'en-us', 'fr-fr',
                  'ar', 'de', 'en', 'es-419', 'es-es', 'fr', 'it', 'ja',
                  'ko', 'pl', 'pt-br', 'ru', 'th', 'zh-hans', 'zh-hant']
        self.rows = [header,
                     ['Description', '2', 'Texte', ''] + ['old description'] * 17,
                     ['ReleaseNotes', '3', 'Texte', ''] + ['old notes'] * 17,
                     ['Title', '4', 'Texte', ''] + ['Existing title'] * 17]
        image_type = "Chemin d'accès relatif (ou URL à consigner dans l'Espace partenaires)"
        for index in range(1, 5):
            self.rows.append([f'DesktopScreenshot{index}', str(99 + index), image_type, ''] +
                             [f'https://example.test/{code}/{index}.png' for code in header[4:]])
        self.rows.append(['Trailer1', '250', 'URL', ''] + [f'trailer-{code}' for code in header[4:]])
        self.write_source(self.rows)
        buffer = io.BytesIO()
        Image.new('RGB', (1366, 768), '#123456').save(buffer, format='PNG')
        self.png = buffer.getvalue()
        for code in listing.CANONICAL_TO_IMAGES.values():
            directory = self.screenshots / code
            directory.mkdir(parents=True)
            for filename in listing.SCREENSHOTS:
                (directory / filename).write_bytes(self.png)

    def write_source(self, rows):
        with self.source.open('w', encoding='utf-8-sig', newline='') as stream:
            csv.writer(stream).writerows(rows)

    def bundle(self, **kwargs):
        args = {'title': 'Elden PVP Tracker', 'screenshots': self.screenshots,
                'descriptions': self.descriptions, 'notes': self.notes}
        args.update(kwargs)
        return listing.prepare_listing_bundle(self.source, self.destination, **args)

    def result_rows(self):
        with (self.destination / 'listing.csv').open(encoding='utf-8-sig', newline='') as stream:
            return list(csv.reader(stream))

    def test_17_existing_15_new_preserves_existing_titles_images_and_metadata(self):
        before = self.source.read_bytes()
        result = self.bundle()
        output = self.result_rows()
        self.assertEqual(self.source.read_bytes(), before)
        self.assertTrue((self.destination / 'listing.csv').read_bytes().startswith(b'\xef\xbb\xbf'))
        self.assertEqual((result['languages'], result['titles_filled'], result['screenshots_filled'], result['images_copied']),
                         (30, 15, 60, 60))
        self.assertEqual(output[0][:len(self.rows[0])], self.rows[0])
        for index in range(1, len(output)):
            self.assertEqual(output[index][:4], self.rows[index][:4])
        for index in range(3, len(output)):
            self.assertEqual(output[index][:len(self.rows[0])], self.rows[index])
        self.assertEqual(output[1][output[0].index('de')], 'Description de-DE')
        self.assertEqual(output[2][output[0].index('fr-fr')], 'Release fr-FR')
        self.assertEqual(output[1][1], '2')  # distinct from Indonesian "id"
        self.assertEqual(output[3][output[0].index('id')], 'Elden PVP Tracker')
        for locale in ('id', 'nl', 'pt-PT'):
            index = output[0].index(locale)
            code = listing.CANONICAL_TO_IMAGES[locale]
            for number, filename in enumerate(listing.SCREENSHOTS):
                self.assertEqual(output[4 + number][index], f'StoreDraft/images/{code}/{filename}')
                self.assertEqual((self.destination / 'images' / code / filename).read_bytes(), self.png)
        self.assertFalse((self.destination / 'images' / 'deu').exists())
        self.assertEqual(len(list(self.destination.rglob('*.png'))), 60)

    def test_only_blank_existing_alias_cells_are_filled(self):
        self.rows[3][4] = ''  # en-US title
        self.rows[4][5] = ''  # fr-FR screenshot 1
        self.write_source(self.rows)
        result = self.bundle()
        output = self.result_rows()
        self.assertEqual(result['titles_filled'], 16)
        self.assertEqual(result['screenshots_filled'], 61)
        self.assertEqual(output[3][4], 'Elden PVP Tracker')
        self.assertEqual(output[4][5], 'StoreDraft/images/fra/01-guide.png')
        self.assertEqual(output[5][5], self.rows[5][5])
        self.assertEqual((self.destination / 'images/fra/01-guide.png').read_bytes(), self.png)

    def test_missing_duplicate_wrong_type_or_duplicate_id_rejected_before_output(self):
        cases = [
            self.rows[:3] + self.rows[4:],
            self.rows + [list(self.rows[4])],
            [self.rows[0], *self.rows[1:4], [*self.rows[4][:2], 'Texte', *self.rows[4][3:]], *self.rows[5:]],
            [self.rows[0], *self.rows[1:4], [self.rows[4][0], '4', *self.rows[4][2:]], *self.rows[5:]],
        ]
        for rows in cases:
            with self.subTest(case=cases.index(rows)):
                self.write_source(rows)
                before = self.source.read_bytes()
                with self.assertRaises(ValueError):
                    self.bundle()
                self.assertFalse(self.destination.exists())
                self.assertEqual(self.source.read_bytes(), before)

    def test_missing_invalid_or_undersized_images_are_rejected_before_output(self):
        image = self.screenshots / 'ind' / listing.SCREENSHOTS[0]
        for kind in ('missing', 'invalid', 'small'):
            with self.subTest(kind=kind):
                if kind == 'missing':
                    image.unlink()
                elif kind == 'invalid':
                    image.write_bytes(b'not a PNG')
                else:
                    Image.new('RGB', (50, 50)).save(image, format='PNG')
                with self.assertRaises((ValueError, FileNotFoundError)):
                    self.bundle()
                self.assertFalse(self.destination.exists())
                image.write_bytes(self.png)

    def test_existing_bundle_and_invalid_inputs_are_never_overwritten(self):
        for kwargs in ({'title': None}, {'title': ''}, {'title': 'a\nb'}, {'screenshots': None}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.bundle(**kwargs)
            self.assertFalse(self.destination.exists())
        self.destination.mkdir()
        sentinel = self.destination / 'keep.txt'
        sentinel.write_bytes(b'unchanged')
        with self.assertRaises(FileExistsError):
            self.bundle()
        self.assertEqual(sentinel.read_bytes(), b'unchanged')

    def test_cli_requires_explicit_bundle_options_and_creates_only_the_new_folder(self):
        script = Path(__file__).resolve().parents[1] / 'store/prepare_listing_csv.py'
        before = self.source.read_bytes()
        missing = subprocess.run([sys.executable, str(script), str(self.source), str(self.destination), '--bundle'],
                                 capture_output=True, text=True, timeout=30)
        self.assertNotEqual(missing.returncode, 0)
        self.assertFalse(self.destination.exists())
        result = subprocess.run([sys.executable, str(script), str(self.source), str(self.destination), '--bundle',
                                 '--title', 'Elden PVP Tracker', '--screenshots', str(self.screenshots)],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.source.read_bytes(), before)
        self.assertIn('15 titles and 60 screenshot fields', result.stdout)
        self.assertEqual(len(list(self.destination.rglob('*.png'))), 60)


if __name__ == '__main__':
    unittest.main()
