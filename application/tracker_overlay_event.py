"""Keep the most recent visible tracking event in memory for the overlay."""
from html.parser import HTMLParser
import logging
from threading import Lock

_lock = Lock()
_event = ''
_event_language = None
_renderer = None


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


def publish_html(value, *, language=None, renderer=None):
    """Remember the visible text; omit markup, comments and internal metadata."""
    global _event, _event_language, _renderer
    text = _plain_text(value)
    if text:
        with _lock:
            _event = text
            _event_language = language
            _renderer = renderer if callable(renderer) else None


def latest(language=None):
    """Read without consuming, translating an event when its renderer permits it."""
    with _lock:
        text, source_language, renderer = _event, _event_language, _renderer
    if language and language != source_language and renderer is not None:
        try:
            return _plain_text(renderer(language)) or text
        except Exception:
            logging.getLogger(__name__).exception('Unable to translate the latest overlay event')
            return text
    return text


def clear():
    global _event, _event_language, _renderer
    with _lock:
        _event = ''
        _event_language = None
        _renderer = None
