import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from application import first_run, runtime_paths
from test_overlay_settings import load_module


class OverlayDefaultMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env = patch.dict(os.environ, {'APPDATA': self.temp.name, 'LOCALAPPDATA': self.temp.name})
        env.start()
        self.addCleanup(env.stop)
        family = patch.object(runtime_paths, 'package_family_name', return_value=None)
        self.family = family.start()
        self.addCleanup(family.stop)

    def module(self, path):
        module = load_module(path)
        # Distinguish the frozen upgrade preset from future new-install defaults.
        module.DEFAULT_OPTIONS = dict(module.DEFAULT_OPTIONS, font_size=12, background_opacity=10,
                                      show_country=False, show_role=False)
        return module

    def create_existing(self, db_path, generation=None):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(db_path)) as db, db:
            db.execute('CREATE TABLE overlay_options (name TEXT PRIMARY KEY, value TEXT NOT NULL)')
            db.executemany('INSERT INTO overlay_options VALUES (?, ?)', [
                ('font_size', '21'), ('background_opacity', 'broken json'),
                ('show_mode', 'false'), ('unknown_future_option', '"keep me"')])
            db.execute('CREATE TABLE overlay_setting (id INTEGER PRIMARY KEY, enabled INTEGER NOT NULL)')
            db.execute('INSERT INTO overlay_setting VALUES (1, 0)')
            db.execute('CREATE TABLE unrelated_settings (value TEXT NOT NULL)')
            db.execute("INSERT INTO unrelated_settings VALUES ('untouched')")
            if generation is not None:
                db.execute('CREATE TABLE overlay_defaults_version (id INTEGER PRIMARY KEY, version TEXT NOT NULL)')
                db.execute('INSERT INTO overlay_defaults_version VALUES (1, ?)', (generation,))

    def assert_upgraded(self, module):
        self.assertEqual(module.options(), dict(module.UPGRADE_V2_DEFAULT_OPTIONS, show_player_tags=True, show_player_favourite=True))
        self.assertFalse(module.enabled())
        with closing(sqlite3.connect(module.database_setting)) as db:
            self.assertEqual(db.execute('SELECT version FROM overlay_defaults_version WHERE id=1').fetchone(), ('v2',))
            self.assertEqual(db.execute("SELECT value FROM overlay_options WHERE name='unknown_future_option'").fetchone(), ('"keep me"',))
            self.assertEqual(db.execute('SELECT value FROM unrelated_settings').fetchone(), ('untouched',))

    def test_existing_profiles_migrate_once_and_keep_later_customizations(self):
        for generation in (None, 'legacy', 'current'):
            with self.subTest(generation=generation):
                db_path = Path(self.temp.name) / ('settings-' + (generation or 'unmarked') + '.db')
                self.create_existing(db_path, generation)
                module = self.module(db_path)
                module.initialize_defaults(False)
                self.assert_upgraded(module)
                module.set_options({'font_size': 23, 'show_mode': False})
                # A newly imported module simulates the next application launch.
                restarted = self.module(db_path)
                restarted.initialize_defaults(False)
                self.assertEqual(restarted.options()['font_size'], 23)
                self.assertFalse(restarted.options()['show_mode'])
                self.assertFalse(restarted.enabled())

    def test_new_profile_after_interrupted_first_start_keeps_new_baseline(self):
        self.assertTrue(first_run.begin())
        self.assertTrue(first_run.uses_new_overlay_defaults())
        self.assertTrue(first_run.begin())
        module = self.module(runtime_paths.database_path('database_setting.db'))
        module.initialize_defaults(first_run.uses_new_overlay_defaults(),
                                   generation=first_run.overlay_defaults_generation())
        self.assertEqual(module.options(), module.DEFAULT_OPTIONS)
        self.assertTrue(module.enabled())
        module.set_options({'font_size': 22, 'show_country': True})
        self.module(Path(module.database_setting)).initialize_defaults(False)
        self.assertEqual(module.options()['font_size'], 22)
        self.assertTrue(module.options()['show_country'])

    def test_existing_v2_keeps_saved_options(self):
        db_path = Path(self.temp.name) / 'v2.db'
        self.create_existing(db_path, 'v2')
        module = self.module(db_path)
        module.initialize_defaults(False)
        self.assertEqual(module.options()['font_size'], 21)
        self.assertEqual(module.options()['background_opacity'], 10)
        self.assertFalse(module.options()['show_mode'])
        self.assertFalse(module.enabled())

    def test_interrupted_old_first_run_receives_upgrade_preset(self):
        runtime_paths.data_dir().mkdir(parents=True)
        first_run._save({'state': 'pending', 'overlay_defaults': 'current'})
        self.assertTrue(first_run.begin())
        module = self.module(runtime_paths.database_path('database_setting.db'))
        module.initialize_defaults(first_run.uses_new_overlay_defaults(),
                                   generation=first_run.overlay_defaults_generation())
        self.assertEqual(module.options(), dict(module.UPGRADE_V2_DEFAULT_OPTIONS, show_player_tags=True, show_player_favourite=True))

    def test_failed_first_start_keeps_new_install_preset_for_retry(self):
        self.assertTrue(first_run.begin())
        with patch('application.error_reports.report'):
            first_run.finish()  # Expected failure: no test databases exist yet.
        self.assertEqual(first_run.read_status()['state'], 'failed')
        module = self.module(runtime_paths.database_path('database_setting.db'))
        module.initialize_defaults(first_run.uses_new_overlay_defaults(),
                                   generation=first_run.overlay_defaults_generation())
        self.assertEqual(module.options(), module.DEFAULT_OPTIONS)

    def test_existing_profile_missing_settings_database_receives_upgrade_preset(self):
        runtime_paths.data_dir().mkdir(parents=True)
        runtime_paths.database_path('database_user.db').write_bytes(b'existing')
        self.assertFalse(first_run.begin())
        module = self.module(runtime_paths.database_path('database_setting.db'))
        module.initialize_defaults(first_run.uses_new_overlay_defaults())
        self.assertEqual(module.options(), dict(module.UPGRADE_V2_DEFAULT_OPTIONS, show_player_tags=True, show_player_favourite=True))
        module.set_options({'show_country': False})
        module.initialize_defaults(False)
        self.assertFalse(module.options()['show_country'])

    def test_existing_store_private_profile_migrates_without_touching_other_data(self):
        self.family.return_value = 'Example.Tracker_family'
        private = runtime_paths._private_data_dir()
        private.mkdir(parents=True)
        (private / 'database_user.db').write_bytes(b'existing')
        db_path = private / 'database_setting.db'
        self.create_existing(db_path, 'legacy')
        self.assertFalse(first_run.begin())
        self.assertEqual(runtime_paths.database_path('database_setting.db'), db_path)
        module = self.module(db_path)
        module.initialize_defaults(first_run.uses_new_overlay_defaults())
        self.assert_upgraded(module)
        self.assertEqual((private / 'database_user.db').read_bytes(), b'existing')
        module.set_options({'font_size': 24})
        self.module(db_path).initialize_defaults(False)
        self.assertEqual(module.options()['font_size'], 24)

    def test_failed_migration_is_atomic_and_can_be_retried(self):
        db_path = Path(self.temp.name) / 'atomic.db'
        self.create_existing(db_path, 'legacy')
        with closing(sqlite3.connect(db_path)) as db, db:
            # Fail late in the preset so earlier writes must be rolled back.
            db.execute("CREATE TRIGGER fail_insert BEFORE INSERT ON overlay_options "
                       "WHEN NEW.name='ping_bad_color' BEGIN SELECT RAISE(ABORT, 'test failure'); END")
            db.execute("CREATE TRIGGER fail_update BEFORE UPDATE ON overlay_options "
                       "WHEN NEW.name='ping_bad_color' BEGIN SELECT RAISE(ABORT, 'test failure'); END")
            before = db.execute('SELECT name, value FROM overlay_options ORDER BY name').fetchall()
        module = self.module(db_path)
        with self.assertRaises(sqlite3.DatabaseError):
            module.initialize_defaults(False)
        with closing(sqlite3.connect(db_path)) as db, db:
            self.assertEqual(db.execute('SELECT name, value FROM overlay_options ORDER BY name').fetchall(), before)
            self.assertEqual(db.execute('SELECT version FROM overlay_defaults_version WHERE id=1').fetchone(), ('legacy',))
            db.execute('DROP TRIGGER fail_insert')
            db.execute('DROP TRIGGER fail_update')
        module.initialize_defaults(False)
        self.assert_upgraded(module)


if __name__ == '__main__':
    unittest.main()
