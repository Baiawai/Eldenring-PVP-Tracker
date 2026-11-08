"""Local, offline translations for application-generated counter messages."""
import html
import json
import re
from functools import lru_cache
from pathlib import Path
from application.game_language import UI_TO_GAME
from application.locale_catalog import messages

@lru_cache(maxsize=1)
def packs():
    return json.loads((Path(__file__).with_name('locales') / 'ui_packs.json').read_text(encoding='utf-8'))


def localize_counter(text, language):
    if language == 'fra' or language not in packs():
        return text
    pack = packs()[language]
    modern = pack['modern']
    locale = UI_TO_GAME.get(language, 'engus')
    game = messages()[locale]
    exact = {
        'Invocation de l’allié…': ('game', '2300000'),
        "Impossible d'invoquer l'allié.": ('game', '2490000'),
        "Invasion d'un autre monde…": ('game', '2301200'),
        'Retour dans votre monde · Combat sans résultat': ('modern', 'return_without_result'),
        'Une erreur de connexion est survenue.<br>Retour dans votre monde…': ('game', '2701200'),
    }
    if text in exact:
        kind, key = exact[text]
        return html.escape((game if kind == 'game' else modern)[key], quote=False).replace('\n', '<br>')
    search_prefix = "Vous tentez d'envahir un autre monde"
    if text.startswith(search_prefix):
        if 'proches uniquement' in text:
            result = game['2331200']
        elif 'proches et distants' in text:
            result = game['2331201']
        else:
            result = re.split(r'\s*[(（]', game['2331200'], maxsplit=1)[0].strip()
        return html.escape(result, quote=False).replace('\n', '<br>')
    named = (("Vous avez envahi le monde de ", '2601200', 'hostName'),
             ('Monde envahi : combat contre ', '2600200', 'joinName'))
    for prefix, ident, field in named:
        if text.startswith(prefix):
            # The captured name was escaped by the caller; never unescape it.
            value = text[len(prefix):]
            template = html.escape(game[ident], quote=False)
            return template.replace(html.escape('<?' + field + '?>', quote=False), value).replace('\n', '<br>')
    if text.startswith('Impossible d’acquérir ') and '<br>' in text:
        first = text.split('<br>', 1)[0]
        item = first[len('Impossible d’acquérir '):].rstrip('.')
        template = html.escape(game['dialogue:334510'], quote=False)
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
        'Chasseur renvoyé dans son monde':'hunter_dismissed', 'Chasseur mort':'hunter_died',
        'Autre envahisseur arrivé':'coinvader_arrived', 'Autre envahisseur mort':'coinvader_died',
        'Envahisseur arrivé':'invasion_detected', 'Envahisseur mort':'invader_died',
    }
    for prefix, key in role_prefixes.items():
        marker = prefix + ' : '
        if text.startswith(marker):
            return html.escape(modern[key], quote=False) + ' : ' + text[len(marker):]
    return text
