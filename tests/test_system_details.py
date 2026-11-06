"""Read-only storage measurements with temporary, isolated files."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from application import system_details


class SystemDetailsTests(unittest.TestCase):
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


if __name__ == '__main__':
    unittest.main()
