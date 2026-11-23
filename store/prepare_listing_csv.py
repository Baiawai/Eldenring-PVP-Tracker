"""Prepare a separate, reviewable MSIX listing CSV; never contacts Microsoft."""
import argparse
import csv
import io
import json
import re
from io import BytesIO
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
DESCRIPTIONS = ROOT / 'store' / 'descriptions-fiche-1.0.10.0.md'
NOTES = ROOT / 'store' / 'notes-de-version-1.0.11.0.md'
# The draft headings use the region-specific labels shown in the review files.
# They are not necessarily the language codes of the existing Store listings.
LOCALES = (
    'fr-FR', 'en-US', 'de-DE', 'it-IT', 'es-ES', 'es-419', 'pt-BR', 'pl-PL',
    'ru-RU', 'ja-JP', 'ko-KR', 'zh-CN', 'zh-TW', 'th-TH', 'ar-SA', 'nl-NL',
    'tr-TR', 'uk-UA', 'cs-CZ', 'ro-RO', 'hu-HU', 'el-GR', 'id-ID', 'vi-VN',
    'hi-IN', 'sv-SE', 'da-DK', 'nb-NO', 'fi-FI', 'pt-PT',
)
# Match the exact language resources declared by create_manifest.py. Each
# entry names the corresponding text in the region-labelled draft files.
CANONICAL_TO_DRAFT = {
    'fr': 'fr-FR', 'en': 'en-US', 'de': 'de-DE', 'it': 'it-IT',
    'es-ES': 'es-ES', 'es-419': 'es-419', 'pt-BR': 'pt-BR', 'pl': 'pl-PL',
    'ru': 'ru-RU', 'ja': 'ja-JP', 'ko': 'ko-KR', 'zh-Hans': 'zh-CN',
    'zh-Hant': 'zh-TW', 'th': 'th-TH', 'ar': 'ar-SA', 'nl': 'nl-NL',
    'tr': 'tr-TR', 'uk': 'uk-UA', 'cs': 'cs-CZ', 'ro': 'ro-RO',
    'hu': 'hu-HU', 'el': 'el-GR', 'id': 'id-ID', 'vi': 'vi-VN',
    'hi': 'hi-IN', 'sv': 'sv-SE', 'da': 'da-DK', 'nb': 'nb-NO',
    'fi': 'fi-FI', 'pt-PT': 'pt-PT',
}
# Screenshot directories use the app's internal language identifiers.
CANONICAL_TO_IMAGES = {
    'fr': 'fra', 'en': 'eng', 'de': 'deu', 'it': 'ita', 'es-ES': 'spaes',
    'es-419': 'spaar', 'pt-BR': 'por', 'pl': 'pol', 'ru': 'rus', 'ja': 'jap',
    'ko': 'kor', 'zh-Hans': 'chi', 'zh-Hant': 'zht', 'th': 'tha', 'ar': 'ara',
    'nl': 'nld', 'tr': 'tur', 'uk': 'ukr', 'cs': 'ces', 'ro': 'ron',
    'hu': 'hun', 'el': 'ell', 'id': 'ind', 'vi': 'vie', 'hi': 'hin',
    'sv': 'swe', 'da': 'dan', 'nb': 'nor', 'fi': 'fin', 'pt-PT': 'ptpt',
}
SCREENSHOTS = ('01-guide.png', '02-overlay-settings.png', '03-language-settings.png', '04-statistics.png')
_HEADING = re.compile(r'^## [^\n]* \(([^()\n]+)\)[ \t]*$', re.MULTILINE)


def _load_drafts(path, limit):
    content = Path(path).read_text(encoding='utf-8')
    matches = list(_HEADING.finditer(content))
    drafts = {}
    for i, match in enumerate(matches):
        code = match.group(1).casefold()
        if code in drafts:
            raise ValueError('Duplicate locale in draft: ' + match.group(1))
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        value = content[match.end():end].strip()
        if not value or len(value.encode('utf-16-le')) // 2 > limit:
            raise ValueError('Draft is empty or exceeds its Store limit: ' + match.group(1))
        if re.search(r'\{[^{}]+\}|<\?[^>]+\?>', value):
            raise ValueError('Unresolved placeholder in draft: ' + match.group(1))
        drafts[code] = value
    if set(drafts) != {locale.casefold() for locale in LOCALES}:
        raise ValueError('Drafts must contain exactly the 30 expected locales')
    return drafts


