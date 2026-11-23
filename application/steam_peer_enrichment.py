"""Bounded in-memory Steam avatar cache and current connection durations.

The helper supplies avatar images obtained through Steamworks; this module
never performs network requests or writes personal data to disk.
"""
import base64
import binascii
import math
import time
from collections import OrderedDict
from io import BytesIO

from PIL import Image, UnidentifiedImageError

_MAX_AVATAR_BYTES = 128 * 1024
_MAX_ENTRIES = 128
_TTL_SECONDS = 6 * 60 * 60


def _valid_id(value):
    return isinstance(value, str) and len(value) == 17 and value.isascii() and value.isdigit()


def _measurement(value, maximum):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return value if 0 <= value <= maximum else None


def _decode_avatar(value):
    if not isinstance(value, str) or len(value) > (_MAX_AVATAR_BYTES * 4 // 3 + 8):
        return None
    try:
        data = base64.b64decode(value, validate=True)
        if len(data) > _MAX_AVATAR_BYTES or not data.startswith(b'\x89PNG\r\n\x1a\n'):
            return None
        with Image.open(BytesIO(data)) as image:
            if image.format != 'PNG' or not (1 <= image.width <= 128 and 1 <= image.height <= 128):
                return None
            image.verify()
        return data
    except (ValueError, TypeError, OSError, binascii.Error, UnidentifiedImageError, Image.DecompressionBombError):
        return None


class PeerCache:
    """Call under the caller's lock; durations start at first live observation."""
    def __init__(self):
        self._avatars = OrderedDict()
        self._started = {}
        self._next_avatar_revision = 0

    def update(self, peers, now=None):
        now = time.monotonic() if now is None else now
        current = set()
        result = []
        for peer in peers[:16]:
            sid = peer.get('id')
            if not _valid_id(sid) or sid in current:
                continue
            current.add(sid)
            self._started.setdefault(sid, now)
            data = _decode_avatar(peer.get('avatar_png'))
            if data is not None:
                old = self._avatars.get(sid)
                if old and old[1] == data:
                    revision = old[2]
                else:
                    self._next_avatar_revision += 1
                    revision = self._next_avatar_revision
                self._avatars[sid] = (now, data, revision)
                self._avatars.move_to_end(sid)
            entry = self._avatars.get(sid)
            if entry and now - entry[0] >= _TTL_SECONDS:
                del self._avatars[sid]
                entry = None
            clean = {key: value for key, value in peer.items() if key != 'avatar_png'}
            clean['ping'] = _measurement(clean.get('ping'), 60000)
            clean['average_ping'] = _measurement(clean.get('average_ping'), 60000)
            clean['jitter'] = _measurement(clean.get('jitter'), 60000)
            clean['quality'] = _measurement(clean.get('quality'), 1)
            clean['connected_seconds'] = max(0, int(now - self._started[sid]))
            clean['avatar_available'] = entry is not None
            clean['avatar_revision'] = entry[2] if entry else None
            result.append(clean)
        self._started = {sid: started for sid, started in self._started.items() if sid in current}
        while len(self._avatars) > _MAX_ENTRIES:
            self._avatars.popitem(last=False)
        return result

    def avatar(self, sid, now=None):
        if not _valid_id(sid) or sid not in self._started:
            return None
        now = time.monotonic() if now is None else now
        entry = self._avatars.get(sid)
        if not entry or now - entry[0] >= _TTL_SECONDS:
            return None
        return entry[1]
