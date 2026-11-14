import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class OnboardingStateTests(unittest.TestCase):
    def test_first_capture_and_existing_captures_are_recorded_durably(self):
        script = '''
from contextlib import closing
import sqlite3
from flask import Flask
app = Flask(__name__)
from application import init
from application import detection_history
client = app.test_client()
def status(): return client.get('/onboarding-status').get_json()
assert status() == {'first_capture': False, 'first_event': False}
detection_history.record_detection('Suivi démarré', 'System', 'monitor_start')
assert status() == {'first_capture': False, 'first_event': False}
detection_history.record_detection('Notification de jeu', 'Unknown')
assert status() == {'first_capture': False, 'first_event': True}
init.add_capture('test', 0, 0, 1, '15', '2000-01-01', 'Arena', 'fixture')
assert status() == {'first_capture': False, 'first_event': True}
for mode in ('Arena', 'Invasion', 'Defense'):
    for victory, defeat in ((1,0), (0,1)):
        with closing(sqlite3.connect(init.database_capture)) as db, db:
            db.execute('DELETE FROM tracker_onboarding')
        init.add_capture('test', victory, defeat, 0, '15', '2000-01-01', mode, 'fixture')
        assert status() == {'first_capture': True, 'first_event': True}
with closing(sqlite3.connect(init.database_capture)) as db, db:
    db.execute('DELETE FROM tabel_captures')
    db.execute('DELETE FROM detection_history')
assert status() == {'first_capture': True, 'first_event': True}
with closing(sqlite3.connect(init.database_capture)) as db, db:
    db.execute('DELETE FROM tracker_onboarding')
    db.execute('DELETE FROM tracker_first_game_event')
init.add_capture('test', 0, 0, 1, '15', '2000-01-01', 'Arena', 'fixture')
with closing(sqlite3.connect(init.database_capture)) as db, db:
    db.execute('DELETE FROM tracker_first_game_event')
init.create_tables()
assert status() == {'first_capture': False, 'first_event': True}
init.add_capture('test', 0, 1, 0, '15', '2000-01-01', 'Defense', 'fixture')
with closing(sqlite3.connect(init.database_capture)) as db, db:
    db.execute('DELETE FROM tracker_onboarding')
init.create_tables()
assert status() == {'first_capture': True, 'first_event': True}
'''
        with tempfile.TemporaryDirectory(prefix='tracker-onboarding-') as directory:
            env = os.environ.copy()
            env['APPDATA'] = directory
            result = subprocess.run([sys.executable, '-c', script], cwd=ROOT, env=env,
                                    capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
