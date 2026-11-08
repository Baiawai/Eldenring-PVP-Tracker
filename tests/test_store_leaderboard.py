import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask


class LeaderboardUnavailableTests(unittest.TestCase):
    def test_sync_route_is_unavailable_in_all_builds(self):
        app = Flask('test_leaderboard_unavailable')
        main = types.ModuleType('__main__')
        main.app = app
        path = Path(__file__).resolve().parents[1] / 'application' / 'multi.py'
        spec = importlib.util.spec_from_file_location('application._leaderboard_test', path)
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'__main__': main}):
            spec.loader.exec_module(module)
        response = app.test_client().get('/syncMulti')
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json()['reason'], 'leaderboard_unavailable')
        self.assertFalse(hasattr(module, 'requests'))
