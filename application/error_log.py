"""Locate the tracker's own diagnostic log without accepting a client path."""
import os
import tempfile
from pathlib import Path

from application.runtime_paths import data_dir, _private_data_dir


def selected_log():
    logical = data_dir() / 'tracker-errors.log'
    private_dir = _private_data_dir()
    private = private_dir / logical.name if private_dir else None
    candidate = logical
    try:
        if private and private.is_file() and (not logical.exists() or os.path.samefile(logical, private)):
            candidate = private
    except OSError:
        pass
    fallback = Path(tempfile.gettempdir()) / 'Elden Ring PvP Tracker' / logical.name
    existing = []
    for path in (candidate, fallback):
        try:
            if path.is_file() and not path.is_symlink():
                existing.append((path.stat().st_mtime, path))
        except OSError:
            pass
    return (max(existing, key=lambda item: item[0])[1], True) if existing else (candidate, False)


def open_log():
    path, available = selected_log()
    if not available:
        return False
    try:
        os.startfile(str(path))
        return True
    except OSError:
        return False
