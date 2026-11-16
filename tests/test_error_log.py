import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from application import error_log


class ErrorLogTests(unittest.TestCase):
    def test_missing_log_is_not_created_and_cannot_be_opened(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(error_log, 'data_dir', return_value=Path(temp) / 'data'), \
                patch.object(error_log, '_private_data_dir', return_value=None), patch.object(error_log.tempfile, 'gettempdir', return_value=temp):
            path, exists = error_log.selected_log()
            self.assertEqual(path, Path(temp) / 'data' / 'tracker-errors.log')
            self.assertFalse(exists)
            self.assertFalse(error_log.open_log())
            self.assertFalse(path.exists())

    def test_latest_existing_log_is_opened_without_accepting_a_path(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(error_log, 'data_dir', return_value=Path(temp) / 'data'), \
                patch.object(error_log, '_private_data_dir', return_value=None), patch.object(error_log.tempfile, 'gettempdir', return_value=temp):
            main = Path(temp) / 'data' / 'tracker-errors.log'
            fallback = Path(temp) / 'Elden Ring PvP Tracker' / 'tracker-errors.log'
            main.parent.mkdir(); fallback.parent.mkdir()
            main.write_text('first'); fallback.write_text('latest')
            os.utime(main, (100, 100)); os.utime(fallback, (200, 200))
            with patch.object(error_log.os, 'startfile') as start:
                self.assertTrue(error_log.open_log())
                start.assert_called_once_with(str(fallback))

    def test_store_private_log_is_selected_when_logical_path_is_missing(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(error_log, 'data_dir', return_value=Path(temp) / 'logical'), \
                patch.object(error_log, '_private_data_dir', return_value=Path(temp) / 'private'), patch.object(error_log.tempfile, 'gettempdir', return_value=temp):
            private = Path(temp) / 'private' / 'tracker-errors.log'
            private.parent.mkdir(); private.write_text('error')
            self.assertEqual(error_log.selected_log(), (private, True))


if __name__ == '__main__':
    unittest.main()
