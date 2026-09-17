import base64
from contextlib import redirect_stdout, redirect_stderr
from dataclasses import replace
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import repo_cloner as app


def bb_item(name="repo", protocol="ssh"):
    return {"slug": name, "links": {"clone": [{"name": protocol, "href": "git@example.com:p/repo.git"}]}}


class ProviderTests(unittest.TestCase):
    def test_explicit_repositories_preserve_names_and_urls_without_api(self):
        source = {
            "provider": "git",
            "repositories": [
                {"name": "my-copy", "url": "git@github.com:org/original.git"},
                {"name": "web", "url": "https://example.com/team/web.git"},
            ],
        }
        with patch.object(app, "Api") as api:
            self.assertEqual(list(app.repositories(source, "ssh")), [
                app.Repository("my-copy", "git@github.com:org/original.git"),
                app.Repository("web", "https://example.com/team/web.git"),
            ])
        api.assert_not_called()

    def test_explicit_repositories_validate_entire_list_before_yielding(self):
        valid = {"name": "first", "url": "https://example.com/first.git"}
        for invalid in (
            {"name": "FIRST", "url": "https://example.com/other.git"},
            {"name": "../escape", "url": "https://example.com/other.git"},
            {"name": "bad", "url": "ext::command"},
            {"name": "bad", "url": "/local/repo"},
            {"name": "bad", "url": "https://secret@example.com/repo.git"},
            {"name": "bad"},
            "not an object",
        ):
            with self.subTest(invalid=invalid):
                iterator = app.repositories({"provider": "git", "repositories": [valid, invalid]}, "ssh")
                with self.assertRaises(app.ClonerError):
                    next(iterator)
        for invalid in (None, [], "https://example.com/repo.git"):
            with self.subTest(entries=invalid), self.assertRaises(app.ClonerError):
                list(app.repositories({"provider": "git", "repositories": invalid}, "ssh"))

    def test_github_pagination(self):
        item = {"name": "repo", "ssh_url": "git@github.com:o/repo.git"}
        with patch.object(app.Api, "get", side_effect=[[item] * 100, [item]]) as get:
            repos = list(app.repositories({"provider": "github", "organization": "org"}, "ssh"))
        self.assertEqual(len(repos), 101)
        self.assertIn("page=2", get.call_args.args[0])

    def test_cloud_filter_and_next(self):
        next_url = "https://api.bitbucket.org/2.0/next"
        with patch.object(app.Api, "get", side_effect=[
            {"values": [bb_item()], "next": next_url}, {"values": []}
        ]) as get:
            repos = list(app.repositories({"provider": "bitbucket-cloud", "workspace": "w", "project": "ABC"}, "ssh"))
        self.assertEqual(len(repos), 1)
        self.assertIn("project.key%3D%22ABC%22", get.call_args_list[0].args[0])
        self.assertEqual(get.call_args.args[0], next_url)

    def test_server_offset_and_https_link(self):
        with patch.object(app.Api, "get", side_effect=[
            {"values": [], "isLastPage": False, "nextPageStart": 37},
            {"values": [bb_item(protocol="http")], "isLastPage": True}
        ]) as get:
            repos = list(app.repositories({"provider": "bitbucket-server", "baseUrl": "https://example.com", "project": "P"}, "https"))
        self.assertEqual(len(repos), 1)
        self.assertIn("start=37", get.call_args.args[0])

    def test_invalid_offset(self):
        with patch.object(app.Api, "get", return_value={"values": [], "isLastPage": False, "nextPageStart": 0}):
            with self.assertRaises(app.ClonerError):
                list(app.repositories({"provider": "bitbucket-server", "baseUrl": "https://example.com", "project": "P"}, "ssh"))

    def test_auth_and_cross_host_rejection(self):
        with patch.dict("os.environ", {"TEST_TOKEN": "secret", "TEST_EMAIL": "me@example.com"}):
            api = app.Api("https://example.com", {"tokenEnv": "TEST_TOKEN", "usernameEnv": "TEST_EMAIL"})
        expected = base64.b64encode(b"me@example.com:secret").decode()
        self.assertEqual(api.headers["Authorization"], "Basic " + expected)
        for url in ("https://other.example.com/page", "http://example.com/page"):
            with self.assertRaises(app.ClonerError):
                api.get(url)

    def test_missing_token(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(app.ClonerError):
                app.Api("https://example.com", {"tokenEnv": "MISSING"})


class RemoteIdentityTests(unittest.TestCase):
    def test_only_safe_default_normalization_is_equal(self):
        self.assertEqual(
            app._remote_identity("https://EXAMPLE.com:443/org/repo"),
            app._remote_identity("https://example.com/org/repo"),
        )
        self.assertEqual(
            app._remote_identity("ssh://GIT@EXAMPLE.com:22/org/repo"),
            app._remote_identity("ssh://GIT@example.com/org/repo"),
        )
        self.assertEqual(
            app._remote_identity("git@EXAMPLE.com:org/repo"),
            app._remote_identity("git@example.com:org/repo"),
        )

    def test_strict_spelling_and_transport_boundaries(self):
        equal = app._remote_identity("https://example.com/org/repo")
        for different in (
            "http://example.com/org/repo",
            "ssh://example.com/org/repo",
            "git@example.com:org/repo",
            "https://example.com/ORG/repo",
            "https://example.com/org/repo.git",
            "https://example.com/org/repo/",
            "https://example.com/org%2Frepo",
            "https://example.com:8443/org/repo",
            "https://user@example.com/org/repo",
            "https://example.com/org/repo?x=1",
            "https://example.com/org/repo#part",
            "file:///tmp/repo",
            "/tmp/repo",
            "ext::helper",
        ):
            self.assertNotEqual(equal, app._remote_identity(different))

        self.assertNotEqual(
            app._remote_identity("ssh://git@example.com/org/repo"),
            app._remote_identity("ssh://deploy@example.com/org/repo"),
        )
        self.assertNotEqual(
            app._remote_identity("git@example.com:org/repo"),
            app._remote_identity("git@example.com:ORG/repo"),
        )
        self.assertIsNone(app._remote_identity("deploy@example.com:org/repo"))

    def test_malformed_and_ambiguous_urls_are_rejected(self):
        for value in (
            "",
            "https://",
            "https:///repo",
            "https://example.com:bad/repo",
            "https://example.com/repo?query",
            "https://example.com/repo#fragment",
            "https://user:password@example.com/repo",
            "ssh://git:password@example.com/repo",
            "ssh://example.com:22",
            "git@example.com:",
            "git@example.com:repo with space",
            "git@example.com:repo?query",
            "git@example.com:repo#fragment",
            "deploy@example.com:repo",
            "git@example.com:\x01repo",
            "git@example.com:repo\x00",
        ):
            self.assertIsNone(app._remote_identity(value), value)


class GitCommandTests(unittest.TestCase):
    def test_expected_absence_is_distinguished_from_git_failure(self):
        missing = subprocess.CompletedProcess(["git"], 1, b"", b"")
        with patch.object(app, "_git", return_value=missing):
            self.assertIsNone(
                app._git_optional(
                    Path("."),
                    ["symbolic-ref", "-q", "HEAD"],
                    Path("."),
                    expected_exit_codes=(1,),
                )
            )
            self.assertIsNone(app._oid(Path("."), "missing", Path("."), optional=True))

        diagnostic = subprocess.CompletedProcess(["git"], 1, b"", b"permission denied")
        with patch.object(app, "_git", return_value=diagnostic):
            with self.assertRaises(app.ClonerError):
                app._oid(Path("."), "HEAD", Path("."), optional=True)

        corrupt = subprocess.CompletedProcess(
            ["git"], 3, b"", b"fatal: bad config line 1 in file .git/config"
        )
        with patch.object(app, "_git", return_value=corrupt):
            with self.assertRaises(app.ClonerError):
                app._config_values(Path("."), "remote.origin.url", Path("."))
        broken_repo = subprocess.CompletedProcess(
            ["git"], 128, b"", b"fatal: not a git repository (or any of the parent directories): .git"
        )
        with patch.object(app, "_git", return_value=broken_repo):
            with self.assertRaises(app.ClonerError):
                app._oid(Path("."), "HEAD", Path("."), optional=True)

    def test_utf8_surrogateescape_decoding_preserves_git_bytes(self):
        result = subprocess.CompletedProcess(["git"], 0, b"bad-\xe2\x98\x83\0", b"")
        with patch.object(app, "_git", return_value=result):
            self.assertEqual(
                app._git_optional(Path("."), ["status"], Path(".")),
                "bad-☃\0",
            )
        invalid = subprocess.CompletedProcess(["git"], 0, b"bad-\xff", b"")
        with patch.object(app, "_git", return_value=invalid):
            value = app._git_optional(Path("."), ["status"], Path("."))
        self.assertEqual(value.encode("utf-8", "surrogateescape"), b"bad-\xff")

    def test_absolute_cwd_and_no_dash_c(self):
        result = subprocess.CompletedProcess(["git"], 0, b"", b"")
        worktree = Path(tempfile.gettempdir()) / "repo cloner worktree"
        hooks = Path(tempfile.gettempdir()) / "repo cloner hooks"
        with patch.object(app.subprocess, "run", return_value=result) as run:
            app._git(worktree, ["status"], hooks)
        command = run.call_args.args[0]
        self.assertNotIn("-C", command)
        self.assertEqual(run.call_args.kwargs["cwd"], str(worktree.resolve()))
        self.assertFalse(run.call_args.kwargs["shell"])
        self.assertEqual(run.call_args.kwargs["encoding"], "utf-8")
        self.assertEqual(run.call_args.kwargs["errors"], "surrogateescape")
        self.assertIn(f"core.hooksPath={hooks.resolve()}", command)


def _run_git(cwd: Path, *args: str, env: dict[str, str], check: bool = True):
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        env=env,
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


class GitFixture:
    """A bare remote, writer clone and target clone isolated from user Git config."""

    def __init__(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "fixture root with spaces"
        self.root.mkdir()
        self.home = self.root / "home"
        self.home.mkdir()
        self.env = os.environ.copy()
        self.env.update({
            "GIT_CONFIG_NOSYSTEM": "1",
            "HOME": str(self.home),
            "XDG_CONFIG_HOME": str(self.root / "xdg"),
            "GIT_ALLOW_PROTOCOL": "file",
        })
        self.remote = self.root / "remote.git"
        self.writer = self.root / "writer"
        self.target = self.root / "target"
        self._create()

    def close(self):
        self.temp.cleanup()

    def git(self, cwd: Path, *args: str, check: bool = True):
        return _run_git(cwd, *args, env=self.env, check=check)

    def _create(self):
        _run_git(self.root, "init", "--bare", str(self.remote), env=self.env)
        _run_git(self.root, "init", str(self.writer), env=self.env)
        self.git(self.writer, "config", "user.name", "Fixture User")
        self.git(self.writer, "config", "user.email", "fixture@example.com")
        self.git(self.writer, "symbolic-ref", "HEAD", "refs/heads/main")
        (self.writer / "file.txt").write_text("one\n", encoding="utf-8")
        self.git(self.writer, "add", "file.txt")
        self.git(self.writer, "commit", "-m", "one")
        self.git(self.writer, "remote", "add", "origin", str(self.remote))
        self.git(self.writer, "push", "-u", "origin", "main")
        self.git(self.remote, "symbolic-ref", "HEAD", "refs/heads/main")
        self.git(self.root, "clone", "--branch", "main", str(self.remote), str(self.target))
        self.git(self.target, "config", "user.name", "Fixture User")
        self.git(self.target, "config", "user.email", "fixture@example.com")

    def push_change(self, content: str):
        (self.writer / "file.txt").write_text(content, encoding="utf-8")
        self.git(self.writer, "add", "file.txt")
        self.git(self.writer, "commit", "-m", content.strip())
        self.git(self.writer, "push", "origin", "main")

    def target_head(self) -> str:
        return self.git(self.target, "rev-parse", "HEAD").stdout.strip()

    def remote_head(self) -> str:
        return self.git(self.writer, "rev-parse", "HEAD").stdout.strip()


class ExistingUpdateTests(unittest.TestCase):
    def setUp(self):
        self.fixture = GitFixture()
        self.addCleanup(self.fixture.close)
        self.output = io.StringIO()
        self.stdout = redirect_stdout(self.output)
        self.stderr = redirect_stderr(self.output)
        self.stdout.__enter__()
        self.stderr.__enter__()
        self.addCleanup(self.stderr.__exit__, None, None, None)
        self.addCleanup(self.stdout.__exit__, None, None, None)
        self.env_patch = patch.dict("os.environ", self.fixture.env, clear=True)
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)

    def repo(self):
        return app.Repository("target", str(self.fixture.remote))

    def local_identity(self, value: str):
        return ("local", os.path.normcase(os.path.normpath(os.path.abspath(value))))

    def update(self):
        with patch.object(app, "_remote_identity", side_effect=self.local_identity):
            return app.clone(self.repo(), self.fixture.root, False)

    def test_behind_branch_fast_forwards_to_fetched_oid(self):
        initial = self.fixture.target_head()
        self.fixture.push_change("two\n")
        fetched = self.fixture.remote_head()
        self.assertNotEqual(initial, fetched)
        self.assertEqual(self.update(), "updated")
        self.assertEqual(self.fixture.target_head(), fetched)
        self.assertEqual((self.fixture.target / "file.txt").read_text(), "two\n")

    def test_explicit_selection_clones_and_updates_at_overridden_destination(self):
        self.fixture.push_change("selected update\n")
        fetched = self.fixture.remote_head()
        config = self.fixture.root / "selection.json"
        config.write_text(json.dumps({
            "destination": str(self.fixture.root / "unused"),
            "sources": [{
                "name": self.fixture.root.name,
                "provider": "git",
                "include": ["target", "new-copy"],
                "repositories": [
                    {"name": name, "url": str(self.fixture.remote)}
                    for name in ("target", "new-copy", "excluded")
                ],
            }],
        }), encoding="utf-8")
        with patch.object(app, "_remote_identity", side_effect=self.local_identity):
            self.assertEqual(app.run(config, destination=self.fixture.root.parent), 0)
        self.assertEqual(self.fixture.target_head(), fetched)
        self.assertEqual(
            self.fixture.git(self.fixture.root / "new-copy", "rev-parse", "HEAD").stdout.strip(),
            fetched,
        )
        self.assertFalse((self.fixture.root / "excluded").exists())
        self.assertFalse((self.fixture.root / "unused").exists())
        self.assertIn("cloned=1 updated=1 unchanged=0 skipped=1 planned=0 failed=0", self.output.getvalue())

    def test_same_tip_is_unchanged(self):
        head = self.fixture.target_head()
        self.assertEqual(self.update(), "unchanged")
        self.assertEqual(self.fixture.target_head(), head)

    def test_local_commit_is_preserved_and_tracking_can_fetch(self):
        (self.fixture.target / "local.txt").write_text("local\n", encoding="utf-8")
        self.fixture.git(self.fixture.target, "add", "local.txt")
        self.fixture.git(self.fixture.target, "commit", "-m", "local")
        local_head = self.fixture.target_head()
        self.fixture.push_change("remote\n")
        self.assertEqual(self.update(), "skipped")
        self.assertEqual(self.fixture.target_head(), local_head)
        self.assertEqual((self.fixture.target / "local.txt").read_text(), "local\n")

    def test_dirty_worktree_is_skipped_before_fetch(self):
        before = self.fixture.remote_head()
        (self.fixture.target / "file.txt").write_text("edited\n", encoding="utf-8")
        self.assertEqual(self.update(), "skipped")
        self.assertEqual(self.fixture.target_head(), before)
        self.assertEqual((self.fixture.target / "file.txt").read_text(), "edited\n")

    def test_staged_change_is_skipped_and_preserved(self):
        (self.fixture.target / "staged.txt").write_text("staged\n", encoding="utf-8")
        self.fixture.git(self.fixture.target, "add", "staged.txt")
        self.assertEqual(self.update(), "skipped")
        self.assertEqual(self.fixture.git(self.fixture.target, "diff", "--cached", "--name-only").stdout.strip(), "staged.txt")

    def test_untracked_change_is_skipped_and_preserved(self):
        untracked = self.fixture.target / "untracked.txt"
        untracked.write_text("untracked\n", encoding="utf-8")
        self.assertEqual(self.update(), "skipped")
        self.assertEqual(untracked.read_text(), "untracked\n")

    def test_nonascii_dirty_filename_is_decoded_and_preserved(self):
        untracked = self.fixture.target / "한글-☃.txt"
        untracked.write_text("untracked\n", encoding="utf-8")
        self.assertEqual(self.update(), "skipped")
        self.assertEqual(untracked.read_text(), "untracked\n")

    def test_assume_unchanged_index_entry_is_skipped(self):
        self.fixture.git(self.fixture.target, "update-index", "--assume-unchanged", "file.txt")
        self.assertEqual(self.update(), "skipped")
        self.assertEqual(self.fixture.target_head(), self.fixture.remote_head())

    def test_skip_worktree_index_entry_is_skipped(self):
        self.fixture.git(self.fixture.target, "update-index", "--skip-worktree", "file.txt")
        self.assertEqual(self.update(), "skipped")

    def test_operation_marker_is_skipped(self):
        marker = Path(
            self.fixture.git(self.fixture.target, "rev-parse", "--git-path", "MERGE_HEAD").stdout.strip()
        )
        if not marker.is_absolute():
            marker = self.fixture.target / marker
        marker.write_text("0" * 40 + "\n", encoding="ascii")
        self.assertEqual(self.update(), "skipped")
        marker.unlink()

    def test_all_common_operation_markers_are_skipped(self):
        markers = (
            "rebase-apply",
            "rebase-merge",
            "CHERRY_PICK_HEAD",
            "REVERT_HEAD",
            "sequencer",
            "BISECT_START",
            "index.lock",
        )
        for name in markers:
            marker = Path(self.fixture.git(self.fixture.target, "rev-parse", "--git-path", name).stdout.strip())
            if not marker.is_absolute():
                marker = self.fixture.target / marker
            if name in {"rebase-apply", "rebase-merge", "sequencer"}:
                marker.mkdir()
            else:
                marker.write_text("marker\n", encoding="ascii")
            try:
                self.assertEqual(self.update(), "skipped", name)
            finally:
                if marker.is_dir() and not marker.is_symlink():
                    shutil.rmtree(marker)
                else:
                    marker.unlink()

    def test_custom_tracking_mapping_is_resolved_without_invention(self):
        self.fixture.git(self.fixture.target, "config", "--unset-all", "remote.origin.fetch")
        self.fixture.git(
            self.fixture.target,
            "config",
            "--add",
            "remote.origin.fetch",
            "+refs/heads/*:refs/remotes/cache/*",
        )
        self.fixture.git(self.fixture.target, "update-ref", "-d", "refs/remotes/cache/main")
        self.fixture.push_change("custom\n")
        expected = self.fixture.remote_head()
        self.assertEqual(self.update(), "updated")
        self.assertEqual(self.fixture.target_head(), expected)
        self.assertEqual(
            self.fixture.git(self.fixture.target, "rev-parse", "refs/remotes/cache/main").stdout.strip(),
            expected,
        )

    def test_ambiguous_fetch_mappings_are_skipped(self):
        self.fixture.git(self.fixture.target, "config", "--add", "remote.origin.fetch", "refs/heads/main:refs/remotes/other/main")
        self.fixture.push_change("ambiguous\n")
        self.assertEqual(self.update(), "skipped")

    def test_missing_fetch_mapping_is_skipped(self):
        self.fixture.git(self.fixture.target, "config", "--unset-all", "remote.origin.fetch")
        self.fixture.push_change("no-map\n")
        self.assertEqual(self.update(), "skipped")

    def test_local_upstream_is_skipped(self):
        self.fixture.git(self.fixture.target, "config", "branch.main.remote", ".")
        self.assertEqual(self.update(), "skipped")

    def test_malformed_branch_merge_is_skipped(self):
        self.fixture.git(self.fixture.target, "config", "branch.main.merge", "refs/tags/main")
        self.assertEqual(self.update(), "skipped")

    def test_symbolic_tracking_destination_is_skipped(self):
        self.fixture.git(self.fixture.target, "config", "--unset-all", "remote.origin.fetch")
        self.fixture.git(
            self.fixture.target,
            "config",
            "--add",
            "remote.origin.fetch",
            "refs/heads/main:refs/remotes/custom/main",
        )
        (self.fixture.target / ".git" / "refs" / "remotes" / "custom").mkdir(parents=True, exist_ok=True)
        self.fixture.git(
            self.fixture.target,
            "symbolic-ref",
            "refs/remotes/custom/main",
            "refs/remotes/origin/main",
        )
        self.assertEqual(self.update(), "skipped")

    def test_unborn_branch_is_skipped(self):
        self.fixture.git(self.fixture.target, "checkout", "--orphan", "unborn")
        self.fixture.git(self.fixture.target, "rm", "-rf", ".")
        self.assertEqual(self.update(), "skipped")

    def test_remote_rewrite_to_diverged_commit_is_skipped(self):
        base = self.fixture.target_head()
        self.fixture.push_change("old remote history\n")
        self.assertEqual(self.update(), "updated")
        local_head = self.fixture.target_head()
        self.fixture.git(self.fixture.writer, "reset", "--hard", base)
        (self.fixture.writer / "remote.txt").write_text("remote\n", encoding="utf-8")
        self.fixture.git(self.fixture.writer, "add", "remote.txt")
        self.fixture.git(self.fixture.writer, "commit", "-m", "remote")
        self.fixture.git(self.fixture.writer, "push", "--force", "origin", "main")
        self.assertEqual(self.update(), "skipped")
        self.assertEqual(self.fixture.target_head(), local_head)
        self.assertEqual(
            self.fixture.git(self.fixture.target, "rev-parse", "refs/remotes/origin/main").stdout.strip(),
            self.fixture.remote_head(),
        )

    def test_remote_rewind_is_skipped_but_tracking_metadata_moves(self):
        base = self.fixture.target_head()
        self.fixture.push_change("remote-child\n")
        child = self.fixture.remote_head()
        self.assertEqual(self.update(), "updated")
        self.assertEqual(self.fixture.target_head(), child)
        self.fixture.git(self.fixture.writer, "reset", "--hard", base)
        self.fixture.git(self.fixture.writer, "push", "--force", "origin", "main")
        self.assertEqual(self.update(), "skipped")
        self.assertEqual(self.fixture.target_head(), child)
        self.assertEqual(
            self.fixture.git(self.fixture.target, "rev-parse", "refs/remotes/origin/main").stdout.strip(),
            base,
        )

    def test_rewritten_remote_can_still_be_a_fast_forward_from_initial_head(self):
        base = self.fixture.target_head()
        self.fixture.push_change("old-tracking\n")
        old_tracking = self.fixture.remote_head()
        self.fixture.git(self.fixture.target, "fetch", "origin")
        self.assertEqual(
            self.fixture.git(self.fixture.target, "rev-parse", "refs/remotes/origin/main").stdout.strip(),
            old_tracking,
        )
        self.fixture.git(self.fixture.writer, "reset", "--hard", base)
        (self.fixture.writer / "new.txt").write_text("new\n", encoding="utf-8")
        self.fixture.git(self.fixture.writer, "add", "new.txt")
        self.fixture.git(self.fixture.writer, "commit", "-m", "rewritten-new")
        self.fixture.git(self.fixture.writer, "push", "--force", "origin", "main")
        fresh = self.fixture.remote_head()
        self.assertEqual(self.update(), "updated")
        self.assertEqual(self.fixture.target_head(), fresh)

    def test_fetch_has_no_destination_before_conditional_tracking_publication(self):
        old = self.fixture.target_head()
        self.fixture.push_change("publication\n")
        fresh = self.fixture.remote_head()
        real_git = app._git
        fetches = []
        publications = []

        def observe(target, args, hooks_path=None, **kwargs):
            result = real_git(target, args, hooks_path, **kwargs)
            if args[0] == "fetch":
                fetches.append(args)
                self.assertEqual(args[-1], "refs/heads/main:")
                self.assertEqual(
                    self.fixture.git(target, "rev-parse", "refs/remotes/origin/main").stdout.strip(),
                    old,
                )
                self.assertEqual(self.fixture.git(target, "rev-parse", "FETCH_HEAD").stdout.strip(), fresh)
            elif args[0] == "update-ref":
                publications.append(args)
                self.assertEqual(args, ["update-ref", "--no-deref", "refs/remotes/origin/main", fresh, old])
            return result

        with patch.object(app, "_git", side_effect=observe):
            self.assertEqual(self.update(), "updated")
        self.assertEqual(len(fetches), 1)
        self.assertEqual(len(publications), 1)

    def test_tracking_compare_and_swap_detects_a_concurrent_update(self):
        initial = self.fixture.target_head()
        self.fixture.push_change("concurrent tracking\n")
        fresh = self.fixture.remote_head()
        real_git = app._git
        commands = []

        def race(target, args, hooks_path=None, **kwargs):
            commands.append(args[0])
            if args[0] == "update-ref":
                self.fixture.git(target, "update-ref", "refs/remotes/origin/main", fresh)
            return real_git(target, args, hooks_path, **kwargs)

        with patch.object(app, "_git", side_effect=race):
            self.assertEqual(self.update(), "skipped")
        self.assertEqual(self.fixture.target_head(), initial)
        self.assertNotIn("merge", commands)
        self.assertEqual(commands.count("fetch"), 1)
        self.assertEqual(commands.count("update-ref"), 1)

    def test_tracking_publication_error_is_failed_without_fast_forward(self):
        initial = self.fixture.target_head()
        self.fixture.push_change("publication failure\n")
        real_git = app._git
        commands = []

        def deny(target, args, hooks_path=None, **kwargs):
            commands.append(args[0])
            if args[0] == "update-ref":
                return subprocess.CompletedProcess(args, 1, "", "permission denied")
            return real_git(target, args, hooks_path, **kwargs)

        with patch.object(app, "_git", side_effect=deny):
            with self.assertRaisesRegex(app.ClonerError, "publication failed"):
                self.update()
        self.assertEqual(self.fixture.target_head(), initial)
        self.assertNotIn("merge", commands)

    def test_tracking_deleted_at_compare_and_swap_is_not_recreated(self):
        initial = self.fixture.target_head()
        self.fixture.push_change("deleted tracking\n")
        tracking = "refs/remotes/origin/main"
        real_git = app._git
        commands = []

        def race(target, args, hooks_path=None, **kwargs):
            commands.append(args[0])
            if args[0] == "update-ref":
                self.fixture.git(target, "update-ref", "-d", tracking)
            return real_git(target, args, hooks_path, **kwargs)

        with patch.object(app, "_git", side_effect=race):
            self.assertEqual(self.update(), "skipped")
        self.assertEqual(self.fixture.target_head(), initial)
        self.assertEqual(
            self.fixture.git(self.fixture.target, "rev-parse", "--verify", "--quiet", tracking, check=False).returncode,
            1,
        )
        self.assertNotIn("merge", commands)
        self.assertEqual(commands.count("fetch"), 1)
        self.assertEqual(commands.count("update-ref"), 1)

    def test_tracking_created_at_zero_old_compare_and_swap_is_preserved(self):
        initial = self.fixture.target_head()
        tracking = "refs/remotes/origin/main"
        self.fixture.git(self.fixture.target, "update-ref", "-d", tracking)
        self.fixture.push_change("created tracking\n")
        real_git = app._git
        commands = []

        def race(target, args, hooks_path=None, **kwargs):
            commands.append(args[0])
            if args[0] == "update-ref":
                self.assertEqual(args[-1], "0" * len(initial))
                self.fixture.git(target, "update-ref", tracking, initial)
            return real_git(target, args, hooks_path, **kwargs)

        with patch.object(app, "_git", side_effect=race):
            self.assertEqual(self.update(), "skipped")
        self.assertEqual(self.fixture.target_head(), initial)
        self.assertEqual(
            self.fixture.git(self.fixture.target, "rev-parse", tracking).stdout.strip(), initial,
        )
        self.assertNotIn("merge", commands)
        self.assertEqual(commands.count("fetch"), 1)
        self.assertEqual(commands.count("update-ref"), 1)

    def test_tracking_changed_after_publication_prevents_fast_forward(self):
        initial = self.fixture.target_head()
        self.fixture.push_change("post-publication race\n")
        tracking = "refs/remotes/origin/main"
        real_git = app._git
        commands = []

        def race(target, args, hooks_path=None, **kwargs):
            commands.append(args[0])
            result = real_git(target, args, hooks_path, **kwargs)
            if args[0] == "update-ref":
                self.assertEqual(result.returncode, 0)
                self.fixture.git(target, "update-ref", tracking, initial)
            return result

        with patch.object(app, "_git", side_effect=race):
            self.assertEqual(self.update(), "skipped")
        self.assertEqual(self.fixture.target_head(), initial)
        self.assertNotIn("merge", commands)
        self.assertEqual(commands.count("fetch"), 1)
        self.assertEqual(commands.count("update-ref"), 1)

    def test_late_same_oid_symbolic_metadata_conversion_preserves_referent(self):
        target = self.fixture.target
        initial = self.fixture.target_head()
        before_file = (target / "file.txt").read_bytes()
        before_index = (target / ".git" / "index").read_bytes()
        self.fixture.push_change("late symbolic race\n")
        fresh = self.fixture.remote_head()
        self.fixture.git(target, "fetch", "--refmap=", "origin", "refs/heads/main:")
        tracking = "refs/remotes/origin/main"
        real_git = app._git
        publications = []

        def race(directory, args, hooks_path=None, **kwargs):
            if args[0] == "update-ref":
                publications.append(args)
                self.fixture.git(directory, "symbolic-ref", tracking, "refs/heads/main")
            return real_git(directory, args, hooks_path, **kwargs)

        with tempfile.TemporaryDirectory() as hooks, patch.object(app, "_git", side_effect=race):
            app._publish_tracking(target, tracking, initial, fresh, Path(hooks))
        self.assertEqual(len(publications), 1)
        self.assertIn("--no-deref", publications[0])
        self.assertEqual(self.fixture.target_head(), initial)
        self.assertEqual((target / "file.txt").read_bytes(), before_file)
        self.assertEqual((target / ".git" / "index").read_bytes(), before_index)
        self.assertEqual(self.fixture.git(target, "rev-parse", tracking).stdout.strip(), fresh)
        # CAS compares OIDs, not ref kinds; it may replace the symbolic metadata.
        self.assertEqual(
            self.fixture.git(target, "symbolic-ref", "-q", tracking, check=False).returncode, 1,
        )

    def test_symbolic_tracking_race_does_not_change_the_local_branch(self):
        initial = self.fixture.target_head()
        self.fixture.push_change("symbolic race\n")
        real_git = app._git
        commands = []

        def race(target, args, hooks_path=None, **kwargs):
            commands.append(args[0])
            result = real_git(target, args, hooks_path, **kwargs)
            if args[0] == "fetch":
                self.fixture.git(target, "symbolic-ref", "refs/remotes/origin/main", "refs/heads/main")
            return result

        with patch.object(app, "_git", side_effect=race):
            self.assertEqual(self.update(), "skipped")
        self.assertEqual(self.fixture.target_head(), initial)
        self.assertNotIn("update-ref", commands)
        self.assertNotIn("merge", commands)
        self.assertEqual(
            self.fixture.git(self.fixture.target, "symbolic-ref", "refs/remotes/origin/main").stdout.strip(),
            "refs/heads/main",
        )

    def test_invalid_fetch_head_fails_before_tracking_publication(self):
        initial = self.fixture.target_head()
        self.fixture.push_change("invalid fetch head\n")
        real_git = app._git
        for invalid in ("", "not-an-oid\t\tbranch\n", f"{initial}\t\tbranch\n{initial}\t\tbranch\n"):
            with self.subTest(invalid=invalid):
                commands = []

                def corrupt(target, args, hooks_path=None, **kwargs):
                    commands.append(args[0])
                    result = real_git(target, args, hooks_path, **kwargs)
                    if args[0] == "fetch":
                        (self.fixture.target / ".git" / "FETCH_HEAD").write_text(invalid, encoding="utf-8")
                    return result

                with patch.object(app, "_git", side_effect=corrupt):
                    with self.assertRaises(app.ClonerError):
                        self.update()
                self.assertNotIn("update-ref", commands)
                self.assertNotIn("merge", commands)
                self.assertEqual(self.fixture.target_head(), initial)

    def test_fetch_head_change_before_publication_is_skipped(self):
        initial = self.fixture.target_head()
        self.fixture.push_change("changed fetch head\n")
        original = app._fetched_commit
        calls = 0

        def change(target, hooks_path):
            nonlocal calls
            oid = original(target, hooks_path)
            calls += 1
            if calls == 1:
                (self.fixture.target / ".git" / "FETCH_HEAD").write_text(
                    f"{initial}\t\tbranch\n", encoding="utf-8",
                )
            return oid

        with patch.object(app, "_fetched_commit", side_effect=change):
            self.assertEqual(self.update(), "skipped")
        self.assertEqual(self.fixture.target_head(), initial)
        self.assertEqual(calls, 2)

    def test_ignored_collision_fails_without_overwriting_file(self):
        (self.fixture.writer / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
        self.fixture.git(self.fixture.writer, "add", ".gitignore")
        self.fixture.git(self.fixture.writer, "commit", "-m", "ignore")
        self.fixture.git(self.fixture.writer, "push", "origin", "main")
        self.fixture.git(self.fixture.target, "pull", "--ff-only")
        ignored = self.fixture.target / "ignored.txt"
        ignored.write_text("keep\n", encoding="utf-8")
        (self.fixture.writer / "ignored.txt").write_text("remote\n", encoding="utf-8")
        self.fixture.git(self.fixture.writer, "add", "-f", "ignored.txt")
        self.fixture.git(self.fixture.writer, "commit", "-m", "tracked")
        self.fixture.git(self.fixture.writer, "push", "origin", "main")
        with self.assertRaises(app.ClonerError):
            self.update()
        self.assertEqual(ignored.read_text(), "keep\n")

    def test_linked_worktree_with_upstream_can_update(self):
        linked = self.fixture.root / "linked"
        self.fixture.git(self.fixture.writer, "worktree", "add", "-b", "linked", str(linked), "origin/main")
        self.fixture.git(linked, "config", "branch.linked.remote", "origin")
        self.fixture.git(linked, "config", "branch.linked.merge", "refs/heads/main")
        self.fixture.push_change("two\n")
        expected = self.fixture.remote_head()
        with patch.object(app, "_remote_identity", side_effect=self.local_identity):
            self.assertEqual(app.clone(app.Repository("linked", str(self.fixture.remote)), self.fixture.root, False), "updated")
        self.assertEqual(self.fixture.git(linked, "rev-parse", "HEAD").stdout.strip(), expected)

    def test_stale_tracking_ref_is_recreated(self):
        self.fixture.git(self.fixture.target, "update-ref", "-d", "refs/remotes/origin/main")
        self.fixture.push_change("two\n")
        fetched = self.fixture.remote_head()
        self.assertEqual(self.update(), "updated")
        self.assertEqual(self.fixture.target_head(), fetched)

    def test_url_mismatch_and_no_upstream_are_skipped(self):
        other = self.fixture.root / "other.git"
        self.fixture.git(self.fixture.root, "init", "--bare", str(other))
        self.fixture.git(self.fixture.target, "remote", "set-url", "origin", str(other))
        self.assertEqual(self.update(), "skipped")
        self.fixture.git(self.fixture.target, "config", "--unset-all", "branch.main.remote")
        self.assertEqual(self.update(), "skipped")

    def test_pushurl_is_not_part_of_fetch_identity(self):
        self.fixture.git(self.fixture.target, "config", "remote.origin.pushurl", str(self.fixture.root / "push-only.git"))
        self.fixture.push_change("two\n")
        self.assertEqual(self.update(), "updated")

    def test_saved_hooks_are_not_run_and_config_is_unchanged(self):
        hooks = self.fixture.root / "saved hooks"
        hooks.mkdir()
        sentinel = self.fixture.root / "hook-ran"
        hook = hooks / "post-merge"
        hook.write_text(
            f"#!/bin/sh\nprintf ran > '{sentinel.as_posix()}'\n",
            encoding="utf-8",
        )
        hook.chmod(0o755)
        reference_hook = hooks / "reference-transaction"
        reference_hook.write_text(
            f"#!/bin/sh\nprintf ran > '{sentinel.as_posix()}'\n",
            encoding="utf-8",
        )
        reference_hook.chmod(0o755)
        self.fixture.git(self.fixture.target, "config", "core.hooksPath", str(hooks))
        config = self.fixture.target / ".git" / "config"
        before = config.read_bytes()
        self.fixture.push_change("hooks\n")
        real_git = app._git
        calls = []

        def observe_git(target, args, hooks_path=None, **kwargs):
            calls.append((Path(target), Path(hooks_path) if hooks_path is not None else None, tuple(args)))
            return real_git(target, args, hooks_path, **kwargs)

        with patch.object(app, "_git", side_effect=observe_git):
            self.assertEqual(self.update(), "updated")
        self.assertFalse(sentinel.exists())
        self.assertEqual(config.read_bytes(), before)
        self.assertTrue(calls)
        hook_paths = {str(path) for _, path, _ in calls}
        self.assertEqual(len(hook_paths), 1)
        self.assertIn(" ", next(iter(hook_paths)))
        self.assertTrue(all(path.is_absolute() for target, path, _ in calls))
        self.assertTrue(all(target == self.fixture.target.resolve() for target, _, _ in calls))
        self.assertTrue(all("-C" not in args for _, _, args in calls))
        fetches = [args for _, _, args in calls if args and args[0] == "fetch"]
        merges = [args for _, _, args in calls if args and args[0] == "merge"]
        self.assertEqual(len(fetches), 1)
        self.assertIn("--refmap=", fetches[0])
        self.assertFalse(any(arg.startswith("+") for arg in fetches[0]))
        self.assertEqual(len(merges), 1)
        self.assertIn("--ff-only", merges[0])
        self.assertIn("--no-autostash", merges[0])
        self.assertIn("--no-overwrite-ignore", merges[0])

    def test_noncolliding_ignored_file_is_preserved_during_update(self):
        (self.fixture.writer / ".gitignore").write_text("local-only.txt\n", encoding="utf-8")
        self.fixture.git(self.fixture.writer, "add", ".gitignore")
        self.fixture.git(self.fixture.writer, "commit", "-m", "ignore")
        self.fixture.git(self.fixture.writer, "push", "origin", "main")
        self.fixture.git(self.fixture.target, "pull", "--ff-only")
        ignored = self.fixture.target / "local-only.txt"
        ignored.write_text("keep\n", encoding="utf-8")
        self.fixture.push_change("tracked-after-ignore\n")
        self.assertEqual(self.update(), "updated")
        self.assertEqual(ignored.read_text(), "keep\n")

    def test_submodule_recursion_setting_is_overridden_per_command(self):
        self.fixture.git(self.fixture.target, "config", "submodule.recurse", "true")
        self.fixture.push_change("no-recursion\n")
        self.assertEqual(self.update(), "updated")

    def test_dirty_submodule_is_skipped_and_recursion_is_not_attempted(self):
        subremote = self.fixture.root / "subremote.git"
        subwriter = self.fixture.root / "subwriter"
        self.fixture.git(self.fixture.root, "init", "--bare", str(subremote))
        self.fixture.git(self.fixture.root, "init", str(subwriter))
        self.fixture.git(subwriter, "config", "user.name", "Fixture User")
        self.fixture.git(subwriter, "config", "user.email", "fixture@example.com")
        self.fixture.git(subwriter, "symbolic-ref", "HEAD", "refs/heads/main")
        (subwriter / "sub.txt").write_text("sub\n", encoding="utf-8")
        self.fixture.git(subwriter, "add", "sub.txt")
        self.fixture.git(subwriter, "commit", "-m", "sub")
        self.fixture.git(subwriter, "remote", "add", "origin", str(subremote))
        self.fixture.git(subwriter, "push", "-u", "origin", "main")
        self.fixture.git(subremote, "symbolic-ref", "HEAD", "refs/heads/main")
        self.fixture.git(self.fixture.writer, "submodule", "add", str(subremote), "submodule")
        self.fixture.git(self.fixture.writer, "add", ".gitmodules", "submodule")
        self.fixture.git(self.fixture.writer, "commit", "-m", "submodule")
        self.fixture.git(self.fixture.writer, "push", "origin", "main")
        self.fixture.git(self.fixture.target, "pull", "--ff-only", "origin", "main")
        self.fixture.git(self.fixture.target, "submodule", "update", "--init")
        (self.fixture.target / "submodule" / "sub.txt").write_text("dirty\n", encoding="utf-8")
        self.fixture.push_change("parent-after-submodule\n")
        self.fixture.git(self.fixture.target, "config", "submodule.recurse", "true")
        self.assertEqual(self.update(), "skipped")

    def test_fetch_state_race_is_skipped_without_retry(self):
        self.fixture.push_change("race\n")
        real_snapshot = app._snapshot
        calls = 0

        def racing_snapshot(target, expected_url, hooks_path):
            nonlocal calls
            calls += 1
            snapshot = real_snapshot(target, expected_url, hooks_path)
            if calls == 2:
                return replace(snapshot, head_oid="0" * 40)
            return snapshot

        with patch.object(app, "_remote_identity", side_effect=self.local_identity), \
                patch.object(app, "_snapshot", side_effect=racing_snapshot):
            self.assertEqual(app.clone(self.repo(), self.fixture.root, False), "skipped")
        self.assertEqual(calls, 2)

    def test_postcondition_branch_change_fails_without_rollback(self):
        self.fixture.push_change("postcondition\n")
        real_git = app._git

        def branch_race(target, args, hooks_path=None, **kwargs):
            result = real_git(target, args, hooks_path, **kwargs)
            if args and args[0] == "merge":
                merged = self.fixture.git(self.fixture.target, "rev-parse", "HEAD").stdout.strip()
                self.fixture.git(self.fixture.target, "branch", "raced", merged)
                self.fixture.git(self.fixture.target, "symbolic-ref", "HEAD", "refs/heads/raced")
            return result

        with patch.object(app, "_remote_identity", side_effect=self.local_identity), \
                patch.object(app, "_git", side_effect=branch_race):
            with self.assertRaisesRegex(app.ClonerError, "unexpected HEAD"):
                app.clone(self.repo(), self.fixture.root, False)
        self.assertEqual(
            self.fixture.git(self.fixture.target, "symbolic-ref", "-q", "HEAD").stdout.strip(),
            "refs/heads/raced",
        )

    def test_git_update_error_does_not_stop_next_repository(self):
        target2 = self.fixture.root / "target2"
        self.fixture.git(self.fixture.root, "clone", "--branch", "main", str(self.fixture.remote), str(target2))
        self.fixture.git(target2, "config", "user.name", "Fixture User")
        self.fixture.git(target2, "config", "user.email", "fixture@example.com")
        self.fixture.push_change("next\n")
        config = self.fixture.root / "run.json"
        config.write_text(
            json.dumps({
                "destination": str(self.fixture.root.parent),
                "sources": [{"name": self.fixture.root.name}],
            }),
            encoding="utf-8",
        )
        repositories = [
            app.Repository("target", str(self.fixture.remote)),
            app.Repository("target2", str(self.fixture.remote)),
        ]
        real_git = app._git

        def fail_first(target, args, hooks_path=None, **kwargs):
            if Path(target).name == "target" and args and args[0] == "fetch":
                raise app.ClonerError("simulated fetch failure")
            return real_git(target, args, hooks_path, **kwargs)

        with patch.object(app, "_remote_identity", side_effect=self.local_identity), \
                patch.object(app, "repositories", return_value=repositories), \
                patch.object(app, "_git", side_effect=fail_first):
            self.assertEqual(app.run(config, False), 1)
        self.assertEqual(self.fixture.git(target2, "rev-parse", "HEAD").stdout.strip(), self.fixture.remote_head())

    def test_multiple_fetch_urls_are_skipped(self):
        self.fixture.git(self.fixture.target, "config", "--add", "remote.origin.url", str(self.fixture.root / "other.git"))
        self.fixture.push_change("two\n")
        self.assertEqual(self.update(), "skipped")

    def test_explicit_fetch_does_not_update_other_refs(self):
        self.fixture.git(self.fixture.target, "branch", "keep")
        self.fixture.git(self.fixture.target, "tag", "keep-tag")
        before_branch = self.fixture.git(self.fixture.target, "rev-parse", "refs/heads/keep").stdout.strip()
        before_tag = self.fixture.git(self.fixture.target, "rev-parse", "refs/tags/keep-tag").stdout.strip()
        self.fixture.push_change("two\n")
        self.assertEqual(self.update(), "updated")
        self.assertEqual(self.fixture.git(self.fixture.target, "rev-parse", "refs/heads/keep").stdout.strip(), before_branch)
        self.assertEqual(self.fixture.git(self.fixture.target, "rev-parse", "refs/tags/keep-tag").stdout.strip(), before_tag)

    def test_detached_head_is_skipped(self):
        self.fixture.git(self.fixture.target, "checkout", "--detach", "HEAD")
        self.assertEqual(self.update(), "skipped")

    def test_non_git_directory_is_skipped_without_git_or_temp(self):
        target = self.fixture.root / "empty"
        target.mkdir()
        with patch.object(app.subprocess, "run") as run, \
                patch.object(app.tempfile, "TemporaryDirectory") as temporary:
            self.assertEqual(app.clone(app.Repository("empty", "https://example.com/repo"), self.fixture.root, False), "skipped")
        run.assert_not_called()
        temporary.assert_not_called()

    def test_dry_run_existing_directory_has_no_git_or_temp_operation(self):
        with patch.object(app.subprocess, "run") as run, \
                patch.object(app.tempfile, "TemporaryDirectory") as temporary:
            self.assertEqual(app.clone(self.repo(), self.fixture.root, True), "planned")
        run.assert_not_called()
        temporary.assert_not_called()

    def test_dry_run_missing_target_does_not_create_parent(self):
        parent = self.fixture.root / "absent"
        repo = app.Repository("repo", "git@example.com:p/repo.git")
        with patch.object(app.subprocess, "run") as run, \
                patch.object(app.tempfile, "TemporaryDirectory") as temporary:
            self.assertEqual(app.clone(repo, parent, True), "planned")
        self.assertFalse(parent.exists())
        run.assert_not_called()
        temporary.assert_not_called()

    def test_prepare_cleanup_failure_reports_path(self):
        hooks = self.fixture.root / "prepare hooks"
        hooks.mkdir()
        (hooks / "occupied").write_text("x", encoding="utf-8")

        class BrokenTemporary:
            name = str(hooks)

            def cleanup(self):
                raise OSError("cannot remove")

        with patch.object(app.tempfile, "TemporaryDirectory", return_value=BrokenTemporary()):
            with self.assertRaises(app.ClonerError):
                self.update()
        self.assertIn(str(hooks), self.output.getvalue())
        shutil.rmtree(hooks)

    def test_git_error_and_cleanup_failure_preserve_original_error(self):
        hooks = self.fixture.root / "error hooks"
        hooks.mkdir()

        class BrokenTemporary:
            name = str(hooks)

            def cleanup(self):
                raise OSError("cannot remove")

        with patch.object(app.tempfile, "TemporaryDirectory", return_value=BrokenTemporary()), \
                patch.object(app, "_snapshot", side_effect=app.ClonerError("fetch setup failed")):
            with self.assertRaisesRegex(app.ClonerError, "fetch setup failed"):
                self.update()
        self.assertIn(str(hooks), self.output.getvalue())
        shutil.rmtree(hooks)

    def test_keyboard_interrupt_and_cleanup_failure_preserve_130_path(self):
        hooks = self.fixture.root / "interrupt hooks"
        hooks.mkdir()

        class BrokenTemporary:
            name = str(hooks)

            def cleanup(self):
                raise OSError("cannot remove")

        with patch.object(app.tempfile, "TemporaryDirectory", return_value=BrokenTemporary()), \
                patch.object(app, "_snapshot", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.update()
        self.assertIn(str(hooks), self.output.getvalue())
        shutil.rmtree(hooks)

    def test_success_with_cleanup_failure_is_not_reported_as_updated(self):
        hooks = self.fixture.root / "success hooks"
        hooks.mkdir()
        self.fixture.push_change("cleanup\n")

        class BrokenTemporary:
            name = str(hooks)

            def cleanup(self):
                raise OSError("cannot remove")

        with patch.object(app.tempfile, "TemporaryDirectory", return_value=BrokenTemporary()):
            with self.assertRaisesRegex(app.ClonerError, "Temporary hooks directory cleanup failed"):
                self.update()
        self.assertIn(str(hooks), self.output.getvalue())
        shutil.rmtree(hooks)

    def test_existing_file_is_preserved(self):
        file_target = self.fixture.root / "file-target"
        file_target.write_text("keep", encoding="utf-8")
        self.assertEqual(app.clone(app.Repository("file-target", "https://example.com/repo"), self.fixture.root, False), "skipped")
        self.assertEqual(file_target.read_text(), "keep")

    @unittest.skipUnless(os.name == "nt", "Windows junction contract")
    def test_windows_junction_is_preserved_without_git(self):
        junction = self.fixture.root / "junction-target"
        subprocess.run(
            ["cmd", "/d", "/c", "mklink", "/J", str(junction), str(self.fixture.target)],
            check=True, capture_output=True,
        )
        try:
            self.assertTrue(app._is_reparse_point(junction))
            with patch.object(app.subprocess, "run") as run, \
                    patch.object(app.tempfile, "TemporaryDirectory") as temporary:
                self.assertEqual(
                    app.clone(
                        app.Repository(junction.name, "https://example.com/repo"),
                        self.fixture.root, False,
                    ),
                    "skipped",
                )
            run.assert_not_called()
            temporary.assert_not_called()
            self.assertTrue(junction.is_dir())
            self.assertEqual((self.fixture.target / "file.txt").read_text(), "one\n")
        finally:
            junction.rmdir()

    def test_symlink_is_preserved(self):
        file_target = self.fixture.root / "link-source"
        file_target.write_text("keep", encoding="utf-8")
        link = self.fixture.root / "link-target"
        try:
            link.symlink_to(file_target)
        except (OSError, NotImplementedError):
            self.skipTest("symbolic links are unavailable")
        self.assertEqual(app.clone(app.Repository("link-target", "https://example.com/repo"), self.fixture.root, False), "skipped")
        self.assertTrue(link.is_symlink())


class CloneFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.output = io.StringIO()
        self.stdout = redirect_stdout(self.output)
        self.stderr = redirect_stderr(self.output)
        self.stdout.__enter__()
        self.stderr.__enter__()
        self.addCleanup(self.stderr.__exit__, None, None, None)
        self.addCleanup(self.stdout.__exit__, None, None, None)

    def tearDown(self):
        self.temp.cleanup()

    def test_new_clone_success_and_existing_invalid_git_is_failed(self):
        repo = app.Repository("repo", "git@example.com:p/repo.git")

        def fake_clone(args, check):
            target = Path(args[-1])
            target.mkdir()
            (target / ".git").mkdir()
            (target / "file").write_text("content", encoding="utf-8")

        with patch.object(app.subprocess, "run", side_effect=fake_clone) as run:
            self.assertEqual(app.clone(repo, self.root, False), "cloned")
        self.assertEqual(run.call_count, 1)
        self.assertEqual((self.root / "repo/file").read_text(), "content")
        with self.assertRaises(app.ClonerError):
            app.clone(repo, self.root, False)

    def test_failed_clone_not_marked_complete(self):
        repo = app.Repository("repo", "git@example.com:p/repo.git")

        def fake_clone(args, check):
            Path(args[-1]).mkdir()
            raise subprocess.CalledProcessError(128, args)

        with patch.object(app.subprocess, "run", side_effect=fake_clone):
            with self.assertRaises(app.ClonerError):
                app.clone(repo, self.root, False)
        self.assertFalse((self.root / "repo").exists())
        self.assertEqual(len(list(self.root.glob(".clone-*"))), 1)

    def test_invalid_paths_and_remote_helpers(self):
        for name in ("..", "../escape", "a/b", "a\\b", "CON", "trailing."):
            with self.assertRaises(app.ClonerError):
                app.folder_name(name)
        with self.assertRaises(app.ClonerError):
            app.clone(app.Repository("repo", "ext::command"), self.root, True)

    def test_source_failure_continues_and_counts_six_result_kinds(self):
        config = self.root / "config.json"
        config.write_text(json.dumps({"sources": [{"name": "a"}, {"name": "b"}]}), encoding="utf-8")
        repo = app.Repository("repo", "git@example.com:p/repo.git")
        with patch.object(app, "repositories", side_effect=[app.ClonerError("failure"), [repo]]):
            self.assertEqual(app.run(config, True), 1)
        output = self.output.getvalue()
        self.assertIn("planned=1", output)
        self.assertIn("updated=0 unchanged=0 skipped=0", output)
        self.assertFalse((self.root / "clones").exists())

    def test_clone_failure_continues(self):
        config = self.root / "config.json"
        config.write_text(json.dumps({"sources": [{"name": "a"}]}), encoding="utf-8")
        repo = app.Repository("repo", "git@example.com:p/repo.git")
        with patch.object(app, "repositories", return_value=[repo, repo]), \
                patch.object(app, "clone", side_effect=[app.ClonerError("failure"), "planned"]):
            self.assertEqual(app.run(config, True), 1)
        self.assertIn("planned=1 failed=1", self.output.getvalue())

    def test_only_safe_skips_return_zero(self):
        config = self.root / "config.json"
        config.write_text(json.dumps({"sources": [{"name": "a"}]}), encoding="utf-8")
        repo = app.Repository("repo", "git@example.com:p/repo.git")
        with patch.object(app, "repositories", return_value=[repo]), \
                patch.object(app, "clone", return_value="skipped"):
            self.assertEqual(app.run(config, True), 0)
        self.assertIn("failed=0", self.output.getvalue())

    def test_main_returns_130_on_interrupt(self):
        with patch.object(app, "run", side_effect=KeyboardInterrupt), \
                patch("sys.argv", ["repo_cloner.py"]):
            self.assertEqual(app.main(), 130)
        self.assertIn("Interrupted", self.output.getvalue())

    def test_all_six_counts_are_unique_per_repository(self):
        config = self.root / "config.json"
        config.write_text(json.dumps({"sources": [{"name": "a"}]}), encoding="utf-8")
        repos = [app.Repository(str(index), "git@example.com:p/repo.git") for index in range(6)]
        with patch.object(app, "repositories", return_value=repos), \
                patch.object(
                    app,
                    "clone",
                    side_effect=["cloned", "updated", "unchanged", "skipped", "planned", app.ClonerError("failure")],
                ):
            self.assertEqual(app.run(config, True), 1)
        self.assertIn(
            "cloned=1 updated=1 unchanged=1 skipped=1 planned=1 failed=1",
            self.output.getvalue(),
        )


class DestinationSelectionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.config = self.root / "settings" / "repos.json"
        self.config.parent.mkdir()
        self.data = {
            "destination": "../copies",
            "sources": [{
                "name": "chosen",
                "provider": "git",
                "repositories": [
                    {"name": "renamed", "url": "git@github.com:org/original.git"},
                ],
            }],
        }
        self.output = io.StringIO()
        stdout = redirect_stdout(self.output)
        stderr = redirect_stderr(self.output)
        stdout.__enter__()
        stderr.__enter__()
        self.addCleanup(stderr.__exit__, None, None, None)
        self.addCleanup(stdout.__exit__, None, None, None)

    def save(self):
        self.config.write_text(json.dumps(self.data), encoding="utf-8")

    def test_config_relative_destination_and_offline_preview(self):
        self.save()
        with patch.object(app, "Api") as api, \
                patch.object(app.subprocess, "run") as git, \
                patch.object(app.tempfile, "TemporaryDirectory") as temporary:
            self.assertEqual(app.run(self.config, True), 0)
        api.assert_not_called()
        git.assert_not_called()
        temporary.assert_not_called()
        target = self.root / "copies" / "chosen" / "renamed"
        self.assertIn(f"PLAN  CLONE git@github.com:org/original.git -> {target}", self.output.getvalue())
        self.assertFalse(target.parent.exists())

    def test_cli_relative_destination_uses_working_directory(self):
        self.save()
        old_cwd = Path.cwd()
        os.chdir(self.root)
        try:
            with patch("sys.argv", [
                "repo_cloner.py", "--config", str(self.config),
                "--destination", "command copies", "--dry-run",
            ]):
                self.assertEqual(app.main(), 0)
        finally:
            os.chdir(old_cwd)
        self.assertIn(str(self.root / "command copies" / "chosen" / "renamed"), self.output.getvalue())
        self.assertFalse((self.root / "command copies").exists())
        self.assertFalse((self.root / "copies").exists())

    def test_absolute_destination_overrides_config_and_routes_real_run(self):
        self.save()
        destination = self.root / "absolute copies"
        with patch.object(app.shutil, "which", return_value="git"), \
                patch.object(app, "clone", return_value="cloned") as clone:
            self.assertEqual(app.run(self.config, destination=destination), 0)
        clone.assert_called_once_with(
            app.Repository("renamed", "git@github.com:org/original.git"),
            destination / "chosen", False,
        )

    def test_config_destination_expands_home(self):
        self.data["destination"] = "~/copies"
        self.save()
        with patch.dict(os.environ, {"HOME": str(self.root), "USERPROFILE": str(self.root)}):
            self.assertEqual(app.run(self.config, True), 0)
        self.assertIn(str(self.root / "copies" / "chosen" / "renamed"), self.output.getvalue())

    def test_filters_are_case_sensitive_and_exclude_wins(self):
        source = self.data["sources"][0]
        source["include"] = ["api-*", "web-?"]
        source["exclude"] = ["*-old"]
        source["repositories"] = [
            {"name": name, "url": f"https://example.com/{name}.git"}
            for name in ("api-core", "api-old", "web-a", "API-extra", "notes")
        ]
        self.save()
        with patch.object(app, "clone", return_value="planned") as clone:
            self.assertEqual(app.run(self.config, True), 0)
        self.assertEqual([call.args[0].name for call in clone.call_args_list], ["api-core", "web-a"])
        self.assertIn("skipped=3 planned=2 failed=0", self.output.getvalue())

    def test_exclude_only_can_select_nothing_without_creating_folders(self):
        self.data["sources"][0]["exclude"] = ["*"]
        self.save()
        with patch.object(app, "clone") as clone:
            self.assertEqual(app.run(self.config, True), 0)
        clone.assert_not_called()
        self.assertIn("skipped=1 planned=0 failed=0", self.output.getvalue())
        self.assertFalse((self.root / "copies").exists())

    def test_api_name_errors_do_not_abort_filtered_repository_processing(self):
        self.data["sources"][0].update({
            "provider": "github", "organization": "org", "include": ["*"],
        })
        self.save()
        valid = app.Repository("valid", "https://example.com/valid.git")
        with patch.object(app, "repositories", return_value=[
            app.Repository(None, "https://example.com/bad.git"),
            app.Repository("../escape", "https://example.com/bad.git"),
            valid,
        ]), patch.object(app, "clone", return_value="planned") as clone:
            self.assertEqual(app.run(self.config, True), 1)
        clone.assert_called_once_with(valid, self.root / "copies" / "chosen", True)
        self.assertIn("skipped=0 planned=1 failed=2", self.output.getvalue())

    def test_invalid_patterns_fail_before_listing_or_cloning(self):
        for key in ("include", "exclude"):
            for invalid in ("*", None, [""], ["  "], [1]):
                with self.subTest(key=key, invalid=invalid):
                    self.data["sources"][0][key] = invalid
                    self.save()
                    with patch.object(app, "repositories") as repositories, \
                            patch.object(app, "clone") as clone, \
                            self.assertRaises(app.ClonerError):
                        app.run(self.config, True)
                    repositories.assert_not_called()
                    clone.assert_not_called()
            del self.data["sources"][0][key]

    def test_invalid_destination_is_reported_before_listing(self):
        for invalid in ("", " ", None, 12, []):
            with self.subTest(destination=invalid):
                self.data["destination"] = invalid
                self.save()
                with patch.object(app, "repositories") as repositories, \
                        self.assertRaises(app.ClonerError):
                    app.run(self.config, True)
                repositories.assert_not_called()

    def test_invalid_explicit_source_does_not_block_the_next_source(self):
        self.data["sources"].insert(0, {
            "name": "invalid", "provider": "git",
            "repositories": [{"name": "bad", "url": "ext::command"}],
        })
        self.save()
        self.assertEqual(app.run(self.config, True), 1)
        self.assertIn("planned=1 failed=1", self.output.getvalue())

    def test_existing_preview_is_unverified_and_redacts_invalid_url(self):
        target = self.root / "renamed"
        target.mkdir()
        with patch.object(app.subprocess, "run") as git, \
                patch.object(app.tempfile, "TemporaryDirectory") as temporary:
            self.assertEqual(app.clone(
                app.Repository("renamed", "https://secret@example.com/repo.git"),
                self.root, True,
            ), "planned")
        git.assert_not_called()
        temporary.assert_not_called()
        self.assertIn("UPDATE?", self.output.getvalue())
        self.assertIn("eligibility not checked", self.output.getvalue())
        self.assertNotIn("secret", self.output.getvalue())


if __name__ == "__main__":
    unittest.main()
