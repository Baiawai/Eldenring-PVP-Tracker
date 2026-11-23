"""Bounded, consent-gated lookup of Steam identities in the ranking.

The badge lookup is restricted to authenticated participants and verified
Steam accounts. It is separate from publishing a Steam profile link.
IDs are sent in a POST body, not in the URL. No network call blocks a reader.
"""
import math
import threading
import time
from contextlib import closing
from urllib.error import HTTPError

from application import network_retry

_MODES = frozenset(('Arena', 'Invasion', 'Defense', 'All'))
_LOW = '76561197960265729'
_HIGH = '76561202255233023'
_TTL = 30.0
_MIN_REQUEST_INTERVAL = 10.0
_ERROR_BACKOFF = 60.0
_UNAVAILABLE_BACKOFF = 600.0
_STAT_KEYS = ('victory', 'defeat', 'egality', 'combats', 'ratio')


def _steam_id(value):
    return isinstance(value, str) and len(value) == 17 and value.isascii() and value.isdigit() and _LOW <= value <= _HIGH


def locally_permitted():
    """Require the same accepted event terms and current origin as ranking UI."""
    try:
        from application import online_leaderboard as online
        enabled, ident, token, pending, server = online._settings()
        origin = online._base_url()
        if not enabled or pending or not origin or not online._event_permission():
            return False
        with closing(online._db()) as db:
            consent_url, transition_nonce = db.execute(
                'SELECT server_consent_url,server_transition_nonce FROM online_leaderboard WHERE id=1').fetchone()
        if transition_nonce or (server and server != origin) or (consent_url and consent_url != origin):
            return False
        if online.FROZEN:
            if any((ident, token, server)) and not all((ident, token, server)):
                return False
            if not any((ident, token, server)) and consent_url != origin:
                return False
        return True
    except Exception:
        return False


def _request(mode, ids, origin):
    from application import online_leaderboard
    return online_leaderboard._call('POST', '/api/v1/leaderboards/peers',
                                    {'mode': mode, 'steam_ids': list(ids)}, root=origin)


def _request_members(mode, ids, origin):
    """Use the private, badge-only adapter without calling the rank endpoint."""
    if mode != 'All':
        raise ValueError('invalid tracker membership lookup')
    from application._private_peer_badges import request_badges
    return request_badges(ids, origin)


def _origin():
    from application import online_leaderboard
    return online_leaderboard._base_url()


def _parse(payload, mode, ids):
    if (not isinstance(payload, dict) or not isinstance(payload.get('entries'), list) or
            (mode != 'All' and payload.get('mode') != mode) or
            (mode == 'All' and 'mode' in payload)):
        raise ValueError('invalid leaderboard peer response')
    if len(payload['entries']) > len(ids):
        raise ValueError('too many leaderboard peer results')
    result = {}
    for entry in payload['entries']:
        if not isinstance(entry, dict):
            raise ValueError('invalid leaderboard peer entry')
        ident = entry.get('steam_id')
        if ident not in ids or ident in result:
            raise ValueError('invalid leaderboard peer identity')
        if mode == 'All':
            # This lookup proves only a ranking association. Do not
            # retain rank or statistics and never infer a negative result.
            result[ident] = True
            continue
        rank = entry.get('rank')
        if type(rank) is not int or rank < 1:
            raise ValueError('invalid leaderboard peer rank')
        raw_stats = entry.get('stats')
        if not isinstance(raw_stats, dict) or not isinstance(entry.get('history_unverified'), bool):
            raise ValueError('invalid leaderboard peer statistics')
        stats = {}
        for key in _STAT_KEYS:
            value = raw_stats.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0:
                stats[key] = value
        result[ident] = {'rank': rank, 'stats': stats, 'history_unverified': entry['history_unverified']}
    return result


class PeerRankingCache:
    def __init__(self, request=_request, permission=locally_permitted, clock=time.monotonic,
                 origin=_origin):
        self._request, self._permission, self._clock = request, permission, clock
        self._origin = origin
        self._lock = threading.Lock()
        self._data = {}
        self._generation = 0
        self._running = False
        self._next_request = 0.0

    def snapshot(self, mode, ids, *, permitted):
        """Return cached matches immediately and schedule at most one request."""
        if not permitted:
            with self._lock:
                self._generation += 1
                self._data.clear()
            return {}
        if mode not in _MODES or not isinstance(ids, (tuple, list, set)):
            return {}
        selected = tuple(sorted({ident for ident in ids if _steam_id(ident)}))[:16]
        if not selected:
            return {}
        try:
            origin = self._origin()
        except Exception:
            return {}
        if not origin:
            return {}
        key = (origin, mode, selected)
        now = self._clock()
        with self._lock:
            self._data = {k: v for k, v in self._data.items() if v[0] > now}
            cached = self._data.get(key)
            if cached:
                if mode == 'All':
                    return dict(cached[1])
                return {ident: dict(info, stats=dict(info['stats'])) for ident, info in cached[1].items()}
            if not self._running and now >= self._next_request:
                self._running = True
                self._next_request = now + _MIN_REQUEST_INTERVAL
                generation = self._generation
                try:
                    threading.Thread(target=self._fetch, args=(key, generation), daemon=True,
                                     name='overlay-peer-ranking').start()
                except Exception:
                    self._running = False
                    self._next_request = now + _ERROR_BACKOFF
            return {}

    def _fetch(self, key, generation):
        origin, mode, ids = key
        delay = 0.0
        try:
            with self._lock:
                if generation != self._generation:
                    return
            if not self._permission() or self._origin() != origin:
                return
            with self._lock:
                if generation != self._generation:
                    return
            payload = self._request(mode, ids, origin)
            values = _parse(payload, mode, ids)
            if not self._permission() or self._origin() != origin:
                return
            with self._lock:
                if generation == self._generation:
                    if len(self._data) >= 8:
                        self._data.pop(next(iter(self._data)))
                    self._data[key] = (self._clock() + _TTL, values)
        except Exception as error:
            fallback = _UNAVAILABLE_BACKOFF if isinstance(error, HTTPError) and error.code in (404, 405) else _ERROR_BACKOFF
            delay = max(fallback, network_retry.retry_after(error) or 0)
            if isinstance(error, HTTPError):
                error.close()
        finally:
            with self._lock:
                if delay:
                    self._next_request = max(self._next_request, self._clock() + delay)
                self._running = False


_CACHE = PeerRankingCache()


def snapshot(mode, steam_ids, *, permitted):
    return _CACHE.snapshot(mode, steam_ids, permitted=permitted)


def _tracker_member_permitted():
    try:
        from application import overlay_settings
        return overlay_settings.options().get('show_tracker_user', True) is True and locally_permitted()
    except Exception:
        return False


# Shared by the overlay and the application cards. In-flight responses are
# discarded if the user turns off the option or withdraws ranking consent.
_MEMBER_CACHE = PeerRankingCache(request=_request_members, permission=_tracker_member_permitted)


def tracker_members(steam_ids, *, enabled):
    """Return positive matches from the shared cache without blocking capture.

    Absence means unknown, not a confirmed non-user. The switch and the local
    ranking consent both gate lookup, while the background worker checks the
    same consent again before publishing a response.
    """
    if not enabled:
        return _MEMBER_CACHE.snapshot('All', (), permitted=False)
    if not isinstance(steam_ids, (tuple, list, set)) or not any(_steam_id(value) for value in steam_ids):
        return {}
    return _MEMBER_CACHE.snapshot('All', steam_ids, permitted=locally_permitted())
