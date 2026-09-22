"""Live TUI for Git work, with noninteractive authentication and child cleanup."""

from collections import deque
from contextlib import redirect_stderr, redirect_stdout
import codecs
import os
import queue
import re
import shlex
import shutil
import signal
import subprocess
import sys
import threading
import time

from repo_cloner_tui import clipped


class Progress:
    def __init__(self, ui, total, counts):
        self.ui = ui
        self.output = sys.stdout
        self.total = total
        self.counts = counts
        self.completed = 0
        self.label = ""
        self.logs = deque(maxlen=100)
        self.results = []
        self.failures = []
        self.started = time.monotonic()
        self.current_started = self.started
        self.last_output = self.started
        self.auth_required = False
        self.finished = False
        self.ssh_commands = {}

    def write(self, text):
        for line in text.replace("\r", "\n").splitlines():
            if line.strip():
                self.logs.append(line)
                self.last_output = time.monotonic()
                lower = line.lower()
                if any(marker in lower for marker in (
                    "host key verification failed", "remote host identification has changed",
                    "permission denied (publickey", "could not read username", "terminal prompts disabled",
                    "authentication failed", "cannot prompt", "could not read password",
                )):
                    self.auth_required = True
        return len(text)

    def flush(self):
        pass

    def poll_cancel(self):
        if os.name == "nt":
            import msvcrt
            ready = msvcrt.kbhit()
        else:
            import select
            ready = bool(select.select([sys.stdin], [], [], 0)[0])
        if ready and self.ui.key() == "cancel":
            raise KeyboardInterrupt

    def render(self):
        width, height = shutil.get_terminal_size((100, 28))
        width = max(1, width - 1)
        now = time.monotonic()
        percent = self.completed * 100 // self.total
        bars = max(1, min(30, width - 20))
        filled = bars * self.completed // self.total
        state = "COMPLETE" if self.finished else "RUNNING"
        if self.auth_required:
            state = "AUTH / SSH SETUP REQUIRED"
        lines = ["REPO CLONER | Execution", f"[{('=' * filled).ljust(bars, '.')}] {self.completed}/{self.total} ({percent}%)",
                 f"{state} | Total {now - self.started:.0f}s | Current {now - self.current_started:.0f}s",
                 f"Repository: {self.label}",
                 " ".join(f"{key}={value}" for key, value in self.counts.items())]
        if self.auth_required:
            lines += ["Git authentication/SSH verification failed. No prompt is waiting here.",
                      "Verify the host fingerprint and set up Git/SSH authentication, then retry."]
        elif not self.finished and now - self.last_output >= 10:
            lines += [f"No Git output for {now - self.last_output:.0f}s; process is still active.",
                      "Network/server or credential helper may be slow. Q: stop."]
        else:
            lines += ["Git prompts disabled during TUI execution.", ""]
        lines += self.results[-3:]
        lines += ["-" * width, "Recent Git output:"]
        remaining = max(1, height - len(lines) - 3)
        lines += list(self.logs)[-remaining:]
        lines += ["-" * width, "Enter: close results" if self.finished else "Q / Esc / Ctrl+C: stop (completed work is kept)"]
        if height < 12 or width < 60:
            lines = [f"{state} {self.completed}/{self.total}", "Enlarge terminal to 61 x 12.",
                     "Enter: close" if self.finished else "Q / Esc / Ctrl+C: stop"]
        self.output.write("\x1b[H\x1b[2J" + "\n".join(clipped(line, width) for line in lines[:max(1, height - 1)]))
        self.output.flush()

    def environment(self, cwd):
        env = os.environ.copy()
        env.update(GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never")
        # Preserve the configured SSH executable/options, adding noninteractive policy.
        key = str(cwd or os.getcwd())
        if key not in self.ssh_commands:
            command = env.get("GIT_SSH_COMMAND")
            if not command:
                result = subprocess.run(["git", "config", "--get", "core.sshCommand"], cwd=cwd,
                                        capture_output=True, text=True, stdin=subprocess.DEVNULL)
                command = result.stdout.strip() if result.returncode == 0 else ""
            if not command:
                command = shlex.quote(env["GIT_SSH"]) if env.get("GIT_SSH") else "ssh"
            if env.get("GIT_SSH_VARIANT") in {"plink", "putty", "tortoiseplink"} or "plink" in command.lower():
                command += " -batch"
            else:
                # First value wins in OpenSSH, so prepend to existing -o options.
                # Keep the executable and append policy before its remaining arguments.
                parts = re.match(r'''^(\s*(?:"[^"]+"|'[^']+'|\S+))(.*)$''', command, re.DOTALL)
                if not parts:
                    raise OSError("Empty SSH command")
                command = parts[1] + " -o BatchMode=yes -o StrictHostKeyChecking=yes" + parts[2]
            self.ssh_commands[key] = command
        env["GIT_SSH_COMMAND"] = self.ssh_commands[key]
        return env

    @staticmethod
    def stop(process):
        if process.poll() is not None:
            return
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            if os.name != "nt":
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            else:
                process.kill()
            process.wait()

    def run(self, command, **kwargs):
        """subprocess.run adapter: retain machine-readable output for core Git checks."""
        captured = kwargs.get("capture_output", False)
        cwd = kwargs.get("cwd")
        events = queue.Queue(maxsize=256)
        cancelled = threading.Event()
        stdout = []
        stderr = []
        options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
        process = subprocess.Popen(command, cwd=cwd, env=self.environment(cwd), stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, **options)

        def read(stream, name):
            decoder = codecs.getincrementaldecoder("utf-8")("replace")
            pending = ""

            def emit(text):
                while not cancelled.is_set():
                    try:
                        events.put(text, timeout=0.1)
                        return
                    except queue.Full:
                        continue
            try:
                while not cancelled.is_set():
                    chunk = os.read(stream.fileno(), 4096)
                    if not chunk:
                        break
                    if captured:
                        (stdout if name == "stdout" else stderr).append(chunk)
                    text = decoder.decode(chunk)
                    if name == "stderr" or not captured:
                        pending += text.replace("\r", "\n")
                        lines = pending.split("\n")
                        pending = lines.pop()
                        for line in lines:
                            emit(line)
                        if len(pending) > 65536:
                            emit(pending)
                            pending = ""
                if pending and (name == "stderr" or not captured):
                    emit(pending)
            finally:
                stream.close()

        readers = [threading.Thread(target=read, args=(process.stdout, "stdout"), daemon=True),
                   threading.Thread(target=read, args=(process.stderr, "stderr"), daemon=True)]
        for reader in readers:
            reader.start()
        try:
            while process.poll() is None or any(reader.is_alive() for reader in readers) or not events.empty():
                self.poll_cancel()
                try:
                    self.write(events.get(timeout=0.1))
                except queue.Empty:
                    pass
                self.render()
            returncode = process.wait()
        except BaseException:
            cancelled.set()
            self.stop(process)
            raise
        finally:
            for reader in readers:
                reader.join(timeout=3)
        out, err = b"".join(stdout), b"".join(stderr)
        if kwargs.get("text"):
            encoding, errors = kwargs.get("encoding", "utf-8"), kwargs.get("errors", "strict")
            out, err = out.decode(encoding, errors), err.decode(encoding, errors)
        result = subprocess.CompletedProcess(command, returncode, out if captured else None, err if captured else None)
        if kwargs.get("check") and returncode:
            raise subprocess.CalledProcessError(returncode, command, output=result.stdout, stderr=result.stderr)
        return result


def execute(ui, tasks, counts, clone, error_type, runner_context):
    progress = Progress(ui, len(tasks), counts)
    try:
        with ui.screen():
            token = runner_context.set(progress.run)
            try:
                with redirect_stdout(progress), redirect_stderr(progress):
                    for repo, parent, label in tasks:
                        progress.poll_cancel()
                        progress.label = f"{label}/{repo.name}"
                        progress.current_started = progress.last_output = time.monotonic()
                        progress.auth_required = False
                        progress.logs.clear()
                        progress.render()
                        try:
                            outcome = clone(repo, parent, False)
                        except (error_type, OSError) as exc:
                            outcome = "failed"
                            progress.write(str(exc))
                        counts[outcome] += 1
                        progress.completed += 1
                        summary = f"{outcome.upper()} {progress.label}"
                        if progress.auth_required:
                            summary += " (Git authentication / SSH host verification needs setup)"
                        progress.results.append(summary)
                        if outcome == "failed":
                            progress.failures.append((progress.label, list(progress.logs)))
                        progress.write(summary)
                        progress.render()
            finally:
                runner_context.reset(token)
            progress.finished = True
            progress.render()
            while ui.key() not in {"enter", "cancel"}:
                pass
    finally:
        for result in progress.results:
            print(result)
        # Preserve the latest diagnostics, including any retained clone path.
        for label, logs in progress.failures:
            print(f"Git diagnostics: {label}")
            for line in logs:
                print(clipped(line, 500))
        if not progress.finished:
            for line in progress.logs:
                print(clipped(line, 500))
        print(("Done: " if progress.finished else "Interrupted: ")
              + " ".join(f"{key}={value}" for key, value in counts.items()))
    return 1 if counts["failed"] else 0
