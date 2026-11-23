"""Optional non-interactive Windows overlay. This module never starts it on import.

The provider returns a short sequence of display lines, or a dictionary with
``lines`` and boolean ``capture_active``. It must not block. No tracker,
network or persistent-data access is performed by this module.
"""
import ctypes
import logging
import json
import sys
import threading
import unicodedata
import uuid
import re
import math
from io import BytesIO
import textwrap
from functools import lru_cache
from ctypes import wintypes

from PIL import Image, ImageDraw
from application.runtime_paths import RESOURCE_DIR

import win32api
import win32con
import win32gui

_LOG = logging.getLogger(__name__)
_WDA_EXCLUDEFROMCAPTURE = 0x11
_WIDTH = 380
_LINE_HEIGHT = 26
_MARGIN = 12
_MAX_LINES = 22
_INDICATOR_SIZE = 10
_INDICATOR_GAP = 8
_DEFAULT_OPTIONS = {'background_opacity': 50, 'background_color': '#1a1a1a',
                    'text_color': '#c7c7c7', 'text_opacity': 50, 'font_size': 15, 'show_status': True,
                    'position': 'top_right', 'border_radius': 4, 'border_color': '#cab486',
                    'width_percent': 80, 'show_overlay_border': False}
_POSITIONS = ('top_left', 'top_right', 'bottom_left', 'bottom_right')
_SCENE_BOOL = ('show_mode', 'show_peers', 'show_event', 'show_avatars', 'show_player_name',
               'show_steam_id', 'show_ping', 'show_ping_average', 'show_jitter', 'show_quality',
               'show_duration', 'show_player_count', 'show_player_stats', 'show_country', 'show_role', 'show_tracker_user',
               'show_player_tags', 'show_player_favourite')
_SCENE_FALSE_DEFAULTS = frozenset(('show_steam_id', 'show_jitter', 'show_ping_average',
                                   'show_quality', 'show_player_count'))
_SCENE_NUMBERS = {'avatar_size': (24, 96, 48), 'card_spacing': (0, 24, 8), 'card_size': (48, 160, 60)}
_SCENE_COLORS = {'ping_good_color': '#85cda4', 'ping_medium_color': '#e1c16e', 'ping_bad_color': '#de7777'}
_FLAG_ATLAS = RESOURCE_DIR.parent / 'static' / 'overlay-country-flags.png'
_FLAG_COLUMNS, _FLAG_CELL_WIDTH, _FLAG_CELL_HEIGHT = 16, 48, 36


@lru_cache(maxsize=1)
def _flag_atlas():
    """Load the bundled, offline flag atlas once; tolerate a missing asset."""
    try:
        with Image.open(_FLAG_ATLAS) as source:
            codes = json.loads(source.info['country_codes'])
            image = source.convert('RGBA')
        if (not isinstance(codes, list) or not codes or
                any(not isinstance(code, str) or re.fullmatch(r'[A-Z]{2}', code) is None for code in codes) or
                len(codes) != len(set(codes)) or image.width != _FLAG_COLUMNS * _FLAG_CELL_WIDTH or
                image.height != math.ceil(len(codes) / _FLAG_COLUMNS) * _FLAG_CELL_HEIGHT):
            return None
        return image, {code: index for index, code in enumerate(codes)}
    except (OSError, ValueError, TypeError, KeyError, Image.DecompressionBombError):
        return None


@lru_cache(maxsize=256)
def _country_flag(code, width):
    """Return a small cached image, never reading untrusted paths or the network."""
    if not isinstance(code, str) or re.fullmatch(r'[A-Z]{2}', code) is None:
        return None
    atlas = _flag_atlas()
    index = atlas[1].get(code) if atlas else None
    if index is None:
        return None
    x = (index % _FLAG_COLUMNS) * _FLAG_CELL_WIDTH
    y = (index // _FLAG_COLUMNS) * _FLAG_CELL_HEIGHT
    return atlas[0].crop((x, y, x + _FLAG_CELL_WIDTH, y + _FLAG_CELL_HEIGHT)).resize(
        (width, max(1, round(width * _FLAG_CELL_HEIGHT / _FLAG_CELL_WIDTH))), Image.Resampling.LANCZOS)


def _options(value):
    """Validate presentation options independently from persisted settings."""
    source = value if isinstance(value, dict) else {}
    result = dict(_DEFAULT_OPTIONS)
    for key, low, high in (('background_opacity', 0, 100), ('text_opacity', 0, 100),
                           ('font_size', 12, 32), ('border_radius', 0, 30), ('width_percent', 60, 100)):
        number = source.get(key)
        if isinstance(number, int) and not isinstance(number, bool) and low <= number <= high:
            result[key] = number
    for key in ('background_color', 'text_color', 'border_color'):
        color = source.get(key)
        if isinstance(color, str) and re.fullmatch(r'#[0-9a-fA-F]{6}', color):
            result[key] = color.lower()
    for key in ('show_status', 'show_overlay_border'):
        if isinstance(source.get(key), bool):
            result[key] = source[key]
    if source.get('position') in _POSITIONS:
        result['position'] = source['position']
    return result


def _scene_options(value):
    source = value if isinstance(value, dict) else {}
    result = _options(source)
    for key in _SCENE_BOOL:
        result[key] = source[key] if isinstance(source.get(key), bool) else key not in _SCENE_FALSE_DEFAULTS
    for key, (low, high, default) in _SCENE_NUMBERS.items():
        item = source.get(key)
        result[key] = item if type(item) is int and low <= item <= high else default
    for key, default in _SCENE_COLORS.items():
        item = source.get(key)
        result[key] = item.lower() if isinstance(item, str) and re.fullmatch(r'#[0-9a-fA-F]{6}', item) else default
    return result


def _lines(value):
    """Bound the amount of third-party text painted into the overlay."""
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (tuple, list)):
        return ()
    return tuple(str(line).replace('\r', ' ').replace('\n', ' ')[:160]
                 for line in value[:_MAX_LINES] if line is not None)


