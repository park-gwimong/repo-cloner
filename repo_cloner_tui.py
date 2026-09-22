"""Dependency-free full-screen selection for Windows and POSIX terminals."""

from contextlib import contextmanager
import os
from pathlib import Path
import shutil
import sys
import textwrap
import unicodedata


def clipped(text, width):
    """Remove terminal controls and truncate by display cells, including CJK."""
    result = []
    used = 0
    for char in text:
        if not char.isprintable():
            char = "?"
        cells = 0 if unicodedata.combining(char) else (
            2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1)
        if used + cells > width:
            break
        result.append(char)
        used += cells
    return "".join(result)


class TerminalUI:
    def __init__(self):
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            raise ValueError("--tui requires an interactive terminal; use -i or batch mode for redirected input/output")
        if os.name != "nt" and os.environ.get("TERM") == "dumb":
            raise ValueError("--tui requires an ANSI terminal")

    @contextmanager
    def screen(self):
        """Always restore the console modes, cursor and previous screen."""
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes

            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.GetStdHandle.argtypes = [wintypes.DWORD]
            kernel.GetStdHandle.restype = wintypes.HANDLE
            kernel.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
            kernel.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            handle = kernel.GetStdHandle(-11)
            original = wintypes.DWORD()
            if not kernel.GetConsoleMode(handle, ctypes.byref(original)):
                raise OSError("Cannot read console mode; use Windows Terminal or -i")
            if not kernel.SetConsoleMode(handle, original.value | 4):
                raise OSError("Cannot enable ANSI console mode; use -i")

            def restore():
                kernel.SetConsoleMode(handle, original.value)
        else:
            import termios
            import tty

            fd = sys.stdin.fileno()
            original = termios.tcgetattr(fd)
            tty.setcbreak(fd)

            def restore():
                termios.tcsetattr(fd, termios.TCSADRAIN, original)
        try:
            sys.stdout.write("\x1b[?1049h\x1b[?25l")
            sys.stdout.flush()
            yield
        finally:
            try:
                sys.stdout.write("\x1b[0m\x1b[?25h\x1b[?1049l")
                sys.stdout.flush()
            finally:
                restore()

    def key(self, *, text=False):
        if os.name == "nt":
            import msvcrt

            value = msvcrt.getwch()
            if value in {"\x00", "\xe0"}:
                return {"H": "up", "P": "down", "I": "pageup", "Q": "pagedown",
                        "G": "home", "O": "end", "K": "left", "M": "right"}.get(msvcrt.getwch(), "")
        else:
            import select

            raw = os.read(sys.stdin.fileno(), 1)
            if not raw:
                return "cancel"
            size = (2 if 0xC2 <= raw[0] <= 0xDF else 3 if 0xE0 <= raw[0] <= 0xEF
                    else 4 if 0xF0 <= raw[0] <= 0xF4 else 1)
            for _ in range(size - 1):
                raw += os.read(sys.stdin.fileno(), 1)
            value = raw.decode("utf-8", errors="replace")
            if value == "\x1b":
                sequence = ""
                while select.select([sys.stdin], [], [], 0.05)[0]:
                    sequence += os.read(sys.stdin.fileno(), 1).decode("ascii", errors="ignore")
                    if sequence and (sequence[-1].isalpha() or sequence[-1] == "~"):
                        break
                    if len(sequence) >= 8:
                        break
                return {"[A": "up", "[B": "down", "[C": "right", "[D": "left", "[5~": "pageup", "[6~": "pagedown",
                        "[H": "home", "[F": "end", "OH": "home", "OF": "end",
                        "[1~": "home", "[4~": "end", "": "cancel"}.get(sequence, "")
        if value in {"\x03", "\x04", "\x1b"} or (not text and value in {"q", "Q"}):
            return "cancel"
        if value in {"\r", "\n"}:
            return "enter"
        if value in {"\x08", "\x7f"}:
            return "backspace"
        return value if text else value.lower()

    def draw(self, title, labels, cursor, chosen, footer, selecting=True, status=None):
        width, height = shutil.get_terminal_size((100, 28))
        width = max(1, width - 1)
        page = max(1, height - 10)
        start = cursor // page * page
        # Clear each frame; a resize is picked up on the next key press.
        lines = [clipped("REPO CLONER | " + title, width), "-" * width]
        for index in range(start, min(len(labels), start + page)):
            marker = ("[x] " if index in chosen else "[ ] ") if selecting else ""
            line = clipped(f"{'>' if index == cursor else ' '} {marker}{labels[index][getattr(self, 'offset', 0):]}", width)
            lines.append(f"\x1b[7m{line}\x1b[0m" if index == cursor else line)
        lines.extend([""] * max(0, page - min(page, len(labels) - start)))
        lines += ["-" * width, clipped(status if status is not None else (
            f"{cursor + 1}/{len(labels)}  Selected: {len(chosen)}" if selecting
            else "UPDATE? = eligibility checked during execution"), width),
            *textwrap.wrap(footer, width=width)]
        # Show a compact hint if the normal menu cannot fit.
        if height < 12 or width < 60:
            lines = [clipped("Enlarge terminal (61 x 12). Q: cancel", width)]
        sys.stdout.write("\x1b[H\x1b[2J" + "\n".join(lines))
        sys.stdout.flush()
        return page if height >= 12 and width >= 60 else 0

    @staticmethod
    def move(key, cursor, count, page):
        if key in {"up", "k"}:
            cursor -= 1
        elif key in {"down", "j"}:
            cursor += 1
        elif key == "pageup":
            cursor -= page
        elif key == "pagedown":
            cursor += page
        elif key == "home":
            cursor = 0
        elif key == "end":
            cursor = count - 1
        return max(0, min(count - 1, cursor))

    def choose(self, title, labels):
        """Choose exactly one item; Enter accepts the highlighted row."""
        cursor = 0
        self.offset = 0
        with self.screen():
            while True:
                page = self.draw(title, labels, cursor, set(),
                                 "Up/Down: move | Enter: choose | Q: cancel",
                                 selecting=False, status="Choose one option")
                key = self.key()
                if key == "cancel":
                    raise KeyboardInterrupt
                if not page:
                    continue
                if key == "enter":
                    return cursor
                cursor = self.move(key, cursor, len(labels), page)

    def edit(self, title, default="", validator=None):
        """Edit a case-preserving Unicode value inside the alternate screen."""
        value = str(default)
        cursor = len(value)
        message = "Edit the value; Ctrl+U clears it."
        with self.screen():
            while True:
                width = max(10, shutil.get_terminal_size((100, 28)).columns - 6)
                # Keep the insertion point visible even for long paths.
                start = max(0, cursor - width // 2)
                self.offset = 0
                shown = value[start:cursor] + "|" + value[cursor:]
                page = self.draw(title, [shown], 0, set(),
                                 "Type: edit | Left/Right/Home/End | Backspace | Enter: accept | Esc: cancel",
                                 selecting=False, status=message)
                key = self.key(text=True)
                if key == "cancel":
                    raise KeyboardInterrupt
                if not page:
                    continue
                if key == "enter":
                    try:
                        result = value.strip()
                        if not result:
                            raise ValueError("A value is required.")
                        if validator:
                            validator(result)
                        return result
                    except ValueError as exc:
                        message = str(exc)
                elif key == "backspace" and cursor:
                    value = value[:cursor - 1] + value[cursor:]
                    cursor -= 1
                elif key == "\x15":
                    value, cursor = "", 0
                elif key == "left":
                    cursor = max(0, cursor - 1)
                elif key == "right":
                    cursor = min(len(value), cursor + 1)
                elif key == "home":
                    cursor = 0
                elif key == "end":
                    cursor = len(value)
                elif len(key) == 1 and key.isprintable():
                    value = value[:cursor] + key + value[cursor:]
                    cursor += 1

    def configure(self, credentials, config_path, destination=None):
        """Build an in-memory job. Only authentication is read from JSON."""
        from repo_cloner import ClonerError, folder_name, _remote_identity, available_workspaces
        from urllib.parse import urlsplit

        def folder(value):
            try:
                folder_name(value)
            except ClonerError as exc:
                raise ValueError(str(exc)) from None

        def https_url(value):
            parsed = urlsplit(value)
            if (parsed.scheme != "https" or not parsed.hostname or parsed.username
                    or parsed.password or parsed.query or parsed.fragment):
                raise ValueError("Enter an HTTPS server URL without credentials, query or fragment.")

        def git_url(value):
            if _remote_identity(value) is None:
                raise ValueError("Enter an HTTPS or SSH Git URL without a password/token.")

        def destination_path(value):
            if any(ord(char) < 32 for char in value):
                raise ValueError("Path contains a control character.")
            path = Path(value).expanduser().absolute()
            for ancestor in (path, *path.parents):
                if ancestor.exists() and not ancestor.is_dir():
                    raise ValueError("Destination or its parent is a file, not a directory.")

        initial = destination.expanduser().absolute() if destination is not None else config_path.resolve().parent / "clones"
        root = self.edit("Destination directory (relative paths use current directory)", str(initial), destination_path)
        root = str(Path(root).expanduser().absolute())
        protocol = ["ssh", "https"][self.choose("Clone protocol", ["SSH", "HTTPS"])]
        sources = []
        while True:
            provider = ["bitbucket-cloud", "github", "bitbucket-server", "git"][self.choose(
                "Repository provider", ["Bitbucket Cloud", "GitHub Organization",
                                        "Bitbucket Server / Data Center", "Direct Git URLs"])]
            source = {"provider": provider}
            if provider == "bitbucket-cloud":
                workspaces = available_workspaces(credentials)
                if not workspaces:
                    raise ClonerError("No accessible Bitbucket workspaces found. Check the token account's workspace membership.")
                selected = self.choose("Bitbucket workspace", [
                    f"{name} ({slug})" if name != slug else slug for slug, name in workspaces])
                source["workspace"] = workspaces[selected][0]
            elif provider == "github":
                source["organization"] = self.edit("GitHub organization")
                source["apiUrl"] = self.edit("GitHub API URL", "https://api.github.com", https_url)
            elif provider == "bitbucket-server":
                source["baseUrl"] = self.edit("Bitbucket server HTTPS URL", validator=https_url)

            # Bitbucket folder names come from project discovery, not a user alias.
            source["name"] = (source["organization"] if provider == "github"
                              else f"source-{len(sources) + 1}")
            if provider == "git":
                # Direct URLs have no project metadata to discover.
                source["name"] = self.edit("Project name for these Git repositories", validator=folder)
                entries = []
                while True:
                    url = self.edit("Git clone URL", validator=git_url)

                    def repo_name(value):
                        folder(value)
                        if any(r["name"].casefold() == value.casefold() for r in entries):
                            raise ValueError("Repository folder name is already used.")

                    name = self.edit("Repository folder name", validator=repo_name)
                    entries.append({"name": name, "url": url})
                    if self.choose("Add another Git repository?", ["Continue", "Add repository"]) == 0:
                        break
                source["repositories"] = entries
            else:
                if "token" in credentials:
                    source["token"] = credentials["token"]
                if provider == "bitbucket-cloud" and "username" in credentials:
                    source["username"] = credentials["username"]
            sources.append(source)
            if self.choose("Sources configured", ["Discover projects and repositories", "Add another source"]) == 0:
                break
        return {"destination": root, "protocol": protocol, "sources": sources}

    def select(self, title, labels):
        if not labels:
            return []
        chosen = set()
        cursor = 0
        self.offset = 0
        with self.screen():
            while True:
                page = self.draw(title, labels, cursor, chosen,
                                 "Up/Down: move | Left/Right: pan | Space: select | A: all | N: none | Enter: next | Q: cancel")
                key = self.key()
                if key == "cancel":
                    raise KeyboardInterrupt
                if not page:
                    continue
                if key == "enter":
                    return sorted(chosen)
                if key == " ":
                    chosen.symmetric_difference_update({cursor})
                elif key == "a":
                    chosen = set(range(len(labels)))
                elif key == "n":
                    chosen.clear()
                if key == "left":
                    self.offset = max(0, self.offset - 10)
                elif key == "right":
                    self.offset = min(max(len(label) for label in labels) - 1, self.offset + 10)
                cursor = self.move(key, cursor, len(labels), page)

    def confirm(self, labels, *, dry_run=False):
        cursor = 0
        self.offset = 0
        with self.screen():
            while True:
                page = self.draw("Preview only" if dry_run else "Review execution targets",
                                 labels, cursor, set(),
                                 "Arrows/PgUp/PgDn: scroll/pan | Enter: finish | Q: cancel" if dry_run else
                                 "Arrows/PgUp/PgDn: scroll/pan | Enter/Y: execute | N/Esc/Q: cancel",
                                 selecting=False)
                key = self.key()
                if key == "cancel":
                    raise KeyboardInterrupt
                if not page:
                    continue
                if key == "enter":
                    return not dry_run
                if not dry_run and key == "n":
                    return False
                if not dry_run and key == "y":
                    return True
                if key == "left":
                    self.offset = max(0, self.offset - 10)
                elif key == "right":
                    self.offset = min(max(len(label) for label in labels) - 1, self.offset + 10)
                cursor = self.move(key, cursor, len(labels), page)
