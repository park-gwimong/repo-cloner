from contextlib import nullcontext, redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import repo_cloner as app
from repo_cloner_tui import TerminalUI


SECRET = "test-secret"
REAL_REPOSITORIES = app.repositories


def listing(source, protocol):
    """Fake API listing keyed by provider."""
    provider = source["provider"]
    if provider == "bitbucket-cloud":
        names = ["api", "web", "odd[1]"]
    elif provider == "github":
        names = ["service", "tools"]
    else:
        return iter(REAL_REPOSITORIES(source, protocol))
    return iter(app.Repository(name, f"https://example.com/{name}.git") for name in names)


class CredentialsReferenceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root / "conf").mkdir()
        self.credentials = self.root / "conf" / "repositories.json"
        self.credentials.write_text(json.dumps({"username": "me@example.com", "token": SECRET}), encoding="utf-8")
        self.batch = self.root / "conf" / "batch.json"

    def run_batch(self, document):
        self.batch.write_text(json.dumps(document), encoding="utf-8")
        seen = []

        def fake(source, protocol):
            seen.append(source)
            return iter(())
        with patch.object(app, "repositories", side_effect=fake), redirect_stdout(io.StringIO()):
            code = app.run(self.batch, dry_run=True)
        return code, seen

    def test_default_credentials_follow_tui_rules_per_provider(self):
        code, seen = self.run_batch({"credentials": "./repositories.json", "sources": [
            {"name": "bb", "provider": "bitbucket-cloud", "workspace": "w", "project": "P"},
            {"name": "gh", "provider": "github", "organization": "org"},
            {"name": "direct", "provider": "git",
             "repositories": [{"name": "r", "url": "https://example.com/r.git"}]},
        ]})
        self.assertEqual(code, 0)
        bb, gh, direct = seen
        self.assertEqual((bb["username"], bb["token"]), ("me@example.com", SECRET))
        self.assertEqual(gh["token"], SECRET)
        self.assertNotIn("username", gh)
        self.assertNotIn("token", direct)
        self.assertNotIn("credentials", bb)

    def test_relative_credentials_use_batch_folder_not_current_directory(self):
        with patch("os.getcwd", return_value=str(self.root)):
            code, seen = self.run_batch({"credentials": "repositories.json", "sources": [
                {"name": "gh", "provider": "github", "organization": "org"}]})
        self.assertEqual((code, seen[0]["token"]), (0, SECRET))

    def test_source_level_reference_and_inline_token_override_default(self):
        other = self.root / "other.json"
        other.write_text(json.dumps({"token": "other-secret"}), encoding="utf-8")
        code, seen = self.run_batch({"credentials": "./repositories.json", "sources": [
            {"name": "a", "provider": "github", "organization": "o", "credentials": str(other)},
            {"name": "b", "provider": "github", "organization": "o", "token": "inline"},
        ]})
        self.assertEqual([s["token"] for s in seen], ["other-secret", "inline"])

    def test_invalid_references_stop_before_listing_without_leaking_secrets(self):
        (self.root / "conf" / "extra.json").write_text(
            json.dumps({"token": SECRET, "sources": []}), encoding="utf-8")
        (self.root / "conf" / "broken.json").write_text("{" + SECRET, encoding="utf-8")
        cases = [
            {"credentials": "missing.json"},
            {"credentials": "extra.json"},
            {"credentials": "broken.json"},
            {"credentials": ""},
            {"credentials": 5},
        ]
        for top in cases:
            with self.subTest(top=top), self.assertRaises(app.ClonerError) as caught:
                self.run_batch({**top, "sources": [{"name": "gh", "provider": "github", "organization": "o"}]})
            self.assertNotIn(SECRET, str(caught.exception))
        with self.assertRaisesRegex(app.ClonerError, "not both"):
            self.run_batch({"sources": [{"name": "gh", "provider": "github", "organization": "o",
                                         "credentials": "repositories.json", "token": "x"}]})


class TuiBatchExportTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.credentials = self.root / "repositories.json"
        self.credentials.write_text(json.dumps({"username": "me@example.com", "token": SECRET}), encoding="utf-8")
        self.batch = self.root / "batch.json"
        self.config = {"destination": str(self.root / "clones"), "protocol": "https", "sources": [
            {"name": "source-1", "provider": "bitbucket-cloud", "workspace": "w",
             "username": "me@example.com", "token": SECRET},
            {"name": "org", "provider": "github", "organization": "org",
             "apiUrl": "https://api.github.com", "token": SECRET},
            {"name": "team", "provider": "git", "repositories": [
                {"name": "one", "url": "https://example.com/one.git"},
                {"name": "two", "url": "https://example.com/two.git"}]},
        ]}

    def tui_run(self, repo_selection, *, save=True, confirm=True, dry_run=True):
        ui = Mock()
        ui.select.side_effect = [[0, 1, 2], [0], repo_selection]
        ui.confirm.return_value = confirm
        if save:
            ui.save_batch.side_effect = lambda export, default: app.write_batch(self.batch, export)
        planned = []

        def clone(repo, parent, dry):
            planned.append(parent / repo.name)
            return "planned"
        with patch.object(app, "available_projects", return_value=[("CTRL", "관제 시스템")]), \
                patch.object(app, "repositories", side_effect=listing), \
                patch.object(app, "clone", side_effect=clone), \
                patch.object(app.shutil, "which", return_value="git"), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as err:
            code = app.run(self.credentials, dry_run, ui=ui, config=self.config)
        return code, ui, planned, err.getvalue()

    def test_saved_batch_has_no_secrets_and_reproduces_tui_paths(self):
        # Tasks: api, web, odd[1], service, tools, one, two
        code, ui, tui_targets, _ = self.tui_run([0, 2, 4, 6])
        self.assertEqual(code, 0)
        self.assertEqual(ui.save_batch.call_args.args[1], self.root / "batch.json")
        text = self.batch.read_text(encoding="utf-8")
        self.assertNotIn(SECRET, text)
        self.assertNotIn("me@example.com", text)
        document = json.loads(text)
        self.assertEqual(document["credentials"], "./repositories.json")
        self.assertEqual(document["destination"], "./clones")
        self.assertEqual(document["protocol"], "https")
        self.assertEqual(document["sources"], [
            {"name": "관제 시스템", "provider": "bitbucket-cloud", "workspace": "w",
             "project": "CTRL", "include": ["api", "odd[[]1]"]},
            {"name": "org", "provider": "github", "organization": "org",
             "apiUrl": "https://api.github.com", "include": ["tools"]},
            {"name": "team", "provider": "git",
             "repositories": [{"name": "two", "url": "https://example.com/two.git"}]},
        ])

        batch_targets = []
        seen = []

        def batch_listing(source, protocol):
            seen.append(source)
            return listing(source, protocol)

        def clone(repo, parent, dry):
            batch_targets.append(parent / repo.name)
            return "planned"
        with patch.object(app, "repositories", side_effect=batch_listing), \
                patch.object(app, "clone", side_effect=clone), redirect_stdout(io.StringIO()):
            self.assertEqual(app.run(self.batch, dry_run=True), 0)
        self.assertEqual(batch_targets, tui_targets)
        self.assertEqual(seen[0]["token"], SECRET)
        self.assertEqual(seen[0]["username"], "me@example.com")

    def test_cancelled_confirmation_does_not_offer_save(self):
        code, ui, planned, _ = self.tui_run([0], confirm=False, dry_run=False)
        self.assertEqual((code, planned), (0, []))
        ui.save_batch.assert_not_called()

    def test_duplicate_folder_names_cannot_be_exported(self):
        repo = app.Repository("r", "https://example.com/r.git")
        expanded = [({"provider": "github", "organization": "a"}, ("Same",)),
                    ({"provider": "github", "organization": "b"}, ("same",))]
        tasks = [(repo, self.root, "Same"), (repo, self.root, "same")]
        with self.assertRaisesRegex(app.ClonerError, "unique"):
            app.batch_export(self.root, "ssh", self.credentials, expanded, tasks, [0, 1])

    def test_export_failure_warns_and_skips_saving(self):
        ui = Mock()
        with patch.object(app, "batch_export", side_effect=app.ClonerError("boom")),                 redirect_stderr(io.StringIO()) as err:
            app._offer_batch_save(ui, self.credentials, self.root, "ssh", [], [], [])
        ui.save_batch.assert_not_called()
        self.assertIn("Batch file cannot be saved: boom", err.getvalue())

    def test_portable_paths(self):
        base = self.root / "conf"
        self.assertEqual(app._portable_path(base, base), ".")
        self.assertEqual(app._portable_path(base / "a b" / "c", base), "./a b/c")
        with patch.object(Path, "home", return_value=self.root):
            self.assertEqual(app._portable_path(self.root / "x", base), "~/x")
        with patch.object(Path, "home", return_value=base):
            outside = Path(app.os.path.abspath(self.root / "elsewhere"))
            self.assertEqual(app._portable_path(outside, base), str(outside))