def _presentation(value):
    """Return display lines and capture state; retain legacy list providers."""
    if isinstance(value, dict):
        return _lines(value.get('lines')), value.get('capture_active') is True, _options(value.get('options'))
    return _lines(value), True, _options(None)


def _fit_lines(lines, monitor, font_size=18):
    """Bound the window vertically and show how many lines could not fit."""
    height = max(1, monitor[3] - monitor[1])
    capacity = max(1, (height - 2 * _MARGIN) // (font_size + 8))
    if len(lines) <= capacity:
        return lines
    if capacity == 1:
        return ('… (+' + str(len(lines)) + ')',)
    if capacity == 2:
        return (lines[0], '… (+' + str(len(lines) - 1) + ')')
    tail_count = min(3, capacity - 2)
    head_count = capacity - 1 - tail_count
    hidden_count = len(lines) - head_count - tail_count
    return lines[:head_count] + ('… (+' + str(hidden_count) + ')',) + lines[-tail_count:]


def _position(monitor, width, height, position):
    left, top, right, bottom = monitor
    margin_x = min(_MARGIN, max(0, (right - left - width) // 2))
    margin_y = min(_MARGIN, max(0, (bottom - top - height) // 2))
    x = left + margin_x if position.endswith('_left') else right - width - margin_x
    y = bottom - height - margin_y if position.startswith('bottom_') else top + margin_y
    return x, y, width, height


def _bounds(monitor, line_count, font_size=18, position='top_right', width_percent=100):
    left, top, right, bottom = monitor
    available_width = max(1, right - left)
    available_height = max(1, bottom - top)
    width = min(max(1, round(_WIDTH * font_size / 18 * width_percent / 100)), available_width)
    height = min(_MARGIN * 2 + max(1, line_count) * (font_size + 8), available_height)
    return _position(monitor, width, height, position)


def _text_flags(text):
    flags = (win32con.DT_SINGLELINE | win32con.DT_VCENTER |
             win32con.DT_END_ELLIPSIS | win32con.DT_NOPREFIX)
    # Use the first strong character to choose the direction for each line.
    for char in text:
        direction = unicodedata.bidirectional(char)
        if direction in ('R', 'AL'):
            return flags | win32con.DT_RIGHT | win32con.DT_RTLREADING
        if direction == 'L':
            break
    return flags | win32con.DT_LEFT


class _BitmapInfoHeader(ctypes.Structure):
    _fields_ = [('biSize', wintypes.DWORD), ('biWidth', wintypes.LONG),
                ('biHeight', wintypes.LONG), ('biPlanes', wintypes.WORD),
                ('biBitCount', wintypes.WORD), ('biCompression', wintypes.DWORD),
                ('biSizeImage', wintypes.DWORD), ('biXPelsPerMeter', wintypes.LONG),
                ('biYPelsPerMeter', wintypes.LONG), ('biClrUsed', wintypes.DWORD),
                ('biClrImportant', wintypes.DWORD)]


class _BitmapInfo(ctypes.Structure):
    _fields_ = [('bmiHeader', _BitmapInfoHeader), ('bmiColors', wintypes.DWORD * 3)]


class _BlendFunction(ctypes.Structure):
    _fields_ = [('BlendOp', ctypes.c_ubyte), ('BlendFlags', ctypes.c_ubyte),
                ('SourceConstantAlpha', ctypes.c_ubyte), ('AlphaFormat', ctypes.c_ubyte)]


def _rgb(value):
    return tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))


def _surface_color(background, accent, strength):
    """Tint a user's chosen background without replacing their color."""
    return tuple(round(base * (1 - strength) + tint * strength)
                 for base, tint in zip(background, accent))


def _composite_text(image, mask, color, options):
    """Composite GDI's antialiased coverage at the chosen text opacity."""
    opacity = options['text_opacity']
    if opacity != 100:
        mask = mask.point([round(value * opacity / 100) for value in range(256)])
    layer = Image.new('RGBA', image.size, _rgb(color) + (255,))
    layer.putalpha(mask)
    image.alpha_composite(layer)


def _compose(mask, options, capture_active):
    """Make premultiplied BGRA pixels with separate background and text alpha."""
    alpha = round(options['background_opacity'] * 255 / 100)
    image = Image.new('RGBA', mask.size, _rgb(options['background_color']) + (alpha,))
    _composite_text(image, mask, options['text_color'], options)
    if options['show_status']:
        draw = ImageDraw.Draw(image)
        line_height = options['font_size'] + 8
        top = _MARGIN + (line_height - _INDICATOR_SIZE) // 2
        color = (92, 218, 133, 255) if capture_active else (239, 100, 100, 255)
        draw.ellipse((_MARGIN, top, _MARGIN + _INDICATOR_SIZE - 1,
                      top + _INDICATOR_SIZE - 1), fill=color)
    return image.convert('RGBa').tobytes('raw', 'BGRa')


def _draw_mask(dc, width, height, lines, options):
    """Use Windows text shaping and font fallback to render a grayscale mask."""
    win32gui.FillRect(dc, (0, 0, width, height), win32gui.GetStockObject(win32con.BLACK_BRUSH))
    font = win32gui.LOGFONT()
    font.lfFaceName = 'Segoe UI'
    font.lfHeight = -options['font_size']
    font.lfQuality = 4  # ANTIALIASED_QUALITY, without coloured ClearType pixels.
    font_handle = win32gui.CreateFontIndirect(font)
    old_font = None
    try:
        old_font = win32gui.SelectObject(dc, font_handle)
        win32gui.SetBkMode(dc, win32con.TRANSPARENT)
        win32gui.SetTextColor(dc, win32api.RGB(255, 255, 255))
        for index, line in enumerate(lines):
            top = _MARGIN + index * (options['font_size'] + 8)
            left = _MARGIN + (_INDICATOR_SIZE + _INDICATOR_GAP if index == 0 and options['show_status'] else 0)
            win32gui.DrawText(dc, line, -1, (left, top, max(left, width - _MARGIN),
                                           top + options['font_size'] + 8), _text_flags(line))
    finally:
        if old_font:
            win32gui.SelectObject(dc, old_font)
        win32gui.DeleteObject(font_handle)


@lru_cache(maxsize=512)
def _measure_text(value, font_size):
    """Measure metric labels with the same GDI font used for painting."""
    dc = win32gui.GetDC(0)
    handle = old = None
    try:
        font = win32gui.LOGFONT()
        font.lfFaceName, font.lfHeight, font.lfQuality = 'Segoe UI', -font_size, 4
        handle = win32gui.CreateFontIndirect(font)
        old = win32gui.SelectObject(dc, handle)
        return win32gui.GetTextExtentPoint32(dc, value)[0]
    finally:
        if old:
            win32gui.SelectObject(dc, old)
        if handle:
            win32gui.DeleteObject(handle)
        if dc:
            win32gui.ReleaseDC(0, dc)


def _wrap_measured(value, width, font_size, first_width=None):
    """Break long labels at word boundaries, falling back to characters for CJK."""
    value = ' '.join(str(value).split())
    if not value:
        return []
    result = []
    while value and len(result) < 4:
        available = first_width if not result and first_width is not None else width
        if _measure_text(value, font_size) <= available:
            result.append(value)
            value = ''
            break
        low, high = 1, len(value)
        while low < high:
            mid = (low + high + 1) // 2
            if _measure_text(value[:mid], font_size) <= available:
                low = mid
            else:
                high = mid - 1
        cut = max(1, low)
        boundary = value.rfind(' ', 0, cut + 1)
        if boundary > 0:
            cut = boundary
        result.append(value[:cut].strip())
        value = value[cut:].strip()
    if value and len(result) == 4:
        result[-1] = _ellipsize(result[-1], width, font_size)
    return result


def _ellipsize(value, width, font_size):
    """Make the truncation indicator fit the available measured width."""
    value = value.rstrip()
    while value and _measure_text(value + '…', font_size) > width:
        value = value[:-1].rstrip()
    return value + '…'


def _tag_row(tags, width, font, fallback_color):
    """Keep tags on one line; summarize any that cannot fit in the card."""
    valid = []
    for tag in tags:
        if not isinstance(tag, dict) or not isinstance(tag.get('name'), str):
            continue
        name = ' '.join(tag['name'].split())[:50]
        if not name:
            continue
        color = tag.get('color')
        if not isinstance(color, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
            color = fallback_color
        valid.append((name, color))
    if width < 12:
        return []
    items, used = [], 0
    for name, color in valid:
        label = name if _measure_text(name, font) <= width - 10 else _ellipsize(name, max(1, width - 10), font)
        size = min(width, _measure_text(label, font) + 10)
        if used + (4 if items else 0) + size > width:
            break
        used += (4 if items else 0) + size
        items.append((label, color, size))
    if len(items) < len(valid):
        while True:
            label = '+' + str(len(valid) - len(items))
            size = _measure_text(label, font) + 10
            if used + (4 if items else 0) + size <= width:
                items.append((label, fallback_color, size))
                break
            if not items:
                break
            used -= items.pop()[2] + (4 if len(items) else 0)
    return items


def _scene_plan(view, options, monitor):
    """Build bounded cards with only data and fields supplied by the tracker."""
    labels = view.get('labels') if isinstance(view.get('labels'), dict) else {}
    label = lambda key, fallback: str(labels.get(key) or fallback)
    font = options['font_size']
    line = font + 7
    available_width = max(1, monitor[2] - monitor[0])
    available_height = max(1, monitor[3] - monitor[1])
    width = min(max(1, round(460 * font / 18 * options['width_percent'] / 100)), available_width)
    max_height = max(1, available_height - min(_MARGIN, max(0, available_height - 1)))
    left, right = _MARGIN, max(_MARGIN + 1, width - _MARGIN)
    entries, card_shapes, quality_indicators, badges, stars = [], [], [], [], []
    y = _MARGIN

    def text(value, x1, y1, x2, color=None):
        value = ' '.join(str(value or '').split())[:160]
        if value and y1 + line <= max_height:
            entries.append((value, (x1, y1, max(x1 + 1, x2), y1 + line), color or options['text_color']))

    if options['show_status']:
        status_lines = _wrap_measured(str(view.get('status') or '—'), max(1, right - left - 18), font)
        for value in status_lines:
            text(value, left + 18, y, right)
            y += line
        status_y = y - len(status_lines) * line + (line - _INDICATOR_SIZE) // 2
    else:
        status_y = None
    if options['show_mode']:
        for value in _wrap_measured(label('mode', 'Mode') + ' : ' + str(view.get('mode') or '—'), max(1, right - left), font):
            text(value, left, y, right)
            y += line
    if options['show_player_count']:
        count = view.get('player_count')
        count = count if type(count) is int and 0 <= count <= 16 else '—'
        for value in _wrap_measured(label('player_count', 'Players') + ' : ' + str(count), max(1, right - left), font):
            text(value, left, y, right)
            y += line
    raw_event = str(view.get('event') or label('no_event', '—')) if options['show_event'] else ''
    event_lines = _wrap_measured(raw_event, max(1, right - left), font) if raw_event else []
    if len(event_lines) > 2:
        event_lines = event_lines[:2]
        event_lines[-1] = _ellipsize(event_lines[-1], max(1, right - left), font)
    # Give the divider breathing room on both sides when it separates content.
    divider_spacing = 8 if y > _MARGIN and (options['show_peers'] or event_lines) else 0
    header_y = y + divider_spacing
    y = header_y + divider_spacing + (1 if divider_spacing else 0)
    footer_height = len(event_lines) * line + (_MARGIN if event_lines else 0)
    cards = view.get('cards') if options['show_peers'] and isinstance(view.get('cards'), list) else []
    cards = cards[:16]
    card_rows = []
    for card in cards:
        if not isinstance(card, dict):
            continue
        rows = []
        inner_width = max(1, right - left - 16)
        avatar_size = min(options['avatar_size'], inner_width) if options['show_avatars'] else 0
        country = card.get('country_code')
        country_name = card.get('country_name')
        country_name = ' '.join(country_name.split())[:160] if isinstance(country_name, str) else ''
        flag_width = min(24, max(12, round(font * 1.3)))
        show_country = bool(options['show_country'] and country_name and isinstance(country, str)
                            and re.fullmatch(r'[A-Z]{2}', country))
        flag = _country_flag(country, flag_width) if show_country else None
        country_text_width = inner_width - (flag.width + 6 if flag else 0)
        show_country = show_country and country_text_width >= _measure_text('…', font)
        if not show_country:
            flag = None
        # A large avatar leaves too little horizontal room at narrow widths.
        # Stack it above the text rather than overlap or lose the Steam ID.
        avatar_above = bool(avatar_size and inner_width - avatar_size - 10 < max(100, font * 9))
        content_width = max(1, inner_width - (avatar_size + 10 if avatar_size and not avatar_above else 0))
        gap = max(10, font // 2)
        raw_name, steam_id = card.get('name'), card.get('id')
        name = (str(raw_name) if raw_name and raw_name != steam_id else label('unknown_name', 'Unidentified')) if options['show_player_name'] else ''
        favourite = options['show_player_favourite'] and card.get('favourite') is True
        star_size = min(line - 2, max(font + 2, round(font * 1.2))) if favourite else 0
        star_space = star_size + 4 if favourite else 0
        ping = card.get('ping')
        ping = ping if isinstance(ping, (int, float)) and not isinstance(ping, bool) and math.isfinite(ping) and 0 <= ping <= 60000 else None
        ping_text = (f'{math.floor(ping + .5)} ms' if ping is not None else '—') if options['show_ping'] else ''
        ping_color = options['text_color'] if ping is None else options['ping_good_color'] if ping < 100 else options['ping_medium_color'] if ping < 180 else options['ping_bad_color']
        ping_width = _measure_text(ping_text, font) if ping_text else 0
        name_width = content_width - ping_width - gap - star_space
        ping_row_index = None
        if name and ping_text and name_width >= _measure_text('…', font):
            name_lines = _wrap_measured(name, content_width, font, first_width=name_width)
            ping_row_index = len(rows)
            rows.append((name_lines[0], ping_text, ping_color))
            rows.extend((piece, '', None) for piece in name_lines[1:])
        else:
            rows.extend((piece, '', None) for piece in _wrap_measured(name, content_width, font, first_width=max(1, content_width - star_space)))
            if ping_text:
                ping_row_index = len(rows)
                rows.append(('', ping_text, ping_color))
        if favourite and not rows:
            rows.append(('', '', None))
        role = card.get('role')
        role_fallbacks = {'ally': 'Ally', 'cooperator': 'Enemy ally', 'hunter': 'Hunter',
                          'invader': 'Invader', 'duelist': 'Duelist'}
        if options['show_role'] and isinstance(role, str) and role in role_fallbacks:
            rows.extend((piece, '', None) for piece in
                        _wrap_measured(label('role_' + role, role_fallbacks[role]), content_width, font))
        tracker_start = len(rows)
        if options['show_tracker_user'] and card.get('tracker_member') is True:
            rows.extend((piece, '', None) for piece in
                        _wrap_measured(label('tracker_user', 'Tracker user'), max(1, content_width - 10), font))
        tracker_end = len(rows)
        tags = card.get('tags') if options['show_player_tags'] and isinstance(card.get('tags'), list) else []
        tag_items = _tag_row(tags, inner_width, font, options['text_color'])
        if options['show_steam_id']:
            rows.extend((piece, '', None) for piece in _wrap_measured('SteamID : ' + str(card.get('id') or '—'), content_width, font))
        details = []
        if options['show_duration']:
            details.append(label('duration', 'Connection') + ' : ' + str(card.get('duration') or '—'))
        if options['show_ping_average']:
            avg = card.get('average_ping')
            avg = str(math.floor(avg + .5)) + ' ms' if isinstance(avg, (int, float)) and not isinstance(avg, bool) and math.isfinite(avg) and 0 <= avg <= 60000 else '—'
            details.append(label('average_ping', 'Average ping') + ' : ' + avg)
        if options['show_jitter']:
            jitter = card.get('jitter')
            jitter = str(math.floor(jitter + .5)) + ' ms' if isinstance(jitter, (int, float)) and not isinstance(jitter, bool) and math.isfinite(jitter) and 0 <= jitter <= 60000 else '—'
            details.append(label('jitter', 'Ping variation') + ' : ' + jitter)
        quality_text = None
        quality_color = None
        if options['show_quality']:
            quality = card.get('quality')
            if isinstance(quality, (int, float)) and not isinstance(quality, bool) and math.isfinite(quality) and 0 <= quality <= 1:
                quality_text = label('quality', 'Connection quality') + ' : ' + str(math.floor(quality * 100 + .5)) + ' %'
                quality_color = '#82d7a1' if quality >= .9 else '#e6be72' if quality >= .7 else '#e07878'
            else:
                quality_text = label('quality_unavailable', 'Connection quality unavailable')
                quality_color = '#9a9a92'
        trailing = []
        if options['show_player_stats']:
            encounters = card.get('encounters')
            value = str(encounters) if type(encounters) is int and 0 <= encounters <= 9007199254740991 else '—'
            trailing.append(label('encounters', 'Encounters') + ' : ' + value)
        if not rows and not details and quality_text is None and not trailing and not avatar_size and not show_country and not tag_items:
            continue
        for value in details:
            rows.extend((piece, '', None) for piece in _wrap_measured(value, content_width, font))
        quality_start = len(rows)
        quality_indent = 12 if content_width > 12 else 0
        if quality_text is not None:
            rows.extend((piece, '', None) for piece in _wrap_measured(quality_text, max(1, content_width - quality_indent), font))
        quality_end = len(rows)
        for value in trailing:
            rows.extend((piece, '', None) for piece in _wrap_measured(value, content_width, font))
        text_offset = avatar_size + 8 if avatar_above else 0
        content_height = max(avatar_size, text_offset + len(rows) * line if rows else 0)
        country_gap = 4 if content_height and show_country else 0
        country_height = max(line, flag.height if flag else 0) if show_country else 0
        tag_gap = 5 if tag_items and (content_height or show_country) else 0
        tag_height = line + 2 if tag_items else 0
        height = max(options['card_size'], 16 + content_height + country_gap + country_height + tag_gap + tag_height)
        card_rows.append((card, rows, height, avatar_size, avatar_above, flag, text_offset, ping_row_index,
                          quality_start, quality_end, quality_color, quality_indent, tracker_start, tracker_end,
                          country_name, show_country, content_height, country_gap, country_height, tag_items, tag_height, star_size, star_space))

    spacing = options['card_spacing']
    if options['show_peers'] and not cards:
        text(view.get('peer_status') or '—', left, y, right)
        y += line
    total = len(card_rows)
    displayed = 0
    for (card, rows, height, avatar_size, avatar_above, flag, text_offset, ping_row_index,
         quality_start, quality_end, quality_color, quality_indent, tracker_start, tracker_end,
         country_name, show_country, content_height, country_gap, country_height, tag_items, tag_height, star_size, star_space) in card_rows:
        more = displayed + 1 < total
        reserve = footer_height + (line if more else 0) + _MARGIN
        if y + height + reserve > max_height:
            break
        rect = (left, y, right, y + height)
        flag_position = None
        if show_country:
            country_top = y + 8 + content_height + country_gap
            if flag is not None:
                flag_position = (flag, (left + 8, country_top + (country_height - flag.height) // 2))
            country_x = left + 8 + (flag.width + 6 if flag else 0)
            country_right = max(country_x + 1, right - 8)
            available = country_right - country_x
            value = country_name if _measure_text(country_name, font) <= available else _ellipsize(country_name, available, font)
            text(value, country_x, country_top + (country_height - line) // 2, country_right)
        card_shapes.append((rect, card.get('avatar'), avatar_size, card.get('role'), flag_position))
        x = left + 8 + (avatar_size + 10 if avatar_size and not avatar_above else 0)
        inner_right = max(x + 2, right - 8)
        if star_size:
            stars.append((x, y + 8 + text_offset + (line - star_size) // 2, star_size))
        for index, (first, second, second_color) in enumerate(rows):
            row_y = y + 8 + text_offset + index * line
            if tracker_start <= index < tracker_end:
                badge_right = min(inner_right, x + _measure_text(first, font) + 10)
                badges.append(((x, row_y, badge_right, row_y + line), '#d4af37'))
                text(first, x + 5, row_y, max(x + 6, badge_right - 5), '#d4af37')
                continue
            if quality_start <= index < quality_end:
                if index == quality_start and quality_indent:
                    quality_indicators.append((x, row_y + (line - 7) // 2, quality_color))
                text(first, x + quality_indent, row_y, inner_right)
                continue
            if index == ping_row_index:
                ping_left = max(x, inner_right - _measure_text(second, font))
                name_x = x + (star_space if index == 0 else 0)
                text(first, name_x, row_y, max(name_x + 1, ping_left - max(10, font // 2)))
                text(second, ping_left, row_y, inner_right, second_color)
                continue
            split = x + max(1, (inner_right - x) // 2)
            gap = max(10, font // 2)
            text(first, x + (star_space if index == 0 else 0), row_y, split - gap // 2 if second else inner_right)
            if second:
                text(second, split + (gap + 1) // 2, row_y, inner_right, second_color)
        tag_x, tag_y = left + 8, y + height - 8 - tag_height
        for value, color, badge_width in tag_items:
            badge_rect = (tag_x, tag_y, tag_x + badge_width, tag_y + tag_height)
            badges.append((badge_rect, color))
            text(value, tag_x + 5, tag_y + 1, tag_x + badge_width - 5, color)
            tag_x += badge_width + 4
        y += height + spacing
        displayed += 1
    hidden = total - displayed
    if hidden:
        text('… (+' + str(hidden) + ')', left, y, right)
        y += line
    if event_lines:
        y += 4
        for value in event_lines:
            text(value, left, y, right)
            y += line
    height = min(max_height, max(1, y + _MARGIN - (spacing if displayed and not hidden and not event_lines else 0)))
    bounds = _position(monitor, width, height, options['position'])
    return {'bounds': bounds, 'entries': entries, 'cards': card_shapes, 'quality_indicators': quality_indicators, 'badges':badges, 'stars':stars,
            'status_y': status_y, 'header_y': header_y, 'visible_cards': displayed,
            'hidden_cards': hidden}


def _draw_entries(dc, width, height, entries, options):
    win32gui.FillRect(dc, (0, 0, width, height), win32gui.GetStockObject(win32con.BLACK_BRUSH))
    font = win32gui.LOGFONT()
    font.lfFaceName, font.lfHeight, font.lfQuality = 'Segoe UI', -options['font_size'], 4
    handle = win32gui.CreateFontIndirect(font)
    old = None
    try:
        old = win32gui.SelectObject(dc, handle)
        win32gui.SetBkMode(dc, win32con.TRANSPARENT)
        win32gui.SetTextColor(dc, win32api.RGB(255, 255, 255))
        for value, rect, _color in entries:
            win32gui.DrawText(dc, value, -1, rect, _text_flags(value))
    finally:
        if old:
            win32gui.SelectObject(dc, old)
        win32gui.DeleteObject(handle)


def _scene_base(plan, options, capture_active):
    """Create decorative surfaces; the user's opacity affects only the background."""
    width, height = plan['bounds'][2:]
    alpha = round(options['background_opacity'] * 255 / 100)
    image = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    border = _rgb(options['border_color'])
    radius = options['border_radius']
    draw.rounded_rectangle((0, 0, max(0, width - 1), max(0, height - 1)), radius=radius,
                           fill=_rgb(options['background_color']) + (alpha,),
                           outline=border + (round(alpha * .45),) if options['show_overlay_border'] else None,
                           width=1)
    divider = min(height - 1, plan['header_y'])
    if divider > _MARGIN:
        draw.line((_MARGIN, divider, max(_MARGIN, width - _MARGIN), divider),
                  fill=border + (round(alpha * .42),), width=1)
    if plan['status_y'] is not None:
        top = plan['status_y']
        color = (92, 218, 133, 255) if capture_active else (239, 100, 100, 255)
        draw.ellipse((_MARGIN, top, _MARGIN + 9, top + 9), fill=color)
    background = _rgb(options['background_color'])
    avatar_color = _surface_color(background, (12, 10, 8), .35)
    for rect, avatar, size, role, flag in plan['cards']:
        # Use stronger red/blue tints so roles remain distinguishable through
        # the chosen transparency. Friendly and unknown roles stay bronze.
        if role == 'invader':
            card_color = _surface_color(background, (170, 45, 40), .35)
        elif role == 'hunter':
            card_color = _surface_color(background, (40, 75, 170), .35)
        else:
            card_color = _surface_color(background, (130, 99, 59), .15)
        draw.rounded_rectangle(rect, radius=radius, fill=card_color + (round(alpha * .86),),
                               outline=border + (round(alpha * .38),), width=1)
        if not size:
            if flag is not None:
                image.alpha_composite(*flag)
            continue
        x, y = rect[0] + 8, rect[1] + 8
        image_data = None
        if isinstance(avatar, bytes) and len(avatar) <= 1024 * 1024:
            try:
                with Image.open(BytesIO(avatar)) as source:
                    if source.format == 'PNG' and 0 < source.width <= 1024 and 0 < source.height <= 1024:
                        image_data = source.convert('RGBA').resize((size, size), Image.Resampling.LANCZOS)
            except (OSError, ValueError, Image.DecompressionBombError):
                pass
        if image_data is not None:
            mask = Image.new('L', (size, size), 0)
            ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1), radius=max(2, size // 8), fill=255)
            image.paste(image_data, (x, y), mask)
        else:
            draw.rounded_rectangle((x, y, x + size, y + size), radius=max(2, size // 8),
                                   fill=avatar_color + (round(alpha * .95),),
                                   outline=border + (round(alpha * .5),))
            color = (174, 153, 112, 255)
            draw.ellipse((x + size * .32, y + size * .15, x + size * .68, y + size * .51), fill=color)
            draw.ellipse((x + size * .17, y + size * .50, x + size * .83, y + size * .95), fill=color)
        if flag is not None:
            image.alpha_composite(*flag)
    if plan.get('quality_indicators'):
        markers = Image.new('RGBA', image.size, (0, 0, 0, 0))
        marker_draw = ImageDraw.Draw(markers)
        marker_alpha = round(options['text_opacity'] * 255 / 100)
        for left, top, color in plan['quality_indicators']:
            marker_draw.ellipse((left, top, left + 6, top + 6), fill=_rgb(color) + (marker_alpha,))
        image.alpha_composite(markers)
    if plan.get('badges') or plan.get('stars'):
        foreground = Image.new('RGBA', image.size, (0, 0, 0, 0))
        foreground_draw = ImageDraw.Draw(foreground)
        foreground_alpha = round(options['text_opacity'] * 255 / 100)
        for rect, color in plan.get('badges', ()):
            foreground_draw.rectangle(rect, outline=_rgb(color) + (foreground_alpha,), width=1)
        for x, y, size in plan.get('stars', ()):
            center_x, center_y = x + size / 2, y + size / 2
            points = []
            for index in range(10):
                angle = -math.pi / 2 + index * math.pi / 5
                radius = size * (.48 if index % 2 == 0 else .21)
                points.append((round(center_x + radius * math.cos(angle)), round(center_y + radius * math.sin(angle))))
            foreground_draw.polygon(points, fill=(215, 185, 112, foreground_alpha))
        image.alpha_composite(foreground)
    return image


def _render_scene_layer(hwnd, plan, capture_active, options):
    """Draw text with Windows font fallback and submit premultiplied pixels."""
    x, y, width, height = plan['bounds']
    image = _scene_base(plan, options, capture_active)
    screen = win32gui.GetDC(0)
    memory = bitmap = old_bitmap = None
    try:
        memory = win32gui.CreateCompatibleDC(screen)
        info = _BitmapInfo()
        info.bmiHeader.biSize = ctypes.sizeof(_BitmapInfoHeader)
        info.bmiHeader.biWidth, info.bmiHeader.biHeight = width, -height
        info.bmiHeader.biPlanes, info.bmiHeader.biBitCount = 1, 32
        pointer = ctypes.c_void_p()
        create = ctypes.windll.gdi32.CreateDIBSection
        create.argtypes = [ctypes.c_void_p, ctypes.POINTER(_BitmapInfo), wintypes.UINT,
                           ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p, wintypes.DWORD]
        create.restype = ctypes.c_void_p
        bitmap = create(screen, ctypes.byref(info), 0, ctypes.byref(pointer), None, 0)
        if not bitmap or not pointer.value:
            raise OSError('CreateDIBSection failed')
        old_bitmap = win32gui.SelectObject(memory, bitmap)
        colors = {entry[2] for entry in plan['entries']}
        for color in colors:
            _draw_entries(memory, width, height, [entry for entry in plan['entries'] if entry[2] == color], options)
            ctypes.windll.gdi32.GdiFlush()
            raw = ctypes.string_at(pointer.value, width * height * 4)
            mask = Image.frombytes('RGBA', (width, height), raw, 'raw', 'BGRA').getchannel('R')
            _composite_text(image, mask, color, options)
        pixels = image.convert('RGBa').tobytes('raw', 'BGRa')
        ctypes.memmove(pointer.value, pixels, len(pixels))
        dest, source = wintypes.POINT(x, y), wintypes.POINT(0, 0)
        size, blend = wintypes.SIZE(width, height), _BlendFunction(0, 0, 255, 1)
        update = ctypes.windll.user32.UpdateLayeredWindow
        update.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(wintypes.POINT),
                           ctypes.POINTER(wintypes.SIZE), ctypes.c_void_p, ctypes.POINTER(wintypes.POINT),
                           wintypes.DWORD, ctypes.POINTER(_BlendFunction), wintypes.DWORD]
        update.restype = wintypes.BOOL
        if not update(hwnd, screen, ctypes.byref(dest), ctypes.byref(size), memory,
                      ctypes.byref(source), 0, ctypes.byref(blend), 2):
            raise OSError('UpdateLayeredWindow failed')
    finally:
        if old_bitmap:
            win32gui.SelectObject(memory, old_bitmap)
        if bitmap:
            win32gui.DeleteObject(bitmap)
        if memory:
            win32gui.DeleteDC(memory)
        if screen:
            win32gui.ReleaseDC(0, screen)


def _render_layer(hwnd, bounds, lines, capture_active, options):
    """Submit a premultiplied-alpha window without changing the foreground."""
    x, y, width, height = bounds
    screen = win32gui.GetDC(0)
    memory = bitmap = old_bitmap = None
    try:
        memory = win32gui.CreateCompatibleDC(screen)
        info = _BitmapInfo()
        info.bmiHeader.biSize = ctypes.sizeof(_BitmapInfoHeader)
        info.bmiHeader.biWidth, info.bmiHeader.biHeight = width, -height
        info.bmiHeader.biPlanes, info.bmiHeader.biBitCount = 1, 32
        pointer = ctypes.c_void_p()
        create = ctypes.windll.gdi32.CreateDIBSection
        create.argtypes = [ctypes.c_void_p, ctypes.POINTER(_BitmapInfo), wintypes.UINT,
                           ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p, wintypes.DWORD]
        create.restype = ctypes.c_void_p
        bitmap = create(screen, ctypes.byref(info), 0, ctypes.byref(pointer), None, 0)
        if not bitmap or not pointer.value:
            raise OSError('CreateDIBSection failed')
        old_bitmap = win32gui.SelectObject(memory, bitmap)
        _draw_mask(memory, width, height, lines, options)
        ctypes.windll.gdi32.GdiFlush()
        data = ctypes.string_at(pointer.value, width * height * 4)
        mask = Image.frombytes('RGBA', (width, height), data, 'raw', 'BGRA').getchannel('R')
        pixels = _compose(mask, options, capture_active)
        ctypes.memmove(pointer.value, pixels, len(pixels))
        dest = wintypes.POINT(x, y)
        source = wintypes.POINT(0, 0)
        size = wintypes.SIZE(width, height)
        blend = _BlendFunction(0, 0, 255, 1)  # AC_SRC_OVER, AC_SRC_ALPHA
        update = ctypes.windll.user32.UpdateLayeredWindow
        update.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(wintypes.POINT),
                           ctypes.POINTER(wintypes.SIZE), ctypes.c_void_p, ctypes.POINTER(wintypes.POINT),
                           wintypes.DWORD, ctypes.POINTER(_BlendFunction), wintypes.DWORD]
        update.restype = wintypes.BOOL
        if not update(hwnd, screen, ctypes.byref(dest), ctypes.byref(size), memory,
                      ctypes.byref(source), 0, ctypes.byref(blend), 2):
            raise OSError('UpdateLayeredWindow failed')
    finally:
        if old_bitmap:
            win32gui.SelectObject(memory, old_bitmap)
        if bitmap:
            win32gui.DeleteObject(bitmap)
        if memory:
            win32gui.DeleteDC(memory)
        if screen:
            win32gui.ReleaseDC(0, screen)


def _monitor_rect(game_window):
    """Prefer the game monitor; use the primary monitor as a safe fallback."""
    try:
        hwnd = game_window() if game_window else win32gui.FindWindow(None, 'ELDEN RING™')
        if hwnd and win32gui.IsWindow(hwnd):
            monitor = win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONEAREST)
            return tuple(win32api.GetMonitorInfo(monitor)['Monitor'])
    except Exception:
        pass
    monitor = win32api.MonitorFromPoint((0, 0), win32con.MONITOR_DEFAULTTOPRIMARY)
    return tuple(win32api.GetMonitorInfo(monitor)['Monitor'])


def _exclude_from_capture(hwnd):
    """Fail closed on older Windows, API failure or unavailable composition."""
    try:
        version = sys.getwindowsversion()
        if version.major < 10 or version.build < 19041:
            return False
        user32 = ctypes.windll.user32
        set_affinity = user32.SetWindowDisplayAffinity
        set_affinity.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        set_affinity.restype = ctypes.c_int
        if not set_affinity(hwnd, _WDA_EXCLUDEFROMCAPTURE):
            return False
        affinity = ctypes.c_uint32()
        get_affinity = user32.GetWindowDisplayAffinity
        get_affinity.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
        get_affinity.restype = ctypes.c_int
        return bool(get_affinity(hwnd, ctypes.byref(affinity)) and
                    affinity.value == _WDA_EXCLUDEFROMCAPTURE)
    except (AttributeError, OSError, TypeError, ValueError):
        return False


class OverlayWindow:
    """A click-through, non-activating window updated on its own daemon thread."""

    def __init__(self, provider, game_window=None, interval=0.5):
        if not callable(provider):
            raise TypeError('provider must be callable')
        if game_window is not None and not callable(game_window):
            raise TypeError('game_window must be callable or None')
        if interval <= 0:
            raise ValueError('interval must be positive')
        self._provider = provider
        self._game_window = game_window
        self._interval = max(0.1, float(interval))
        self._lock = threading.Lock()
        self._thread = None
        self._stop = None
        self._content = ()
        self._capture_active = True
        self._options = _options(None)
        self._scene = None
        self._error = None

    @property
    def error(self):
        """Return a short error code, or None if no failure has occurred."""
        return self._error

    def start(self):
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return False
            self._stop = threading.Event()
            self._error = None
            thread = threading.Thread(target=self._run, args=(self._stop,),
                                      name='tracker-overlay', daemon=True)
            self._thread = thread
            try:
                thread.start()
            except Exception:
                self._thread = None
                self._stop = None
                raise
            return True

    def stop(self, timeout=2.0):
        with self._lock:
            thread, stop = self._thread, self._stop
            if stop is not None:
                stop.set()
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=max(0, timeout))
        return thread is None or not thread.is_alive()

    def _window_proc(self, hwnd, message, wparam, lparam):
        if message == win32con.WM_PAINT:
            # A layered window can receive an internal WM_PAINT without an
            # update region. ValidateRect alone does not clear that request,
            # so PumpWaitingMessages can spin forever before the first frame.
            try:
                _dc, paint = win32gui.BeginPaint(hwnd)
                win32gui.EndPaint(hwnd, paint)
            except Exception:
                self._error = 'window_error'
                _LOG.exception('Unable to validate tracker overlay paint')
                if self._stop is not None:
                    self._stop.set()
                # Do not let another internal WM_PAINT keep the message pump
                # busy forever after a failure in the callback.
                try:
                    win32gui.PostQuitMessage(0)
                except Exception:
                    _LOG.exception('Unable to stop tracker overlay message pump')
            return 0
        if message == win32con.WM_ERASEBKGND:
            return 1
        return win32gui.DefWindowProc(hwnd, message, wparam, lparam)

    def _run(self, stop):
        hwnd = None
        registered = False
        class_name = 'TrackerOverlay_' + uuid.uuid4().hex
        instance = None
        try:
            instance = win32api.GetModuleHandle(None)
            window_class = win32gui.WNDCLASS()
            window_class.hInstance = instance
            window_class.lpszClassName = class_name
            window_class.lpfnWndProc = self._window_proc
            win32gui.RegisterClass(window_class)
            registered = True
            style = (win32con.WS_EX_LAYERED | win32con.WS_EX_TRANSPARENT |
                     win32con.WS_EX_NOACTIVATE | win32con.WS_EX_TOOLWINDOW |
                     win32con.WS_EX_TOPMOST)
            hwnd = win32gui.CreateWindowEx(style, class_name, '', win32con.WS_POPUP,
                                           0, 0, 1, 1, 0, 0, instance, None)
            if not _exclude_from_capture(hwnd):
                self._error = 'capture_exclusion_unavailable'
                return
            previous_bounds = None
            planned_scene = planned_options = planned_monitor = plan = None
            visible = False
            while not stop.is_set():
                win32gui.PumpWaitingMessages()
                if self._error:
                    break
                try:
                    provider_value = self._provider()
                    content, capture_active, options = _presentation(provider_value)
                    monitor = _monitor_rect(self._game_window)
                    scene = provider_value.get('view') if isinstance(provider_value, dict) else None
                    scene = scene if content and isinstance(scene, dict) else None
                    if scene is not None:
                        options = _scene_options(provider_value.get('options'))
                        if plan is None or scene != planned_scene or options != planned_options or monitor != planned_monitor:
                            plan = _scene_plan(scene, options, monitor)
                            planned_scene, planned_options, planned_monitor = scene, options, monitor
                        bounds = plan['bounds']
                    else:
                        content = _fit_lines(content, monitor, options['font_size'])
                        bounds = _bounds(monitor, len(content), options['font_size'], options['position'], options['width_percent'])
                except Exception:
                    # Hide stale data on a transient provider or monitor failure.
                    if visible:
                        win32gui.ShowWindow(hwnd, win32con.SW_HIDE)
                        visible = False
                    stop.wait(self._interval)
                    continue
                if not content:
                    if visible:
                        win32gui.ShowWindow(hwnd, win32con.SW_HIDE)
                        visible = False
                else:
                    if (bounds != previous_bounds or not visible or content != self._content or
                            capture_active != self._capture_active or options != self._options or scene != self._scene):
                        if scene is None:
                            _render_layer(hwnd, bounds, content, capture_active, options)
                        else:
                            _render_scene_layer(hwnd, plan, capture_active, options)
                        self._content = content
                        self._capture_active = capture_active
                        self._options = options
                        self._scene = scene
                    if bounds != previous_bounds or not visible:
                        win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, *bounds,
                                              win32con.SWP_NOACTIVATE | win32con.SWP_SHOWWINDOW)
                        previous_bounds = bounds
                        visible = True
                stop.wait(self._interval)
        except Exception:
            self._error = 'window_error'
            _LOG.exception('Tracker overlay window failed')
        finally:
            _measure_text.cache_clear()
            if hwnd:
                try:
                    win32gui.DestroyWindow(hwnd)
                except Exception:
                    _LOG.exception('Unable to destroy tracker overlay window')
            if registered:
                try:
                    win32gui.UnregisterClass(class_name, instance)
                except Exception:
                    _LOG.exception('Unable to unregister tracker overlay window')
