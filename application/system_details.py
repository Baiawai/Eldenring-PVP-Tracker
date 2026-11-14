"""Read-only storage and environment details for the local interface."""
import functools
import os
import platform
import shutil
import subprocess
from pathlib import Path

from application.runtime_paths import tesseract_path, data_dir, database_path, accessible_data_directories
from application.version import APP_VERSION


def database_sizes(directory):
    """Include SQLite sidecars in each database's size; never open a database."""
    result = []
    try:
        files = sorted(directory.glob('*.db'), key=lambda p: p.name.casefold())
        for path in files:
            size = 0
            for candidate in (path, Path(str(path) + '-wal'), Path(str(path) + '-shm'), Path(str(path) + '-journal')):
                try:
                    size += candidate.stat().st_size
                except FileNotFoundError:
                    pass
            result.append({'name': path.name, 'bytes': size})
        return result
    except OSError:
        return None


@functools.lru_cache(maxsize=1)
def tesseract_version():
    try:
        result = subprocess.run([tesseract_path(), '--version'], capture_output=True, text=True,
                                encoding='utf-8', errors='replace', timeout=5,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), check=True)
        first = result.stdout.splitlines()[0].strip()
        return first or None
    except (OSError, subprocess.SubprocessError, IndexError):
        return None


def snapshot():
    directory = data_dir()
    databases = database_sizes(directory)
    if databases is not None:
        try:
            by_name = {item['name']: item for item in databases}
            for name in ('database_user.db', 'database_capture.db', 'database_multi.db',
                         'database_setting.db', 'usage_metrics.db'):
                selected = database_path(name)
                if selected.parent != directory and selected.is_file():
                    size = 0
                    for suffix in ('', '-wal', '-shm', '-journal'):
                        try:
                            size += Path(str(selected) + suffix).stat().st_size
                        except FileNotFoundError:
                            pass
                    by_name[name] = {'name': name, 'bytes': size}
            databases = sorted(by_name.values(), key=lambda item: item['name'].casefold())
        except OSError:
            databases = None
    try:
        free_bytes = shutil.disk_usage(str(directory)).free
    except OSError:
        free_bytes = None
    return {
        'storage': {'databases': databases,
                    'database_bytes': sum(item['bytes'] for item in databases) if databases is not None else None,
                    'disk_free_bytes': free_bytes},
        'environment': {'tracker': APP_VERSION, 'python': platform.python_version(),
                        'tesseract': tesseract_version(), 'os': platform.platform(),
                        'data_path': '\n'.join(map(str, accessible_data_directories()))},
    }
