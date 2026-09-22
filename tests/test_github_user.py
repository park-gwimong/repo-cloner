from contextlib import redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

import repo_cloner as app
from repo_cloner_tui import TerminalUI


class GitHubUserTests(unittest.TestCase):
    def setUp(self):
        self.source = {"name": "my-account", "provider": "github-user", "token": "test-secret"}

    def test_personal_pagination_and_owner_scope(self):
        item = {"name": "repo", "ssh_url": "git@github.com:me/repo.git", "clone_url": "https://github.com/me/repo.git"}
        with patch.object(app.Api, "get", side_effect=[[item] * 100, [item]]) as get:
            repos = list(app.repositories(self.source, "ssh"))
        self.assertEqual(len(repos), 101)
        self.assertEqual(repos[0].url, item["ssh_url"])
        for page, call in enumerate(get.call_args_list, 1):
            url = urlsplit(call.args[0])
            self.assertEqual(url.path, "/user/repos")
            self.assertEqual(parse_qs(url.query), {"affiliation": ["owner"], "per_page": ["100"], "page": [str(page)]})

    def test_https_enterprise_and_bearer_auth(self):
        source = dict(self.source, username="ignored", apiUrl="https://github.example.com/api/v3")
        with patch.object(app.Api, "get", autospec=True, return_value=[
            {"name": "repo", "clone_url": "https://github.example.com/me/repo.git"}
        ]) as get:
            repo = list(app.repositories(source, "https"))[0]
        self.assertEqual(repo.url, "https://github.example.com/me/repo.git")
        api, url = get.call_args.args
        self.assertEqual(api.headers["Authorization"], "Bearer test-secret")
        self.assertTrue(url.startswith("https://github.example.com/api/v3/user/repos?"))

    def test_account_login_comes_from_api(self):
        with patch.object(app.Api, "get", return_value={"login": "real-login", "type": "User"}) as get:
            self.assertEqual(app.github_account(dict(self.source, username="wrong-name")), "real-login")
        get.assert_called_once_with("https://api.github.com/user")

    def test_invalid_configs_and_responses_fail(self):
        for source in ({"provider": "github-user"}, dict(self.source, organization="org")):
            with patch.object(app.Api, "get") as get:
                with self.assertRaises(app.ClonerError):
                    list(app.repositories(source, "ssh"))
                get.assert_not_called()
        for response in ({"message": "bad"}, None):
            with patch.object(app.Api, "get", return_value=response):
                with self.assertRaises(app.ClonerError):
                    list(app.repositories(self.source, "ssh"))
        for response in ([], {}, {"login": "../outside"}):
            with patch.object(app.Api, "get", return_value=response):
                with self.assertRaises(app.ClonerError):
                    app.github_account(self.source)

    def test_personal_setup_does_not_ask_for_account_name(self):
        ui = object.__new__(TerminalUI)
        with patch.object(ui, "choose", side_effect=[0, 1, 0, 0]), \
                patch.object(ui, "edit", side_effect=[str(Path.cwd()), "https://api.github.com"]) as edit, \
                patch.object(app, "github_account", return_value="real-login"), redirect_stdout(io.StringIO()):
            config = ui.configure({"username": "ignored", "token": "test-secret"}, Path("repositories.json"))
        self.assertEqual(edit.call_count, 2)  # Destination and API URL only.
        self.assertEqual(config["sources"], [{"provider": "github-user", "name": "real-login",
                         "token": "test-secret", "apiUrl": "https://api.github.com"}])

    def test_personal_setup_authentication_failure_or_missing_token_stops(self):
        for credentials in ({}, {"token": "bad-token"}):
            ui = object.__new__(TerminalUI)
            with patch.object(ui, "choose", side_effect=[0, 1, 0]), \
                    patch.object(ui, "edit", side_effect=[str(Path.cwd()), "https://api.github.com"]), \
                    patch.object(app, "github_account", side_effect=app.ClonerError("API HTTP 401")), \
                    redirect_stdout(io.StringIO()):
                with self.assertRaises(app.ClonerError):
                    ui.configure(credentials, Path("repositories.json"))

    def test_selected_repository_path_filters_and_dry_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = dict(self.source, include=["api-*"], exclude=["*-archive"])
            config = {"destination": str(root / "copies"), "sources": [source]}
            ui = Mock()
            ui.select.return_value = [0]
            items = [{"name": name, "ssh_url": f"git@github.com:me/{name}.git"}
                     for name in ("api-main", "api-archive", "web")]
            with patch.object(app.Api, "get", return_value=items), \
                    patch.object(app.subprocess, "run") as git, redirect_stdout(io.StringIO()):
                self.assertEqual(app.run(root / "unused.json", True, ui=ui, config=config), 0)
            git.assert_not_called()
            self.assertFalse((root / "copies").exists())
            labels = ui.confirm.call_args.args[0]
            self.assertEqual(len(labels), 1)
            self.assertIn(str(root / "copies" / "my-account" / "api-main"), labels[0])

    def test_real_execution_uses_account_folder_and_empty_list_is_safe(self):
        ui = Mock()
        ui.select.return_value = [0]
        ui.confirm.return_value = True
        root = Path.cwd() / "unused-github-test-output"
        config = {"destination": str(root), "sources": [self.source]}
        with patch.object(app.Api, "get", return_value=[{"name": "repo", "ssh_url": "git@github.com:me/repo.git"}]), \
                patch.object(app, "clone", return_value="cloned") as clone, \
                patch.object(app.shutil, "which", return_value="git"), redirect_stdout(io.StringIO()):
            self.assertEqual(app.run(Path("unused.json"), ui=ui, config=config), 0)
        self.assertEqual(clone.call_args.args[1], root / "my-account")
        ui.select.return_value = []
        ui.confirm.reset_mock()
        with patch.object(app.Api, "get", return_value=[]), \
                patch.object(app, "clone") as clone, redirect_stdout(io.StringIO()):
            self.assertEqual(app.run(Path("unused.json"), True, ui=ui, config=config), 0)
        clone.assert_not_called()
        ui.confirm.assert_not_called()


if __name__ == "__main__":
    unittest.main()
