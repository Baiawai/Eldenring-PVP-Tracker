"""Exercise the frozen app without touching the user's tracker or opening a port."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parent.parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))
from application.version import APP_VERSION
exe = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else root / 'dist' / 'store' / 'EldenRingTracker' / 'EldenRingTracker.exe'
with tempfile.TemporaryDirectory(prefix='tracker-smoke-', dir=root / 'build') as tmp:
    env = os.environ.copy()
    env['APPDATA'] = tmp
    env['LOCALAPPDATA'] = tmp
    result = Path(tmp) / 'result.json'
    completed = subprocess.run([str(exe), '--distribution-smoke-test', str(result)], env=env, timeout=60)
    if not result.exists():
        raise SystemExit(f'No smoke-test result (exit code {completed.returncode}).')
    data = json.loads(result.read_text(encoding='utf-8'))
    print(json.dumps(data))
    if (completed.returncode or data.get('application_version') != APP_VERSION or
            not all(data.get(key) for key in ('interface', 'version_matches_interface', 'steam_ping_store_no_elevation', 'tesseract', 'optimized_ocr', 'store_mode', 'store_distribution_marker', 'legacy_leaderboard_disabled', 'steam_login_route', 'production_leaderboard', 'leaderboard_route', 'production_ignores_local_config', 'other_origin_blocked'))):
        raise SystemExit('Smoke test failed.')
