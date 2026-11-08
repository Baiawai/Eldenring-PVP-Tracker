"""Read the character card from one screenshot without changing user data."""
import base64
import io
import re
import unicodedata
from PIL import ImageEnhance, ImageOps
import pytesseract


def _crop(image, bounds):
    width, height = image.size
    return image.crop(tuple(round(value * size) for value, size in zip(bounds, (width, height, width, height))))


def _text_image(image):
    image = ImageOps.grayscale(image)
    return ImageEnhance.Contrast(image.resize((image.width * 3, image.height * 3))).enhance(2)


def read(image, language):
    """Read the card when its language-independent play-time field is visible."""
    elapsed = _text_image(_crop(image, (.41, .423, .49, .454)))
    elapsed_text = pytesseract.image_to_string(elapsed, lang='eng', config='--psm 7 -c tessedit_char_whitelist=0123456789:').strip()
    if not re.fullmatch(r'\d{1,4}:[0-5]\d:[0-5]\d', elapsed_text):
        return None
    name_image = _text_image(_crop(image, (.25, .352, .49, .386)))
    name = ' '.join(pytesseract.image_to_string(name_image, lang=language + ('+eng' if language != 'eng' else ''), config='--psm 7').split())
    level_image = _text_image(_crop(image, (.318, .423, .36, .454)))
    level_text = pytesseract.image_to_string(level_image, lang='eng', config='--psm 7 -c tessedit_char_whitelist=0123456789').strip()
    if not re.fullmatch(r'\d{1,3}', level_text) or not 1 <= int(level_text) <= 713:
        return None
    if not 1 <= len(name) <= 16 or not any(c.isalnum() for c in name) or any(unicodedata.category(c).startswith('C') for c in name):
        return None
    avatar = _crop(image, (.5, 1/3, 1 - 1/4.5, 1 - 1/2.5)).convert('RGB')
    out = io.BytesIO()
    avatar.save(out, format='JPEG', quality=95)
    return {'name':name, 'level':int(level_text), 'avatar':base64.b64encode(out.getvalue()).decode('ascii')}
