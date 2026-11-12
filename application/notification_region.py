"""Notification region as fractions of the captured central game image."""
import math
import sqlite3
from contextlib import closing
from application.init import database_setting

DEFAULT_REGION = (0.4, 1.0)

def valid(top, bottom):
    return math.isfinite(top) and math.isfinite(bottom) and 0 <= top < bottom <= 1 and bottom - top >= 0.05 - 1e-9

def load(legacy=None, legacy_height=None):
    with closing(sqlite3.connect(database_setting, timeout=10)) as con:
        con.execute("CREATE TABLE IF NOT EXISTS notification_region (id INTEGER PRIMARY KEY CHECK(id=1), top REAL NOT NULL, bottom REAL NOT NULL)")
        row = con.execute("SELECT top, bottom FROM notification_region WHERE id=1").fetchone()
        if row and valid(*row):
            return tuple(row)
        region = DEFAULT_REGION
        try:
            top, bottom = float(legacy[0]), float(legacy[1])
            height = float(legacy_height)
            candidate = (top / height, (top + top - bottom - 8) / height)
            if top > 0 and bottom > 0 and valid(*candidate):
                region = candidate
        except (ValueError, TypeError, IndexError, ZeroDivisionError):
            pass
        con.execute("INSERT OR REPLACE INTO notification_region(id,top,bottom) VALUES(1,?,?)", region)
        con.commit()
        return region

def save(top, bottom):
    if not valid(top, bottom):
        raise ValueError("Invalid notification region")
    with closing(sqlite3.connect(database_setting, timeout=10)) as con:
        con.execute("CREATE TABLE IF NOT EXISTS notification_region (id INTEGER PRIMARY KEY CHECK(id=1), top REAL NOT NULL, bottom REAL NOT NULL)")
        con.execute("INSERT OR REPLACE INTO notification_region(id,top,bottom) VALUES(1,?,?)", (top,bottom))
        con.commit()

def crop_box(width, height, region):
    if width < 1 or height < 1 or not valid(*region):
        raise ValueError("Invalid image or region")
    top = min(height - 1, max(0, int(round(height * region[0]))))
    bottom = max(top + 1, min(height, int(round(height * region[1]))))
    return (0, top, width, bottom)


def manual_mode():
    """Use automatic detection unless the user selected manual mode."""
    with closing(sqlite3.connect(database_setting, timeout=10)) as con:
        con.execute('CREATE TABLE IF NOT EXISTS notification_region_mode (id INTEGER PRIMARY KEY CHECK(id=1), manual INTEGER NOT NULL CHECK(manual IN (0,1)))')
        row = con.execute('SELECT manual FROM notification_region_mode WHERE id=1').fetchone()
        return bool(row[0]) if row else False


def set_manual_mode(manual):
    if not isinstance(manual, bool):
        raise ValueError('Invalid notification region mode')
    with closing(sqlite3.connect(database_setting, timeout=10)) as con, con:
        con.execute('CREATE TABLE IF NOT EXISTS notification_region_mode (id INTEGER PRIMARY KEY CHECK(id=1), manual INTEGER NOT NULL CHECK(manual IN (0,1)))')
        con.execute('INSERT INTO notification_region_mode(id,manual) VALUES(1,?) ON CONFLICT(id) DO UPDATE SET manual=excluded.manual', (int(manual),))


def load_locked_bounds():
    """Return the fixed automatic region, if the user has locked it."""
    with closing(sqlite3.connect(database_setting, timeout=10)) as con:
        table = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='notification_region_lock'").fetchone()
        row = con.execute('SELECT top,bottom FROM notification_region_lock WHERE id=1').fetchone() if table else None
    return tuple(row) if row and valid(*row) and row[1] - row[0] < .95 else None


def set_locked_bounds(bounds):
    if bounds is not None and (len(bounds) != 2 or not valid(*bounds) or bounds[1] - bounds[0] >= .95):
        raise ValueError('Invalid automatic region')
    with closing(sqlite3.connect(database_setting, timeout=10)) as con, con:
        con.execute('CREATE TABLE IF NOT EXISTS notification_region_lock (id INTEGER PRIMARY KEY CHECK(id=1), top REAL NOT NULL, bottom REAL NOT NULL)')
        if bounds is None:
            con.execute('DELETE FROM notification_region_lock WHERE id=1')
        else:
            con.execute('INSERT INTO notification_region_lock(id,top,bottom) VALUES(1,?,?) ON CONFLICT(id) DO UPDATE SET top=excluded.top,bottom=excluded.bottom', bounds)


