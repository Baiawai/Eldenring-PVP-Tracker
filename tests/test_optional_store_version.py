"""The optional metadata adapter is isolated from Store availability checks."""
import io
import json
import unittest
from unittest.mock import Mock, patch
from urllib.error import URLError

try:
    from application import _private_store_version as adapter
except ImportError:
    adapter = None


class _Response(io.BytesIO):
    status = 200


@unittest.skipIf(adapter is None, 'Private Store metadata adapter not present')
class OptionalStoreVersionTests(unittest.TestCase):
    def fetch(self, payload, installed='1.0.10.0'):
        response = _Response(payload)
        opener = Mock()
        opener.open.return_value = response
        with patch.object(adapter.urllib.request, 'build_opener', return_value=opener):
            result = adapter.fetch_version(installed)
        request = opener.open.call_args.args[0]
        self.assertEqual(request.method, 'GET')
        self.assertEqual(opener.open.call_args.kwargs['timeout'], 3.0)
        self.assertEqual(request.get_header('Accept'), 'application/json')
        self.assertIsNone(request.data)
        return result

    def test_reads_only_a_strictly_newer_valid_version(self):
        self.assertEqual(self.fetch(b'{"version":"1.0.11.0"}'), '1.0.11.0')
        for value in ('1.0.10.0', '1.0.9.0', '0.1.0.0', '1.0.65536.0',
                      '1.0.11', '1.0.11.0 suffix', '', None, 42):
            with self.subTest(value=value):
                self.assertIsNone(self.fetch(json.dumps({'version': value}).encode()))

    def test_bad_json_large_payload_and_missing_field_are_unavailable(self):
        for payload in (b'{', b'{}', b'[]', b'\xff', b' ' * 1025):
            with self.subTest(payload=payload[:20]):
                self.assertIsNone(self.fetch(payload))

    def test_network_failure_and_invalid_input_return_no_version(self):
        with patch.object(adapter.urllib.request, 'build_opener') as build:
            build.return_value.open.side_effect = URLError('offline')
            self.assertIsNone(adapter.fetch_version('1.0.10.0'))
            self.assertIsNone(adapter.fetch_version('invalid'))
            self.assertIsNone(adapter.fetch_version('1.0.10.0', timeout=True))
            self.assertEqual(build.call_count, 1)

    def test_redirects_are_not_followed(self):
        self.assertIsNone(adapter._NoRedirect().redirect_request(None, None, 302, '', {}, 'https://example.invalid'))


if __name__ == '__main__':
    unittest.main()
