import unittest
from werkzeug.datastructures import LanguageAccept
from werkzeug.http import parse_accept_header
from application.browser_language import browser_language

class BrowserLanguageTests(unittest.TestCase):
    def choose(self, header):
        return browser_language(parse_accept_header(header, LanguageAccept))

    def test_preferences_and_fallback(self):
        self.assertEqual(self.choose('fr-CA,fr;q=0.9,en;q=0.8'), 'fra')
        self.assertEqual(self.choose('nl-NL,fr-FR;q=0.9,en;q=0.8'), 'fra')
        self.assertEqual(self.choose('nl-NL,nl;q=0.9'), 'eng')
        self.assertEqual(self.choose('fr;q=0,en;q=0.5'), 'eng')
        self.assertEqual(self.choose(''), 'eng')

    def test_regional_variants(self):
        for tag, expected in [('es-ES','spaes'),('es-MX','spaar'),('es-419','spaar'),('es','spaes'),
                              ('zh-Hant','zht'),('zh-HK','zht'),('zh-CN','chi'),
                              ('zh-Hans-SG','chi'),('ja-JP','jap'),('pt-PT','por')]:
            with self.subTest(tag=tag):
                self.assertEqual(self.choose(tag), expected)

if __name__ == '__main__':
    unittest.main()
