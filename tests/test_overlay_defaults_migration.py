import json
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
        # Make the two generations observably different independently of the
        # actual preset chosen by the user.
        module.DEFAULT_OPTIONS = dict(module.DEFAULT_OPTIONS, font_size=12, background_opacity=10,
                                      show_country=False, show_role=False)
        return module

    def test_new_profile_after_interrupted_first_start_keeps_new_baseline(self):
        self.assertTrue(first_run.begin())
        self.assertTrue(first_run.uses_new_overlay_defaults())
        # The process may stop before creating any database or migration row.
        self.assertTrue(first_run.begin())
        module = self.module(runtime_paths.database_path('database_setting.db'))
        module.initialize_defaults(first_run.uses_new_overlay_defaults(),
                                   generation=first_run.overlay_defaults_generation())
        self.assertEqual(module.options()['font_size'], 12)
        self.assertFalse(module.options()['show_country'])
        module.initialize_defaults(False)
        self.assertEqual(module.options()['font_size'], 12)

    def test_interrupted_old_current_install_keeps_its_original_generation(self):
        runtime_paths.data_dir().mkdir(parents=True)
        first_run._save({'state': 'pending', 'overlay_defaults': 'current'})
        self.assertTrue(first_run.begin())
        self.assertTrue(first_run.uses_new_overlay_defaults())
        self.assertEqual(first_run.overlay_defaults_generation(), 'current')
        module = self.module(runtime_paths.database_path('database_setting.db'))
        module.initialize_defaults(first_run.uses_new_overlay_defaults(),
                                   generation=first_run.overlay_defaults_generation())
        self.assertEqual(module.options()['font_size'], 15)
        self.assertEqual(module.options()['background_opacity'], 50)
        self.assertTrue(module.options()['show_country'])

    def test_failed_first_start_keeps_its_preset_for_retry(self):
        self.assertTrue(first_run.begin())
        with patch('application.error_reports.report'):
            first_run.finish()  # Expected failure: no test databases exist yet.
        self.assertEqual(first_run.read_status()['state'], 'failed')
        self.assertEqual(first_run.overlay_defaults_generation(), 'v2')
        module = self.module(runtime_paths.database_path('database_setting.db'))
        module.initialize_defaults(first_run.uses_new_overlay_defaults(),
                                   generation=first_run.overlay_defaults_generation())
        self.assertEqual(module.options()['font_size'], 12)
        self.assertFalse(module.options()['show_country'])

    def test_existing_current_generation_preserves_unsaved_and_invalid_defaults(self):
        db_path = runtime_paths.database_path('database_setting.db')
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(db_path)) as db, db:
            db.execute('CREATE TABLE overlay_defaults_version (id INTEGER PRIMARY KEY, version TEXT NOT NULL)')
            db.execute("INSERT INTO overlay_defaults_version VALUES (1, 'current')")
            db.execute('CREATE TABLE overlay_options (name TEXT PRIMARY KEY, value TEXT NOT NULL)')
            db.executemany('INSERT INTO overlay_options VALUES (?, ?)', [
                ('font_size', '999'), ('show_mode', 'false'), ('future_option', '"keep"')])
        module = self.module(db_path)
        module.initialize_defaults(True)
        options = module.options()
        self.assertEqual(options['font_size'], 15)
        self.assertEqual(options['background_opacity'], 50)
        self.assertTrue(options['show_country'])
        self.assertTrue(options['show_role'])
        self.assertFalse(options['show_mode'])
        with closing(sqlite3.connect(db_path)) as db:
            self.assertEqual(db.execute('SELECT version FROM overlay_defaults_version').fetchone(), ('current',))
            self.assertEqual(db.execute('SELECT name, value FROM overlay_options ORDER BY name').fetchall(), [
                ('font_size', '999'), ('future_option', '"keep"'), ('show_mode', 'false')])

    def test_v2_generation_uses_current_preset_without_changing_saved_options(self):
        db_path = runtime_paths.database_path('database_setting.db')
        db_path.parent.mkdir(parents=True, exist_ok=True)
        module = self.module(db_path)
        module.initialize_defaults(True)
        module.set_options({'font_size': 21, 'show_country': True})
        self.assertEqual(module.options()['font_size'], 21)
        self.assertTrue(module.options()['show_country'])
        self.assertEqual(module.options()['background_opacity'], 10)
        self.assertFalse(module.options()['show_role'])
        with closing(sqlite3.connect(db_path)) as db:
            self.assertEqual(db.execute('SELECT version FROM overlay_defaults_version').fetchone(), ('v2',))

    def test_existing_profile_missing_settings_database_uses_legacy_baseline(self):
        runtime_paths.data_dir().mkdir(parents=True)
        runtime_paths.database_path('database_user.db').write_bytes(b'existing')
        self.assertFalse(first_run.begin())
        module = self.module(runtime_paths.database_path('database_setting.db'))
        module.initialize_defaults(first_run.uses_new_overlay_defaults())
        self.assertEqual(module.options(), dict(module.LEGACY_DEFAULT_OPTIONS, show_country=True, show_role=True))
        module.set_options({'show_country': False})
        module.initialize_defaults(True)
        self.assertEqual(module.options(), dict(module.LEGACY_DEFAULT_OPTIONS, show_country=False, show_role=True))

    def test_existing_explicit_and_invalid_options_are_not_changed(self):
        runtime_paths.data_dir().mkdir(parents=True)
        db_path = runtime_paths.database_path('database_setting.db')
        with closing(sqlite3.connect(db_path)) as db, db:
            db.execute('CREATE TABLE overlay_options (name TEXT PRIMARY KEY, value TEXT NOT NULL)')
            db.executemany('INSERT INTO overlay_options VALUES (?, ?)', [
                ('font_size', json.dumps(20)), ('background_opacity', 'broken json'),
                ('unknown_future_option', '"keep me"')])
        self.assertFalse(first_run.begin())
        module = self.module(db_path)
        module.initialize_defaults(False)
        self.assertEqual(module.options()['font_size'], 20)
        self.assertEqual(module.options()['background_opacity'], 60)
        with closing(sqlite3.connect(db_path)) as db:
            self.assertEqual(db.execute('SELECT name, value FROM overlay_options ORDER BY name').fetchall(), [
                ('background_opacity', 'broken json'), ('font_size', '20'),
                ('unknown_future_option', '"keep me"')])
        module.set_options({'background_opacity': 40})
        module.initialize_defaults(True)
        self.assertEqual(module.options()['background_opacity'], 40)
        self.assertEqual(module.options()['visibility_mode'], module.LEGACY_DEFAULT_OPTIONS['visibility_mode'])

    def test_old_interrupted_first_run_is_treated_as_existing(self):
        runtime_paths.data_dir().mkdir(parents=True)
        first_run._save({'state': 'pending'})
        self.assertTrue(first_run.begin())
        self.assertFalse(first_run.uses_new_overlay_defaults())
        module = self.module(runtime_paths.database_path('database_setting.db'))
        module.initialize_defaults(first_run.uses_new_overlay_defaults())
        self.assertEqual(module.options()['font_size'], 15)

    def test_existing_store_private_profile_uses_legacy_baseline(self):
        self.family.return_value = 'Example.Tracker_family'
        private = runtime_paths._private_data_dir()
        private.mkdir(parents=True)
        (private / 'database_user.db').write_bytes(b'existing')
        with closing(sqlite3.connect(private / 'database_setting.db')) as db, db:
            db.execute('CREATE TABLE overlay_options (name TEXT PRIMARY KEY, value TEXT NOT NULL)')
            db.execute('INSERT INTO overlay_options VALUES (?, ?)', ('font_size', '21'))
        self.assertFalse(first_run.begin())
        self.assertEqual(runtime_paths.database_path('database_setting.db'), private / 'database_setting.db')
        module = self.module(runtime_paths.database_path('database_setting.db'))
        module.initialize_defaults(first_run.uses_new_overlay_defaults())
        self.assertEqual(module.options()['font_size'], 21)
        self.assertEqual(module.options()['background_opacity'], 60)


if __name__ == '__main__':
    unittest.main()
