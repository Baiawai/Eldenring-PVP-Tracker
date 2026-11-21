import importlib.util
import sqlite3
import sys
import tempfile
import types
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from application import steam_game_language


def write_manifest(root, language, app_id='1245620'):
    path = root / 'steamapps' / 'appmanifest_1245620.acf'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'"AppState" {{ "appid" "{app_id}" "UserConfig" {{ "language" "{language}" }} }}', encoding='utf-8')
    return path


class SteamGameLanguageTests(unittest.TestCase):
    def test_manifest_selection_is_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = write_manifest(root, 'french')
            before = path.read_bytes()
            self.assertEqual(steam_game_language.detect(root), 'frafr')
            self.assertEqual(path.read_bytes(), before)

    def test_other_library_and_steam_language_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'steam'
            library = Path(tmp) / 'another library'
            write_manifest(library, 'latam')
            config = root / 'steamapps' / 'libraryfolders.vdf'
            config.parent.mkdir(parents=True)
            escaped = str(library).replace('\\', '\\\\')
            config.write_text('"libraryfolders" { "1" { "path" "' + escaped + '" } }', encoding='utf-8')
            self.assertEqual(steam_game_language.detect(root), 'spaar')

    def test_missing_unsupported_malformed_and_conflicting_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertIsNone(steam_game_language.detect(root))
            path = write_manifest(root, 'unsupported')
            self.assertIsNone(steam_game_language.detect(root))
            path.write_text('"AppState" { "UserConfig" { "language" "french" }', encoding='utf-8')
            self.assertIsNone(steam_game_language.detect(root))
            write_manifest(root, 'french', app_id='123')
            self.assertIsNone(steam_game_language.detect(root))
            write_manifest(root, 'french')
            second = root / 'other'
            write_manifest(second, 'english')
            escaped = str(second).replace('\\', '\\\\')
            (root / 'steamapps' / 'libraryfolders.vdf').write_text('"libraryfolders" { "1" "' + escaped + '" }', encoding='utf-8')
            self.assertIsNone(steam_game_language.detect(root))

    def test_initialize_migrates_existing_and_detects_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            init = types.ModuleType('application.init')
            init.database_setting = str(Path(tmp) / 'settings.db')
            spec = importlib.util.spec_from_file_location('_steam_test_game_language', Path(__file__).resolve().parents[1] / 'application' / 'game_language.py')
            module = importlib.util.module_from_spec(spec)
            with patch.dict(sys.modules, {'application.init': init}):
                spec.loader.exec_module(module)
            with patch.object(steam_game_language, 'detect', return_value='jpnjp') as detect:
                self.assertEqual(module.initialize('fra', first_run=False), 'frafr')
                detect.assert_not_called()
                self.assertEqual(module.initialize('eng', first_run=True), 'frafr')
                detect.assert_not_called()
                with closing(sqlite3.connect(init.database_setting)) as con, con:
                    con.execute('DELETE FROM game_language')
                self.assertEqual(module.initialize('eng', first_run=True), 'jpnjp')
                self.assertEqual(module.initialize('fra', first_run=True), 'jpnjp')
                detect.assert_called_once()

    def test_first_run_falls_back_when_steam_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            init = types.ModuleType('application.init')
            init.database_setting = str(Path(tmp) / 'settings.db')
            spec = importlib.util.spec_from_file_location('_steam_test_game_language_fallback', Path(__file__).resolve().parents[1] / 'application' / 'game_language.py')
            module = importlib.util.module_from_spec(spec)
            with patch.dict(sys.modules, {'application.init': init}):
                spec.loader.exec_module(module)
            with patch.object(steam_game_language, 'detect', return_value=None):
                self.assertEqual(module.initialize('fra', first_run=True), 'engus')


if __name__ == '__main__':
    unittest.main()
