from contextlib import ExitStack, redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import repo_cloner as app


PROJECT_NAMES = {"A": "관제 시스템", "B": "Beta", "C": "beta", "BAD": "a/b"}


def fake_listing(source, protocol):
    provider = source["provider"]
    if provider in {"bitbucket-cloud", "bitbucket-server"}:
        key = source["project"]
        return iter([app.Repository(f"{key.lower()}-repo", f"https://example.com/{key}.git",
                                    PROJECT_NAMES[key])])
    if provider == "github":
        return iter([app.Repository("svc", "https://example.com/svc.git", "MyOrg")])
    if provider == "github-user":
        return iter([app.Repository("dotfiles", "https://example.com/dotfiles.git", "octo-cat")])
    return iter(app.Repository(r["name"], r["url"]) for r in source["repositories"])


class LayoutTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.config = self.root / "batch.json"

    def run_batch(self, document, *, interactive=False, selections=None):
        self.config.write_text(json.dumps({"destination": "./clones", **document}), encoding="utf-8")
        targets = []

        def clone(repo, parent, dry_run):
            targets.append((parent / repo.name).relative_to(self.root / "clones").as_posix())
            return "planned"
        err = io.StringIO()
        with ExitStack() as stack:
            stack.enter_context(patch.object(app, "repositories", side_effect=fake_listing))
            stack.enter_context(patch.object(app, "clone", side_effect=clone))
            if selections is not None:
                stack.enter_context(patch.object(app, "_select_indices", side_effect=selections))
            stack.enter_context(redirect_stdout(io.StringIO()))
            stack.enter_context(redirect_stderr(err))
            code = app.run(self.config, dry_run=True, interactive=interactive)
        return code, targets, err.getvalue()

    SOURCES = [
        {"name": "company", "provider": "bitbucket-cloud", "workspace": "w", "projects": ["A", "B"]},
        {"name": "srv", "provider": "bitbucket-server", "baseUrl": "https://bb.example.com", "project": "C"},
        {"name": "gh", "provider": "github", "organization": "my-org"},
        {"name": "mine", "provider": "github-user", "token": "t"},
        {"name": "team", "provider": "git", "repositories": [{"name": "r", "url": "https://example.com/r.git"}]},
    ]

    def test_default_layout_keeps_existing_source_paths(self):
        sources = [s for s in self.SOURCES if s["name"] != "srv"]
        code, targets, _ = self.run_batch({"sources": sources})
        self.assertEqual(code, 0)
        self.assertEqual(targets, ["company/A/a-repo", "company/B/b-repo", "gh/svc", "mine/dotfiles", "team/r"])

    def test_project_layout_uses_the_same_folders_as_tui(self):
        sources = [s for s in self.SOURCES if s["name"] != "srv"]
        code, targets, _ = self.run_batch({"layout": "project", "sources": sources})
        self.assertEqual(code, 0)
        # Organization keeps the configured spelling, like TUI; personal uses the owner login.
        self.assertEqual(targets, ["관제 시스템/a-repo", "Beta/b-repo", "my-org/svc", "octo-cat/dotfiles", "team/r"])

    def test_project_layout_rejects_folder_collisions_but_keeps_other_sources(self):
        # Project B "Beta" and project C "beta" collide on case-insensitive file systems.
        code, targets, err = self.run_batch({"layout": "project", "sources": self.SOURCES[:2]})
        self.assertEqual(code, 1)
        self.assertEqual(targets, ["관제 시스템/a-repo", "Beta/b-repo"])
        self.assertIn("already used by another source", err)

    def test_project_layout_reports_unusable_project_names(self):
        code, targets, err = self.run_batch({"layout": "project", "sources": [
            {"name": "x", "provider": "bitbucket-cloud", "workspace": "w", "project": "BAD"}]})
        self.assertEqual((code, targets), (1, []))
        self.assertIn('use layout "source"', err)

    def test_invalid_layout_value_stops_at_start(self):
        with self.assertRaisesRegex(app.ClonerError, "layout must be"):
            self.run_batch({"layout": "flat", "sources": self.SOURCES[-1:]})

    def test_interactive_mode_follows_project_layout(self):
        def available(source):
            return [("A", PROJECT_NAMES["A"]), ("B", PROJECT_NAMES["B"])]
        with patch.object(app, "available_projects", side_effect=available), \
                patch("builtins.input", return_value="y"):
            code, targets, _ = self.run_batch(
                {"layout": "project", "sources": [self.SOURCES[0]]},
                interactive=True, selections=[[0, 1], [0, 1]])
        self.assertEqual(code, 0)
        self.assertEqual(targets, ["관제 시스템/a-repo", "Beta/b-repo"])

    def test_tui_ignores_layout_and_keeps_its_own_folders(self):
        from unittest.mock import Mock
        ui = Mock()
        ui.select.side_effect = [[0]]
        config = {"destination": str(self.root / "clones"), "layout": "project",
                  "sources": [{"name": "team", "provider": "git",
                               "repositories": [{"name": "r", "url": "https://example.com/r.git"}]}]}
        targets = []
        with patch.object(app, "clone", side_effect=lambda repo, parent, dry: targets.append(parent) or "planned"), \
                redirect_stdout(io.StringIO()):
            self.assertEqual(app.run(self.config, True, ui=ui, config=config), 0)
        self.assertEqual(targets, [self.root / "clones" / "team"])


class NamespaceTests(unittest.TestCase):
    def test_bitbucket_clone_link_reads_project_display_name(self):
        item = {"slug": "api", "project": {"key": "A", "name": "관제 시스템"},
                "links": {"clone": [{"name": "ssh", "href": "git@bitbucket.org:w/api.git"}]}}
        self.assertEqual(app.clone_link(item, "ssh").namespace, "관제 시스템")
        del item["project"]
        self.assertIsNone(app.clone_link(item, "ssh").namespace)

    def test_github_listing_reads_owner_login(self):
        page = [{"name": "dotfiles", "ssh_url": "git@github.com:octo-cat/dotfiles.git",
                 "clone_url": "https://github.com/octo-cat/dotfiles.git", "owner": {"login": "octo-cat"}}]
        with patch.object(app.Api, "get", return_value=page):
            repos = list(app.repositories({"provider": "github-user", "token": "t"}, "ssh"))
        self.assertEqual([(r.name, r.namespace) for r in repos], [("dotfiles", "octo-cat")])

    def test_namespace_does_not_affect_equality(self):
        self.assertEqual(app.Repository("a", "u", "x"), app.Repository("a", "u"))


if __name__ == "__main__":
    unittest.main()
