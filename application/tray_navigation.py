"""Deliver tray shortcuts to an existing tracker tab, with a bounded fallback."""
import secrets
import threading
import time

SECTIONS = frozenset(('home', 'captures', 'statistics', 'history', 'settings'))


class Navigation:
    def __init__(self, open_url, clock=time.monotonic, timeout=6):
        self.open_url = open_url
        self.clock = clock
        self.timeout = timeout
        self.lock = threading.Lock()
        self.tab_seen = threading.Event()
        self.tabs = {}
        self.pending = {}

    def poll(self, tab, visible, focused, acknowledged=None):
        if not isinstance(tab, str) or not 1 <= len(tab) <= 80 or not tab.isascii():
            raise ValueError('Invalid tab')
        if not isinstance(visible, bool) or not isinstance(focused, bool):
            raise ValueError('Invalid tab status')
        if acknowledged is not None and (not isinstance(acknowledged, str) or len(acknowledged) > 80):
            raise ValueError('Invalid acknowledgement')
        now = self.clock()
        with self.lock:
            self.tabs = {key: value for key, value in self.tabs.items() if now - value['seen'] < 15}
            if tab not in self.tabs and len(self.tabs) >= 32:
                del self.tabs[min(self.tabs, key=lambda key: self.tabs[key]['seen'])]
            previous = self.tabs.get(tab, {})
            self.tabs[tab] = {'seen': now, 'visible': visible, 'focused': focused,
                              'last_focus': now if focused else previous.get('last_focus', 0)}
            self.tab_seen.set()
            if acknowledged in self.pending and self.pending[acknowledged]['tab'] == tab:
                self.pending[acknowledged]['ack'].set()
            for ident, command in self.pending.items():
                if command['tab'] == tab and not command['ack'].is_set():
                    return {'id': ident, 'section': command['section']}
        return None

    def wait_for_tab(self, timeout):
        return self.tab_seen.wait(timeout)

    def open(self, section):
        if section not in SECTIONS:
            raise ValueError('Invalid section')
        now = self.clock()
        with self.lock:
            eligible = [(key, value) for key, value in self.tabs.items() if now - value['seen'] < 8]
            if eligible:
                tab = max(eligible, key=lambda entry: (entry[1]['focused'], entry[1]['visible'], entry[1]['last_focus'], entry[1]['seen']))[0]
                ident = secrets.token_urlsafe(18)
                acknowledged = threading.Event()
                self.pending[ident] = {'tab': tab, 'section': section, 'ack': acknowledged}
            else:
                ident = None
        url = 'http://localhost:5000/' + ('' if section == 'home' else '#' + section)
        if ident is None:
            self.open_url(url)
            return

        def await_delivery():
            delivered = acknowledged.wait(self.timeout)
            with self.lock:
                self.pending.pop(ident, None)
            if not delivered:
                self.open_url(url)
        threading.Thread(target=await_delivery, name='tray-navigation', daemon=True).start()
