from contextlib import nullcontext, redirect_stdout, redirect_stderr
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import repo_cloner as app
from repo_cloner_tui import TerminalUI


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.ui = object.__new__(TerminalUI)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.path = self.root / "repositories.json"
        self.credentials = {"username": "email@example.com", "token": "test-secret"}
        self.path.write_text(json.dumps(self.credentials), encoding="utf-8")

    def test_edit_preserves_case_q_unicode_and_supports_correction(self):
        with patch.object(self.ui, "screen", return_value=nullcontext()), \
                patch.object(self.ui, "draw", return_value=10), \
                patch.object(self.ui, "key", side_effect=["\x15", "Q", "한", "x", "backspace", "left", "A", "end", "enter"]):
            self.assertEqual(self.ui.edit("Path", "old"), "QA한")

    def test_edit_retries_validation_and_can_cancel(self):
        validate = Mock(side_effect=[ValueError("Invalid"), None])
        with patch.object(self.ui, "screen", return_value=nullcontext()), \
                patch.object(self.ui, "draw", return_value=10), \
                patch.object(self.ui, "key", side_effect=["enter", "A", "enter"]):
            self.assertEqual(self.ui.edit("Name", "x", validate), "xA")
        with patch.object(self.ui, "screen", return_value=nullcontext()), \
                patch.object(self.ui, "draw", return_value=10), \
                patch.object(self.ui, "key", return_value="cancel"):
            with self.assertRaises(KeyboardInterrupt):
                self.ui.edit("Path")

    def test_setup_cloud_destination_and_no_file_changes(self):
        before = self.path.read_bytes()
        destination = self.root / "한글 Path"
        with patch.object(self.ui, "choose", side_effect=[1, 0, 1, 0]) as choose, \
                patch.object(app, "available_workspaces", return_value=[("other", "Other"), ("workspace", "Team")]) as listing, \
                patch.object(self.ui, "edit", side_effect=[str(destination)]) as edit:
            config = self.ui.configure(self.credentials, self.path)
        self.assertEqual(config["destination"], str(destination))
        self.assertEqual(config["protocol"], "https")
        self.assertEqual(edit.call_count, 1)
        listing.assert_called_once_with(self.credentials)
        self.assertEqual(choose.call_args_list[2].args, ("Bitbucket workspace", ["Other (other)", "Team (workspace)"]))
        self.assertEqual(config["sources"], [{"name": "source-1", "provider": "bitbucket-cloud",
                         "workspace": "workspace", **self.credentials}])
        self.assertFalse(destination.exists())
        self.assertEqual(self.path.read_bytes(), before)

    def test_github_uses_bearer_and_cli_destination_is_editable_default(self):
        initial = self.root / "initial"
        changed = self.root / "changed"
        with patch.object(self.ui, "choose", side_effect=[0, 1, 0]), \
                patch.object(self.ui, "edit", side_effect=[str(changed), "org", "https://api.github.com"]) as edit:
            config = self.ui.configure(self.credentials, self.path, initial)
        self.assertEqual(edit.call_args_list[0].args[1], str(initial))
        self.assertEqual(config["destination"], str(changed))
        self.assertNotIn("username", config["sources"][0])
        self.assertEqual(config["sources"][0]["name"], "org")
        self.assertEqual(config["sources"][0]["token"], "test-secret")

    def test_direct_git_does_not_receive_api_credentials(self):
        with patch.object(self.ui, "choose", side_effect=[0, 3, 0, 0]), \
                patch.object(self.ui, "edit", side_effect=[str(self.root), "team", "https://example.com/repo.git", "repo"]):
            config = self.ui.configure(self.credentials, self.path)
        self.assertNotIn("token", config["sources"][0])
        self.assertEqual(config["sources"][0]["repositories"][0]["name"], "repo")

    def test_destination_file_is_rejected_without_creating_folders(self):
        def edit(title, default="", validator=None):
            validator(str(self.path / "child"))
        with patch.object(self.ui, "edit", side_effect=edit):
            with self.assertRaisesRegex(ValueError, "not a directory"):
                self.ui.configure(self.credentials, self.path)

    def test_bitbucket_repositories_clone_directly_under_project_display_name(self):
        for provider in ("bitbucket-cloud", "bitbucket-server"):
            with self.subTest(provider=provider):
                ui = Mock()
                ui.select.side_effect = [[0, 1], [0, 1]]
                ui.confirm.return_value = True
                config = {"destination": str(self.root), "sources": [
                    {"name": "source-1", "provider": provider}]}
                repo = app.Repository("api", "https://example.com/api.git")
                with patch.object(app, "available_projects", return_value=[("A", "관제 시스템"), ("B", "Beta")]), \
                        patch.object(app, "repositories", return_value=[repo]) as listing, \
                        patch.object(app, "clone", return_value="cloned") as clone, \
                        patch.object(app.shutil, "which", return_value="git"), redirect_stdout(io.StringIO()):
                    self.assertEqual(app.run(self.path, ui=ui, config=config), 0)
                self.assertEqual([call.args[0]["project"] for call in listing.call_args_list], ["A", "B"])
                self.assertEqual([call.args[1] for call in clone.call_args_list],
                                 [self.root / "관제 시스템", self.root / "Beta"])
                preview = ui.confirm.call_args.args[0]
                self.assertIn(str(self.root / "관제 시스템" / "api"), preview[0])

    def test_duplicate_or_unsafe_project_names_stop_before_clone(self):
        for projects in ([('A', 'Same'), ('B', 'same')], [('A', '../outside')]):
            ui = Mock()
            ui.select.return_value = list(range(len(projects)))
            config = {"sources": [{"name": "source-1", "provider": "bitbucket-cloud"}]}
            with patch.object(app, "available_projects", return_value=projects), \
                    patch.object(app, "clone") as clone, \
                    patch.object(app.shutil, "which", return_value="git"), redirect_stdout(io.StringIO()):
                with self.assertRaises(app.ClonerError):
                    app.run(self.path, ui=ui, config=config)
            clone.assert_not_called()

    def test_cli_defaults_to_setup_and_passes_in_memory_job(self):
        ui = Mock()
        ui.configure.return_value = {"sources": []}
        with patch("sys.argv", ["repo-cloner", "--config", str(self.path), "--dry-run"]), \
                patch("repo_cloner_tui.TerminalUI", return_value=ui), \
                patch.object(app, "run", return_value=0) as run:
            self.assertEqual(app.main(), 0)
        ui.configure.assert_called_once_with(self.credentials, self.path, None)
        run.assert_called_once_with(self.path, True, ui=ui, config=ui.configure.return_value)

    def test_cli_batch_does_not_open_tui(self):
        with patch("sys.argv", ["repo-cloner", "--batch"]), \
                patch("repo_cloner_tui.TerminalUI") as ui, \
                patch.object(app, "run", return_value=0):
            self.assertEqual(app.main(), 0)
        ui.assert_not_called()

    def test_setup_cancel_cannot_execute(self):
        ui = Mock()
        ui.configure.side_effect = KeyboardInterrupt
        with patch("sys.argv", ["repo-cloner", "--config", str(self.path)]), \
                patch("repo_cloner_tui.TerminalUI", return_value=ui), \
                patch.object(app, "run") as run, redirect_stderr(io.StringIO()):
            self.assertEqual(app.main(), 130)
        run.assert_not_called()

    def test_in_memory_config_dry_run_uses_edited_destination(self):
        destination = self.root / "new path"
        config = {"destination": str(destination), "sources": [{"name": "team", "provider": "git",
                  "repositories": [{"name": "repo", "url": "https://example.com/repo.git"}]}]}
        ui = Mock()
        ui.select.return_value = [0]
        output = io.StringIO()
        with redirect_stdout(output), patch.object(app.subprocess, "run") as git:
            self.assertEqual(app.run(self.path, True, ui=ui, config=config), 0)
        git.assert_not_called()
        self.assertIn(str(destination / "team" / "repo"), ui.confirm.call_args.args[0][0])
        self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
