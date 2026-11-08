"""Prepare a local MSYS2 Tesseract runtime without changing the system install."""
import hashlib
import io
import re
import tarfile
import urllib.request
from pathlib import Path
from compression import zstd

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'build' / 'tesseract-5.5.4'
BASE = 'https://repo.msys2.org/mingw/mingw64/'
TARGET = 'mingw-w64-x86_64-tesseract-ocr'
TARGET_HASH = '77cf3ee8b8c86cfa0286737b921de38e867491459a470319ac83c765f4d4caa5'


def fetch(url):
    with urllib.request.urlopen(url, timeout=90) as response:
        return response.read()


def fields(contents):
    return {part.split('\n', 1)[0].strip('%'): part.split('\n', 1)[1].strip().splitlines()
            for part in contents.strip().split('\n\n') if '\n' in part}


database = {}
with tarfile.open(fileobj=io.BytesIO(fetch(BASE + 'mingw64.db')), mode='r:*') as archive:
    for member in archive:
        if member.name.endswith('/desc'):
            record = fields(archive.extractfile(member).read().decode())
            database[record['NAME'][0]] = record

queue, done = [TARGET], set()
while queue:
    name = queue.pop()
    if name not in database:
        providers = [key for key, value in database.items()
                     if any(re.split(r'[<>=]', item, maxsplit=1)[0] == name
                            for item in value.get('PROVIDES', []))]
        if len(providers) != 1:
            raise RuntimeError(f'MSYS2 dependency has no unique provider: {name}')
        name = providers[0]
    if name in done:
        continue
    if name not in database:
        raise RuntimeError(f'MSYS2 dependency not found: {name}')
    record = database[name]
    filename, expected = record['FILENAME'][0], record['SHA256SUM'][0]
    if name == TARGET and (record['VERSION'][0] != '5.5.4-1' or expected != TARGET_HASH):
        raise RuntimeError('The Tesseract package version or checksum has changed.')
    payload = fetch(BASE + filename)
    if hashlib.sha256(payload).hexdigest() != expected:
        raise RuntimeError(f'Checksum mismatch: {name}')
    print(f'Preparing {name} {record["VERSION"][0]}', flush=True)
    with tarfile.open(fileobj=io.BytesIO(zstd.decompress(payload)), mode='r:') as archive:
        for member in archive:
            if not member.isfile():
                continue
            path = Path(member.name)
            if '..' in path.parts:
                raise RuntimeError(f'Unsafe path in MSYS2 package: {member.name}')
            if path.parts[:2] == ('mingw64', 'bin') and (path.suffix.lower() == '.dll' or (name == TARGET and path.name == 'tesseract.exe')):
                output = DEST / path.name
            elif path.parts[:3] == ('mingw64', 'share', 'licenses'):
                output = DEST / 'licenses' / Path(*path.parts[3:])
            else:
                continue
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(archive.extractfile(member).read())
    queue.extend(re.split(r'[<>=]', dep, maxsplit=1)[0] for dep in record.get('DEPENDS', []))
    done.add(name)

license_file = DEST / 'licenses' / 'tesseract-ocr' / 'LICENSE'
if not (DEST / 'tesseract.exe').is_file() or not license_file.is_file():
    raise RuntimeError('Tesseract executable or license is missing.')
(DEST / 'doc').mkdir(exist_ok=True)
(DEST / 'doc' / 'LICENSE').write_bytes(license_file.read_bytes())
print(f'Prepared Tesseract in {DEST}')
