import os
import errno
import sqlite3
import tempfile
import unittest
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from application import first_run, runtime_paths


class FirstRunTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.env = patch.dict(os.environ, {'APPDATA': self.temporary.name,
                                           'LOCALAPPDATA': self.temporary.name})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.family = patch.object(runtime_paths, 'package_family_name', return_value=None)
        self.family.start()
        self.addCleanup(self.family.stop)

    def create_databases(self):
        for name, table in first_run.DATABASES.items():
            with closing(sqlite3.connect(runtime_paths.database_path(name))) as db:
                db.execute('CREATE TABLE "' + table + '" (id INTEGER)')
                db.commit()

    def test_success_is_reported_once_and_verified_read_only(self):
        self.assertTrue(first_run.begin())
        self.create_databases()
        first_run.finish()
        self.assertEqual(first_run.claim(), {'state':'ready', 'log_available':False})
        self.assertIsNone(first_run.claim())
        self.assertFalse(first_run.begin())

    def test_store_redirected_marker_works_when_replace_crosses_volumes(self):
        with patch.object(first_run.os, 'replace', side_effect=OSError(errno.EXDEV, 'cross-device link')):
            self.assertTrue(first_run.begin())
            self.create_databases()
            first_run.finish()
            self.assertEqual(first_run.claim(), {'state':'ready', 'log_available':False})
            self.assertIsNone(first_run.claim())
        self.assertFalse((runtime_paths.data_dir() / 'initialization-status.tmp').exists())

    def test_marker_does_not_hide_unrelated_replace_errors(self):
        with patch.object(first_run.os, 'replace', side_effect=PermissionError('denied')):
            with self.assertRaises(PermissionError):
                first_run.begin()

    def test_multiple_tabs_receive_only_one_notice(self):
        self.assertTrue(first_run.begin())
        self.create_databases()
        first_run.finish()
        with ThreadPoolExecutor(max_workers=6) as pool:
            notices = list(pool.map(lambda _: first_run.claim(), range(6)))
        self.assertEqual(sum(notice is not None for notice in notices), 1)

    def test_fatal_startup_error_offers_to_open_the_log(self):
        with patch.object(first_run.locale, 'getlocale', return_value=('fr_FR', 'UTF-8')), \
             patch.object(first_run.ctypes.windll.user32, 'MessageBoxW', return_value=6) as dialog, \
             patch.object(first_run.os, 'startfile') as start:
            first_run.report_fatal('Traceback: simulated initialization failure')
        path = runtime_paths.data_dir() / 'tracker-errors.log'
        self.assertIn('simulated initialization failure', path.read_text(encoding='utf-8'))
        self.assertIn(str(path), dialog.call_args.args[1])
        start.assert_called_once_with(str(path))

    def test_fatal_error_uses_supported_windows_language_and_english_fallback(self):
        for system_language, expected in [('de_DE', 'Initialisierung'),
                                          ('ja_JP', '初期化'),
                                          ('xx_XX', 'initialization failed')]:
            with self.subTest(system_language=system_language), \
                 patch.object(first_run.locale, 'getlocale', return_value=(system_language, 'UTF-8')), \
                 patch.object(first_run.ctypes.windll.user32, 'MessageBoxW', return_value=7) as dialog:
                first_run.report_fatal('diagnostic')
                self.assertIn(expected, dialog.call_args.args[1])

    def test_existing_profile_is_not_marked_as_new(self):
        runtime_paths.data_dir().mkdir(parents=True)
        (runtime_paths.data_dir() / 'database_user.db').write_bytes(b'existing')
        self.assertFalse(first_run.begin())
        self.assertFalse((runtime_paths.data_dir() / first_run.MARKER).exists())
        self.assertEqual((runtime_paths.data_dir() / 'database_user.db').read_bytes(), b'existing')

    def test_existing_store_private_profile_is_not_marked_as_new(self):
        with patch.object(runtime_paths, 'package_family_name', return_value='Example.Tracker_family'):
            private = runtime_paths._private_data_dir()
            private.mkdir(parents=True)
            (private / 'database_user.db').write_bytes(b'existing')
            self.assertFalse(first_run.begin())
            self.assertFalse(runtime_paths.data_dir().exists())

    def test_interrupted_first_run_can_finish_after_restart(self):
        self.assertTrue(first_run.begin())
        self.create_databases()
        self.assertTrue(first_run.begin())
        first_run.finish()
        self.assertEqual(first_run.claim()['state'], 'ready')

    def test_failure_saves_details_and_can_open_only_its_log(self):
        self.assertTrue(first_run.begin())
        first_run.finish()
        self.assertEqual(first_run.claim(), {'state':'failed', 'log_available':True})
        log = runtime_paths.data_dir() / 'tracker-errors.log'
        self.assertIn('database_user.db', log.read_text(encoding='utf-8'))
        with patch.object(first_run.os, 'startfile') as start:
            self.assertTrue(first_run.open_log())
            start.assert_called_once_with(str(log))
        first_run.finish()
        self.assertIsNone(first_run.claim())
        self.create_databases()
        first_run.finish()
        self.assertEqual(first_run.claim(), {'state':'ready', 'log_available':False})

    def test_open_log_rejects_other_paths(self):
        runtime_paths.data_dir().mkdir(parents=True)
        other = Path(self.temporary.name) / 'other.txt'
        other.write_text('private', encoding='utf-8')
        first_run._save({'state':'failed', 'log':str(other)})
        with patch.object(first_run.os, 'startfile') as start:
            self.assertFalse(first_run.open_log())
            start.assert_not_called()


if __name__ == '__main__':
    unittest.main()
