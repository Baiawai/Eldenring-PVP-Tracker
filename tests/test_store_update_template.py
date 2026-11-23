import json
import unittest
from pathlib import Path

from flask import Flask, render_template


class StoreUpdateTemplateTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1]
        self.app = Flask(__name__, template_folder=str(root / 'templates'),
                         static_folder=str(root / 'static'))

    def render(self, **overrides):
        data = dict(language='fr', title='Mise à jour requise', message='Disponible',
                    action='Ouvrir Microsoft Store', instruction='Relancer',
                    store_url='ms-windows-store://pdp/?productid=9P7J2LSRPPTF',
                    current_version_label='Version actuelle', new_version_label='Nouvelle version',
                    indicative_version_label='Dernière version publiée (indicative)', available_version_source='store',
                    unavailable_label='Indisponible', current_version='1.0.10.0', available_version='1.0.11.0')
        data.update(overrides)
        with self.app.test_request_context('/'):
            return render_template('store-update.html', **data)

    def test_both_known_versions_and_store_link_are_rendered(self):
        html = self.render()
        for value in ('Version actuelle', 'Nouvelle version', '1.0.10.0', '1.0.11.0',
                      'ms-windows-store://pdp/?productid=9P7J2LSRPPTF'):
            self.assertIn(value, html)

    def test_missing_version_is_not_invented(self):
        html = self.render(available_version=None, unavailable_label='Unavailable')
        self.assertIn('1.0.10.0', html)
        self.assertIn('>Unavailable</bdi>', html)
        self.assertNotIn('1.0.11.0', html)

    def test_site_version_is_explicitly_marked_indicative(self):
        html = self.render(available_version_source='site')
        self.assertIn('Dernière version publiée (indicative)</dt>', html)
        self.assertIn('data-source="site">1.0.11.0', html)

    def test_rtl_and_version_values_are_safe(self):
        html = self.render(language='ar', current_version='<script>alert(1)</script>')
        self.assertIn('dir="rtl"', html)
        self.assertNotIn('<script>alert(1)</script>', html)
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;', html)

    def test_version_labels_are_available_in_all_language_packs(self):
        path = Path(__file__).resolve().parents[1] / 'application/locales/ui_packs.json'
        packs = json.loads(path.read_text(encoding='utf-8'))
        for language, pack in packs.items():
            for key in ('store_update_current_version', 'store_update_new_version',
                        'store_update_latest_published_indicative', 'store_update_version_unavailable'):
                with self.subTest(language=language, key=key):
                    self.assertTrue(pack['modern'].get(key, '').strip())


if __name__ == '__main__':
    unittest.main()
