import base64
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import repo_cloner as app


class EnvTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        environment = patch.dict(os.environ, {}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)

    def test_formats_and_existing_environment(self):
        path = self.root / ".env"
        path.write_text(
            "# comment\n\nexport EMAIL = 'me@example.com'\n"
            'TOKEN="abc#def==" # comment\n'
            "RAW=abc#def== # comment\nEMPTY=\nCOMMENT= # empty\n"
            "KEEP=file\nDUP=first\nDUP=last\n",
            encoding="utf-8-sig",
        )
        os.environ["KEEP"] = "shell"
        app.load_env(path)
        self.assertEqual(dict(os.environ), {
            "EMAIL": "me@example.com", "TOKEN": "abc#def==",
            "RAW": "abc#def==", "EMPTY": "", "COMMENT": "",
            "KEEP": "shell", "DUP": "last",
        })

    def test_missing_file_is_optional(self):
        app.load_env(self.root / ".env")
        self.assertEqual(dict(os.environ), {})

    def test_invalid_file_does_not_leak_or_partially_load(self):
        for line in ("secret", 'TOKEN="secret', 'TOKEN="secret" junk',
                     "TOKEN=secret\x00"):
            with self.subTest(line=line):
                path = self.root / ".env"
                path.write_text("VALID=value\n" + line, encoding="utf-8")
                with self.assertRaises(app.ClonerError) as caught:
                    app.load_env(path)
                self.assertNotIn("secret", str(caught.exception))
                self.assertIn(":2", str(caught.exception))
                self.assertNotIn("VALID", os.environ)

    def test_run_loads_config_sibling_before_authentication(self):
        config = self.root / "repositories.json"
        config.write_text(json.dumps({"sources": [{
            "name": "example", "provider": "bitbucket-cloud",
            "workspace": "workspace", "project": "P",
            "usernameEnv": "EMAIL", "tokenEnv": "TOKEN",
        }]}), encoding="utf-8")
        (self.root / ".env").write_text(
            "EMAIL=me@example.com\nTOKEN=secret\n", encoding="utf-8",
        )
        headers = []

        def get(api, url):
            headers.append(api.headers["Authorization"])
            return {"values": []}

        with patch.object(app.Api, "get", get), redirect_stdout(io.StringIO()):
            self.assertEqual(app.run(config, dry_run=True), 0)
        expected = base64.b64encode(b"me@example.com:secret").decode()
        self.assertEqual(headers, ["Basic " + expected])
        self.assertFalse((self.root / "clones").exists())