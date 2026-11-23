"""Read Elden Ring's selected Steam language without changing Steam files."""
from pathlib import Path
import re

APP_ID = '1245620'
STEAM_LANGUAGES = {
    'french': 'frafr', 'english': 'engus', 'german': 'deude',
    'italian': 'itait', 'spanish': 'spaes', 'latam': 'spaar',
    'latamspanish': 'spaar', 'brazilian': 'porbr', 'polish': 'polpl',
    'russian': 'rusru', 'japanese': 'jpnjp', 'koreana': 'korkr',
    'schinese': 'zhocn', 'tchinese': 'zhotw', 'thai': 'thath',
    'arabic': 'araae',
}

_TOKEN = re.compile(r'\s+|//[^\r\n]*|"((?:\\[\\"]|[^"\\]|\\[^\\"])*)"|([{}])')
_MAX_FILE_SIZE = 4 * 1024 * 1024


def _read_vdf(path):
    """Read bounded KeyValues data, returning None if it is malformed."""
    try:
        with path.open('rb') as source:
            data = source.read(_MAX_FILE_SIZE + 1)
        if len(data) > _MAX_FILE_SIZE:
            return None
        content = data.decode('utf-8-sig')
        tokens = []
        pos = 0
        while pos < len(content):
            match = _TOKEN.match(content, pos)
            if not match:
                return None
            pos = match.end()
            if match.group(1) is not None:
                tokens.append(('string', re.sub(r'\\([\\"])', r'\1', match.group(1))))
            elif match.group(2):
                tokens.append((match.group(2), match.group(2)))

        def parse(index, nested=False):
            result = {}
            while index < len(tokens):
                kind, key = tokens[index]
                if kind == '}':
                    if not nested:
                        raise ValueError('Unexpected closing brace')
                    return result, index + 1
                if kind != 'string' or index + 1 >= len(tokens):
                    raise ValueError('Invalid key')
                index += 1
                kind, value = tokens[index]
                if kind == '{':
                    value, index = parse(index + 1, True)
                elif kind == 'string':
                    index += 1
                else:
                    raise ValueError('Invalid value')
                key = key.lower()
                if key in result:
                    raise ValueError('Duplicate key')
                result[key] = value
            if nested:
                raise ValueError('Unclosed object')
            return result, index

        return parse(0)[0]
    except (OSError, UnicodeError, ValueError, RecursionError):
        return None


def _steam_root():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam') as key:
            path = winreg.QueryValueEx(key, 'SteamPath')[0]
        return Path(path) if isinstance(path, str) and path else None
    except (ImportError, OSError, ValueError):
        return None


def detect(steam_root=None):
    """Return a supported locale from the installed game's Steam manifest.

    None means Steam/the game is unavailable, the setting is absent or
    ambiguous, or the language is unsupported. No Steam file is modified.
    """
    root = Path(steam_root) if steam_root is not None else _steam_root()
    if root is None:
        return None
    libraries = [root]
    folders = _read_vdf(root / 'steamapps' / 'libraryfolders.vdf')
    if folders and isinstance(folders.get('libraryfolders'), dict):
        for key, entry in folders['libraryfolders'].items():
            if not key.isdigit():
                continue
            path = entry.get('path') if isinstance(entry, dict) else entry
            if isinstance(path, str) and path:
                libraries.append(Path(path))
    found = set()
    for library in libraries:
        manifest = _read_vdf(library / 'steamapps' / ('appmanifest_' + APP_ID + '.acf'))
        state = manifest.get('appstate') if isinstance(manifest, dict) else None
        if not isinstance(state, dict) or state.get('appid') != APP_ID:
            continue
        config = state.get('userconfig')
        language = config.get('language') if isinstance(config, dict) else None
        if isinstance(language, str):
            locale = STEAM_LANGUAGES.get(language.strip().lower())
            if locale:
                found.add(locale)
    return found.pop() if len(found) == 1 else None
