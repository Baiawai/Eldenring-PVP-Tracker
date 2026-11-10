import threading
import unittest
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask, request

from application import store_update
def packs():
    path = Path(__file__).resolve().parents[1] / 'application' / 'locales' / 'ui_packs.json'
    return json.loads(path.read_text(encoding='utf-8'))


def package(family=store_update.STORE_FAMILY, signature=3):
    return SimpleNamespace(signature_kind=signature, id=SimpleNamespace(family_name=family))


class StoreUpdateTests(unittest.TestCase):
    def tearDown(self):
        store_update._REQUIRED = False

    def test_only_our_store_signed_package_is_eligible(self):
        self.assertTrue(store_update._is_store_package(package()))
        self.assertFalse(store_update._is_store_package(package(signature=2)))
        self.assertFalse(store_update._is_store_package(package(family='Other_family')))
        with patch.object(store_update, 'FROZEN', False), patch.object(store_update, '_query_store_update') as query:
            self.assertFalse(store_update.check_at_start())
            query.assert_not_called()

    def test_only_main_package_updates_block(self):
        unrelated = SimpleNamespace(package=package(family='Other_family'))
        main = SimpleNamespace(package=package())
        self.assertFalse(store_update._has_main_package_update(package(), [unrelated]))
        self.assertTrue(store_update._has_main_package_update(package(), [unrelated, main]))
        self.assertFalse(store_update._has_main_package_update(package(signature=2), [main]))

    def test_result_and_errors(self):
        with patch.object(store_update, 'FROZEN', True):
            with patch.object(store_update, '_query_store_update', return_value=True):
                self.assertTrue(store_update.check_at_start())
            with patch.object(store_update, '_query_store_update', side_effect=OSError('offline')):
                self.assertFalse(store_update.check_at_start())
            with patch.object(store_update, '_query_store_update', return_value=False):
                self.assertFalse(store_update.check_at_start())

    def test_late_result_cannot_interrupt_the_running_application(self):
        release, completed = threading.Event(), threading.Event()
        def delayed():
            release.wait(2)
            completed.set()
            return True
        with patch.object(store_update, 'FROZEN', True), patch.object(store_update, '_query_store_update', side_effect=delayed):
            self.assertFalse(store_update.check_at_start(timeout=0.01))
            release.set()
            self.assertTrue(completed.wait(2))
            self.assertFalse(store_update.is_required())

    def test_blocked_screen_and_routes(self):
        app = Flask(__name__, template_folder=str(Path(__file__).resolve().parents[1] / 'templates'))
        app.before_request(lambda: store_update.gate_response(request, lambda: 'fra', packs))
        calls = []
        @app.route('/')
        def index():
            calls.append('index')
            return 'tracker'
        @app.route('/start', methods=['POST'])
        def start():
            calls.append('start')
            return 'started'
        @app.route('/exit', methods=['POST'])
        def close():
            return 'closed'
        with app.test_client() as client:
            store_update._REQUIRED = True
            response = client.get('/')
            self.assertEqual(response.status_code, 200)
            self.assertIn('Mise à jour requise', response.get_data(as_text=True))
            self.assertIn(store_update.STORE_URL, response.get_data(as_text=True))
            self.assertEqual(client.post('/start').status_code, 423)
            self.assertEqual(client.post('/exit').status_code, 200)
            self.assertEqual(calls, [])
            store_update._REQUIRED = False
            self.assertEqual(client.post('/start').status_code, 200)

    def test_all_translations_exist(self):
        keys = ('store_update_title', 'store_update_message', 'store_update_instruction', 'store_update_action')
        for language, pack in packs().items():
            with self.subTest(language=language):
                for key in keys:
                    self.assertTrue(pack['modern'].get(key))


if __name__ == '__main__':
    unittest.main()
