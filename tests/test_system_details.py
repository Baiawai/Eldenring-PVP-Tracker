"""Read-only storage measurements with temporary, isolated files."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from application import system_details
from application import runtime_paths


class SystemDetailsTests(unittest.TestCase):
    def test_snapshot_reports_private_database_and_sidecars(self):
        with tempfile.TemporaryDirectory() as temp, \
             patch.dict('os.environ', {'APPDATA': str(Path(temp) / 'roaming'), 'LOCALAPPDATA': str(Path(temp) / 'local')}), \
             patch.object(runtime_paths, 'package_family_name', return_value='Example.Tracker_family'), \
             patch.object(system_details, 'tesseract_version', return_value=None):
            private = runtime_paths._private_data_dir()
            private.mkdir(parents=True)
            (private / 'database_user.db').write_bytes(b'x' * 10)
            (private / 'database_user.db-wal').write_bytes(b'x' * 4)
            result = system_details.snapshot()
            self.assertEqual(result['storage']['database_bytes'], 14)
            self.assertEqual(result['environment']['data_path'], str(private))

    def test_database_sizes_include_sidecars_and_ignore_other_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name, size in [('a.db', 10), ('a.db-wal', 4), ('a.db-shm', 2),
                               ('b.db', 7), ('notes.txt', 100)]:
                (root / name).write_bytes(b'x' * size)
            self.assertEqual(system_details.database_sizes(root), [
                {'name': 'a.db', 'bytes': 16}, {'name': 'b.db', 'bytes': 7}])
            self.assertEqual((root / 'a.db').stat().st_size, 10)

    def test_snapshot_with_missing_tesseract_and_disk(self):
        with tempfile.TemporaryDirectory() as temp, \
             patch.dict('os.environ', {'APPDATA': temp}), \
             patch.object(system_details, 'tesseract_version', return_value=None), \
             patch.object(system_details.shutil, 'disk_usage', side_effect=OSError('unavailable')):
            result = system_details.snapshot()
            self.assertEqual(result['storage']['databases'], [])
            self.assertEqual(result['storage']['database_bytes'], 0)
            self.assertIsNone(result['storage']['disk_free_bytes'])
            self.assertIsNone(result['environment']['tesseract'])
            self.assertEqual(result['environment']['data_path'], str(Path(temp) / 'Elden Ring PvP Tracker'))
            self.assertFalse((Path(temp) / 'Elden Ring PvP Tracker').exists())

    def test_snapshot_shows_every_accessible_location(self):
        with tempfile.TemporaryDirectory() as temp, \
             patch.dict('os.environ', {'APPDATA': temp}), \
             patch.object(system_details, 'accessible_data_directories', return_value=[Path(temp) / 'private', Path(temp) / 'normal']), \
             patch.object(system_details, 'tesseract_version', return_value=None):
            result = system_details.snapshot()
            self.assertEqual(result['environment']['data_path'], str(Path(temp) / 'private') + '\n' + str(Path(temp) / 'normal'))


if __name__ == '__main__':
    unittest.main()
