from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import repo_cloner as app
from test_repo_cloner import GitFixture


class GitTestCase(unittest.TestCase):
    def setUp(self):
        self.fixture = GitFixture()
        self.addCleanup(self.fixture.close)
        env = patch.dict("os.environ", self.fixture.env, clear=True)
        env.start()
        self.addCleanup(env.stop)
        identity = patch.object(app, "_remote_identity", side_effect=self.local_identity)
        identity.start()
        self.addCleanup(identity.stop)

    @staticmethod
    def local_identity(value):
        return ("local", os.path.normcase(os.path.normpath(os.path.abspath(value))))

    def run_quiet(self, func, *args, **kwargs):
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            result = func(*args, **kwargs)
        return result, output.getvalue()


class StatusTests(GitTestCase):
    def setUp(self):
        super().setUp()
        # A destination folder that holds only configured clones.
        self.dest = self.fixture.root / "dest"
        self.team = self.dest / "team"
        self.target = self.team / "target"
        self.team.mkdir(parents=True)
        self.fixture.git(self.team, "clone", "--branch", "main", str(self.fixture.remote), str(self.target))
        for key, value in (("user.name", "Fixture User"), ("user.email", "fixture@example.com")):
            self.fixture.git(self.target, "config", key, value)

    def head(self):
        return self.fixture.git(self.target, "rev-parse", "HEAD").stdout.strip()

    def status(self, names=("target",), **source):
        config = self.fixture.root / "status.json"
        config.write_text(json.dumps({"destination": str(self.dest), "sources": [{
            "name": "team", "provider": "git",
            "repositories": [{"name": n, "url": str(self.fixture.remote)} for n in names], **source,
        }]}), encoding="utf-8")
        return self.run_quiet(app.run, config, status=True)

    def line(self, output, name):
        return next(line for line in output.splitlines() if f"/{name} |" in line)

    def test_clean_repository_is_in_sync_and_nothing_changes(self):
        head = self.head()
        fetch_head = self.target / ".git" / "FETCH_HEAD"
        self.fixture.push_change("remote only\n")
        code, output = self.status()
        self.assertEqual(code, 0)
        # No fetch: the new remote commit is not seen, and no Git state is written.
        self.assertTrue(self.line(output, "target").startswith("OK "))
        self.assertIn("In sync", output)
        self.assertEqual(self.head(), head)
        self.assertFalse(fetch_head.exists())

    def test_behind_ahead_and_diverged_use_the_last_fetch(self):
        self.fixture.push_change("two\n")
        self.fixture.git(self.target, "fetch")
        code, output = self.status()
        self.assertEqual(code, 1)
        self.assertIn("BEHIND", self.line(output, "target"))
        self.assertIn("1 commit(s) behind", output)

        (self.target / "local.txt").write_text("x", encoding="utf-8")
        self.fixture.git(self.target, "add", "local.txt")
        self.fixture.git(self.target, "commit", "-m", "local")
        _, output = self.status()
        self.assertIn("DIVERGED", self.line(output, "target"))

        self.fixture.git(self.target, "merge", "--no-edit", "origin/main")
        _, output = self.status()
        self.assertIn("AHEAD", self.line(output, "target"))
        self.assertIn("not pushed", output)

    def test_skip_reasons_match_update_checks(self):
        (self.target / "file.txt").write_text("edited\n", encoding="utf-8")
        code, output = self.status()
        self.assertEqual(code, 1)
        self.assertIn("SKIP", self.line(output, "target"))
        self.assertIn("local changes", output)

    def test_missing_extra_and_partial_entries(self):
        self.fixture.git(self.team, "init", str(self.team / "stray"))
        (self.team / ".clone-abc123").mkdir()
        (self.team / "plain-folder").mkdir()
        code, output = self.status(names=("target", "new-one"))
        self.assertEqual(code, 1)
        self.assertIn("MISSING", self.line(output, "new-one"))
        self.assertIn("EXTRA", self.line(output, "stray"))
        self.assertIn("PARTIAL", self.line(output, ".clone-abc123"))
        self.assertNotIn("plain-folder", output)
        self.assertIn("missing=1", output)

    def test_lfs_repository_warns_when_git_lfs_is_missing(self):
        (self.fixture.writer / ".gitattributes").write_text("*.bin filter=lfs diff=lfs merge=lfs -text\n",
                                                            encoding="utf-8")
        self.fixture.git(self.fixture.writer, "add", ".gitattributes")
        self.fixture.git(self.fixture.writer, "commit", "-m", "lfs")
        self.fixture.git(self.fixture.writer, "push", "origin", "main")
        self.fixture.git(self.target, "pull", "--ff-only")
        with patch.object(app, "_lfs_installed", return_value=False):
            code, output = self.status()
        self.assertEqual(code, 1)
        self.assertIn("WARN", self.line(output, "target"))
        self.assertIn("git lfs pull", output)
        with patch.object(app, "_lfs_installed", return_value=True):
            self.assertEqual(self.status()[0], 0)

    def test_cli_status_mode(self):
        with patch("sys.argv", ["repo-cloner", "--status", "--config", "batch.json"]), \
                patch("repo_cloner_tui.TerminalUI") as ui, \
                patch.object(app, "run", return_value=0) as run:
            self.assertEqual(app.main(), 0)
        ui.assert_not_called()
        run.assert_called_once_with(Path("batch.json"), False, None, status=True)


