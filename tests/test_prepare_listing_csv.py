"""Protect a real Partner Center export using temporary synthetic CSV files."""
import csv
import io
import tempfile
import unittest
from pathlib import Path

from store import prepare_listing_csv as listing


class PrepareListingCSVTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='tracker-listing-test-')
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.source = self.root / 'export.csv'
        self.output = self.root / 'candidate.csv'
        self.descriptions = self.root / 'descriptions.md'
        self.notes = self.root / 'notes.md'
        self.write_drafts(self.descriptions, 'Description é')
        self.write_drafts(self.notes, 'Notes é')
        self.header = ['Field', 'ID', 'Type', 'default', 'en-us', 'fr-FR', 'es-MX']
        self.rows = [
            self.header,
            ['Description', '11', 'Text', 'default description', 'old English', 'ancien français', 'anterior'],
            ['ReleaseNotes', '12', 'Text', 'default notes', 'old notes', 'anciennes notes', 'notas'],
            ['Title', '13', 'Text', 'Default title', 'Existing title', 'Titre existant', 'Título'],
            ['Feature1', '14', 'Text', 'Default, "quoted"', 'first\nsecond line', '=formula', ''],
            ['DesktopScreenshot1', '15', 'Relative path', 'default.png', 'https://example.test/en.png', '', 'img.png'],
            ['Trailer1', '16', 'URL', 'trailer', '', 'https://example.test/trailer', ''],
        ]
        self.write_source(self.rows)

    def write_drafts(self, path, prefix, *, missing=None, oversized=None, duplicate=None):
        text = '# Not part of the listing\n\n'
        for locale in listing.LOCALES:
            if locale == missing:
                continue
            value = (oversized if locale == 'en-US' and oversized is not None else prefix + ' ' + locale)
            text += '## Language (' + locale + ')\n\n' + value + '\n\n'
        if duplicate:
            text += '## Duplicate (' + duplicate + ')\n\nDuplicate\n'
        path.write_text(text, encoding='utf-8')

    def write_source(self, rows, *, bom=False):
        buffer = io.StringIO(newline='')
        csv.writer(buffer, lineterminator='\r\n').writerows(rows)
        data = buffer.getvalue().encode('utf-8')
        self.source.write_bytes((b'\xef\xbb\xbf' if bom else b'') + data)

    def prepare(self):
        return listing.prepare_listing(self.source, self.output,
            descriptions=self.descriptions, notes=self.notes)

    def read_output(self):
        with self.output.open(encoding='utf-8-sig', newline='') as stream:
            return list(csv.reader(stream, strict=True))

    def test_preserves_input_other_rows_defaults_and_existing_locales(self):
        before = self.source.read_bytes()
        result = self.prepare()
        output = self.read_output()
        self.assertEqual(self.source.read_bytes(), before)
        self.assertEqual(output[0][:len(self.header)], self.header)
        self.assertEqual(result['languages'], 30)
        self.assertEqual(len(result['added_columns']), 30)
        self.assertEqual(len(output), len(self.rows))
        for index in range(1, len(self.rows)):
            # Field, ID, Type and default never change, including target rows.
            self.assertEqual(output[index][:4], self.rows[index][:4])
        for index in range(3, len(self.rows)):
            self.assertEqual(output[index][:len(self.header)], self.rows[index])
            self.assertEqual(output[index][len(self.header):], [''] * 30)
        # An unrelated es-MX listing is preserved even in the two target rows.
        self.assertEqual(output[1][6], 'anterior')
        self.assertEqual(output[2][6], 'notas')
        self.assertEqual(output[1][4:6], ['Description é en-US', 'Description é fr-FR'])
        self.assertEqual(output[2][4:6], ['Notes é en-US', 'Notes é fr-FR'])
        self.assertEqual(output[1][output[0].index('en')], 'Description é en-US')
        self.assertEqual(output[2][output[0].index('fr')], 'Notes é fr-FR')
        self.assertEqual(output[1][output[0].index('es-419')], 'Description é es-419')
        self.assertEqual(output[2][output[0].index('es-419')], 'Notes é es-419')
        self.assertNotIn('de-DE', output[0])
        self.assertNotIn('zh-CN', output[0])
        self.assertNotIn('zh-TW', output[0])
        # Indonesian's "id" is distinct from the fixed metadata column "ID".
        self.assertEqual(output[1][1], '11')
        self.assertEqual(output[2][1], '12')
        self.assertEqual(output[1][output[0].index('id')], 'Description é id-ID')
        self.assertEqual(output[2][output[0].index('id')], 'Notes é id-ID')

    def test_manifest_locales_and_existing_explicit_aliases_are_updated(self):
        header = ['Field', 'ID', 'Type', 'default', 'de', 'fr', 'en', 'id', 'zh-Hans', 'zh-Hant',
                  'fr-FR', 'en-US', 'zh-CN', 'zh-TW', 'es-MX']
        rows = [header,
                ['Description', '11', 'Text', 'default'] + ['old'] * (len(header) - 4),
                ['ReleaseNotes', '12', 'Text', 'default'] + ['old'] * (len(header) - 4),
                ['Title', '13', 'Text', 'default'] + ['keep'] * (len(header) - 4)]
        self.write_source(rows)
        result = self.prepare()
        output = self.read_output()
        expected = {'de': 'de-DE', 'fr': 'fr-FR', 'en': 'en-US', 'id': 'id-ID',
                    'zh-Hans': 'zh-CN', 'zh-Hant': 'zh-TW',
                    'fr-FR': 'fr-FR', 'en-US': 'en-US', 'zh-CN': 'zh-CN', 'zh-TW': 'zh-TW'}
        for code, draft in expected.items():
            with self.subTest(code=code):
                self.assertEqual(output[1][output[0].index(code)], 'Description é ' + draft)
                self.assertEqual(output[2][output[0].index(code)], 'Notes é ' + draft)
        self.assertEqual(output[1][output[0].index('es-MX')], 'old')
        self.assertEqual(output[2][output[0].index('es-MX')], 'old')
        self.assertEqual(output[3][:len(header)], rows[3])
        self.assertNotIn('de-DE', output[0])
        self.assertNotIn('fr-FR', result['added_columns'])
        self.assertEqual(output[1][1], '11')
        self.assertEqual(output[2][1], '12')
        self.assertEqual(len(result['added_columns']), 24)

    def test_french_partner_center_export_header_and_text_type(self):
        # Synthetic content, with the header and locale layout observed on the
        # French Partner Center export. ID is metadata; id is Indonesian.
        header = ['Field', 'ID', 'Type (Type)', 'default', 'en-us', 'fr-fr',
                  'ar', 'de', 'en', 'es-419', 'es-es', 'fr', 'it', 'ja',
                  'ko', 'pl', 'pt-br', 'ru', 'th', 'zh-hans', 'zh-hant']
        rows = [header,
                ['Description', '2', 'Texte', 'default'] + ['old'] * (len(header) - 4),
                ['ReleaseNotes', '3', 'Texte', 'default'] + ['old'] * (len(header) - 4),
                ['Title', '1', 'Texte', 'default'] + ['keep'] * (len(header) - 4)]
        self.write_source(rows)
        result = self.prepare()
        output = self.read_output()
        self.assertEqual(output[0][:len(header)], header)
        self.assertEqual(output[1][:4], rows[1][:4])
        self.assertEqual(output[2][:4], rows[2][:4])
        self.assertEqual(output[3][:len(header)], rows[3])
        for code, draft in [('de', 'de-DE'), ('fr', 'fr-FR'), ('en', 'en-US'),
                            ('fr-fr', 'fr-FR'), ('en-us', 'en-US'),
                            ('zh-hans', 'zh-CN'), ('zh-hant', 'zh-TW'), ('id', 'id-ID')]:
            with self.subTest(code=code):
                self.assertEqual(output[1][output[0].index(code)], 'Description é ' + draft)
                self.assertEqual(output[2][output[0].index(code)], 'Notes é ' + draft)
        self.assertEqual(len(result['added_columns']), 15)
        self.assertNotIn('de-DE', output[0])
        self.assertNotIn('zh-CN', output[0])

    def test_utf8_and_optional_bom_are_preserved(self):
        self.write_source(self.rows, bom=True)
        before = self.source.read_bytes()
        self.prepare()
        self.assertTrue(self.output.read_bytes().startswith(b'\xef\xbb\xbf'))
        self.assertEqual(self.source.read_bytes(), before)
        self.assertIn('Titre existant', self.output.read_text(encoding='utf-8-sig'))
        self.assertIn('Description é fr-FR', self.output.read_text(encoding='utf-8-sig'))

    def test_refuses_to_replace_the_input_or_an_existing_output(self):
        before = self.source.read_bytes()
        with self.assertRaises(ValueError):
            listing.prepare_listing(self.source, self.source,
                descriptions=self.descriptions, notes=self.notes)
        self.assertEqual(self.source.read_bytes(), before)
        self.output.write_bytes(b'do not overwrite')
        with self.assertRaises(FileExistsError):
            self.prepare()
        self.assertEqual(self.output.read_bytes(), b'do not overwrite')
        self.assertEqual(self.source.read_bytes(), before)

    def test_missing_or_ambiguous_target_rows_fail_before_writing(self):
        cases = [
            [self.header, self.rows[1]],
            [self.header, self.rows[2]],
            self.rows + [list(self.rows[1])],
            [self.header, self.rows[1], ['ReleaseNotes', '11', 'Text', '', '', '', '']],
            [self.header, ['Description', '', 'Text', '', '', '', ''], self.rows[2]],
            [self.header, ['Description', '11', 'Image', '', '', '', ''], self.rows[2]],
        ]
        for rows in cases:
            with self.subTest(rows=rows):
                self.write_source(rows)
                before = self.source.read_bytes()
                with self.assertRaises(ValueError):
                    self.prepare()
                self.assertFalse(self.output.exists())
                self.assertEqual(self.source.read_bytes(), before)

    def test_duplicate_missing_or_irregular_columns_are_rejected(self):
        cases = [
            [['Field', 'ID', 'Type'], ['Description', '1', 'Text']],
            [['ID', 'Field', 'Type', 'default'], ['1', 'Description', 'Text', '']],
            [self.header + ['EN-US']] + [row + [''] for row in self.rows[1:]],
            [self.header + ['DEFAULT']] + [row + [''] for row in self.rows[1:]],
            [self.header + ['']] + [row + [''] for row in self.rows[1:]],
            [self.header, self.rows[1][:-1], self.rows[2]],
        ]
        for rows in cases:
            with self.subTest(header=rows[0]):
                self.write_source(rows)
                with self.assertRaises(ValueError):
                    self.prepare()
                self.assertFalse(self.output.exists())

    def test_invalid_utf8_and_unclosed_csv_quotes_are_rejected(self):
        for data in (b'\xff\xfe', b'Field,ID,Type,default\r\nDescription,1,Text,"unterminated'):
            with self.subTest(data=data):
                self.source.write_bytes(data)
                with self.assertRaises((ValueError, UnicodeError)):
                    self.prepare()
                self.assertEqual(self.source.read_bytes(), data)
                self.assertFalse(self.output.exists())

    def test_missing_duplicate_and_oversized_drafts_fail_before_output(self):
        cases = [
            (self.descriptions, {'missing': 'fr-FR'}),
            (self.descriptions, {'duplicate': 'fr-FR'}),
            (self.descriptions, {'oversized': 'x' * 10001}),
            (self.notes, {'oversized': 'x' * 1501}),
            # Count UTF-16 code units, including non-BMP characters.
            (self.notes, {'oversized': '😀' * 751}),
        ]
        for path, kwargs in cases:
            with self.subTest(path=path.name, kwargs=list(kwargs)):
                self.write_drafts(self.descriptions, 'Description é')
                self.write_drafts(self.notes, 'Notes é')
                self.write_drafts(path, 'Fixture', **kwargs)
                with self.assertRaises(ValueError):
                    self.prepare()
                self.assertFalse(self.output.exists())

    def test_prepares_current_review_drafts_without_changing_other_cells(self):
        listing.prepare_listing(self.source, self.output)
        output = self.read_output()
        self.assertIn('30', output[1][output[0].index('fr-FR')])
        self.assertIn('15', output[1][output[0].index('fr-FR')])
        self.assertEqual(output[3][:len(self.header)], self.rows[3])


if __name__ == '__main__':
    unittest.main()