def _prepare_rows(source, descriptions, notes):
    raw = Path(source).read_bytes()
    has_bom = raw.startswith(b'\xef\xbb\xbf')
    text = raw.decode('utf-8-sig')
    try:
        rows = list(csv.reader(io.StringIO(text, newline=''), strict=True))
    except csv.Error as exc:
        raise ValueError('Invalid CSV export: ' + str(exc)) from exc
    if not rows or len(rows[0]) < 4:
        raise ValueError('The CSV header is incomplete')
    header = rows[0]
    canonical = [column.strip().casefold() for column in header[:4]]
    if (canonical[:2] != ['field', 'id'] or canonical[2] not in ('type', 'type (type)')
            or canonical[3] != 'default'):
        raise ValueError('Expected Field, ID, Type, default as the first columns')
    # The locale code "id" means Indonesian; unlike the technical "ID"
    # column, it is valid after the first four columns. Compare language
    # headers independently so they can never overwrite field metadata.
    present_locales = [column.strip().casefold() for column in header[4:]]
    if (any(not column for column in present_locales) or
            len(present_locales) != len(set(present_locales)) or
            any(column in ('field', 'type', 'default') for column in present_locales)):
        raise ValueError('The CSV has empty or duplicate column headers')
    if any(len(row) != len(header) for row in rows[1:]):
        raise ValueError('The CSV has incomplete or irregular rows')
    targets = {}
    for row in rows[1:]:
        field = row[0].strip().casefold()
        if field in ('description', 'releasenotes'):
            if field in targets:
                raise ValueError('The CSV contains an ambiguous duplicate target row: ' + row[0])
            if (not row[1].strip().isascii() or not row[1].strip().isdigit() or
                    row[2].strip().casefold() not in ('text', 'texte')):
                raise ValueError('A target row has an absent or unexpected ID or Type: ' + row[0])
            targets[field] = row
    if set(targets) != {'description', 'releasenotes'}:
        raise ValueError('The export must contain Description and ReleaseNotes rows')
    if targets['description'][1].strip() == targets['releasenotes'][1].strip():
        raise ValueError('The two target rows have an ambiguous duplicate ID')

    # Fail closed if application languages change without an explicit choice
    # of the corresponding copy in both drafts.
    packs = json.loads((ROOT / 'application/locales/ui_packs.json').read_text(encoding='utf-8'))
    manifest_codes = {'fr', *(pack['html_lang'] for pack in packs.values())}
    if {code.casefold() for code in manifest_codes} != {code.casefold() for code in CANONICAL_TO_DRAFT}:
        raise ValueError('Store locale mapping does not match the application manifest')
    if {code.casefold() for code in CANONICAL_TO_DRAFT.values()} != {code.casefold() for code in LOCALES}:
        raise ValueError('Store locale mapping does not match the review drafts')
    content = {'description': _load_drafts(descriptions, 10000),
               'releasenotes': _load_drafts(notes, 1500)}
    new_locales = [locale for locale in CANONICAL_TO_DRAFT if locale.casefold() not in present_locales]
    header.extend(new_locales)
    for row in rows[1:]:
        row.extend([''] * len(new_locales))
    positions = {name.strip().casefold(): index for index, name in enumerate(header[4:], start=4)}
    for field, row in targets.items():
        for locale, draft in CANONICAL_TO_DRAFT.items():
            value = content[field][draft.casefold()]
            row[positions[locale.casefold()]] = value
            # Only touch an explicitly corresponding regional draft code when
            # already present in the export. Never create those extra listings.
            if draft.casefold() in present_locales:
                row[positions[draft.casefold()]] = value

    return rows, has_bom, new_locales, present_locales, positions


def _csv_bytes(rows, has_bom):
    buffer = io.StringIO(newline='')
    writer = csv.writer(buffer, lineterminator='\r\n')
    writer.writerows(rows)
    output = buffer.getvalue().encode('utf-8')
    if has_bom:
        output = b'\xef\xbb\xbf' + output
    return output


def prepare_listing(source, destination, *, descriptions=DESCRIPTIONS, notes=NOTES):
    """Build one separate UTF-8 file; preserve all existing non-target cells."""
    source, destination = Path(source), Path(destination)
    if source.resolve() == destination.resolve():
        raise ValueError('The destination must differ from the input export')
    if destination.exists() or destination.is_symlink():
        raise FileExistsError('The destination already exists')
    rows, has_bom, new_locales, _, _ = _prepare_rows(source, descriptions, notes)
    output = _csv_bytes(rows, has_bom)
    with destination.open('xb') as stream:
        stream.write(output)
    return {'languages': len(LOCALES), 'added_columns': new_locales}


def _bundle_fields(rows):
    """Find only unambiguous listing fields in a genuine-style export."""
    wanted = {'title', *(f'desktopscreenshot{i}' for i in range(1, 5))}
    fields = {}
    for row in rows[1:]:
        field = row[0].strip().casefold()
        if field not in wanted:
            continue
        if field in fields:
            raise ValueError('The export contains an ambiguous duplicate field: ' + row[0])
        if not row[1].strip().isascii() or not row[1].strip().isdigit():
            raise ValueError('A bundle field has an invalid ID: ' + row[0])
        field_type = row[2].strip().casefold().replace('’', "'")
        allowed = (('text', 'texte') if field == 'title' else (
            'relative path', 'relative path (or url to file in partner center)',
            "chemin d'accès relatif (ou url à consigner dans l'espace partenaires)",
        ))
        if field_type not in allowed:
            raise ValueError('A bundle field has an unexpected Type: ' + row[0])
        fields[field] = row
    if set(fields) != wanted:
        raise ValueError('The export must include Title and DesktopScreenshot1 through 4')
    ids = [row[1].strip() for row in rows[1:]
           if row[0].strip().casefold() in wanted | {'description', 'releasenotes'}]
    if len(ids) != len(set(ids)):
        raise ValueError('The target fields have ambiguous duplicate IDs')
    return fields


