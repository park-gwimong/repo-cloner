from contextlib import redirect_stdout
import io
import unittest
from unittest.mock import patch

import repo_cloner as app


class CliTests(unittest.TestCase):
    def test_version_prints_package_version_and_exits(self):
        output = io.StringIO()
        with patch("sys.argv", ["repo-cloner", "--version"]), redirect_stdout(output), \
                patch("repo_cloner_tui.TerminalUI") as ui:
            with self.assertRaises(SystemExit) as caught:
                app.main()
        self.assertEqual(caught.exception.code, 0)
        self.assertEqual(output.getvalue().strip(), f"repo-cloner {app.__version__}")
        ui.assert_not_called()


if __name__ == "__main__":
    unittest.main()
