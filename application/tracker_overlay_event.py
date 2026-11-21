"""Keep the most recent visible tracking event in memory for the overlay."""
from html.parser import HTMLParser
from threading import Lock

_lock = Lock()
_event = ''


class _PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, text):
        self.parts.append(text)

    def handle_starttag(self, tag, attrs):
        if tag in ('br', 'p', 'div'):
            self.parts.append(' ')

    def handle_endtag(self, tag):
        if tag in ('p', 'div'):
            self.parts.append(' ')


def _plain_text(value):
    parser = _PlainText()
    parser.feed(value)
    parser.close()
    return ' '.join(''.join(parser.parts).split())[:240]


def publish_html(value):
    """Remember the visible text; omit markup, comments and internal metadata."""
    global _event
    text = _plain_text(value)
    if text:
        with _lock:
            _event = text


def latest():
    """Read without consuming; next events use the current UI language."""
    with _lock:
        return _event


def clear():
    global _event
    with _lock:
        _event = ''
