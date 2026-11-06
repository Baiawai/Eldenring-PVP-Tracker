"""Migration checks use isolated folders, never the real tracker data."""
import errno
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from application import runtime_paths


class DataDirectoryTests(unittest.TestCase):
    def test_migrates_every_file_once_without_changing_contents(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict('os.environ', {'APPDATA': temp}), \
             patch.object(runtime_paths, '_tracker_running', return_value=False):
            old = Path(temp) / runtime_paths.LEGACY_DATA_FOLDER
            (old / 'runtime_images').mkdir(parents=True)
            (old / 'database_user.db').write_bytes(b'profile')
            (old / 'database_user.db-wal').write_bytes(b'pending')
            (old / 'runtime_images' / 'capture.jpg').write_bytes(b'image')
            new = runtime_paths.initialize_data_dir()
            self.assertEqual(new, Path(temp) / 'Elden Ring PvP Tracker')
            self.assertFalse(old.exists())
            self.assertEqual((new / 'database_user.db').read_bytes(), b'profile')
            self.assertEqual((new / 'database_user.db-wal').read_bytes(), b'pending')
            self.assertEqual((new / 'runtime_images' / 'capture.jpg').read_bytes(), b'image')
            self.assertEqual(runtime_paths.initialize_data_dir(), new)

    def test_copy_fallback_verifies_before_removing_original(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict('os.environ', {'APPDATA': temp}), \
             patch.object(runtime_paths, '_tracker_running', return_value=False), \
             patch.object(Path, 'rename', side_effect=OSError(errno.EXDEV, 'cross-device')):
            old = Path(temp) / runtime_paths.LEGACY_DATA_FOLDER
            (old / 'captures').mkdir(parents=True)
            (old / 'captures' / 'sample.jpg').write_bytes(b'picture')
            new = runtime_paths.initialize_data_dir()
            self.assertEqual((new / 'captures' / 'sample.jpg').read_bytes(), b'picture')
            self.assertFalse(old.exists())

    def test_copy_verification_failure_keeps_original(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict('os.environ', {'APPDATA': temp}), \
             patch.object(runtime_paths, '_tracker_running', return_value=False), \
             patch.object(Path, 'rename', side_effect=OSError(errno.EXDEV, 'cross-device')):
            old = Path(temp) / runtime_paths.LEGACY_DATA_FOLDER
            old.mkdir()
            (old / 'profile.db').write_bytes(b'profile')
            with patch.object(runtime_paths, '_file_manifest', side_effect=[{'a': b'x'}, {'a': b'y'}]):
                with self.assertRaises(RuntimeError):
                    runtime_paths.initialize_data_dir()
            self.assertEqual((old / 'profile.db').read_bytes(), b'profile')

    def test_existing_destination_does_not_overwrite_either_directory(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict('os.environ', {'APPDATA': temp}):
            old = Path(temp) / runtime_paths.LEGACY_DATA_FOLDER
            new = runtime_paths.data_dir()
            old.mkdir()
            new.mkdir()
            (old / 'database_user.db').write_bytes(b'old')
            (new / 'database_user.db').write_bytes(b'new')
            with self.assertRaises(RuntimeError):
                runtime_paths.initialize_data_dir()
            self.assertEqual((old / 'database_user.db').read_bytes(), b'old')
            self.assertEqual((new / 'database_user.db').read_bytes(), b'new')

    def test_wont_move_while_tracker_is_running(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict('os.environ', {'APPDATA': temp}), \
             patch.object(runtime_paths, '_tracker_running', return_value=True):
            old = Path(temp) / runtime_paths.LEGACY_DATA_FOLDER
            old.mkdir()
            with self.assertRaises(RuntimeError):
                runtime_paths.initialize_data_dir()
            self.assertTrue(old.is_dir())
            self.assertFalse(runtime_paths.data_dir().exists())

    def test_first_install_creates_new_directory(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict('os.environ', {'APPDATA': temp}):
            self.assertTrue(runtime_paths.initialize_data_dir().is_dir())


if __name__ == '__main__':
    unittest.main()
