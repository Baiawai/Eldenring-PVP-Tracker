import threading
import unittest

from application.tray_navigation import Navigation


class TrayNavigationTests(unittest.TestCase):
    def setUp(self):
        self.opened = []
        self.opened_event = threading.Event()
        self.now = 10
        def open_url(url):
            self.opened.append(url)
            self.opened_event.set()
        self.navigation = Navigation(open_url, clock=lambda: self.now, timeout=0.1)

    def test_no_tab_opens_a_new_page(self):
        self.assertFalse(self.navigation.wait_for_tab(0))
        self.navigation.open('statistics')
        self.assertEqual(self.opened, ['http://localhost:5000/#statistics'])

    def test_live_focused_tab_receives_and_acknowledges_command(self):
        self.navigation.poll('older', True, False)
        self.assertTrue(self.navigation.wait_for_tab(0))
        self.navigation.poll('focused', True, True)
        self.navigation.open('settings')
        self.assertIsNone(self.navigation.poll('older', True, False))
        command = self.navigation.poll('focused', True, True)
        self.assertEqual(command['section'], 'settings')
        self.assertIsNone(self.navigation.poll('focused', True, True, command['id']))
        self.assertFalse(self.opened_event.wait(0.2))

    def test_unresponsive_tab_falls_back(self):
        self.navigation.poll('closed', True, True)
        self.navigation.open('history')
        self.assertTrue(self.opened_event.wait(1))
        self.assertEqual(self.opened, ['http://localhost:5000/#history'])

    def test_stale_tab_is_not_selected_and_invalid_data_rejected(self):
        self.navigation.poll('stale', True, True)
        self.now += 9
        self.navigation.open('captures')
        self.assertEqual(self.opened, ['http://localhost:5000/#captures'])
        with self.assertRaises(ValueError):
            self.navigation.poll('tab', 'true', False)
        with self.assertRaises(ValueError):
            self.navigation.open('https://example.com')


if __name__ == '__main__':
    unittest.main()
