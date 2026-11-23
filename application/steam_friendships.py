"""Last known Steam friendship per Steam ID from local encounter history."""


def known_relationships(events):
    # History is returned newest first. A failed lookup is not a revocation.
    relationships = {}
    for event in events:
        steam = event.get('steam') or {}
        sid, value = steam.get('id'), steam.get('steam_friend')
        if isinstance(sid, str) and len(sid) == 17 and sid.isascii() and sid.isdigit() and type(value) is bool and sid not in relationships:
            relationships[sid] = value
    return relationships
