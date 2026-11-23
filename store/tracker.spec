# PyInstaller onedir build: only known, non-personal application resources.
from pathlib import Path
import os
import sys
from PyInstaller.utils.hooks import collect_data_files

root = Path(SPECPATH).parent
datas = [(str(root / name), name) for name in ('static', 'templates')]
datas += [(str(root / 'application' / name), 'application/' + name)
          for name in ('locales', 'geoip', 'steam_peers')]
datas += [(str(root / 'application' / 'steam_logo.png'), 'application')]
datas += [(str(root / 'store' / 'store-build.marker'), 'application')]
# PyWinRT projections load their generated metadata from disk at runtime.
winrt_modules = ['winrt.windows.applicationmodel', 'winrt.windows.services.store',
                 'winrt.windows.foundation', 'winrt.windows.foundation.collections',
                 'winrt.windows.storage.streams']
for module in winrt_modules:
    datas += collect_data_files(module, includes=['*.pywinrt'])
# The optional local metadata adapter is kept out of the public repository.
# Include it in a Store build when present; source-only checkouts still work.
optional_private_modules = []
for private_module in ('_private_store_version', '_private_peer_badges'):
    if (root / 'application' / (private_module + '.py')).is_file():
        optional_private_modules.append('application.' + private_module)
# Python 3.15 stable-ABI extensions may require this compatibility DLL.
python3t = Path(sys.base_prefix) / 'abi3t-compat' / 'python3t.dll'
binaries = [(str(python3t), '.')] if python3t.is_file() else []

a = Analysis([str(root / 'ELDENRING_Tracker.py')], pathex=[str(root)],
             binaries=binaries, datas=datas, hiddenimports=['pystray._win32', 'pythoncom', 'pywintypes', 'winrt.runtime.interop'] + winrt_modules + optional_private_modules,
             hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='EldenRingTracker',
          console=os.environ.get('TRACKER_BUILD_CONSOLE') == '1', icon=str(root / 'static' / 'tracker-eye-ornament.ico'),
          version=str(root / 'file_version_info.txt'))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='EldenRingTracker')