def _read_screenshot(root, code, filename):
    image_path = (root / code / filename).resolve()
    try:
        image_path.relative_to(root)
    except ValueError as exc:
        raise ValueError('A screenshot points outside the screenshot directory') from exc
    if image_path.stat().st_size > 50_000_000:
        raise ValueError('Screenshot exceeds 50 MB: ' + code + '/' + filename)
    raw = image_path.read_bytes()
    if len(raw) > 50_000_000:
        raise ValueError('Screenshot exceeds 50 MB: ' + code + '/' + filename)
    try:
        with Image.open(BytesIO(raw)) as image:
            if image.format != 'PNG' or image.width < 1366 or image.height < 768:
                raise ValueError('Screenshot must be a PNG of at least 1366 × 768: ' + code + '/' + filename)
            image.verify()
    except OSError as exc:
        raise ValueError('Invalid PNG screenshot: ' + code + '/' + filename) from exc
    return raw


def prepare_listing_bundle(source, destination, *, title, screenshots,
                           descriptions=DESCRIPTIONS, notes=NOTES):
    """Create a new review-only import folder, never overwriting any file."""
    source, destination = Path(source), Path(destination)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError('The bundle directory already exists')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', destination.name):
        raise ValueError('The bundle directory name must contain only ASCII letters, digits, dot, underscore or hyphen')
    if not isinstance(title, str) or not title.strip() or len(title) > 256 or any(ord(c) < 32 for c in title):
        raise ValueError('An explicit, valid product title is required')
    if not screenshots:
        raise ValueError('A screenshot directory must be supplied')
    screenshot_root = Path(screenshots).resolve(strict=True)
    if not screenshot_root.is_dir():
        raise ValueError('The screenshot directory does not exist')
    packs = json.loads((ROOT / 'application/locales/ui_packs.json').read_text(encoding='utf-8'))
    expected_images = {'fr': 'fra', **{pack['html_lang']: code for code, pack in packs.items()}}
    if CANONICAL_TO_IMAGES != expected_images:
        raise ValueError('The screenshot mapping does not match the application language codes')
    rows, has_bom, new_locales, present_locales, positions = _prepare_rows(source, descriptions, notes)
    fields = _bundle_fields(rows)
    copies = {}
    title_cells = image_cells = 0
    for locale, draft in CANONICAL_TO_DRAFT.items():
        targets = [locale.casefold()]
        if draft.casefold() in present_locales and draft.casefold() not in targets:
            targets.append(draft.casefold())
        code = CANONICAL_TO_IMAGES[locale]
        for target in targets:
            index = positions[target]
            if not fields['title'][index].strip():
                fields['title'][index] = title.strip()
                title_cells += 1
            for number, filename in enumerate(SCREENSHOTS, start=1):
                row = fields[f'desktopscreenshot{number}']
                if row[index].strip():
                    continue
                relative = Path('images') / code / filename
                if relative not in copies:
                    copies[relative] = _read_screenshot(screenshot_root, code, filename)
                row[index] = '/'.join((destination.name, *relative.parts))
                image_cells += 1
    # All content has been validated before creating the new directory.
    # Existing exports, prior bundles and screenshots are never overwritten.
    destination.mkdir(exist_ok=False)
    for relative, data in copies.items():
        output = destination / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open('xb') as stream:
            stream.write(data)
    with (destination / 'listing.csv').open('xb') as stream:
        stream.write(_csv_bytes(rows, has_bom))
    return {'languages': len(LOCALES), 'added_columns': new_locales,
            'titles_filled': title_cells, 'screenshots_filled': image_cells,
            'images_copied': len(copies)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('export', type=Path, help='Original CSV exported from Partner Center')
    parser.add_argument('output', type=Path, help='New file, or a new folder with --bundle')
    parser.add_argument('--bundle', action='store_true', help='Create an import folder with missing titles and screenshots')
    parser.add_argument('--title', help='Exact product title to use only where missing (required with --bundle)')
    parser.add_argument('--screenshots', type=Path, help='Root of localized screenshot folders (required with --bundle)')
    args = parser.parse_args()
    try:
        if args.bundle:
            result = prepare_listing_bundle(args.export, args.output, title=args.title, screenshots=args.screenshots)
        else:
            if args.title is not None or args.screenshots is not None:
                raise ValueError('--title and --screenshots require --bundle')
            result = prepare_listing(args.export, args.output)
    except (OSError, UnicodeError, ValueError) as exc:
        parser.exit(1, 'Unable to prepare listing: ' + str(exc) + '\n')
    print('Prepared a separate draft with ' + str(result['languages']) + ' language columns.')
    if args.bundle:
        print('Filled ' + str(result['titles_filled']) + ' titles and ' + str(result['screenshots_filled']) + ' screenshot fields; copied ' + str(result['images_copied']) + ' PNG files.')
    print('Review the entire file, titles and screenshots in Partner Center before any import.')


if __name__ == '__main__':
    main()
