"""Pure layout for the in-game peer cards; no window, network or game access."""
import math

from application.overlay_country_names import country_name


def _number(value, maximum=60000):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return value if 0 <= value <= maximum else None


def _name(value, limit=100):
    return ' '.join(value.split())[:limit] if isinstance(value, str) else ''


def _duration(value):
    value = _number(value, 86400 * 365)
    if value is None:
        return None
    seconds = int(value)
    return f'{seconds // 3600:02}:{seconds // 60 % 60:02}:{seconds % 60:02}'


def cards(peer_snapshot, options, avatar_reader=None, language='eng'):
    """Copy only valid displayed data, keeping Steam and game identities separate."""
    if not options.get('show_peers', True) or not peer_snapshot.get('enabled', True):
        return []
    if peer_snapshot.get('status') != 'active':
        return []
    result = []
    for peer in (peer_snapshot.get('peers') or [])[:16]:
        if not isinstance(peer, dict):
            continue
        steam_id = peer.get('id')
        if not isinstance(steam_id, str) or len(steam_id) != 17 or not steam_id.isascii() or not steam_id.isdigit():
            continue
        avatar = None
        if options.get('show_avatars', True) and peer.get('avatar_available') and avatar_reader:
            try:
                avatar = avatar_reader(steam_id)
            except (ValueError, OSError):
                pass
        if not isinstance(avatar, bytes) or len(avatar) > 1024 * 1024:
            avatar = None
        role = peer.get('role')
        role = role if isinstance(role, str) and role in ('invader', 'hunter', 'ally', 'cooperator', 'duelist') else None
        country = peer.get('country_code')
        country = country if isinstance(country, str) and len(country) == 2 and country.isascii() and country.isalpha() and country.isupper() else None
        result.append({'id': steam_id, 'name': _name(peer.get('name')), 'role': role, 'country_code': country,
                       'country_name': country_name(country, language),
                       'ping': _number(peer.get('ping')),
                       'average_ping': _number(peer.get('average_ping')),
                       'jitter': _number(peer.get('jitter')),
                       'quality': _number(peer.get('quality'), 1),
                       'duration': _duration(peer.get('connected_seconds')),
                       'avatar': avatar})
    return result


def ping_color(ping, options):
    if ping is None:
        return options.get('text_color', '#c7c7c7')
    return options.get('ping_good_color', '#85cda4') if ping < 100 else options.get('ping_medium_color', '#e1c16e') if ping < 180 else options.get('ping_bad_color', '#de7777')
