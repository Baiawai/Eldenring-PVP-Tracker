import unittest
from application.invasion_search import SearchVisibility


class SearchVisibilityTests(unittest.TestCase):
    def test_short_ocr_failure_does_not_rearm(self):
        gate = SearchVisibility()
        self.assertFalse(gate.observe(True, True, 0))
        self.assertFalse(gate.observe(True, False, 1))
        self.assertFalse(gate.observe(True, False, 3))
        self.assertFalse(gate.observe(True, True, 4))
        self.assertFalse(gate.observe(True, False, 8))
        self.assertFalse(gate.observe(True, True, 9))

    def test_sustained_absence_rearms_once(self):
        gate = SearchVisibility()
        self.assertFalse(gate.observe(True, True, 0))
        self.assertFalse(gate.observe(True, False, 1))
        self.assertFalse(gate.observe(True, False, 3))
        self.assertTrue(gate.observe(True, False, 6))
        self.assertFalse(gate.observe(False, False, 7))

    def test_capture_pause_does_not_count_as_missing_frames(self):
        gate = SearchVisibility()
        self.assertFalse(gate.observe(True, False, 0))
        self.assertFalse(gate.observe(True, False, 1))
        self.assertFalse(gate.observe(True, False, 60))
        self.assertFalse(gate.observe(True, False, 61))
        self.assertTrue(gate.observe(True, False, 65))
