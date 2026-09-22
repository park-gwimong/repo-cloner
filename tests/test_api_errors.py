from contextlib import redirect_stderr
from http.client import IncompleteRead
import io
import socket
import ssl
import unittest
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError, URLError

import repo_cloner as app


class ApiErrorTests(unittest.TestCase):
    def setUp(self):
        self.api = app.Api('https://example.com', {'token': 'secret'})
        self.response = MagicMock()
        self.response.__enter__.return_value = io.StringIO('{"values": []}')
        self.output = io.StringIO()

    def test_timeout_retries_and_succeeds(self):
        with patch.object(self.api.opener, 'open', side_effect=[TimeoutError('secret'), self.response]) as request, \
                patch.object(app.time, 'sleep') as sleep, redirect_stderr(self.output):
            self.assertEqual(self.api.get('https://example.com/repos'), {'values': []})
        self.assertEqual(request.call_count, 2)
        sleep.assert_called_once_with(1)
        self.assertIn('retrying (2/3)', self.output.getvalue())
        self.assertNotIn('secret', self.output.getvalue())

    def test_transient_failures_stop_after_three_attempts(self):
        for error, expected in (
            (URLError(TimeoutError('secret')), 'timed out'),
            (URLError(socket.gaierror('secret')), 'DNS lookup failed'),
            (ConnectionResetError('secret'), 'connection failed'),
            (IncompleteRead(b'secret'), 'complete response'),
            (HTTPError('https://example.com', 503, 'secret', {}, None), 'HTTP 503'),
        ):
            with self.subTest(expected=expected), \
                    patch.object(self.api.opener, 'open', side_effect=error) as request, \
                    patch.object(app.time, 'sleep') as sleep, redirect_stderr(self.output):
                with self.assertRaises(app.ClonerError) as caught:
                    self.api.get('https://example.com/repos')
            self.assertEqual(request.call_count, 3)
            self.assertEqual(sleep.call_count, 2)
            self.assertIn(expected, str(caught.exception))
            self.assertIn('3 attempts', str(caught.exception))
            self.assertNotIn('secret', str(caught.exception))

    def test_tls_and_auth_fail_without_retry_or_secret_leak(self):
        for error, expected in (
            (URLError(ssl.SSLCertVerificationError('secret')), 'TLS'),
            (HTTPError('https://example.com', 401, 'secret', {}, None), 'HTTP 401'),
            (HTTPError('https://example.com', 403, 'secret', {}, None), 'HTTP 403'),
        ):
            with self.subTest(expected=expected), \
                    patch.object(self.api.opener, 'open', side_effect=error) as request, \
                    patch.object(app.time, 'sleep') as sleep:
                with self.assertRaises(app.ClonerError) as caught:
                    self.api.get('https://example.com/repos')
            self.assertEqual(request.call_count, 1)
            sleep.assert_not_called()
            self.assertIn(expected, str(caught.exception))
            self.assertNotIn('secret', str(caught.exception))

    def test_invalid_json_has_specific_error_and_is_not_retried(self):
        self.response.__enter__.return_value = io.StringIO('<html>secret</html>')
        with patch.object(self.api.opener, 'open', return_value=self.response) as request:
            with self.assertRaises(app.ClonerError) as caught:
                self.api.get('https://example.com/repos')
        self.assertEqual(request.call_count, 1)
        self.assertIn('invalid JSON', str(caught.exception))
        self.assertNotIn('secret', str(caught.exception))