def _banner_edges(image, first_top, last_bottom, line_height):
    """Estimate a dark banner's top and bottom around the recognized text."""
    if image is None:
        return None
    import numpy as np
    frame = np.asarray(image)
    if frame.ndim == 3:
        frame = frame.mean(axis=2)
    if frame.ndim != 2 or frame.shape[0] < 10 or frame.shape[1] < 10:
        return None
    height = frame.shape[0]
    # A horizontal dark strip affects much of the frame; a median resists the
    # white letters and isolated bright background details.
    rows = np.median(frame, axis=1)
    smooth = np.convolve(rows, np.ones(5) / 5, mode='same')
    radius = max(12, round(line_height * 3.5))
    upper = range(max(2, first_top - radius), min(height - 2, first_top))
    lower = range(max(2, last_bottom), min(height - 2, last_bottom + radius))
    if not upper or not lower:
        return None
    top = min(upper, key=lambda y: smooth[y + 2] - smooth[y - 2])
    bottom = max(lower, key=lambda y: smooth[y + 2] - smooth[y - 2])
    if smooth[top + 2] - smooth[top - 2] > -8 or smooth[bottom + 2] - smooth[bottom - 2] < 8:
        return None
    return top, bottom


def analyze_notification(data, image_height, language, image=None, image_width=None):
    """Locate complete catalog messages and count their OCR text lines.

    Return None if the message or its position is uncertain.  The minimum
    capture height accommodates a two-line notification even for a one-line
    event.  Coordinates refer to the central game image.
    """
    from application.locale_catalog import recognize, _normalize_with_offsets, _EVENT_BY_ID
    if image_height <= 0:
        return None
    if image_width is not None and image_width <= 0:
        image_width = None
    groups = {}
    try:
        for i, word in enumerate(data['text']):
            word = str(word).strip()
            if not word or float(data['conf'][i]) < 20:
                continue
            top, height = int(data['top'][i]), int(data['height'][i])
            if top < 0 or height <= 0 or top + height > image_height:
                continue
            key = (int(data['block_num'][i]), int(data['par_num'][i]), int(data['line_num'][i]))
            group = groups.setdefault(key, {'words':[], 'top':top, 'bottom':top + height})
            group['words'].append(word)
            group['top'] = min(group['top'], top)
            group['bottom'] = max(group['bottom'], top + height)
            if image_width:
                try:
                    left, width = int(data['left'][i]), int(data['width'][i])
                    if left < 0 or width <= 0 or left + width > image_width:
                        raise ValueError('Invalid horizontal position')
                    group['left'] = min(group.get('left', left), left)
                    group['right'] = max(group.get('right', left + width), left + width)
                except (KeyError, IndexError, TypeError, ValueError):
                    group['horizontal_invalid'] = True
    except (KeyError, IndexError, TypeError, ValueError):
        return None
    lines = sorted(groups.values(), key=lambda item: item['top'])
    parts, ranges, cursor = [], [], 0
    for line in lines:
        text = ' '.join(line['words'])
        if parts:
            cursor += 1
        ranges.append((cursor, cursor + len(text)))
        parts.append(text)
        cursor += len(text)
    joined = '\n'.join(parts)
    _, offsets = _normalize_with_offsets(joined)
    matched, max_lines = set(), 0
    for match in recognize(joined, language):
        if match['id'] not in _EVENT_BY_ID:
            continue
        start, end = match['span']
        if end <= start or end > len(offsets):
            continue
        left, right = offsets[start], offsets[end - 1] + 1
        indices = [i for i, (a, b) in enumerate(ranges) if a < right and b > left]
        if not indices or any(lines[j]['top'] - lines[i]['bottom'] > image_height * .08 for i, j in zip(indices, indices[1:])):
            continue
        matched.update(indices)
        max_lines = max(max_lines, len(indices))
    if not matched:
        return None
    chosen = [lines[i] for i in sorted(matched)]
    first_top = min(line['top'] for line in chosen)
    last_bottom = max(line['bottom'] for line in chosen)
    heights = sorted(line['bottom'] - line['top'] for line in chosen)
    line_height = heights[len(heights) // 2]
    edges = _banner_edges(image, first_top, last_bottom, line_height)
    if edges:
        top, bottom = edges
        top = max(0, top - 2)
        bottom = min(image_height, bottom + 2)
    else:
        # Keep a conservative area if the background does not show clear edges.
        padding = max(4, round(line_height * 1.3))
        top, bottom = max(0, first_top - padding), min(image_height, last_bottom + padding)
    # Single-line text still needs enough height for a two-line banner.
    # When both lines are visible, retain the detected banner edges instead.
    minimum_text_height = (round(line_height * 4.5) if max_lines < 2
                           else last_bottom - first_top + max(8, round(line_height * .5)))
    minimum = min(image_height, max(round(image_height * .05), minimum_text_height))
    if bottom - top < minimum:
        center = (top + bottom) / 2
        top = max(0, round(center - minimum / 2))
        bottom = min(image_height, top + minimum)
        top = max(0, bottom - minimum)
    result = {'bounds':(top / image_height, bottom / image_height), 'lines':max_lines}
    if image_width and all('left' in line and 'right' in line and not line.get('horizontal_invalid') for line in chosen):
        padding = max(3, round(line_height * .25))
        result['box'] = (max(0, min(line['left'] for line in chosen) - padding) / image_width,
                         max(0, first_top - padding) / image_height,
                         min(image_width, max(line['right'] for line in chosen) + padding) / image_width,
                         min(image_height, last_bottom + padding) / image_height)
    return result


def detected_bounds(data, image_height, language, image=None):
    result = analyze_notification(data, image_height, language, image)
    return result['bounds'] if result else (0.0, 1.0)
