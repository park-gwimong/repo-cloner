import base64
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import repo_cloner as app


class JsonAuthTests(unittest.TestCase):
    def test_json_credentials_ignore_environment_and_dotenv(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / 'repositories.json'
            config.write_text(json.dumps({'sources': [{
                'name': 'example', 'provider': 'bitbucket-cloud',
                'workspace': 'workspace', 'project': 'P',
                'username': 'me@example.com', 'token': 'json-secret',
            }]}), encoding='utf-8')
            (root / '.env').write_text('invalid dotenv contents', encoding='utf-8')
            headers = []

            def get(api, url):
                headers.append(api.headers['Authorization'])
                return {'values': []}

            with patch.dict('os.environ', {'BITBUCKET_CLOUD_TOKEN': 'other'}), \
                    patch.object(app.Api, 'get', get), redirect_stdout(io.StringIO()):
                self.assertEqual(app.run(config, dry_run=True), 0)
            expected = base64.b64encode(b'me@example.com:json-secret').decode()
            self.assertEqual(headers, ['Basic ' + expected])
            self.assertFalse((root / 'clones').exists())

    def test_bearer_and_anonymous_authentication(self):
        self.assertEqual(app.Api('https://example.com', {'token': 'secret'}).headers['Authorization'], 'Bearer secret')
        with patch.dict('os.environ', {'GITHUB_TOKEN': 'secret'}):
            self.assertNotIn('Authorization', app.Api('https://example.com', {}).headers)

    def test_invalid_and_legacy_credentials_fail_without_exposing_values(self):
        for source in (
            {'tokenEnv': 'secret'}, {'usernameEnv': 'secret'},
            {'username': 'secret'}, {'token': ''}, {'token': None},
            {'token': 123}, {'token': 'secret\r\n'},
            {'username': 'secret:invalid', 'token': 'secret'},
            {'username': '', 'token': 'secret'},
        ):
            with self.subTest(source=source), self.assertRaises(app.ClonerError) as caught:
                app.Api('https://example.com', source)
            self.assertNotIn('secret', str(caught.exception))
