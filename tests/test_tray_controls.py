import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from flask import Flask, jsonify

from application import tray_controls


class TrayControlsTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.functions = SimpleNamespace(run_monitor=False, start=Mock(), stop=Mock())
        self.store = SimpleNamespace(is_required=Mock(return_value=False))
        self.icon = SimpleNamespace(notify=Mock())
        self.translate = lambda key, fallback: key

    def invoke(self, start):
        tray_controls.change_tracking(self.app, self.functions, self.store, self.icon, start, self.translate)

    def test_starts_and_stops_using_the_existing_monitor_actions(self):
        self.functions.start.side_effect = lambda: jsonify(request='success')
        self.functions.stop.side_effect = lambda: jsonify(request='success')
        self.invoke(True)
        self.functions.start.assert_called_once()
        self.functions.run_monitor = True
        self.invoke(False)
        self.functions.stop.assert_called_once()

    def test_does_not_restart_or_stop_twice(self):
        self.invoke(False)
        self.functions.run_monitor = True
        self.invoke(True)
        self.functions.start.assert_not_called()
        self.functions.stop.assert_not_called()

    def test_required_store_update_blocks_both_actions(self):
        self.store.is_required.return_value = True
        self.invoke(True)
        self.functions.run_monitor = True
        self.invoke(False)
        self.functions.start.assert_not_called()
        self.functions.stop.assert_not_called()
        self.assertEqual(self.icon.notify.call_count, 2)

    def test_start_failure_is_reported(self):
        self.functions.start.side_effect = lambda: (jsonify(request='error'), 409)
        with self.assertLogs(self.app.logger, level='ERROR'):
            self.invoke(True)
        self.icon.notify.assert_called_once_with('monitor_start_error')


if __name__ == '__main__':
    unittest.main()
