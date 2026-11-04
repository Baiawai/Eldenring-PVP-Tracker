"""Normalize and recognize translated game notification templates.

Catalog matches are converted into the tracker’s existing PvP event transitions.
Real-game OCR quality still depends on the selected language and image.
"""
import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

CATALOG = Path(__file__).with_name('locales') / 'network_messages.json'
PLACEHOLDER = re.compile(r'<\?([A-Za-z][A-Za-z0-9_]*)\?>')
# Thai game fonts use private-use glyph variants for these ordinary characters.
_THAI_GAME_GLYPHS = str.maketrans({'\uf712':'ป', '\uf716':'่', '\uf717':'้', '\uf722':'็', '\uf724':'้'})


def _normalize_with_offsets(text):
    chars, offsets = [], []
    for index, char in enumerate(text):
        char = char.translate(_THAI_GAME_GLYPHS)
        if char in '’‘ʼ':
            char = "'"
        for piece in unicodedata.normalize('NFKD', unicodedata.normalize('NFKC', char).casefold()):
            if unicodedata.combining(piece) or unicodedata.category(piece) == 'Cf':
                continue
            if piece.isspace():
                piece = '\n' if piece in '\r\n' else ' '
                if chars and chars[-1] == ' ':
                    continue
            chars.append(piece)
            offsets.append(index)
    return ''.join(chars), offsets


def _literal_pattern(text):
    normalized, _ = _normalize_with_offsets(text)
    # OCR may omit punctuation around otherwise distinctive words.
    chunks = []
    for char in normalized:
        if char.isspace():
            chunks.append(r'\s*')
        elif char in '.。…!！?？:：,，،؟':
            chunks.append(r'[\s.。!！?？:：,，،؟…]*')
        elif char in '()':
            chunks.append(r'\s*' + re.escape(char) + r'\s*')
        else:
            chunks.append(re.escape(char))
    return ''.join(chunks)


@lru_cache(maxsize=1)
def messages():
    return json.loads(CATALOG.read_text(encoding='utf-8'))


@lru_cache(maxsize=32)
def _patterns(language):
    result = []
    for identifier, template in messages().get(language, {}).items():
        parts, fields, previous = [], [], 0
        for match in PLACEHOLDER.finditer(template):
            parts.append(_literal_pattern(template[previous:match.start()]))
            field = match.group(1)
            group = 'value' + str(len(fields))
            fields.append((field, group))
            suffix = template[match.end():]
            if any(char.isalnum() for char in PLACEHOLDER.sub('', suffix)):
                parts.append(r'(?P<' + group + r'>[^\n]{1,80}?)')
            else:
                # Preserve punctuation inside a player name and constrain
                # the capture to the OCR line.
                parts.append(r'(?P<' + group + r'>[^\n]{1,80})')
            previous = match.end()
        parts.append(_literal_pattern(template[previous:]))
        pattern = ''.join(parts)
        if pattern:
            result.append((identifier, re.compile(pattern), fields))
    return result


def recognize(text, language):
    """Return matching message IDs and original player names from OCR text."""
    normalized, offsets = _normalize_with_offsets(text or '')
    if not offsets:
        return []
    result = []
    for identifier, pattern, fields in _patterns(language):
        match = pattern.search(normalized)
        if not match:
            continue
        values = {}
        for field, group in fields:
            start, end = match.span(group)
            values[field] = text[offsets[start]:offsets[end - 1] + 1].strip().rstrip('.。…!?！？，,:：،؟')
        result.append({'id': identifier, 'values': values, 'span': match.span()})
    return result

# A semantic event is intentionally separate from the game text and from UI
# translations. Several IDs are the same event in different network roles.
_EVENTS = {
    'ally_summoning': ('2300000',),
    'invasion_loading': ('2301200',),
    'arena_assembled': ('2311413',),
    'invasion_search_near': ('2331200',),
    'invasion_search_any': ('2331201',),
    'arena_waiting': ('2341413',),
    'ally_joined': ('2600000',),
    'defense_invaded': ('2600200','2600210','2602200','2602210','2602250','2602260'),
    'hunter_joined': ('2600304','2602304'),
    'invasion_started': ('2601200','2601210'),
    'hunter_summoning': ('2602354',),
    'invasion_victory': ('2611200','2611210'),
    'cooperator_died': ('2620000','2622000'),
    'invader_died': ('2620200','2620210','2622200','2622210'),
    'hunter_died': ('2620304','2622304'),
    'invasion_defeat': ('2621200','2621210'),
    'cooperator_left': ('2630000','2632000'),
    'hunter_left': ('2630304','2632304'),
    'returned_to_world': ('2631200','2631210'),
    'cooperator_dismissed': ('2640000','2642000'),
    'hunter_dismissed': ('2640304','2642304'),
    'connection_error': ('2701200',),
    'hunter_victory': ('2712200','2712210'),
    'arena_all_left': ('2760413',),
    'arena_started': tuple('arena:' + str(i) for i in range(88000,88007)),
    'arena_victory': ('arena:88050',),
    'arena_draw': ('arena:88051',),
    'arena_defeat': ('arena:88052',),
    'player_died': ('game:331305',),
    'inventory_limit': ('dialogue:334510','dialogue:334511','dialogue:334520'),
}
_EVENT_BY_ID = {identifier: event for event, ids in _EVENTS.items() for identifier in ids}


