"""Add local Steam player preferences to overlay cards without name matching."""
import re
import threading
import time

from application import player_tags, steam_friendships, tracker_overlay_data
from application.detection_history import read_steam_history

_lock = threading.Lock()
_preferences_cache = None
_relationships_cache = None
_CACHE_SECONDS = 10


def _preferences():
    global _preferences_cache
    now, revision = time.monotonic(), player_tags.revision()
    with _lock:
        if (_preferences_cache is None or _preferences_cache[0] != revision or
                now - _preferences_cache[1] >= _CACHE_SECONDS):
            _preferences_cache = (revision, now, player_tags.read_preferences(), player_tags.categories())
        return _preferences_cache[2], _preferences_cache[3]


def _relationships():
    global _relationships_cache
    now = time.monotonic()
    with _lock:
        if _relationships_cache is None or now - _relationships_cache[0] >= _CACHE_SECONDS:
            _relationships_cache = (now, steam_friendships.known_relationships(read_steam_history()))
        return _relationships_cache[1]


def annotate(cards, options, language):
    show_tags = options.get('show_player_tags', True) is True
    show_favourite = options.get('show_player_favourite', True) is True
    if not cards or not (show_tags or show_favourite):
        return
    preferences, categories = _preferences()
    relationships = _relationships() if show_tags and any(card.get('steam_friend') is None for card in cards) else {}
    translations, _ = tracker_overlay_data._translation(language)
    defaults = {'steam_friend':'Ami Steam', 'friend':'Ami', 'rival':'Rival', 'partner':'Partenaire'}
    for card in cards:
        sid = card.get('id')
        try:
            preference = preferences.get(player_tags.identity('steam', sid), {})
        except (ValueError, TypeError):
            continue
        card['favourite'] = show_favourite and preference.get('favourite') is True
        if not show_tags:
            continue
        selected = set(preference.get('categories', ()))
        friend = card.get('steam_friend')
        if friend is None:
            friend = relationships.get(sid)
        if friend is True:
            selected.add('steam_friend')
        tags = []
        for category in categories:
            key = category['id']
            if key not in selected:
                continue
            if category.get('builtin') or category.get('former_default'):
                label = translations.get('player_category_' + key, defaults.get(key, key))
            else:
                label = category.get('name', '')
            color = category.get('color', '')
            if isinstance(label, str) and label.strip() and isinstance(color, str) and re.fullmatch(r'#[0-9a-fA-F]{6}', color):
                tags.append({'name':label, 'color':color.lower()})
        card['tags'] = tags
