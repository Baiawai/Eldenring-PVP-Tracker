"""Monitor detection and capture geometry without reading the real screen."""
from unittest import TestCase
from unittest.mock import patch
from io import BytesIO
from tempfile import TemporaryDirectory
from pathlib import Path
import numpy as np
from PIL import Image
import cv2
from application import capture_display


class CaptureDisplayTests(TestCase):
    def test_frame_bytes_match_saved_file_and_previous_decoded_pixels(self):
        image = Image.fromarray(np.random.default_rng(42).integers(0, 256, (120, 200, 3), dtype=np.uint8))
        previous = BytesIO()
        image.save(previous, 'JPEG', optimize=True, quality=95)
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'frame.jpg'
            encoded = capture_display.write_tracker_frame(image, path)
            self.assertEqual(path.read_bytes(), encoded)
            old_pixels = cv2.imdecode(np.frombuffer(previous.getvalue(), dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
            new_pixels = cv2.imdecode(np.frombuffer(encoded, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
            np.testing.assert_array_equal(old_pixels, new_pixels)

    def test_steam_probe_stays_inside_displays_of_different_heights(self):
        for width, height in ((1366, 768), (1600, 900), (1920, 1080), (3840, 2160), (2, 1)):
            with self.subTest(size=(width, height)):
                region = capture_display.steam_detection_region(width, height)
                left, top, region_width, region_height = region
                self.assertGreater(region_width, 0)
                self.assertGreater(region_height, 0)
                self.assertLessEqual(left + region_width, width)
                self.assertLessEqual(top + region_height, height)
                with patch.object(capture_display.ImageGrab, 'grab', return_value=Image.new('RGB', (1, 1))) as grab:
                    capture_display.capture({'x': -100, 'y': 20, 'width': width, 'height': height}, region=region)
                    grab.assert_called_once()
        self.assertEqual(capture_display.steam_detection_region(1920, 1080), (0, 972, 600, 100))

    def test_steam_probe_rejects_invalid_display_dimensions(self):
        with self.assertRaises(ValueError):
            capture_display.steam_detection_region(1920, 0)

    def test_tracker_crop_matches_the_previous_disk_jpeg_pipeline(self):
        rng = np.random.default_rng(17)
        for width, height in ((333, 201), (1920, 1080)):
            with self.subTest(size=(width, height)), TemporaryDirectory() as directory:
                screenshot = Image.fromarray(rng.integers(0, 256, (height, width, 3), dtype=np.uint8))
                path = Path(directory) / 'frame.jpg'
                screenshot.save(path)
                with Image.open(path) as original:
                    expected = original.crop((int(width / 3.2), int(height / 5),
                                              int(width - width / 3.2), int(height - height / 20)))
                actual = capture_display.tracker_crop(screenshot)
                self.assertEqual(actual.size, expected.size)
                self.assertEqual(actual.tobytes(), expected.tobytes())
                old_bytes, new_bytes = BytesIO(), BytesIO()
                expected.save(old_bytes, 'JPEG', optimize=True, quality=95)
                actual.save(new_bytes, 'JPEG', optimize=True, quality=95)
                self.assertEqual(old_bytes.getvalue(), new_bytes.getvalue())

    def test_detects_game_monitor_in_virtual_desktop_coordinates(self):
        with patch.object(capture_display.win32gui, 'FindWindow', return_value=42), \
             patch.object(capture_display.win32gui, 'IsIconic', return_value=False), \
             patch.object(capture_display.win32api, 'MonitorFromWindow', return_value=99), \
             patch.object(capture_display.win32api, 'GetMonitorInfo', return_value={
                 'Monitor':(-1920, 20, 0, 1100), 'Device':'DISPLAY2'}):
            self.assertEqual(capture_display.game_display(),
                             {'name':'DISPLAY2', 'x':-1920, 'y':20, 'width':1920, 'height':1080})

    def test_game_absent_or_minimized_has_no_display(self):
        with patch.object(capture_display.win32gui, 'FindWindow', return_value=0):
            self.assertIsNone(capture_display.game_display())
        with patch.object(capture_display.win32gui, 'FindWindow', return_value=42), \
             patch.object(capture_display.win32gui, 'IsIconic', return_value=True):
            self.assertIsNone(capture_display.game_display())

    def test_monitor_disappearing_has_no_display(self):
        with patch.object(capture_display.win32gui, 'FindWindow', return_value=42), \
             patch.object(capture_display.win32gui, 'IsIconic', return_value=False), \
             patch.object(capture_display.win32api, 'MonitorFromWindow', return_value=0):
            self.assertIsNone(capture_display.game_display())

    def test_selected_display_and_subregion_use_virtual_desktop_coordinates(self):
        display = {'x':-100, 'y':20, 'width':100, 'height':80}
        with patch.object(capture_display.ImageGrab, 'grab', return_value=Image.new('RGB', (20, 10))) as grab:
            capture_display.capture(display, region=(10, 5, 20, 10))
            grab.assert_called_once_with(bbox=(-90, 25, -70, 35), all_screens=True)
            with self.assertRaises(ValueError):
                capture_display.capture(display, region=(90, 0, 20, 10))
