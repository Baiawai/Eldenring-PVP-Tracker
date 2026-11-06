# PyInstaller onedir build: only known, non-personal application resources.
from pathlib import Path
import os

root = Path(SPECPATH).parent
datas = [(str(root / name), name) for name in ('static', 'templates')]
datas += [(str(root / 'application' / name), 'application/' + name)
          for name in ('locales', 'geoip', 'steam_peers')]
datas += [(str(root / 'application' / 'steam_logo.png'), 'application')]

a = Analysis([str(root / 'ELDENRING_Tracker.py')], pathex=[str(root)],
             binaries=[], datas=datas, hiddenimports=['pystray._win32', 'pythoncom', 'pywintypes'],
             hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='EldenRingTracker',
          console=os.environ.get('TRACKER_BUILD_CONSOLE') == '1', icon=str(root / 'static' / 'tracker-eye.ico'))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='EldenRingTracker')
