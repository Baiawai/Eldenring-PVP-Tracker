"""Validate a proposed character card without storing screenshots or profiles."""
import unittest
from unittest.mock import patch
from PIL import Image
from application import profile_capture

class ProfileCaptureTests(unittest.TestCase):
    def setUp(self):
        self.image = Image.new('RGB', (1920, 1080), 'black')

    def test_recognizes_a_unicode_name_level_and_image(self):
        with patch.object(profile_capture.pytesseract, 'image_to_string', side_effect=['12:34:56', '勇者', '150']) as ocr:
            result = profile_capture.read(self.image, 'jpn')
        self.assertEqual((result['name'], result['level']), ('勇者', 150))
        self.assertTrue(result['avatar'])
        self.assertEqual(ocr.call_args_list[1].kwargs['lang'], 'jpn+eng')

    def test_rejects_missing_card_or_invalid_level(self):
        with patch.object(profile_capture.pytesseract, 'image_to_string', return_value=''):
            self.assertIsNone(profile_capture.read(self.image, 'fra'))
        with patch.object(profile_capture.pytesseract, 'image_to_string', side_effect=['1:02:03', 'Name', '999']):
            self.assertIsNone(profile_capture.read(self.image, 'fra'))