class SubmoduleTests(GitTestCase):
    def setUp(self):
        super().setUp()
        root = self.fixture.root
        self.sub_remote = root / "sub.git"
        self.sub_writer = root / "sub-writer"
        self.fixture.git(root, "init", "--bare", str(self.sub_remote))
        self.fixture.git(root, "init", str(self.sub_writer))
        for key, value in (("user.name", "Fixture User"), ("user.email", "fixture@example.com")):
            self.fixture.git(self.sub_writer, "config", key, value)
        self.fixture.git(self.sub_writer, "symbolic-ref", "HEAD", "refs/heads/main")
        self.commit_sub("v1\n")
        self.fixture.git(self.sub_writer, "remote", "add", "origin", str(self.sub_remote))
        self.fixture.git(self.sub_writer, "push", "-u", "origin", "main")
        self.fixture.git(self.sub_remote, "symbolic-ref", "HEAD", "refs/heads/main")
        self.fixture.git(self.fixture.writer, "submodule", "add", str(self.sub_remote), "lib")
        self.fixture.git(self.fixture.writer, "commit", "-m", "add submodule")
        self.fixture.git(self.fixture.writer, "push", "origin", "main")

    def commit_sub(self, content):
        (self.sub_writer / "lib.txt").write_text(content, encoding="utf-8")
        self.fixture.git(self.sub_writer, "add", "lib.txt")
        self.fixture.git(self.sub_writer, "commit", "-m", content.strip())

    def repo(self, name, submodules=True):
        return app.Repository(name, str(self.fixture.remote), submodules=submodules)

    def test_clone_initializes_submodules_only_when_enabled(self):
        result, _ = self.run_quiet(app.clone, self.repo("with-sub"), self.fixture.root, False)
        self.assertEqual(result, "cloned")
        self.assertEqual((self.fixture.root / "with-sub" / "lib" / "lib.txt").read_text(), "v1\n")
        self.run_quiet(app.clone, self.repo("without-sub", submodules=False), self.fixture.root, False)
        self.assertFalse((self.fixture.root / "without-sub" / "lib" / "lib.txt").exists())

    def test_update_follows_submodule_pointer_and_initializes_existing_clones(self):
        # The fixture target was cloned before the submodule existed and is behind.
        result, _ = self.run_quiet(app.clone, self.repo("target"), self.fixture.root, False)
        self.assertEqual(result, "updated")
        lib = self.fixture.target / "lib" / "lib.txt"
        self.assertEqual(lib.read_text(), "v1\n")

        self.commit_sub("v2\n")
        self.fixture.git(self.sub_writer, "push", "origin", "main")
        self.fixture.git(self.fixture.writer, "submodule", "update", "--remote", "lib")
        self.fixture.git(self.fixture.writer, "commit", "-am", "bump lib")
        self.fixture.git(self.fixture.writer, "push", "origin", "main")
        result, _ = self.run_quiet(app.clone, self.repo("target"), self.fixture.root, False)
        self.assertEqual(result, "updated")
        self.assertEqual(lib.read_text(), "v2\n")
        status = self.fixture.git(self.fixture.target, "status", "--porcelain").stdout
        self.assertEqual(status, "")

    def test_status_reports_uninitialized_submodules(self):
        self.run_quiet(app.clone, self.repo("plain", submodules=False), self.fixture.root, False)
        state, detail = app._inspect(self.repo("plain"), self.fixture.root / "plain")
        self.assertEqual(state, "warn")
        self.assertIn("submodules not initialized", detail)
        self.assertEqual(app._inspect(self.repo("plain", submodules=False), self.fixture.root / "plain")[0], "ok")

    def test_invalid_submodules_setting_stops_at_start(self):
        config = self.fixture.root / "bad.json"
        source = {"name": "x", "provider": "git",
                  "repositories": [{"name": "r", "url": str(self.fixture.remote)}]}
        for document in ({"submodules": "yes", "sources": [source]},
                         {"sources": [{**source, "submodules": 1}]}):
            config.write_text(json.dumps(document), encoding="utf-8")
            with self.subTest(document=document), self.assertRaisesRegex(app.ClonerError, "submodules"):
                self.run_quiet(app.run, config, dry_run=True)


if __name__ == "__main__":
    unittest.main()
