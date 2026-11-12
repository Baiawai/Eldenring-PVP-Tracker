"""Check the limited-thread OCR against pytesseract without using game data."""
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from pytesseract import pytesseract

from application import ocr_runner
from application.locale_catalog import messages
from application.runtime_paths import tesseract_path

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / 'application' / 'locales' / 'tessdata'
FONTS = Path(os.environ.get('WINDIR', r'C:\Windows')) / 'Fonts'
LOCALES = (
    ('frafr', 'fra', 'arial.ttf'), ('engus', 'eng', 'arial.ttf'),
    ('deude', 'deu', 'arial.ttf'), ('itait', 'ita', 'arial.ttf'),
    ('spaes', 'spa', 'arial.ttf'), ('spaar', 'spa', 'arial.ttf'),
    ('porbr', 'por', 'arial.ttf'), ('polpl', 'pol', 'arial.ttf'),
    ('rusru', 'rus', 'arial.ttf'), ('jpnjp', 'jpn', 'msgothic.ttc'),
    ('korkr', 'kor', 'malgun.ttf'), ('zhocn', 'chi_sim', 'msyh.ttc'),
    ('zhotw', 'chi_tra', 'simsun.ttc'), ('thath', 'tha', 'tahoma.ttf'),
    ('araae', 'ara', 'arial.ttf'),
)


@unittest.skipUnless(Path(tesseract_path()).is_file(), 'Tesseract is unavailable')
class OcrRunnerTests(unittest.TestCase):
    def test_overlay_text_detection_matches_pytesseract(self):
        old_cmd = pytesseract.tesseract_cmd
        pytesseract.tesseract_cmd = tesseract_path()
        try:
            with patch.dict(os.environ, {'TESSDATA_PREFIX': str(MODELS)}):
                for text in ('', 'STEAM', 'OPEN WORLD'):
                    with self.subTest(text=text):
                        image = Image.new('RGB', (600, 100), 'black')
                        ImageDraw.Draw(image).text((20, 25), text, fill='white',
                                                   font=ImageFont.truetype(str(FONTS / 'arial.ttf'), 35))
                        expected = pytesseract.image_to_string(image)
                        actual = ocr_runner.image_to_string(image)
                        self.assertEqual(actual, expected)
                        self.assertEqual('STEAM' in actual, 'STEAM' in expected)
        finally:
            pytesseract.tesseract_cmd = old_cmd

    def test_thread_limit_is_local_and_respects_an_existing_choice(self):
        old_cmd = pytesseract.tesseract_cmd
        pytesseract.tesseract_cmd = tesseract_path()
        try:
            with patch.dict(os.environ, {'TESSDATA_PREFIX': str(MODELS)}):
                os.environ.pop('OMP_THREAD_LIMIT', None)
                with patch.object(ocr_runner.subprocess, 'Popen', wraps=subprocess.Popen) as launch:
                    ocr_runner.image_to_string(Image.new('RGB', (80, 40), 'white'), lang='eng')
                self.assertEqual(launch.call_args.kwargs['env']['OMP_THREAD_LIMIT'], '1')
                self.assertNotIn('OMP_THREAD_LIMIT', os.environ)
                os.environ['OMP_THREAD_LIMIT'] = '3'
                with patch.object(ocr_runner.subprocess, 'Popen', wraps=subprocess.Popen) as launch:
                    ocr_runner.image_to_string(Image.new('RGB', (80, 40), 'white'), lang='eng')
                self.assertEqual(launch.call_args.kwargs['env']['OMP_THREAD_LIMIT'], '3')
        finally:
            pytesseract.tesseract_cmd = old_cmd

    def test_missing_model_raises_a_tesseract_error(self):
        old_cmd = pytesseract.tesseract_cmd
        pytesseract.tesseract_cmd = tesseract_path()
        try:
            with patch.dict(os.environ, {'TESSDATA_PREFIX': str(MODELS)}):
                with self.assertRaises(pytesseract.TesseractError):
                    ocr_runner.image_to_string(Image.new('RGB', (80, 40), 'white'), lang='missing_model')
        finally:
            pytesseract.tesseract_cmd = old_cmd

    def test_same_output_as_pytesseract_for_supported_languages(self):
        old_cmd = pytesseract.tesseract_cmd
        pytesseract.tesseract_cmd = tesseract_path()
        try:
            with patch.dict(os.environ, {'TESSDATA_PREFIX': str(MODELS)}):
                for locale, model, font_name in LOCALES:
                    with self.subTest(locale=locale):
                        if not (MODELS / (model + '.traineddata')).is_file() or not (FONTS / font_name).is_file():
                            self.skipTest('OCR model or font unavailable')
                        image = Image.new('RGB', (1100, 160), 'white')
                        ImageDraw.Draw(image).text((20, 40), messages()[locale]['arena:88050'],
                                                   fill='black', font=ImageFont.truetype(str(FONTS / font_name), 38))
                        gray = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)
                        before = dict(os.environ)
                        expected = pytesseract.image_to_string(gray, lang=model, config='--psm 6 --oem 1')
                        actual = ocr_runner.image_to_string(gray, lang=model, config='--psm 6 --oem 1')
                        self.assertEqual(actual, expected)
                        self.assertEqual(dict(os.environ), before)
                        expected_positions = pytesseract.image_to_data(
                            gray, lang=model, config='--psm 6 --oem 1', output_type=pytesseract.Output.DICT)
                        actual_positions = ocr_runner.image_to_data(gray, lang=model, config='--psm 6 --oem 1')
                        self.assertEqual(actual_positions, expected_positions)
        finally:
            pytesseract.tesseract_cmd = old_cmd


if __name__ == '__main__':
    unittest.main()