class SaveBatchScreenTests(unittest.TestCase):
    def setUp(self):
        self.ui = object.__new__(TerminalUI)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.export = app.BatchExport(self.root / "clones", "ssh", None, (
            {"name": "team", "provider": "git",
             "repositories": [{"name": "r", "url": "https://example.com/r.git"}]},))

    def save(self, choices, path=None):
        with patch.object(self.ui, "choose", side_effect=choices), \
                patch.object(self.ui, "edit", return_value=str(path or self.root / "batch.json")) as edit, \
                redirect_stdout(io.StringIO()) as out:
            result = self.ui.save_batch(self.export, self.root / "batch.json")
        return result, edit, out.getvalue()

    def test_default_choice_skips_saving(self):
        result, edit, _ = self.save([0])
        self.assertIsNone(result)
        edit.assert_not_called()
        self.assertFalse((self.root / "batch.json").exists())

    def test_save_writes_file_and_prints_next_command(self):
        target = self.root / "new" / "my batch.json"
        result, edit, out = self.save([1], target)
        self.assertEqual(result, target)
        self.assertEqual(edit.call_args.args[1], str(self.root / "batch.json"))
        self.assertEqual(json.loads(target.read_text(encoding="utf-8"))["destination"],
                         app._portable_path(self.root / "clones", target.parent))
        self.assertIn("--batch --config", out)

    def test_existing_file_is_kept_unless_overwrite_is_chosen(self):
        target = self.root / "batch.json"
        target.write_text("keep", encoding="utf-8")
        result, _, _ = self.save([1, 0])
        self.assertIsNone(result)
        self.assertEqual(target.read_text(encoding="utf-8"), "keep")
        result, _, _ = self.save([1, 1])
        self.assertEqual(result, target)
        self.assertIn("sources", target.read_text(encoding="utf-8"))
        self.assertEqual([p.name for p in self.root.iterdir() if p.name.endswith(".tmp")], [])

    def test_cancel_key_skips_saving_without_stopping_the_run(self):
        result, _, out = self.save(KeyboardInterrupt)
        self.assertIsNone(result)
        self.assertIn("not saved", out)

    def test_path_validator_rejects_directories(self):
        def edit(title, default="", validator=None):
            validator(str(self.root))
        with patch.object(self.ui, "choose", return_value=1), patch.object(self.ui, "edit", side_effect=edit):
            with self.assertRaisesRegex(ValueError, "directory"):
                self.ui.save_batch(self.export, self.root / "batch.json")


if __name__ == "__main__":
    unittest.main()
