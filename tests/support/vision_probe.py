"""Stable synthetic probe of the OpenCV operations used by the tracker."""
import hashlib
import json
import cv2
import numpy as np

rng = np.random.default_rng(42)
image = rng.integers(0, 256, (120, 200, 3), dtype=np.uint8)
gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
mask = cv2.inRange(hsv, np.array([0, 0, 150]), np.array([179, 100, 255]))
template = gray[30:70, 50:90].copy()
match = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
_, peak, _, location = cv2.minMaxLoc(match)
encoded = cv2.imencode('.jpg', image)[1]
decoded = cv2.imdecode(encoded, cv2.IMREAD_GRAYSCALE)
print(json.dumps({'gray':hashlib.sha256(gray.tobytes()).hexdigest(),
                  'mask':hashlib.sha256(mask.tobytes()).hexdigest(),
                  'peak':round(peak, 6), 'location':location,
                  'decoded_shape':decoded.shape}))
