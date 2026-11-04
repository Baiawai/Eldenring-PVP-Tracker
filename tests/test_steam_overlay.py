import unittest
from unittest.mock import patch
from application.steam_overlay import OverlayDetector, overlay_indicators_match, is_steam_overlay_window

class SteamOverlayTests(unittest.TestCase):
    def test_signal_requires_all_observed_windows_indicators(self):
        desktop = (0, 0, 3840, 1080)
        self.assertTrue(overlay_indicators_match(1, 1, True, 42, 42, desktop, desktop))
        for args in [(1, None, True, 42, 42, desktop, desktop),
                     (1, 1, False, 42, 42, desktop, desktop),
                     (1, 1, True, 43, 42, desktop, desktop),
                     (1, 1, True, 42, 42, (0,0,1920,1080), desktop),
                     (None, None, True, 42, 42, desktop, desktop)]:
            with self.subTest(args=args): self.assertFalse(overlay_indicators_match(*args))

    def test_confirmation_resets_when_indicators_disappear(self):
        detector = OverlayDetector(confirmation_seconds=0.4)
        with patch('application.steam_overlay.has_overlay_indicators', side_effect=[True,True,True,False,True,True]):
            self.assertFalse(detector.update(1, now=1))
            self.assertFalse(detector.update(1, now=1.2))
            self.assertTrue(detector.update(1, now=1.5))
            self.assertFalse(detector.update(1, now=1.6))
            self.assertFalse(detector.update(1, now=1.7))
            self.assertTrue(detector.update(1, now=2.2))

    def test_steam_window_signal_works_without_mouse_heuristic(self):
        detector = OverlayDetector(confirmation_seconds=0.4)
        with patch('application.steam_overlay.has_overlay_indicators', return_value=False):
            self.assertFalse(detector.update(None, now=1, overlay_window=True))
            self.assertTrue(detector.update(None, now=1.5, overlay_window=True))
            self.assertFalse(detector.update(None, now=1.6, overlay_window=False))

    def test_unowned_or_game_window_is_not_an_overlay_window(self):
        self.assertFalse(is_steam_overlay_window(1, 1))
        with patch('application.steam_overlay.win32gui.GetWindow', return_value=0):
            self.assertFalse(is_steam_overlay_window(2, 1))

if __name__ == '__main__': unittest.main()
