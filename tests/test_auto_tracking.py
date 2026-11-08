"""Automatic start is opt-in and only triggers on a game-window edge."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from application import auto_tracking


class AutoTrackingTests(unittest.TestCase):
    def test_game_window_edges_and_disable(self):
        gate = auto_tracking.StartGate()
        self.assertFalse(gate.update(False, True))
        self.assertTrue(gate.update(True, True))
        self.assertFalse(gate.update(True, True))  # A manual stop is respected.
        self.assertFalse(gate.update(True, False))
        self.assertTrue(gate.update(True, True))
        self.assertFalse(gate.update(False, True))
        self.assertTrue(gate.update(True, True))

    def test_setting_is_off_by_default_and_validated(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(auto_tracking, '_database', return_value=str(Path(tmp) / 'settings.db')):
            self.assertFalse(auto_tracking.enabled())
            auto_tracking.save(True)
            self.assertTrue(auto_tracking.enabled())
            auto_tracking.save(False)
            self.assertFalse(auto_tracking.enabled())
            with self.assertRaises(ValueError):
                auto_tracking.save('false')


if __name__ == '__main__':
    unittest.main()
