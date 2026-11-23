"""Isolated checks run by a built Store executable before release."""
from types import SimpleNamespace
from unittest.mock import patch


def ping_without_elevation(peer_tracking):
    """Exercise Store ping entry points without launching Steam or a helper."""
    if not peer_tracking.STORE_BUILD:
        return False
    cache = SimpleNamespace(update=lambda peers: peers)
    try:
        with patch.object(peer_tracking, 'enabled', return_value=True), \
             patch.object(peer_tracking, 'snapshot', return_value={}) as snapshot, \
             patch.object(peer_tracking.ctypes.windll.user32, 'FindWindowW', return_value=1), \
             patch.object(peer_tracking, '_elevated_stream', side_effect=AssertionError('unexpected elevation')) as elevated, \
             patch.object(peer_tracking.subprocess, 'Popen', side_effect=AssertionError('unexpected helper launch')) as process, \
             patch.object(peer_tracking.shell, 'ShellExecuteEx', side_effect=AssertionError('unexpected shell elevation')) as shell, \
             patch.object(peer_tracking, '_peer_cache', cache), \
             patch.object(peer_tracking, '_observer', None), \
             patch.object(peer_tracking, '_snapshot', {}), \
             patch.object(peer_tracking, '_ask_elevation', False), \
             patch.object(peer_tracking, '_auto_ping_pending', False), \
             patch.object(peer_tracking, '_process', None):
            automatic = peer_tracking.request_auto_ping()
            manual = peer_tracking.activate_ping()
            peer_tracking._publish('active', [{'id': '76561198000000001', 'ping': 42}], 'admin_required')
            return (automatic is True and manual is True and snapshot.call_count == 2
                    and not elevated.called and not process.called and not shell.called
                    and not peer_tracking._ask_elevation and not peer_tracking._auto_ping_pending
                    and peer_tracking._snapshot['ping_mode'] == 'steam_only'
                    and peer_tracking._snapshot['peers'][0]['ping'] == 42)
    except (AssertionError, AttributeError, KeyError, TypeError):
        return False
