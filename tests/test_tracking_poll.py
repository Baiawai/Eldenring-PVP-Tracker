import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class TrackingPollingTests(unittest.TestCase):
    def test_poll_does_not_overlap_when_server_is_slow(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('Node is not installed')
        source = (ROOT / 'static/app.js').read_text(encoding='utf-8')
        code = source[source.index('function intervall(){'):source.index('\nvar status_capture', source.index('function intervall(){'))]
        script = '''
let trackingPollInFlight = false, previewStatusVersion = 0, calls = [];
const $ = {ajax: options => calls.push(options)};
''' + code + '''
intervall(); intervall();
if (calls.length !== 1) throw Error('overlapping interval requests');
calls[0].complete(); intervall();
if (calls.length !== 2) throw Error('poll did not resume');
'''
        result = subprocess.run([node, '-'], input=script, text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
