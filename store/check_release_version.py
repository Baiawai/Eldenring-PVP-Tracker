"""Validate Store package and Windows executable versions before a build."""
import argparse
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from application.version import APP_VERSION


def validate_store_version(value):
    """Require four numeric components in the Store's supported range."""
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]+(?:\.[0-9]+){3}', value):
        raise ValueError('Store version must contain four numeric components')
    parts = tuple(int(part) for part in value.split('.'))
    if parts[0] == 0 or any(part > 65535 for part in parts) or parts[3] != 0:
        raise ValueError('Store version requires a nonzero major, components <= 65535 and revision 0')
    return parts


def validate_release(version, app_version, metadata):
    parts = validate_store_version(version)
    if version != app_version:
        raise ValueError('Package version does not match application/version.py')
    for field in ('filevers', 'prodvers'):
        matches = re.findall(r'(?m)^\s*' + field + r'\s*=\s*\(([^)]*)\)', metadata)
        if len(matches) != 1 or not re.fullmatch(r'\s*\d+\s*,\s*\d+\s*,\s*\d+\s*,\s*\d+\s*,?\s*', matches[0]):
            raise ValueError('Invalid executable version tuple: ' + field)
        if tuple(int(part) for part in re.findall(r'\d+', matches[0])) != parts:
            raise ValueError('Executable version does not match package: ' + field)
    for field in ('FileVersion', 'ProductVersion'):
        pattern = r'StringStruct\(\s*u?[\'"]' + field + r'[\'"]\s*,\s*u?[\'"]([^\'"]+)[\'"]\s*\)'
        matches = re.findall(pattern, metadata)
        if matches != [version]:
            raise ValueError('Executable version does not match package: ' + field)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--version', required=True)
    args = parser.parse_args()
    try:
        metadata = (ROOT / 'file_version_info.txt').read_text(encoding='utf-8')
        validate_release(args.version, APP_VERSION, metadata)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print('Store package and executable versions match application/version.py.')


if __name__ == '__main__':
    main()
