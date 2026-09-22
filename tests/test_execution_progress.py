from contextlib import nullcontext, redirect_stdout
import io
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
from unittest.mock import Mock, patch

import repo_cloner as app
from repo_cloner_progress import Progress, execute


class ExecutionProgressTests(unittest.TestCase):
    def setUp(self):
        self.output = io.StringIO()
        self.counts = dict.fromkeys(("cloned", "updated", "unchanged", "skipped", "planned", "failed"), 0)
        self.ui = Mock()
        self.ui.screen.return_value = nullcontext()
        self.ui.key.return_value = "enter"
        with redirect_stdout(self.output):
            self.progress = Progress(self.ui, 2, self.counts)

    def test_git_output_and_carriage_return_progress_are_captured(self):
        with patch.object(self.progress, "poll_cancel"), patch.object(self.progress, "environment", return_value=os.environ.copy()):
            result = self.progress.run([sys.executable, "-c",
                "import sys; print('machine-output'); sys.stderr.write('Receiving: 50%\\rReceiving: 100%\\n')"],
                capture_output=True, text=True, encoding="utf-8", errors="surrogateescape", check=True)
        self.assertEqual(result.stdout.strip(), "machine-output")
        self.assertIn("Receiving: 100%", result.stderr)
        self.assertNotIn("machine-output", self.output.getvalue())
        self.assertIn("Receiving: 100%", self.output.getvalue())

    def test_host_key_failure_is_visible_without_prompting(self):
        with patch.object(self.progress, "poll_cancel"), patch.object(self.progress, "environment", return_value=os.environ.copy()):
            with self.assertRaises(subprocess.CalledProcessError):
                self.progress.run([sys.executable, "-c",
                    "import sys; sys.stderr.write('Host key verification failed.\\n'); sys.exit(128)"], check=True)
        self.assertTrue(self.progress.auth_required)
        self.assertIn("AUTH / SSH SETUP REQUIRED", self.output.getvalue())

    def test_environment_keeps_ssh_options_and_disables_prompts(self):
        command = '"C:/Program Files/OpenSSH/ssh.exe" -i "C:/keys/my key" -o StrictHostKeyChecking=ask'
        with patch.dict(os.environ, {"GIT_SSH_COMMAND": command, "GIT_SSH_VARIANT": "ssh"}):
            env = self.progress.environment(None)
        self.assertEqual(env["GIT_TERMINAL_PROMPT"], "0")
        self.assertEqual(env["GCM_INTERACTIVE"], "never")
        self.assertTrue(env["GIT_SSH_COMMAND"].startswith('"C:/Program Files/OpenSSH/ssh.exe" -o BatchMode=yes -o StrictHostKeyChecking=yes'))
        self.assertIn('-i "C:/keys/my key"', env["GIT_SSH_COMMAND"])

    def test_configured_ssh_command_is_preserved(self):
        with patch.dict(os.environ, {}, clear=True), patch("repo_cloner_progress.subprocess.run",
                return_value=subprocess.CompletedProcess([], 0, 'ssh -F "C:/ssh config"\n', '')) as config:
            env = self.progress.environment(str(Path.cwd()))
        self.assertIn('-F "C:/ssh config"', env["GIT_SSH_COMMAND"])
        config.assert_called_once()

    def test_long_silence_is_not_labeled_authentication_failure(self):
        self.progress.last_output = time.monotonic() - 20
        self.progress.render()
        self.assertIn("No Git output", self.output.getvalue())
        self.assertNotIn("AUTH / SSH", self.output.getvalue())

    def test_cancel_stops_running_child(self):
        created = []
        popen = subprocess.Popen
        def spawn(*args, **kwargs):
            process = popen(*args, **kwargs)
            created.append(process)
            return process
        with patch.object(self.progress, "poll_cancel", side_effect=KeyboardInterrupt), \
                patch.object(self.progress, "environment", return_value=os.environ.copy()), \
                patch("repo_cloner_progress.subprocess.Popen", side_effect=spawn):
            with self.assertRaises(KeyboardInterrupt):
                self.progress.run([sys.executable, "-c", "import time; time.sleep(30)"], check=True)
        self.assertIsNotNone(created[0].poll())

    def test_tasks_continue_after_failure_and_context_restores(self):
        tasks = [(app.Repository(name, "git@example.com:a/repo.git"), Path.cwd(), "team") for name in ("one", "two")]
        def clone(repo, parent, dry_run):
            self.assertFalse(dry_run)
            self.assertIsNotNone(app._git_process_runner.get())
            if repo.name == "one":
                print("Host key verification failed.")
                print("Partial clone retained: C:/copies/.clone-example")
                raise app.ClonerError("Clone failed")
            return "cloned"
        with patch.object(Progress, "poll_cancel"), redirect_stdout(self.output):
            self.assertEqual(execute(self.ui, tasks, self.counts, clone, app.ClonerError, app._git_process_runner), 1)
        self.assertIsNone(app._git_process_runner.get())
        self.assertEqual(self.counts["cloned"], 1)
        self.assertEqual(self.counts["failed"], 1)
        self.assertIn("2/2 (100%)", self.output.getvalue())
        self.assertIn("C:/copies/.clone-example", self.output.getvalue())

    def test_core_git_uses_adapter_and_preserves_result(self):
        expected = subprocess.CompletedProcess([], 0, "test\n", "")
        runner = Mock(return_value=expected)
        token = app._git_process_runner.set(runner)
        try:
            self.assertIs(app._git(Path.cwd(), ["status"]), expected)
        finally:
            app._git_process_runner.reset(token)
        runner.assert_called_once()

    def test_dry_run_never_opens_execution_ui(self):
        config = {"sources": [{"name": "test", "provider": "git", "repositories": [
            {"name": "repo", "url": "https://example.com/repo.git"}]}]}
        self.ui.select.return_value = [0]
        with redirect_stdout(self.output), patch("repo_cloner_progress.execute") as execute_mock:
            self.assertEqual(app.run(Path("unused.json"), True, ui=self.ui, config=config, progress_ui=self.ui), 0)
        execute_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
