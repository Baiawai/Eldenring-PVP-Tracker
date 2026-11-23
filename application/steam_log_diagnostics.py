"""Observe only Steam IPC log metadata, without reading or changing its contents."""
import os
import time
from pathlib import Path


class LogProbe:
    """A read-only, non-elevated observation; it is not proof Steam logging is enabled."""

    ACTIVE_SECONDS = 180

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self.reset()

    def reset(self):
        self._path = None
        self._signature = None
        self._observed_at = None

    @property
    def receiving_until(self):
        return None if self._observed_at is None else self._observed_at + self.ACTIVE_SECONDS

    def observe(self, path):
        if path is None:
            self.reset()
            return 'unknown'
        path = Path(path)
        if path != self._path:
            self.reset()
            self._path = path
        try:
            # Opening the file checks only the current process's permissions.
            # The separately elevated ping helper can have different rights.
            with path.open('rb') as stream:
                stat = os.fstat(stream.fileno())
        except FileNotFoundError:
            self._signature = self._observed_at = None
            return 'missing'
        except (OSError, ValueError):
            self._signature = self._observed_at = None
            return 'unreadable'
        signature = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)
        now = self._clock()
        if self._signature is not None and signature != self._signature:
            self._observed_at = now
        self._signature = signature
        if self._observed_at is not None and 0 <= now - self._observed_at < self.ACTIVE_SECONDS:
            return 'receiving'
        return 'waiting'
