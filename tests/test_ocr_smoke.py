"""Exercise Tesseract and the image stack without a game or personal captures."""
import os
import subprocess
from pathlib import Path
import unittest
from unittest.mock import patch

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from pytesseract import pytesseract

from application.locale_catalog import classify, messages

ROOT = Path(__file__).resolve().parents[1]
TESSERACT = Path(os.environ.get('ProgramFiles', r'C:\Program Files')) / 'Tesseract-OCR' / 'tesseract.exe'
FONT = Path(os.environ.get('WINDIR', r'C:\Windows')) / 'Fonts' / 'arial.ttf'
MODELS = ROOT / 'application/locales/tessdata'


@unittest.skipUnless(TESSERACT.is_file() and FONT.is_file(), 'Tesseract or the test font is unavailable')
class OcrSmokeTests(unittest.TestCase):
    def test_all_game_models_are_visible_in_a_path_with_spaces(self):
        required = {'fra', 'eng', 'deu', 'ita', 'spa', 'por', 'pol', 'rus',
                    'jpn', 'kor', 'chi_sim', 'chi_tra', 'tha', 'ara'}
        environment = os.environ.copy()
        environment['TESSDATA_PREFIX'] = str(MODELS)
        result = subprocess.run([str(TESSERACT), '--list-langs'], env=environment,
                                capture_output=True, text=True, encoding='utf-8', timeout=20, check=True)
        self.assertTrue(required.issubset(set(result.stdout.splitlines())), result.stdout)

    def test_synthetic_victory_messages_in_french_and_english(self):
        old_cmd = pytesseract.tesseract_cmd
        pytesseract.tesseract_cmd = str(TESSERACT)
        try:
            for language, model in [('frafr', 'fra'), ('engus', 'eng')]:
                with self.subTest(language=language):
                    if not (MODELS / (model + '.traineddata')).is_file():
                        self.skipTest('OCR model missing: ' + model)
                    image = Image.new('RGB', (1000, 120), 'white')
                    ImageDraw.Draw(image).text((20, 25), messages()[language]['arena:88050'],
                                                fill='black', font=ImageFont.truetype(str(FONT), 48))
                    gray = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)
                    with patch.dict(os.environ, {'TESSDATA_PREFIX': str(MODELS)}):
                        text = pytesseract.image_to_string(gray, lang=model, config='--psm 7')
                    self.assertTrue(any(event['event'] == 'arena_victory' for event in classify(text, language)), repr(text))
        finally:
            pytesseract.tesseract_cmd = old_cmd
