"""Store version checks operate before any package or user data is touched."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from application.version import APP_VERSION
from store.check_release_version import validate_release, validate_store_version


ROOT = Path(__file__).resolve().parents[1]


class ReleaseVersionTests(unittest.TestCase):
    def test_actual_application_and_executable_metadata_agree(self):
        metadata = (ROOT / 'file_version_info.txt').read_text(encoding='utf-8')
        validate_release(APP_VERSION, APP_VERSION, metadata)
        self.assertIn("version=str(root / 'file_version_info.txt')",
                      (ROOT / 'store/tracker.spec').read_text(encoding='utf-8'))

    def test_store_version_components_are_validated(self):
        self.assertEqual(validate_store_version('1.0.10.0'), (1, 0, 10, 0))
        self.assertEqual(validate_store_version('1.1.0.0'), (1, 1, 0, 0))
        for version in ('', '1.1.0', '1.1.0.0.0', '0.1.0.0', '1.1.0.1',
                        '1.65536.0.0', '1.-1.0.0', '1.１.0.0'):
            with self.subTest(version=version), self.assertRaises(ValueError):
                validate_store_version(version)

    def test_package_and_each_executable_version_must_match(self):
        metadata = (ROOT / 'file_version_info.txt').read_text(encoding='utf-8')
        with self.assertRaises(ValueError):
            validate_release('1.1.0.0', APP_VERSION, metadata)
        for old, new in (('filevers=(1,0,10,0)', 'filevers=(1,0,0,0)'),
                         ('prodvers=(1,0,10,0)', 'prodvers=(1,0,0,0)'),
                         ("StringStruct(u'FileVersion', u'1.0.10.0')", "StringStruct(u'FileVersion', u'1.0.0.0')"),
                         ("StringStruct(u'ProductVersion', u'1.0.10.0')", "StringStruct(u'ProductVersion', u'1.0.0.0')")):
            with self.subTest(field=old), self.assertRaises(ValueError):
                self.assertIn(old, metadata)
                validate_release(APP_VERSION, APP_VERSION, metadata.replace(old, new))

    @unittest.skipUnless(os.name == 'nt', 'PowerShell build guard is Windows-specific')
    def test_wrong_explicit_version_is_rejected_before_build(self):
        with tempfile.TemporaryDirectory() as directory:
            output, work = Path(directory) / 'output', Path(directory) / 'work'
            result = subprocess.run([
                'powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                '-File', str(ROOT / 'store/build.ps1'), '-Version', '1.1.0.0', '-ExecutableOnly',
                '-OutputDir', str(output), '-WorkDir', str(work), '-TesseractDir', directory,
            ], cwd=ROOT, capture_output=True, text=True, timeout=30)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Package version does not match application/version.py', result.stderr)
            self.assertFalse(output.exists())
            self.assertFalse(work.exists())


if __name__ == '__main__':
    unittest.main()
