"""Separate installed resources from writable runtime images."""
import os
import sys
import socket
import errno
import hashlib
import shutil
import ctypes
from pathlib import Path

RESOURCE_DIR = Path(__file__).resolve().parent
FROZEN = bool(getattr(sys, 'frozen', False))


def is_store_build(frozen, resource_dir):
    return bool(frozen and (resource_dir / 'store-build.marker').is_file())


STORE_BUILD = is_store_build(FROZEN, RESOURCE_DIR)
DATA_FOLDER = 'Elden Ring PvP Tracker'
LEGACY_DATA_FOLDER = 'hid_el_cou'


def data_dir():
    return Path(os.environ['APPDATA']) / DATA_FOLDER


def package_family_name():
    """Return the current package identity, not the identity of another app."""
    if not FROZEN or os.name != 'nt':
        return None
    try:
        get_family = ctypes.windll.kernel32.GetCurrentPackageFamilyName
        get_family.argtypes = [ctypes.POINTER(ctypes.c_uint32), ctypes.c_wchar_p]
        get_family.restype = ctypes.c_long
        length = ctypes.c_uint32(0)
        if get_family(ctypes.byref(length), None) != 122 or not 0 < length.value <= 1024:
            return None
        buffer = ctypes.create_unicode_buffer(length.value)
        if get_family(ctypes.byref(length), buffer) != 0:
            return None
        return buffer.value or None
    except (AttributeError, OSError, ValueError):
        return None


def _private_data_dir():
    family = package_family_name()
    local = os.environ.get('LOCALAPPDATA')
    if not family or not local or Path(family).name != family:
        return None
    return Path(local) / 'Packages' / family / 'LocalCache' / 'Roaming' / DATA_FOLDER


def existing_data_file(name, directory=None):
    """Find an existing Store file without replacing a different logical file."""
    if not isinstance(name, str) or Path(name).name != name or not name:
        raise ValueError('Invalid data filename')
    logical = (Path(directory) if directory is not None else data_dir()) / name
    folder = _private_data_dir()
    if folder is None:
        return logical
    private = folder / name
    try:
        if not private.is_file():
            return logical
        try:
            logical.stat()
        except FileNotFoundError:
            # A key or migration marker belongs to the selected profile, not
            # to an unrelated private copy shadowed by another database.
            return private if database_path('database_user.db').parent == folder else logical
        return private if os.path.samefile(logical, private) else logical
    except OSError:
        return logical


def database_path(name):
    """Resolve an existing Store database without switching between different files.

    A missing database keeps the logical path so Windows can create it normally.
    Existing SQLite sidecars must also refer to the same files before changing
    the path, otherwise their pending transactions could be missed.
    """
    if not isinstance(name, str) or Path(name).name != name or not name.endswith('.db'):
        raise ValueError('Invalid database filename')
    logical = data_dir() / name
    folder = _private_data_dir()
    if folder is None:
        return logical
    private = folder / name
    try:
        if not private.is_file():
            return logical
        def present(path):
            try:
                path.stat()
                return True
            except FileNotFoundError:
                return False
        try:
            logical.stat()
            logical_exists = True
        except FileNotFoundError:
            logical_exists = False
        if logical_exists and not os.path.samefile(logical, private):
            return logical
        for suffix in ('-wal', '-shm', '-journal'):
            left, right = Path(str(logical) + suffix), Path(str(private) + suffix)
            left_exists, right_exists = present(left), present(right)
            if logical_exists:
                if left_exists != right_exists or (left_exists and not os.path.samefile(left, right)):
                    return logical
            elif left_exists:
                return logical
        return private
    except OSError:
        return logical


def accessible_data_directories():
    """Find Explorer-visible locations of the databases in the current process view.

    MSIX can overlay individual files, so both directories may be required.
    Database files may be selected from the private package directory.
    """
    logical = data_dir()
    private = _private_data_dir()
    if private is None:
        return [logical]
    locations = []
    for name in ('database_user.db', 'database_capture.db', 'database_multi.db',
                 'database_setting.db', 'usage_metrics.db'):
        resolved = database_path(name)
        if resolved.is_file() and resolved.parent not in locations:
            locations.append(resolved.parent)
    try:
        entries = sorted(logical.iterdir(), key=lambda path: path.name.casefold())
    except OSError:
        return locations or [logical]
    for current in entries:
        candidate = private / current.name
        try:
            location = private if candidate.exists() and os.path.samefile(current, candidate) else logical
        except OSError:
            location = logical
        if location not in locations:
            locations.append(location)
    return locations or [logical]


def _tracker_running():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
        connection.settimeout(0.5)
        return connection.connect_ex(('127.0.0.1', 5000)) == 0


def _file_manifest(root):
    result = {}
    for path in root.rglob('*'):
        if path.is_symlink():
            raise RuntimeError(f'Data migration cannot copy a symbolic link: {path}')
        relative = str(path.relative_to(root))
        if path.is_dir():
            result[relative] = None
        elif path.is_file():
            digest = hashlib.sha256()
            with path.open('rb') as source:
                for block in iter(lambda: source.read(1024 * 1024), b''):
                    digest.update(block)
            result[relative] = digest.digest()
        else:
            raise RuntimeError(f'Data migration cannot copy this item: {path}')
    return result


def initialize_data_dir():
    """Move the old data directory once, without merging or overwriting files."""
    target = data_dir()
    legacy = target.parent / LEGACY_DATA_FOLDER
    if legacy.exists():
        if target.exists():
            raise RuntimeError(f'Data migration stopped: both {legacy} and {target} exist.')
        if _tracker_running():
            raise RuntimeError('Data migration stopped: the tracker may already be running.')
        try:
            legacy.rename(target)
        except OSError as error:
            if error.errno != errno.EXDEV:
                raise
            # Some Windows environments disallow directory renames. Copy first,
            # verify every file and only then remove the original directory.
            before = _file_manifest(legacy)
            shutil.copytree(legacy, target, symlinks=True)
            if _file_manifest(target) != before or _file_manifest(legacy) != before:
                raise RuntimeError('Data migration verification failed; both folders were kept.')
            shutil.rmtree(legacy)
    else:
        target.mkdir(parents=True, exist_ok=True)
    return target

def image_dir():
    if not FROZEN:
        return RESOURCE_DIR
    directory = data_dir() / 'runtime_images'
    private_root = _private_data_dir()
    if private_root is not None:
        private = private_root / 'runtime_images'
        try:
            if private.is_dir():
                if not directory.exists() or os.path.samefile(directory, private):
                    return private
            elif not directory.exists() and database_path('database_user.db').parent == private_root:
                private.mkdir(parents=True, exist_ok=True)
                return private
        except OSError:
            pass
    directory.mkdir(parents=True, exist_ok=True)
    return directory

def tesseract_path():
    if FROZEN:
        return str(Path(sys.executable).resolve().parent / 'tesseract' / 'tesseract.exe')
    local = RESOURCE_DIR.parent / 'build' / 'tesseract-5.5.4' / 'tesseract.exe'
    if local.is_file():
        return str(local)
    return r'C:\Program Files\Tesseract-OCR\tesseract.exe'
