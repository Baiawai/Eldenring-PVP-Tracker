"""Offline display names for countries in the tracker's supported UI languages.

The region names are generated from ICU/CLDR and bundled with the app; they
describe the estimated country, not the player's language or identity.
"""
from functools import lru_cache
import json
from pathlib import Path
import re


@lru_cache(maxsize=1)
def _catalog():
    try:
        with (Path(__file__).parent / 'locales' / 'overlay_country_names.json').open(encoding='utf-8') as source:
            data = json.load(source)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def country_name(code, language='eng'):
    """Return a localized name for a bundled country code, or None."""
    if not isinstance(code, str) or re.fullmatch(r'[A-Z]{2}', code) is None:
        return None
    catalog = _catalog()
    names = catalog.get(language, {}) if isinstance(language, str) else {}
    fallback = catalog.get('eng', {})
    value = (names.get(code) if isinstance(names, dict) else None) or (fallback.get(code) if isinstance(fallback, dict) else None)
    return value if isinstance(value, str) and value else None
