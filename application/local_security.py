"""Restrict the local HTTP interface to requests from the tracker origin."""
from urllib.parse import urlsplit

_ALLOWED_HOSTS = frozenset(('localhost', 'localhost:5000', '127.0.0.1',
                            '127.0.0.1:5000', '[::1]', '[::1]:5000'))


def is_allowed_request(host, origin=None, referer=None, fetch_site=None):
    """Allow local navigation and same-origin API requests, but reject cross-site calls."""
    host = (host or '').lower()
    if host not in _ALLOWED_HOSTS:
        return False
    if fetch_site and fetch_site.lower() not in ('same-origin', 'none'):
        return False
    for value in (origin, referer):
        if value:
            try:
                parsed = urlsplit(value)
                if parsed.scheme.lower() != 'http' or parsed.netloc.lower() != host:
                    return False
            except ValueError:
                return False
    return True
