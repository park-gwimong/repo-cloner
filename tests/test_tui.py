from contextlib import nullcontext, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import repo_cloner as app
from repo_cloner_tui import TerminalUI, clipped


class MenuTests(unittest.TestCase):
    def setUp(self):
        self.ui = object.__new__(TerminalUI)

    def select(self, keys):
        with patch.object(self.ui, "screen", return_value=nullcontext()), \
                patch.object(self.ui, "draw", return_value=3), \
                patch.object(self.ui, "key", side_effect=keys):
            return self.ui.select("Repositories", ["a", "b", "c", "d"])

    def test_multi_select_navigation_and_toggle(self):
        self.assertEqual(self.select([" ", "down", " ", "up", " ", "end", " ", "enter"]), [1, 3])
        self.assertEqual(self.select(["a", "n", "pagedown", " ", "enter"]), [3])
        self.assertEqual(self.select(["a", "enter"]), [0, 1, 2, 3])
        self.assertEqual(self.select(["enter"]), [])

    def test_cancel_and_empty_list(self):
        with self.assertRaises(KeyboardInterrupt):
            self.select(["cancel"])
        with patch.object(self.ui, "screen") as screen:
            self.assertEqual(self.ui.select("Empty", []), [])
            screen.assert_not_called()

    def test_confirmation_accepts_enter_or_y_and_dry_run_only_finishes(self):
        for keys, dry_run, expected in [
            (["enter"], False, True), (["n"], False, False),
            (["enter"], True, False),
            (["y"], False, True), (["y", "enter"], True, False),
        ]:
            with self.subTest(keys=keys, dry_run=dry_run), \
                    patch.object(self.ui, "screen", return_value=nullcontext()), \
                    patch.object(self.ui, "draw", return_value=3), \
                    patch.object(self.ui, "key", side_effect=keys):
                self.assertEqual(self.ui.confirm(["CLONE repo"], dry_run=dry_run), expected)

    def test_small_screen_cannot_confirm_hidden_targets(self):
        with patch.object(self.ui, "screen", return_value=nullcontext()), \
                patch.object(self.ui, "draw", side_effect=[0, 0, 3]), \
                patch.object(self.ui, "key", side_effect=["y", "enter", "n"]):
            self.assertFalse(self.ui.confirm(["CLONE repo"]))

    def test_render_uses_real_escape_codes_and_sanitizes_labels(self):
        output = io.StringIO()
        with redirect_stdout(output), patch("repo_cloner_tui.shutil.get_terminal_size", return_value=(80, 24)):
            self.ui.draw("Test", ["abc\x1b[2J"], 0, set(), "Enter: next")
        self.assertTrue(output.getvalue().startswith("\x1b[H\x1b[2J"))
        self.assertIn("abc?[2J", output.getvalue())
        self.assertNotIn("abc\x1b", output.getvalue())
        self.assertEqual(clipped("\uac00\ub098\ub2e4", 4), "\uac00\ub098")

    def test_console_is_restored_on_exception(self):
        import ctypes
        kernel = Mock()
        kernel.GetStdHandle.return_value = 1
        def get_mode(handle, pointer):
            pointer._obj.value = 1
            return True
        kernel.GetConsoleMode.side_effect = get_mode
        kernel.SetConsoleMode.return_value = True
        output = io.StringIO()
        with patch("repo_cloner_tui.os.name", "nt"), \
                patch.object(ctypes, "WinDLL", return_value=kernel, create=True), \
                redirect_stdout(output):
            with self.assertRaises(KeyboardInterrupt):
                with self.ui.screen():
                    raise KeyboardInterrupt
        self.assertEqual(kernel.SetConsoleMode.call_args_list[-1].args, (1, 1))
        self.assertIn("\x1b[?25h\x1b[?1049l", output.getvalue())

    def test_horizontal_scroll(self):
        output = io.StringIO()
        self.ui.offset = 10
        with redirect_stdout(output), patch("repo_cloner_tui.shutil.get_terminal_size", return_value=(80, 24)):
            self.ui.draw("Test", ["0123456789visible"], 0, set(), "Enter")
        self.assertIn("visible", output.getvalue())
        self.assertNotIn("0123456789", output.getvalue())

    def test_windows_keys(self):
        import types
        fake = types.SimpleNamespace(getwch=Mock(side_effect=["\xe0", "H", "\r", " ", "\x03"]))
        with patch("repo_cloner_tui.os.name", "nt"), patch.dict("sys.modules", {"msvcrt": fake}):
            self.assertEqual([self.ui.key() for _ in range(4)], ["up", "enter", " ", "cancel"])

    def test_rejects_redirected_terminal(self):
        with patch("repo_cloner_tui.sys.stdin.isatty", return_value=False):
            with self.assertRaisesRegex(ValueError, "interactive terminal"):
                TerminalUI()


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.config = self.root / "config.json"
        self.config.write_text(json.dumps({"sources": [{
            "name": "team", "provider": "git", "repositories": [
                {"name": "one", "url": "https://example.com/team/one.git"},
                {"name": "two", "url": "https://example.com/team/two.git"}
            ]}]}), encoding="utf-8")
        self.ui = Mock()
        self.ui.select.return_value = [1]

    def run_config(self, **kwargs):
        with redirect_stdout(io.StringIO()), patch.object(app.shutil, "which", return_value="git"):
            return app.run(self.config, ui=self.ui, **kwargs)

    def test_dry_run_only_selected_repository_and_no_git(self):
        with patch.object(app.subprocess, "run") as git:
            self.assertEqual(self.run_config(dry_run=True), 0)
        git.assert_not_called()
        self.assertFalse((self.root / "clones").exists())
        self.ui.confirm.assert_called_once()
        labels = self.ui.confirm.call_args.args[0]
        self.assertEqual(len(labels), 1)
        self.assertIn("CLONE | team/two", labels[0])
        self.assertTrue(self.ui.confirm.call_args.kwargs["dry_run"])

    def test_decline_and_cancel_do_not_clone(self):
        self.ui.confirm.return_value = False
        with patch.object(app, "clone") as clone:
            self.assertEqual(self.run_config(), 0)
            self.ui.confirm.side_effect = KeyboardInterrupt
            with self.assertRaises(KeyboardInterrupt):
                self.run_config()
        clone.assert_not_called()

    def test_confirm_executes_selected_target(self):
        self.ui.confirm.return_value = True
        with patch.object(app, "clone", return_value="cloned") as clone:
            self.assertEqual(self.run_config(), 0)
        self.assertEqual(clone.call_args.args[0].name, "two")
        self.assertEqual(clone.call_args.args[1], self.root / "clones" / "team")

    def test_no_selection_does_not_confirm(self):
        self.ui.select.return_value = []
        with patch.object(app, "clone") as clone:
            self.assertEqual(self.run_config(), 0)
        clone.assert_not_called()
        self.ui.confirm.assert_not_called()


if __name__ == "__main__":
    unittest.main()
