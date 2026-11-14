"""Migration checks use isolated folders, never the real tracker data."""
import errno
import os
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

    def test_visible_package_path_is_selected_only_for_the_active_database(self):
        with tempfile.TemporaryDirectory() as temp, \
             patch.dict('os.environ', {'APPDATA': str(Path(temp) / 'roaming'), 'LOCALAPPDATA': str(Path(temp) / 'local')}), \
             patch.object(runtime_paths, 'package_family_name', return_value='Example.Tracker_family'):
            logical = runtime_paths.data_dir()
            private = Path(temp) / 'local' / 'Packages' / 'Example.Tracker_family' / 'LocalCache' / 'Roaming' / runtime_paths.DATA_FOLDER
            logical.mkdir(parents=True)
            private.mkdir(parents=True)
            (private / 'database_user.db').write_bytes(b'private profile')
            (logical / 'database_user.db').write_bytes(b'other profile')
            self.assertEqual(runtime_paths.accessible_data_directories(), [logical])
            (logical / 'database_user.db').unlink()
            os.link(private / 'database_user.db', logical / 'database_user.db')
            self.assertEqual(runtime_paths.accessible_data_directories(), [private])
            (logical / 'database_setting.db').write_bytes(b'normal settings')
            self.assertEqual(set(runtime_paths.accessible_data_directories()), {private, logical})
            self.assertEqual((private / 'database_user.db').read_bytes(), b'private profile')

    def test_unpacked_app_does_not_redirect_to_an_existing_store_directory(self):
        with tempfile.TemporaryDirectory() as temp, \
             patch.dict('os.environ', {'APPDATA': str(Path(temp) / 'roaming'), 'LOCALAPPDATA': str(Path(temp) / 'local')}), \
             patch.object(runtime_paths, 'FROZEN', False):
            self.assertIsNone(runtime_paths.package_family_name())
            self.assertEqual(runtime_paths.accessible_data_directories(), [runtime_paths.data_dir()])

    def test_current_package_family_is_queried_from_windows(self):
        family = 'Example.Tracker_family'
        class FamilyApi:
            def __call__(self, size, buffer):
                if buffer is None:
                    size._obj.value = len(family) + 1
                    return 122
                buffer.value = family
                return 0
        with patch.object(runtime_paths, 'FROZEN', True), \
             patch.object(runtime_paths.ctypes, 'windll') as windll:
            windll.kernel32.GetCurrentPackageFamilyName = FamilyApi()
            self.assertEqual(runtime_paths.package_family_name(), family)


if __name__ == '__main__':
    unittest.main()
