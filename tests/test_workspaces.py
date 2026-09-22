from contextlib import redirect_stdout
import io
from pathlib import Path
import unittest
from unittest.mock import patch

import repo_cloner as app
from repo_cloner_tui import TerminalUI


class WorkspaceTests(unittest.TestCase):
    def test_all_pages_deduplicated_sorted_and_missing_name_uses_slug(self):
        credentials = {"username": "user@example.com", "token": "test-secret"}
        next_url = "https://api.bitbucket.org/2.0/user/workspaces?page=2"
        output = io.StringIO()
        with patch.object(app.Api, "get", side_effect=[
            {"values": [{"workspace": {"slug": "zulu"}},
                        {"workspace": {"slug": "team", "name": "Alpha"}}], "next": next_url},
            {"values": [{"workspace": {"slug": "team", "name": "Alpha"}},
                        {"workspace": {"slug": "beta", "name": "Beta"}}]},
        ]) as get, redirect_stdout(output):
            result = app.available_workspaces(credentials)
        self.assertEqual(result, [("team", "Alpha"), ("beta", "Beta"), ("zulu", "zulu")])
        self.assertEqual(get.call_args_list[0].args[0], "https://api.bitbucket.org/2.0/user/workspaces?pagelen=100")
        self.assertEqual(get.call_args_list[1].args[0], next_url)
        self.assertIn("page 2", output.getvalue())
        self.assertNotIn("test-secret", output.getvalue())
        self.assertNotIn("user@example.com", output.getvalue())

    def test_repeated_page_is_rejected(self):
        first = "https://api.bitbucket.org/2.0/user/workspaces?pagelen=100"
        with patch.object(app.Api, "get", return_value={"values": [], "next": first}) as get, \
                redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(app.ClonerError, "repeated workspace"):
                app.available_workspaces({})
        get.assert_called_once()

    def test_permission_failure_explains_scope(self):
        with patch.object(app.Api, "get", side_effect=app.ClonerError("API HTTP 403")), \
                redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(app.ClonerError, "read:workspace:bitbucket"):
                app.available_workspaces({})

    def test_invalid_responses_are_reported(self):
        for response in ([], {}, {"values": [None]}, {"values": [{"workspace": {}}]},
                         {"values": [], "next": ["bad"]}):
            with self.subTest(response=response), patch.object(app.Api, "get", return_value=response), \
                    redirect_stdout(io.StringIO()):
                with self.assertRaises(app.ClonerError):
                    app.available_workspaces({})

    def test_empty_list_or_failure_stops_setup_without_manual_workspace_input(self):
        for result in ([], app.ClonerError("API HTTP 401")):
            ui = object.__new__(TerminalUI)
            effect = result if isinstance(result, Exception) else None
            with patch.object(app, "available_workspaces", return_value=result, side_effect=effect), \
                    patch.object(ui, "choose", side_effect=[0, 0]) as choose, \
                    patch.object(ui, "edit", return_value=str(Path.cwd())) as edit:
                with self.assertRaises(app.ClonerError):
                    ui.configure({}, Path("repositories.json"))
            self.assertEqual(edit.call_count, 1)  # Destination only.
            self.assertEqual(choose.call_count, 2)  # Protocol and provider only.

    def test_cancel_workspace_menu_stops_setup(self):
        ui = object.__new__(TerminalUI)
        with patch.object(app, "available_workspaces", return_value=[("team", "Team")]), \
                patch.object(ui, "choose", side_effect=[0, 0, KeyboardInterrupt]), \
                patch.object(ui, "edit", return_value=str(Path.cwd())) as edit:
            with self.assertRaises(KeyboardInterrupt):
                ui.configure({}, Path("repositories.json"))
        self.assertEqual(edit.call_count, 1)


if __name__ == "__main__":
    unittest.main()
