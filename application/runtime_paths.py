"""Separate installed resources from writable runtime images."""
import os
import sys
import socket
import errno
import hashlib
import shutil
from pathlib import Path

RESOURCE_DIR = Path(__file__).resolve().parent
FROZEN = bool(getattr(sys, 'frozen', False))
DATA_FOLDER = 'Elden Ring PvP Tracker'
LEGACY_DATA_FOLDER = 'hid_el_cou'


def data_dir():
    return Path(os.environ['APPDATA']) / DATA_FOLDER


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
    directory.mkdir(parents=True, exist_ok=True)
    return directory

def tesseract_path():
    if FROZEN:
        return str(Path(sys.executable).resolve().parent / 'tesseract' / 'tesseract.exe')
    local = RESOURCE_DIR.parent / 'build' / 'tesseract-5.5.4' / 'tesseract.exe'
    if local.is_file():
        return str(local)
    return r'C:\Program Files\Tesseract-OCR\tesseract.exe'
