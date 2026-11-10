from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import repo_cloner as app


ROOT = Path(__file__).resolve().parent.parent

PAGE = [
    {"name": "live", "ssh_url": "git@github.com:o/live.git", "owner": {"login": "o"}},
    {"name": "old", "ssh_url": "git@github.com:o/old.git", "owner": {"login": "o"}, "archived": True},
    {"name": "copy", "ssh_url": "git@github.com:o/copy.git", "owner": {"login": "o"}, "fork": True},
]


class GithubFilterTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.config = Path(temp.name) / "batch.json"

    def run_batch(self, **source):
        self.config.write_text(json.dumps({"sources": [
            {"name": "org", "provider": "github", "organization": "o", **source}]}), encoding="utf-8")
        planned = []
        output = io.StringIO()
        with patch.object(app.Api, "get", return_value=PAGE), \
                patch.object(app, "clone", side_effect=lambda repo, parent, dry: planned.append(repo.name) or "planned"), \
                redirect_stdout(output), redirect_stderr(output):
            code = app.run(self.config, dry_run=True)
        return code, planned, output.getvalue()

    def test_listing_reads_archived_and_fork_flags(self):
        with patch.object(app.Api, "get", return_value=PAGE):
            repos = list(app.repositories({"provider": "github", "organization": "o"}, "ssh"))
        self.assertEqual([(r.name, r.archived, r.fork) for r in repos],
                         [("live", False, False), ("old", True, False), ("copy", False, True)])

    def test_default_keeps_every_repository(self):
        code, planned, _ = self.run_batch()
        self.assertEqual((code, planned), (0, ["live", "old", "copy"]))

    def test_skip_flags_count_as_skipped_with_reason(self):
        code, planned, output = self.run_batch(skipArchived=True, skipForks=True)
        self.assertEqual((code, planned), (0, ["live"]))
        self.assertIn("SKIP  [org/old] (archived)", output)
        self.assertIn("SKIP  [org/copy] (fork)", output)
        self.assertIn("skipped=2", output)
        _, planned, _ = self.run_batch(skipArchived=True, skipForks=False)
        self.assertEqual(planned, ["live", "copy"])

    def test_invalid_or_unsupported_settings_stop_at_start(self):
        with self.assertRaisesRegex(app.ClonerError, "skipForks must be true or false"):
            self.run_batch(skipForks="yes")
        self.config.write_text(json.dumps({"sources": [{"name": "x", "provider": "git", "skipArchived": True,
                               "repositories": [{"name": "r", "url": "https://example.com/r.git"}]}]}),
                               encoding="utf-8")
        with self.assertRaisesRegex(app.ClonerError, "only supported for GitHub"), \
                redirect_stdout(io.StringIO()):
            app.run(self.config, dry_run=True)

    def test_selection_menu_marks_archived_and_forks(self):
        ui = Mock()
        ui.select.return_value = []
        config = {"destination": str(self.config.parent / "clones"),
                  "sources": [{"name": "org", "provider": "github", "organization": "o"}]}
        with patch.object(app.Api, "get", return_value=PAGE), redirect_stdout(io.StringIO()):
            app.run(self.config, True, ui=ui, config=config)
        labels = ui.select.call_args.args[1]
        self.assertTrue(labels[0].startswith("org/live ->"))
        self.assertTrue(labels[1].startswith("org/old [archived] ->"))
        self.assertTrue(labels[2].startswith("org/copy [fork] ->"))


class ExampleTests(unittest.TestCase):
    def test_batch_examples_hold_no_secrets_and_pass_validation(self):
        examples = sorted((ROOT / "examples").glob("batch.*.json"))
        self.assertTrue(examples)
        for path in examples:
            with self.subTest(example=path.name):
                document = json.loads(path.read_text(encoding="utf-8"))
                sources = document["sources"]
                self.assertTrue(all("token" not in s and "username" not in s for s in sources))
                references = [document.get("credentials")] + [s.get("credentials") for s in sources]
                self.assertTrue(all(r is None or r.startswith("./") for r in references))
                # Start-up validation passes once the referenced credential files exist.
                with tempfile.TemporaryDirectory() as directory:
                    copy = Path(directory) / "batch.json"
                    copy.write_text(json.dumps(document), encoding="utf-8")
                    for reference in filter(None, references):
                        (Path(directory) / reference).write_text(
                            json.dumps({"username": "you@example.com", "token": "fake"}), encoding="utf-8")
                    with patch.object(app, "repositories", return_value=iter(())), \
                            redirect_stdout(io.StringIO()):
                        self.assertEqual(app.run(copy, dry_run=True), 0)


if __name__ == "__main__":
    unittest.main()
