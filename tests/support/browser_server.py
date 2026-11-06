"""Isolated UI test server; never starts a monitor or contacts the leaderboard."""
import os
import sys
import types
import webbrowser
from pathlib import Path

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))
webbrowser.open_new = lambda *args, **kwargs: True
module = types.ModuleType('__main__')
module.__file__ = str(root / 'ELDENRING_Tracker.py')
module.__dict__['__name__'] = 'isolated_browser_test'
sys.modules['__main__'] = module
exec(compile(Path(module.__file__).read_bytes(), module.__file__, 'exec'), module.__dict__)

from application import functions, multi, peer_tracking
functions.sync_leaderboard_data = lambda: False
multi.sync_leaderboard_data = lambda: False
multi.requests.post = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('Unexpected network request'))
peer_tracking.snapshot = lambda: {'status':'game_closed', 'ping_mode':'admin_required', 'peers':[], 'enabled':False}
# The test server uses a separate ephemeral port; production remains restricted.
module.is_allowed_request = lambda *args, **kwargs: True
from waitress import serve
serve(module.app, host='127.0.0.1', port=int(os.environ['TRACKER_TEST_PORT']), threads=4, _quiet=True)
