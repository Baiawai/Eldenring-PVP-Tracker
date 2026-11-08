"""Tracking notifications stay optional and never affect the monitor."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from application import tracker_notifications


class NotificationTests(unittest.TestCase):
    def test_preferences_are_independent_and_off_by_default(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(tracker_notifications, '_database', return_value=str(Path(tmp) / 'settings.db')):
            self.assertEqual(tracker_notifications.load(), {kind:False for kind in tracker_notifications.KINDS})
            tracker_notifications.save('game_hidden', True)
            self.assertEqual(tracker_notifications.load(), {'monitor_error':False, 'game_hidden':True, 'monitor_stop':False})
            with self.assertRaises(ValueError):
                tracker_notifications.save('other', True)
            with self.assertRaises(ValueError):
                tracker_notifications.save('game_hidden', 'false')

    def test_dispatch_failure_does_not_propagate(self):
        with patch.object(tracker_notifications.threading.Thread, 'start', side_effect=RuntimeError('unavailable')):
            self.assertIsNone(tracker_notifications.notify('game_hidden'))
