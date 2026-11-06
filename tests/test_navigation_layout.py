"""Check the main navigation and the relocated profile counters."""
from html.parser import HTMLParser
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
VOID_TAGS = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}


class LayoutParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.counter_ancestors = []
        self.navigation_ids = []
        self.ids = set()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = set(attrs.get('class', '').split())
        self.ids.add(attrs.get('id'))
        if 'scoreboard' in classes:
            self.counter_ancestors.append([item.get('id') for _, item in self.stack])
        if tag == 'li' and any('main-menu' in item.get('class', '').split() for _, item in self.stack):
            self.navigation_ids.append(attrs.get('id'))
        if tag not in VOID_TAGS:
            self.stack.append((tag, attrs))

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break


class NavigationLayoutTests(unittest.TestCase):
    def test_counters_are_in_profile_and_navigation_remains_complete(self):
        parser = LayoutParser()
        parser.feed((ROOT / 'templates/index.html').read_text(encoding='utf-8'))
        self.assertEqual(len(parser.counter_ancestors), 1)
        self.assertIn('profile_sidebar', parser.counter_ancestors[0])
        self.assertEqual(set(parser.navigation_ids), {'start', 'menu_button_captures', 'menu_button_multi',
            'menu_button_info', 'menu_button_players', 'menu_button_history', 'menu_button_settings',
            'menu_button_information'})
        self.assertTrue({'sidebar_legend', 'sidebar_last_combat'} <= parser.ids)
        self.assertTrue({'session_combats', 'session_victories', 'session_defeats'}.isdisjoint(parser.ids))


if __name__ == '__main__':
    unittest.main()
