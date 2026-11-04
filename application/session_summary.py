"""Counters for the current monitoring session and its most recent result."""
from threading import Lock

class SessionSummary:
    def __init__(self, last=None):
        self._lock = Lock()
        self._last = last
        self._reset_counts()

    def _reset_counts(self):
        self._combats = self._wins = self._losses = self._streak = 0
        self._pending = None

    def start(self):
        with self._lock:
            self._reset_counts()

    def combat_started(self, mode, opponent=''):
        with self._lock:
            self._combats += 1
            self._pending = {'mode': mode, 'opponent': opponent or ''}

    def combat_finished(self, result, opponent=''):
        with self._lock:
            if not self._pending:
                return
            self._wins += int(result == 'victory')
            self._losses += int(result == 'defeat')
            self._streak = self._streak + 1 if result == 'victory' else 0
            self._last = dict(self._pending, result=result)
            if opponent:
                self._last['opponent'] = opponent
            self._pending = None

    def correct_connection_error(self):
        with self._lock:
            if self._last and self._last['mode'] == 'Invasion' and self._last['result'] == 'no_result':
                self._last['result'] = 'connection_error'

    def snapshot(self):
        with self._lock:
            return {'combats':self._combats, 'victories':self._wins, 'defeats':self._losses,
                    'streak':self._streak, 'last':dict(self._last) if self._last else None}
