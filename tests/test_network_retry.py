import io
import socket
import ssl
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from application import network_retry


def http(status, headers=None):
    return HTTPError('https://example.invalid/token-secret', status, 'private', headers or {}, io.BytesIO())


class NetworkRetryTests(unittest.TestCase):
    def test_only_explicit_operations_can_be_replayed(self):
        for method, path in [('GET', '/api/v1/leaderboards?mode=Arena'), ('POST', '/api/v1/events'), ('POST', '/api/v1/baselines')]:
            self.assertTrue(network_retry.replay_safe(method, path))
        for method, path in [('POST', '/api/v1/installations'), ('POST', '/api/v1/steam/login'), ('DELETE', '/api/v1/profile'), ('PUT', '/api/v1/profile')]:
            self.assertFalse(network_retry.replay_safe(method, path))

    @patch('application.network_retry.time.sleep')
    @patch('application.network_retry.random.uniform', return_value=1.0)
    def test_transient_read_is_retried_with_bounded_backoff(self, random_delay, sleep):
        operation = Mock(side_effect=[http(503), URLError(TimeoutError()), {'ok': True}])
        self.assertEqual(network_retry.execute(operation, safe=True), {'ok': True})
        self.assertEqual(operation.call_count, 3)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [1.0, 2.0])

    @patch('application.network_retry.time.sleep')
    def test_retry_after_and_terminal_refusals(self, sleep):
        operation = Mock(side_effect=[http(429, {'Retry-After': '12'}), 'ok'])
        self.assertEqual(network_retry.execute(operation, safe=True), 'ok')
        self.assertGreaterEqual(sleep.call_args.args[0], 12)
        sleep.reset_mock()
        for error, safe in [(http(403), True), (http(429, {'Retry-After': '120'}), True),
                            (URLError(ssl.SSLError('bad cert')), True), (http(503), False),
                            (URLError(socket.gaierror(socket.EAI_NONAME, 'bad dns')), True)]:
            operation = Mock(side_effect=error)
            with self.assertRaises(type(error)):
                network_retry.execute(operation, safe=safe)
            self.assertEqual(operation.call_count, 1)
            if isinstance(error, HTTPError):
                error.close()
        sleep.assert_not_called()


if __name__ == '__main__':
    unittest.main()
