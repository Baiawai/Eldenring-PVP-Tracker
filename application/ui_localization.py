"""Local, offline translations for application-generated counter messages."""
import html
import json
import re
from functools import lru_cache
from pathlib import Path
from application.game_language import UI_TO_GAME
from application.locale_catalog import messages, _THAI_GAME_GLYPHS


def display_game_text(text):
    """Convert game-font glyph variants in a catalog template for the UI."""
    return text.translate(_THAI_GAME_GLYPHS)

@lru_cache(maxsize=1)
def packs():
    return json.loads((Path(__file__).with_name('locales') / 'ui_packs.json').read_text(encoding='utf-8'))


def localize_overlay_time(text, language):
    """Translate only a generated result-duration suffix for overlay display.

    History and the live browser translate their own display; their persisted
    canonical messages must retain the existing Time: marker.
    """
    label = packs().get(language, {}).get('modern', {}).get('time', 'Temps')
    suffix = r'(<br\s*/?>)\s*Time:\s*(?=(?:—|-?\d+\s*s)\s*(?:$|<))'
    return re.sub(suffix, lambda match: match.group(1) + ' ' + html.escape(label, quote=False) + ': ', text)


def localize_counter(text, language):
    if language == 'fra' or language not in packs():
        return text
    pack = packs()[language]
    modern = pack['modern']
    locale = UI_TO_GAME.get(language, 'engus')
    game = messages()[locale]
    ui_only = language not in UI_TO_GAME
    hunter_prefix = 'Son objectif accompli, le Chasseur '
    hunter_suffix = " s'en est retourné dans son monde."
    if text.startswith(hunter_prefix) and text.endswith(hunter_suffix):
        name = text[len(hunter_prefix):-len(hunter_suffix)]
        if name:
            template = html.escape(modern['hunter_objective_completed_message'], quote=False)
            return template.replace('{name}', name).replace('\n', '<br>')
    invasion_suffix = ' a envahi votre monde'
    if text.endswith(invasion_suffix) and len(text) > len(invasion_suffix):
        # The name is already escaped by the tracker; keep it escaped.
        value = text[:-len(invasion_suffix)]
        template = html.escape(modern['tracking_defending_against'], quote=False)
        return template.replace('{name}', value).replace('\n', '<br>')
    exact = {
        'Invocation de l’allié…': ('game', '2300000'),
        "Impossible d'invoquer l'allié.": ('game', '2490000'),
        "Invasion d'un autre monde…": ('game', '2301200'),
        'Retour dans votre monde · Combat sans résultat': ('modern', 'return_without_result'),
        'Une erreur de connexion est survenue.<br>Retour dans votre monde…': ('game', '2701200'),
    }
    if text in exact:
        kind, key = exact[text]
        ui_key = {
            '2300000': 'tracking_summoning_ally', '2490000': 'tracking_ally_summon_failed',
            '2301200': 'tracking_invading', '2701200': 'tracking_connection_return',
        }.get(key)
        value = modern[ui_key] if ui_only and kind == 'game' else display_game_text(game[key]) if kind == 'game' else modern[key]
        return html.escape(value, quote=False).replace('\n', '<br>')
    if text == 'Vous avez envahi un autre monde':
        # The second line of this game notification contains the host name.
        # When OCR cannot recover it, use only the complete introductory line.
        value = modern['tracking_invaded_world'] if ui_only else display_game_text(game['2601200'].split('\n', 1)[0])
        return html.escape(value, quote=False)
    mode_prefix = 'MODE : DUEL - '
    if text.startswith(mode_prefix):
        prefix = html.escape(modern['online_mode'], quote=False) + ' : ' + html.escape(modern['capture_duel'], quote=False) + ' - '
        return prefix + text[len(mode_prefix):]
    search_prefix = "Vous tentez d'envahir un autre monde"
    if text.startswith(search_prefix):
        if 'proches uniquement' in text:
            result = modern['tracking_search_near'] if ui_only else game['2331200']
        elif 'proches et distants' in text:
            result = modern['tracking_search_far'] if ui_only else game['2331201']
        else:
            result = modern['tracking_search_general'] if ui_only else re.split(r'\s*[(（]', game['2331200'], maxsplit=1)[0].strip()
        return html.escape(display_game_text(result), quote=False).replace('\n', '<br>')
    named = (("Vous avez envahi le monde de ", '2601200', 'hostName'),
             ('Monde envahi : combat contre ', '2600200', 'joinName'))
    for prefix, ident, field in named:
        if text.startswith(prefix):
            # The captured name was escaped by the caller; never unescape it.
            value = text[len(prefix):]
            if ui_only:
                key = 'tracking_invaded_host' if field == 'hostName' else 'tracking_defending_against'
                template = html.escape(modern[key], quote=False)
                return template.replace('{name}', value).replace('\n', '<br>')
            template = html.escape(display_game_text(game[ident]), quote=False)
            return template.replace(html.escape('<?' + field + '?>', quote=False), value).replace('\n', '<br>')
    if text.startswith('Impossible d’acquérir ') and '<br>' in text:
        first = text.split('<br>', 1)[0]
        item = first[len('Impossible d’acquérir '):].rstrip('.')
        if ui_only:
            translated = html.escape(modern['tracking_item_unavailable'], quote=False).replace('{item}', item).replace('\n', '<br>')
        else:
            template = html.escape(display_game_text(game['dialogue:334510']), quote=False)
            translated = template.replace(html.escape('<?itemName?>', quote=False), item).replace('\n', '<br>')
        return translated + '<br><span class="inventory-warning">' + html.escape(modern['inventory_warning'], quote=False) + '</span>'
    role_prefixes = {
        'Allié arrivé': 'summoned_ally', 'Allié reparti': 'ally_left',
        'Allié renvoyé dans son monde': 'ally_dismissed', 'Allié mort':'ally_died',
        'Allié adverse arrivé':'cooperator_summoned', 'Allié adverse reparti':'cooperator_left',
        'Allié adverse renvoyé dans son monde':'cooperator_dismissed', 'Allié adverse mort':'cooperator_died',
        'Coopérateur adverse arrivé':'cooperator_summoned', 'Coopérateur adverse reparti':'cooperator_left',
        'Coopérateur adverse renvoyé dans son monde':'cooperator_dismissed',
        'Coopérateur adverse mort':'cooperator_died', 'Chasseur arrivé':'hunter_arrived',
        'Chasseur en cours d’invocation':'hunter_summoning', 'Chasseur reparti':'hunter_left',
        'Objectif du chasseur accompli':'hunter_objective_completed',
        'Chasseur renvoyé dans son monde':'hunter_dismissed', 'Chasseur mort':'hunter_died',
        'Autre envahisseur arrivé':'coinvader_arrived', 'Autre envahisseur mort':'coinvader_died',
        'Envahisseur arrivé':'invasion_detected', 'Envahisseur mort':'invader_died',
    }
    for prefix, key in role_prefixes.items():
        marker = prefix + ' : '
        if text.startswith(marker):
            return html.escape(modern[key], quote=False) + ' : ' + text[len(marker):]
    return text