def classify(text, language):
    """Identify semantic game events without updating application state."""
    found, accepted = [], []
    catalog = messages().get(language, {})
    matches = recognize(text, language)
    matches.sort(key=lambda item: len(PLACEHOLDER.sub('', catalog[item['id']])), reverse=True)
    for match in matches:
        event = _EVENT_BY_ID.get(match['id'])
        if not event:
            continue
        start, end = match['span']
        if any(event == other and start < right and end > left for other, left, right in accepted):
            continue
        accepted.append((event, start, end))
        found.append({'event': event, 'values': match['values'], '_span': (start, end)})

    def overlaps(a, b):
        return a['_span'][0] < b['_span'][1] and b['_span'][0] < a['_span'][1]

    # The generic return-to-world message is contained in result and error
    # messages. A loading message can also be part of the invasion start.
    specific_results = {'invasion_victory', 'invasion_defeat', 'connection_error', 'hunter_victory'}
    found = [item for item in found if not (
        item['event'] == 'returned_to_world' and any(
            other['event'] in specific_results and overlaps(item, other) for other in found))]
    found = [item for item in found if not (
        item['event'] == 'player_died' and any(
            other['event'] == 'invasion_defeat' and overlaps(item, other) for other in found))]
    found = [item for item in found if not (
        item['event'] == 'invasion_loading' and any(
            other['event'] in ('invasion_started', 'invasion_search_near', 'invasion_search_any')
            and overlaps(item, other) for other in found))]
    found = [item for item in found if not (
        item['event'] in ('cooperator_left', 'hunter_left') and any(
            other['event'] == item['event'].replace('_left', '_dismissed')
            and overlaps(item, other) for other in found))]

    # Some localizations use the same text for summoning and arrival.
    ambiguous = []
    for joined in [item for item in found if item['event'] == 'hunter_joined']:
        for summoning in [item for item in found if item['event'] == 'hunter_summoning']:
            if overlaps(joined, summoning) and joined['values'] == summoning['values']:
                ambiguous.append((joined, summoning))
                break
    for joined, summoning in ambiguous:
        if joined in found and summoning in found:
            found.remove(joined)
            found.remove(summoning)
            found.append({'event':'hunter_observed', 'values':joined['values'], '_span':joined['_span']})
    return [{'event': item['event'], 'values': item['values']} for item in found]

def tracker_notifications(text, language):
    """Produce internal French compatibility messages for existing detectors.

    This adapter is deliberately side-effect free. It is not connected to the
    active tracker until language selection, persistence and UI are integrated.
    """
    result = []
    for item in classify(text, language):
        event, values = item['event'], item['values']
        name = values.get('joinName') or values.get('deadName') or values.get('leaveName') or ''
        host = values.get('hostName', '')
        inventory_item = values.get('itemName') or 'certains objets'
        variants = {
            'ally_summoning': "Invocation de l'allié…",
            'invasion_loading': "Invasion d'un autre monde…",
            'arena_assembled': 'Tous les combattants sont rassemblés.',
            'invasion_search_near': "Vous tentez d'envahir un autre monde… (Étendue : proches uniquement)",
            'invasion_search_any': "Vous tentez d'envahir un autre monde… (Étendue : proches/distants)",
            'arena_waiting': 'Veuillez attendre que tous les combattants soient rassemblés.',
            'ally_joined': 'Doigt crochu allié ' + name + ' invoqué.',
            'defense_invaded': 'Le Doigt sanglant ' + name + ' a envahi votre monde !',
            'hunter_joined': 'Chasseur ' + name + ' invoqué.',
            'hunter_summoning': 'Invocation du Chasseur ' + name + '.',
            'hunter_observed': 'Invocation du Chasseur ' + name + '.',
            'invasion_started': "Invasion d'un autre monde.\nTerrassez " + host + ', Hôte des Doigts !',
            'invasion_victory': 'Hôte des Doigts vaincu. Retour dans votre monde.',
            'cooperator_died': 'Le Doigt crochu ' + name + ' est mort.',
            'invader_died': 'Le Doigt sanglant ' + name + ' est mort.',
            'hunter_died': 'Le Chasseur ' + name + ' est mort.',
            'invasion_defeat': 'Vous avez péri. Retour dans votre monde.',
            'cooperator_left': 'Le Doigt crochu ' + name + ' est retourné dans son monde.',
            'hunter_left': 'Le Chasseur ' + name + ' est retourné dans son monde.',
            'returned_to_world': 'Retour dans votre monde…',
            'cooperator_dismissed': 'Le Doigt crochu ' + name + ' a été renvoyé dans son monde.',
            'hunter_dismissed': 'Le Chasseur ' + name + ' a été renvoyé dans son monde.',
            'connection_error': 'Une erreur de connexion est survenue. Retour dans votre monde…',
            'arena_all_left': 'Tous les combattants ont quitté le combat.',
            'arena_started': 'Début du combat.',
            'arena_victory': 'Vous remportez la victoire !',
            'arena_draw': "Le combat s'achève par une égalité.",
            'arena_defeat': 'Vous avez perdu.',
            'player_died': 'VOUS AVEZ PÉRI',
            'inventory_limit': "Impossible d'acquérir " + inventory_item + '.',
        }
        value = variants.get(event)
        # Never invent a name or falsely mark a hunter-mode objective as ours.
        if value and ((event != 'invasion_started' or host) and
                      (event not in {'ally_joined', 'defense_invaded', 'hunter_joined',
                                     'hunter_summoning', 'hunter_observed', 'cooperator_died',
                                     'invader_died', 'hunter_died', 'cooperator_left',
                                     'hunter_left', 'cooperator_dismissed', 'hunter_dismissed'} or name)):
            result.append(value)
    return list(dict.fromkeys(result))
