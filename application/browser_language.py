"""Choose a supported interface/game locale from browser language preferences."""
LANGUAGE_CODES = {
    'fr':'fra', 'en':'eng', 'de':'deu', 'it':'ita', 'pt':'por', 'pl':'pol',
    'ru':'rus', 'ja':'jap', 'ko':'kor', 'th':'tha', 'ar':'ara',
}

def browser_language(preferences):
    """Read (BCP 47 tag, quality) pairs, already ordered by preference."""
    for tag, quality in preferences:
        if not quality or not tag or tag == '*':
            continue
        parts = tag.replace('_', '-').lower().split('-')
        language = parts[0]
        if language == 'zh':
            return 'zht' if any(p in ('hant', 'tw', 'hk', 'mo') for p in parts[1:]) else 'chi'
        if language == 'es':
            region = next((p for p in parts[1:] if (len(p) == 2 and p.isalpha()) or p == '419'), '')
            return 'spaes' if region in ('', 'es') else 'spaar'
        if language in LANGUAGE_CODES:
            return LANGUAGE_CODES[language]
    return 'eng'
