"""Associate live OCR observations with unambiguous matching Steam names.

The game may show a character name instead of a Steam name; an equal name is
only a probable association, not proof of identity. No history is consulted.
"""
import threading
import time
import unicodedata


def _name_key(value):
    if not isinstance(value, str):
        return ''
    return ' '.join(unicodedata.normalize('NFKC', value).split()).casefold()


def annotate_arena_duelist(cards, *, mode, mode_detected, running, ready, error, fight, participant_id):
    """Use the unique observed arena peer only while its duel is active."""
    if not mode_detected or mode != 'Arena':
        return cards
    result = [dict(card, role=None) for card in cards if isinstance(card, dict)]
    if running and ready and not error and fight and len(result) == 1 and participant_id:
        if result[0].get('id') == participant_id:
            result[0]['role'] = 'duelist'
    return result


class RoleTracker:
    """Keep probable roles only while their matching Steam peer is present."""

    _ARRIVALS = frozenset(('joined', 'invaded'))
    _DEPARTURES = frozenset(('left', 'dismissed', 'died', 'completed'))
    _ROLES = frozenset(('ally', 'cooperator', 'hunter', 'invader'))

    def __init__(self, pending_seconds=10, clock=time.monotonic):
        self._lock = threading.Lock()
        self._clock = clock
        self._pending_seconds = pending_seconds
        self._clear_locked()

    def _clear_locked(self):
        self._active = False
        self._status = None
        self._peers = {}
        self._bindings = {}
        self._pending = {}
        self._conflicts = set()

    def clear(self):
        with self._lock:
            self._clear_locked()

    def _expire(self, now):
        self._pending = {key: item for key, item in self._pending.items() if now <= item[1]}

    def _match(self, key, role):
        matches = [ident for ident, name in self._peers.items() if name == key]
        if len(matches) != 1 or key in self._conflicts:
            return False
        ident = matches[0]
        previous = self._bindings.get(ident)
        if previous and previous[1] != role:
            # Conflicting roles for one name do not identify either player.
            self._bindings.pop(ident, None)
            self._conflicts.add(key)
            return False
        self._bindings[ident] = (key, role)
        return True

    def update_peers(self, status, peers):
        """Consume each complete Steam snapshot, including disconnects."""
        with self._lock:
            if status == 'starting':
                # Startup can lag behind OCR. Retain only new, short-lived
                # observations until the first active snapshot arrives.
                if self._status != 'starting':
                    self._clear_locked()
                self._status = 'starting'
                self._expire(self._clock())
                return
            if status != 'active' or not isinstance(peers, list):
                self._clear_locked()
                return
            self._active = True
            self._status = 'active'
            now = self._clock()
            self._expire(now)
            previous_peers = self._peers
            current = {}
            for peer in peers[:16]:
                if not isinstance(peer, dict):
                    continue
                ident, name = peer.get('id'), _name_key(peer.get('name'))
                if isinstance(ident, str) and len(ident) == 17 and ident.isascii() and ident.isdigit() and name:
                    current[ident] = name
            # A transition to an empty peer set ends the previous encounter.
            if previous_peers and not current:
                self._pending.clear()
            self._peers = current
            self._conflicts.intersection_update(current.values())
            counts = {name: list(current.values()).count(name) for name in current.values()}
            self._bindings = {ident: item for ident, item in self._bindings.items()
                              if current.get(ident) == item[0] and counts[item[0]] == 1
                              and item[0] not in self._conflicts}
            for name in [name for name, count in counts.items() if count > 1]:
                self._pending.pop(name, None)
            for name, (role, _) in list(self._pending.items()):
                if self._match(name, role) or name in self._conflicts:
                    self._pending.pop(name, None)

    def observe(self, sighting):
        """Record a confirmed OCR event without persisting player information."""
        if not isinstance(sighting, dict):
            return
        key, role, event = _name_key(sighting.get('name')), sighting.get('role'), sighting.get('event')
        if not key or not isinstance(role, str) or role not in self._ROLES or not isinstance(event, str) or event not in self._ARRIVALS | self._DEPARTURES:
            return
        with self._lock:
            if not self._active and self._status != 'starting':
                return
            now = self._clock()
            self._expire(now)
            if event in self._DEPARTURES:
                self._pending.pop(key, None)
                self._bindings = {ident: item for ident, item in self._bindings.items() if item[0] != key}
                return
            matches = sum(name == key for name in self._peers.values())
            if matches > 1 or key in self._conflicts:
                self._pending.pop(key, None)
                return
            if matches == 1:
                self._match(key, role)
                return
            pending = self._pending.get(key)
            if pending and pending[0] != role:
                self._pending.pop(key, None)
                self._conflicts.add(key)
            else:
                self._pending[key] = (role, now + self._pending_seconds)

    def annotate(self, cards):
        """Return copies with roles solely from this tracker, never caller input."""
        with self._lock:
            result = []
            for card in cards:
                if not isinstance(card, dict):
                    continue
                copy = dict(card)
                binding = self._bindings.get(copy.get('id')) if self._active else None
                copy['role'] = binding[1] if binding and _name_key(copy.get('name')) == binding[0] else None
                result.append(copy)
            return result
