import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from flask import Flask


class StoreLeaderboardTests(unittest.TestCase):
    def test_store_blocks_network_and_sync_route_before_accessing_data(self):
        app = Flask('test_store_leaderboard')
        main = types.ModuleType('__main__')
        main.app = app
        init = types.ModuleType('application.init')
        init.load_user = Mock(side_effect=AssertionError('user data accessed'))
        init.load_settings = Mock(side_effect=AssertionError('settings accessed'))
        secur = types.ModuleType('application.secur')
        secur.encrypt_value = secur.decrypt_value = secur.decrypt_rows = Mock()
        path = Path(__file__).resolve().parents[1] / 'application' / 'multi.py'
        spec = importlib.util.spec_from_file_location('application._store_multi_test', path)
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'__main__': main, 'application.init': init, 'application.secur': secur}):
            spec.loader.exec_module(module)
        module.FROZEN = True
        with patch.object(module.requests, 'post', side_effect=AssertionError('network request')):
            self.assertFalse(module.sync_leaderboard_data())
            response = app.test_client().get('/syncMulti')
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.get_json()['reason'], 'leaderboard_unavailable')
        init.load_user.assert_not_called()
        init.load_settings.assert_not_called()
