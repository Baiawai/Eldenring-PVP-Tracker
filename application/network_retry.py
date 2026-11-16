"""Bounded retries for explicitly replay-safe API operations."""
import errno
import random
import socket
import ssl
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError, URLError

_RETRYABLE_STATUS = frozenset((408, 429, 500, 502, 503, 504))
_RETRYABLE_ERRNO = frozenset((errno.ECONNRESET, errno.ECONNREFUSED, errno.ECONNABORTED,
                               errno.ENETUNREACH, errno.EHOSTUNREACH, errno.ETIMEDOUT,
                               10054, 10061, 10053, 10051, 10065, 10060))


def transient(error):
    if isinstance(error, HTTPError):
        return error.code in _RETRYABLE_STATUS
    if isinstance(error, URLError):
        error = error.reason
    if isinstance(error, ssl.SSLError):
        return False
    if isinstance(error, socket.gaierror):
        return error.errno == socket.EAI_AGAIN
    return isinstance(error, TimeoutError) or (isinstance(error, OSError) and error.errno in _RETRYABLE_ERRNO)


def retry_after(error):
    if not isinstance(error, HTTPError) or error.code != 429 or not error.headers:
        return None
    value = error.headers.get('Retry-After')
    if not value:
        return None
    try:
        if value.strip().isdigit():
            return float(value.strip())
        target = parsedate_to_datetime(value)
        if target.tzinfo is None:
            target = target.replace(tzinfo=timezone.utc)
        return max(0.0, (target - datetime.now(timezone.utc)).total_seconds())
    except (ValueError, TypeError, OverflowError):
        return None


def replay_safe(method, path):
    route = path.split('?', 1)[0]
    return method.upper() == 'GET' or (method.upper() == 'POST' and route in ('/api/v1/events', '/api/v1/baselines'))


def execute(action, *, safe, attempts=3):
    for attempt in range(attempts):
        try:
            return action()
        except (HTTPError, URLError, OSError) as error:
            error.tracker_replay_safe = safe
            if not safe or not transient(error) or attempt + 1 >= attempts:
                raise
            server_delay = retry_after(error)
            if server_delay is not None and server_delay > 30:
                raise
            delay = max(server_delay or 0, random.uniform(0.75, 1.25) * (2 ** attempt))
            if isinstance(error, HTTPError):
                error.close()
            time.sleep(delay)
