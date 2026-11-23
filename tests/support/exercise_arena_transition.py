"""Synthetic OCR mode-transition checks without live tracker data or images."""
import os
from pathlib import Path
import sys
import time
import types
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from application import runtime_paths

images = Path(os.environ['APPDATA']) / 'test-runtime-images'
images.mkdir(parents=True, exist_ok=True)
runtime_paths.image_dir = lambda: images
module = types.ModuleType('__main__')
module.__file__ = str(ROOT / 'ELDENRING_Tracker.py')
module.__dict__['__name__'] = 'isolated_arena_transition_test'
sys.modules['__main__'] = module
exec(compile(Path(module.__file__).read_bytes(), module.__file__, 'exec'), module.__dict__)

from application import functions as f, player_sightings
from application.locale_catalog import messages

frame = images / 'synthetic.jpg'
frame.write_bytes(b'synthetic frame')
score = []


def record_score(*args):
    score.append((f.mode_select, args))


def reset(locale, *, active=True, mode='Defense'):
    score.clear()
    f.game_locale = locale
    f.detect_mod_active = f.detect_mod_en if locale == 'engus' else f.detect_mod_fr
    f.detect_text_active = f.detect_text_en if locale == 'engus' else f.detect_text_fr
    f.correspondly_active = f.correspondly_fr
    f.mode_select = mode
    f.mode_detected = True
    f.fight = active
    f.invasion_phase = 'fight' if active else 'finished'
    f.opponent_name = 'Example'
    f.time_start = time.time() - 20
    f.stape = 1 if active else 0
    f.fighter_find = f.fighters_exit = f.fighter_exit = False
    f.error = f.want_annul = f.wait_fighter = f.connexion_error = False
    f.run_monitor = False
    f.sighting_tracker = player_sightings.SightingTracker()
    f.overlay_invasion_tracker = player_sightings.SightingTracker()


with patch.object(f, 'apply_score', side_effect=record_score), \
     patch.object(f, 'emit_tracking_event'), patch.object(f, 'record_sighting', return_value=False), \
     patch.object(f, '_seal_pvp_participant', return_value=''), \
     patch.object(f, 'add_capture'), patch.object(f, '_remember_defense_victory'), \
     patch.object(f.cv2, 'imread'), patch.object(f.cv2, 'imwrite'), \
     patch.object(f.steam_history, 'begin_arena'):
    for locale, catalog in messages().items():
        start = catalog['arena:88000'].replace('<?matchDuel_TotalTime?>', '180')
        reset(locale)
        f.process_game_text(start, str(frame), None, notification_text='')
        assert (f.mode_select, f.fight) == ('Arena', True), locale
        assert score == [('Defense', (0, 0, 0, 0, 1, 0, 0, 0, 0)),
                         ('Arena', (0, 0, 0, 1, 0, 0, 1, 0, 0))], (locale, score)
        f.process_game_text(start, str(frame), None, notification_text='')
        assert len(score) == 2, (locale, score)

        reset(locale, active=False)
        f.process_game_text('', str(frame), None, notification_text=start)
        assert (f.mode_select, f.fight) == ('Arena', True), locale
        assert score == [('Arena', (0, 0, 0, 1, 0, 0, 1, 0, 0))], (locale, score)

        reset(locale)
        f.process_game_text('', str(frame), None, notification_text=catalog['2311413'])
        assert (f.mode_select, f.fight) == ('Arena', False), locale
        assert score == [('Defense', (0, 0, 0, 0, 1, 0, 0, 0, 0))], (locale, score)
        f.process_game_text(start, str(frame), None, notification_text='')
        assert (f.mode_select, f.fight) == ('Arena', True), locale
        assert len(score) == 2, (locale, score)

        reset(locale)
        waiting = catalog['2341413'].replace('<?matchRemainingCount?>', '1')
        f.process_game_text('', str(frame), None, notification_text=waiting)
        assert (f.mode_select, f.fight) == ('Arena', False), locale
        assert score == [('Defense', (0, 0, 0, 0, 1, 0, 0, 0, 0))], (locale, score)
        f.process_game_text(start, str(frame), None, notification_text='')
        assert (f.mode_select, f.fight) == ('Arena', True), locale
        assert len(score) == 2, (locale, score)

    reset('frafr')
    f.process_game_text('Début du combat.', str(frame), None, notification_text='')
    assert (f.mode_select, f.fight, score) == ('Defense', True, [])

    start = messages()['frafr']['arena:88000'].replace('<?matchDuel_TotalTime?>', '180')
    reset('frafr', mode='Invasion')
    f.process_game_text(start, str(frame), None, notification_text='')
    assert (f.mode_select, f.fight, score) == ('Invasion', True, [])

    reset('frafr')
    f.process_game_text('Le Doigt sanglant Example est mort.', str(frame), None, notification_text=start)
    assert (f.mode_select, f.fight) == ('Defense', False)
    assert score == [('Defense', (1, 0, 0, 0, 0, 0, 0, 0, 0))], score
    f.process_game_text(start, str(frame), None, notification_text='')
    assert (f.mode_select, f.fight) == ('Arena', True)
    assert score[-1] == ('Arena', (0, 0, 0, 1, 0, 0, 1, 0, 0)), score

    for identifier, expected in [('game:331305', (0, 1, 0, 0, 0, 0, 0, 0, 0)),
                                 ('2701200', (0, 0, 0, 0, 0, 0, 0, 1, 0))]:
        reset('frafr')
        result = messages()['frafr'][identifier]
        f.process_game_text(result, str(frame), None, notification_text=start)
        assert (f.mode_select, f.fight) == ('Defense', False), identifier
        assert score == [('Defense', expected)], (identifier, score)
