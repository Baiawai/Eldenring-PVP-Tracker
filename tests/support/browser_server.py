"""Isolated UI test server; never starts a monitor or contacts the leaderboard."""
import os
import sys
import types
import webbrowser
from pathlib import Path

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))
from application import runtime_paths
test_images = Path(os.environ['APPDATA']) / 'test-runtime-images'
test_images.mkdir(parents=True, exist_ok=True)
runtime_paths.image_dir = lambda: test_images
webbrowser.open_new = lambda *args, **kwargs: True
module = types.ModuleType('__main__')
module.__file__ = str(root / 'ELDENRING_Tracker.py')
module.__dict__['__name__'] = 'isolated_browser_test'
sys.modules['__main__'] = module
exec(compile(Path(module.__file__).read_bytes(), module.__file__, 'exec'), module.__dict__)

from application import functions, multi, online_leaderboard, peer_tracking
peer_tracking.snapshot = lambda: {'status':'game_closed', 'ping_mode':'admin_required', 'peers':[], 'enabled':False}
def no_leaderboard_network(*args, **kwargs):
    raise RuntimeError('Leaderboard network is disabled in browser tests')
online_leaderboard._call = no_leaderboard_network
# The test server uses a separate ephemeral port; production remains restricted.
module.is_allowed_request = lambda *args, **kwargs: True
from waitress import serve
serve(module.app, host='127.0.0.1', port=int(os.environ['TRACKER_TEST_PORT']), threads=4, _quiet=True)
