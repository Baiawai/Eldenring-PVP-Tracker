"""Offline country lookup for public IP addresses (user-country)."""
import ipaddress
from functools import lru_cache
from pathlib import Path

try:
    import maxminddb
except ImportError:
    maxminddb = None

DATABASE = Path(__file__).with_name("geoip") / "user-country.mmdb"

@lru_cache(maxsize=1)
def _reader():
    if maxminddb is None:
        return None
    try:
        return maxminddb.open_database(str(DATABASE))
    except (OSError, ValueError):
        return None

@lru_cache(maxsize=8192)
def country_code(ip):
    if not isinstance(ip, str):
        return None
    try:
        address = ipaddress.ip_address(ip)
        if not address.is_global:
            return None
        reader = _reader()
        if reader is None:
            return None
        record = reader.get(str(address)) or {}
        code = (record.get("country") or {}).get("iso_code")
        return code.upper() if isinstance(code, str) and len(code) == 2 and code.isascii() and code.isalpha() else None
    except (ValueError, OSError, TypeError, KeyError):
        return None
