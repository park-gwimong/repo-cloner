"""Bulk clone and safely fast-forward GitHub and Bitbucket repositories."""

from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Iterator
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import uuid4


class ClonerError(Exception):
    """An actionable configuration, API or clone error."""


class _SkipUpdate(Exception):
    """An existing repository cannot be updated without risking local state."""


@dataclass(frozen=True)
class _Upstream:
    remote: str
    source_ref: str
    tracking_ref: str
    raw_url: str
    effective_url: str


@dataclass(frozen=True)
class _UpdateSnapshot:
    head_oid: str
    branch_ref: str
    upstream: _Upstream
    status: str
    hidden_index: tuple[str, ...]


_OID_RE = re.compile(r"^(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})$")
_REF_RE = re.compile(r"^refs/heads/[^/\x00]+(?:/[^/\x00]+)*$")
_TRACKING_RE = re.compile(r"^refs/remotes/[^/\x00]+(?:/[^/\x00]+)*$")


def _ascii_host(host: str, *, ipv6: bool = False) -> str | None:
    try:
        host.encode("ascii")
    except UnicodeEncodeError:
        return None
    pattern = r"[0-9A-Fa-f:.]+" if ipv6 else r"[A-Za-z0-9.-]+"
    return host.lower() if re.fullmatch(pattern, host) else None


def load_env(path: Path) -> None:
    """Load single-line dotenv assignments without replacing existing variables."""
    try:
        content = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return
    values = {}
    for number, line in enumerate(content.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)", line)
        if not match:
            raise ClonerError(f"Invalid .env assignment at {path}:{number}")
        key, value = match.groups()
        if value.startswith(("'", '"')):
            end = value.find(value[0], 1)
            tail = value[end + 1:].strip()
            if end < 0 or (tail and not tail.startswith("#")):
                raise ClonerError(f"Invalid .env quoted value at {path}:{number}")
            value = value[1:end]
        else:
            value = re.split(r"\s+#", value, maxsplit=1)[0].rstrip()
            if value.startswith("#"):
                value = ""
        if "\x00" in value:
            raise ClonerError(f"Invalid .env value at {path}:{number}")
        values[key] = value
    for key, value in values.items():
        os.environ.setdefault(key, value)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@dataclass(frozen=True)
class Repository:
    name: str
    url: str


def folder_name(value: str) -> str:
    if (not isinstance(value, str) or not value or value in {".", ".."}
            or re.search(r'[<>:"/\\|?*\x00-\x1f]', value)
            or value.endswith((".", " "))
            or re.match(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\.|$)", value, re.I)):
        raise ClonerError(f"Invalid folder name: {value!r}")
    return value


def required(source: dict, key: str) -> str:
    value = source.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ClonerError(f"Missing or invalid setting: {key}")
    return value


def _remote_identity(url: str):
    """Return a strict, comparison-only identity for a supported Git URL.

    The result intentionally retains path, user and encoding spelling.  Only
    URL scheme spelling, ASCII host case and an omitted/default port are
    normalized.  ``None`` means the value is not a URL form that this tool can
    safely identify.
    """
    if (not isinstance(url, str) or not url or "\\" in url
            or any(ord(char) < 0x20 or ord(char) == 0x7F for char in url)
            or any(char.isspace() for char in url)):
        return None

    # SCP syntax is not parsed by urllib.  Keep its user and path verbatim.
    scp = re.fullmatch(r"(git)@([^:/\s]+):(.+)", url)
    if scp and "?" not in scp.group(3) and "#" not in scp.group(3):
        user, host, path = scp.groups()
        normalized_host = _ascii_host(host)
        if normalized_host is None:
            return None
        return ("scp", user, normalized_host, path)

    try:
        parsed = urlsplit(url)
        scheme = parsed.scheme.lower()
        if scheme not in {"https", "ssh"} or not parsed.netloc:
            return None
        if parsed.netloc.endswith(":"):
            return None
        if ("?" in url or "#" in url or parsed.query or parsed.fragment
                or parsed.password is not None):
            return None
        host = parsed.hostname
        if not host:
            return None
        if not parsed.path:
            return None
        normalized_host = _ascii_host(host, ipv6=":" in host)
        if normalized_host is None:
            return None
        try:
            port = parsed.port
        except ValueError:
            return None
        default = 443 if scheme == "https" else 22
        normalized_port = default if port in (None, default) else port
        # urllib's hostname is not guaranteed to preserve a raw IPv6
        # spelling, so reject bracketed/ambiguous values rather than guessing.
        if ":" in host and not (urlsplit(url).netloc.startswith("[") or
                                re.search(r"@\[", urlsplit(url).netloc)):
            return None
        user = None
        if scheme == "ssh":
            # urlsplit exposes a decoded username on some Python versions;
            # parse the raw authority so user spelling remains strict.
            authority = parsed.netloc.rsplit("@", 1)
            if len(authority) == 2:
                user = authority[0]
                if not user or ":" in user or "@" in user:
                    return None
            elif "@" in parsed.netloc:
                return None
        elif parsed.username is not None or "@" in parsed.netloc:
            return None
        return (scheme, user, normalized_host, normalized_port, parsed.path)
    except ValueError:
        return None


def _git(
    target: Path,
    args: list[str],
    hooks_path: Path | None = None,
    *,
    read_only: bool = False,
    extra_config: tuple[str, ...] = (),
    check: bool = True,
) -> subprocess.CompletedProcess:
    """Run Git from one absolute cwd without invoking a shell."""
    target_abs = Path(os.path.abspath(os.fspath(target)))
    command = ["git"]
    if hooks_path is not None:
        hooks_abs = os.path.abspath(os.fspath(hooks_path))
        command.extend(["-c", f"core.hooksPath={hooks_abs}"])
    command.extend(extra_config)
    if read_only:
        command.append("--no-optional-locks")
    command.extend(args)
    try:
        return subprocess.run(
            command,
            cwd=str(target_abs),
            check=check,
            shell=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="surrogateescape",
        )
    except FileNotFoundError:
        raise ClonerError("Git was not found in PATH. Install Git first.") from None
    except subprocess.CalledProcessError as exc:
        raise ClonerError(f"Git command failed (exit {exc.returncode})") from None
    except OSError as exc:
        raise ClonerError(f"Git command failed ({type(exc).__name__})") from None


def _decode_git_output(value: bytes | str | None) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", "surrogateescape")
    if isinstance(value, str):
        return value
    return ""


def _git_stdout(result: subprocess.CompletedProcess) -> str:
    return _decode_git_output(result.stdout)


def _git_stderr(result: subprocess.CompletedProcess) -> str:
    return _decode_git_output(result.stderr)


def _expected_git_absence(result: subprocess.CompletedProcess, expected_exit_codes: tuple[int, ...]) -> bool:
    return result.returncode in expected_exit_codes and not _git_stderr(result)


def _git_result(
    target: Path,
    args: list[str],
    hooks_path: Path,
    *,
    expected_exit_codes: tuple[int, ...],
) -> subprocess.CompletedProcess | None:
    result = _git(target, args, hooks_path, read_only=True, check=False)
    if result.returncode == 0:
        return result
    if _expected_git_absence(result, expected_exit_codes):
        return None
    raise ClonerError(f"Git command failed (exit {result.returncode})")


def _git_optional(
    target: Path,
    args: list[str],
    hooks_path: Path,
    *,
    expected_exit_codes: tuple[int, ...] = (),
) -> str | None:
    result = _git_result(
        target,
        args,
        hooks_path,
        expected_exit_codes=expected_exit_codes,
    )
    if result is None:
        return None
    return _git_stdout(result).rstrip("\r\n")


def _git_required(target: Path, args: list[str], hooks_path: Path) -> str:
    result = _git(target, args, hooks_path, read_only=True)
    return _git_stdout(result).rstrip("\r\n")


def _single_line(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    lines = value.splitlines()
    if len(lines) != 1 or not lines[0]:
        return None
    return lines[0]


def _safe_ref(value: str, pattern: re.Pattern[str]) -> bool:
    if not pattern.fullmatch(value):
        return False
    if any(ord(char) < 0x20 or ord(char) == 0x7F or char.isspace() for char in value):
        return False
    if any(token in value for token in ("..", "@{", "*", "?", "\\", "^", "~", ":")):
        return False
    return not any(part in {"", ".", ".."} for part in value.split("/"))


def _fetch_destination(spec: str, source_ref: str) -> str | None:
    """Resolve one configured fetch refspec to the requested source."""
    if not isinstance(spec, str) or not spec or spec.startswith("^"):
        return None
    if spec.startswith("+"):
        spec = spec[1:]
    if spec.count(":") != 1:
        return None
    source, destination = spec.split(":", 1)
    if not source or not destination:
        return None
    if source == source_ref:
        return destination
    if source.endswith("/*") and destination.endswith("/*"):
        source_prefix = source[:-1]
        if source_ref.startswith(source_prefix):
            return destination[:-1] + source_ref[len(source_prefix):]
    return None


def _config_values(target: Path, key: str, hooks_path: Path) -> list[str]:
    result = _git_result(
        target,
        ["config", "--get-all", key],
        hooks_path,
        expected_exit_codes=(1,),
    )
    if result is None:
        return []
    value = _git_stdout(result).rstrip("\r\n")
    return value.splitlines() if value else []


def _normalize_path(path: Path | str) -> str:
    return os.path.normcase(os.path.normpath(os.path.abspath(os.fspath(path))))


def _present(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def _git_path(target: Path, marker: str, hooks_path: Path) -> Path:
    raw = _single_line(_git_required(target, ["rev-parse", "--git-path", marker], hooks_path))
    if raw is None:
        raise ClonerError("Git returned an invalid internal path")
    path = Path(raw)
    return path if path.is_absolute() else Path(os.path.abspath(target / path))


def _oid(target: Path, ref: str, hooks_path: Path, *, optional: bool = False) -> str | None:
    args = ["rev-parse", "--verify", f"{ref}^{{commit}}"]
    if optional:
        args.insert(2, "--quiet")
        value = _git_optional(target, args, hooks_path, expected_exit_codes=(1,))
    else:
        value = _git_required(target, args, hooks_path)
    if value is None:
        if optional:
            return None
        raise ClonerError("Git did not return a commit ID")
    if not _OID_RE.fullmatch(value):
        raise ClonerError("Git returned an invalid commit ID")
    return value.lower()


def _direct_ref_oid(target: Path, ref: str, hooks_path: Path) -> str | None:
    if _git_optional(
        target, ["symbolic-ref", "-q", ref], hooks_path, expected_exit_codes=(1,)
    ) is not None:
        raise _SkipUpdate("tracking ref became symbolic")
    value = _git_optional(
        target, ["rev-parse", "--verify", "--quiet", ref], hooks_path,
        expected_exit_codes=(1,),
    )
    if value is not None and not _OID_RE.fullmatch(value):
        raise ClonerError("Git returned an invalid tracking object ID")
    return value.lower() if value is not None else None


def _fetched_commit(target: Path, hooks_path: Path) -> str:
    try:
        records = _git_path(target, "FETCH_HEAD", hooks_path).read_text(
            encoding="utf-8", errors="surrogateescape",
        ).splitlines()
    except OSError as exc:
        raise ClonerError(f"Cannot read FETCH_HEAD ({type(exc).__name__})") from None
    if len(records) != 1 or "\t" not in records[0]:
        raise ClonerError("FETCH_HEAD must contain exactly one fetched branch")
    raw_oid = records[0].partition("\t")[0]
    if not _OID_RE.fullmatch(raw_oid):
        raise ClonerError("FETCH_HEAD contains an invalid object ID")
    commit = _oid(target, "FETCH_HEAD", hooks_path)
    if commit != raw_oid.lower():
        raise ClonerError("FETCH_HEAD is not a direct commit")
    return commit


def _publish_tracking(
    target: Path, ref: str, old_oid: str | None, fetched_oid: str, hooks_path: Path,
) -> None:
    if _direct_ref_oid(target, ref, hooks_path) != old_oid:
        raise _SkipUpdate("tracking ref changed before publication")
    result = _git(
        target,
        ["update-ref", "--no-deref", ref, fetched_oid, old_oid or "0" * len(fetched_oid)],
        hooks_path, check=False,
    )
    if result.returncode:
        if _direct_ref_oid(target, ref, hooks_path) != old_oid:
            raise _SkipUpdate("tracking ref changed during publication")
        raise ClonerError(f"Tracking ref publication failed (exit {result.returncode})")
    if _direct_ref_oid(target, ref, hooks_path) != fetched_oid:
        raise _SkipUpdate("tracking ref changed after publication")


def _hidden_index_entries(target: Path, hooks_path: Path) -> tuple[str, ...]:
    value = _git_required(target, ["ls-files", "-v", "-z"], hooks_path)
    entries = tuple(entry for entry in value.split("\x00") if entry)
    hidden = tuple(entry for entry in entries if entry[:1] in {"h", "s", "S"})
    if hidden:
        raise _SkipUpdate("assume-unchanged or skip-worktree index entries")
    return entries


def _progress_marker_paths(target: Path, hooks_path: Path) -> tuple[Path, ...]:
    markers = (
        "MERGE_HEAD",
        "rebase-apply",
        "rebase-merge",
        "CHERRY_PICK_HEAD",
        "REVERT_HEAD",
        "sequencer",
        "BISECT_START",
        "index.lock",
        "HEAD.lock",
        "config.lock",
        "packed-refs.lock",
        "shallow.lock",
    )
    paths = tuple(_git_path(target, marker, hooks_path) for marker in markers)
    present = tuple(path for path in paths if _present(path))
    if present:
        raise _SkipUpdate("Git operation or lock is in progress")
    return paths


def _read_upstream(target: Path, branch_ref: str, expected_url: str, hooks_path: Path) -> _Upstream:
    expected_identity = _remote_identity(expected_url)
    if expected_identity is None:
        raise _SkipUpdate("unsupported or malformed expected remote URL")
    branch_name = branch_ref.removeprefix("refs/heads/")
    remotes = _config_values(target, f"branch.{branch_name}.remote", hooks_path)
    merges = _config_values(target, f"branch.{branch_name}.merge", hooks_path)
    if len(remotes) != 1 or len(merges) != 1:
        raise _SkipUpdate("missing or ambiguous upstream configuration")
    remote, source_ref = remotes[0], merges[0]
    if (not remote or remote == "." or remote.startswith("-")
            or any(char.isspace() or ord(char) < 0x20 or ord(char) == 0x7F for char in remote)
            or not _safe_ref(source_ref, _REF_RE)):
        raise _SkipUpdate("upstream is not a single remote branch")
    fetch_specs = _config_values(target, f"remote.{remote}.fetch", hooks_path)
    destinations = [
        destination
        for spec in fetch_specs
        if (destination := _fetch_destination(spec, source_ref)) is not None
    ]
    if len(destinations) != 1:
        raise _SkipUpdate("upstream has no single configured fetch mapping")
    tracking_ref = destinations[0]
    if not _safe_ref(tracking_ref, _TRACKING_RE):
        raise _SkipUpdate("upstream destination is not a direct tracking ref")
    if _git_optional(
        target,
        ["symbolic-ref", "-q", tracking_ref],
        hooks_path,
        expected_exit_codes=(1,),
    ) is not None:
        raise _SkipUpdate("upstream destination is symbolic")
    configured = _single_line(
        _git_required(target, ["for-each-ref", "--format=%(upstream)", branch_ref], hooks_path)
    )
    if configured is not None and configured != tracking_ref:
        raise _SkipUpdate("upstream ref mapping is ambiguous")

    raw_urls = _config_values(target, f"remote.{remote}.url", hooks_path)
    if len(raw_urls) != 1:
        raise _SkipUpdate("remote has no single fetch URL")
    effective = _git_required(target, ["remote", "get-url", "--all", remote], hooks_path)
    effective_url = _single_line(effective)
    if effective_url is None:
        raise _SkipUpdate("remote has no single effective URL")
    raw_identity = _remote_identity(raw_urls[0])
    effective_identity = _remote_identity(effective_url)
    if raw_identity is None or effective_identity is None:
        raise _SkipUpdate("remote URL is not safely identifiable")
    if raw_identity != expected_identity or effective_identity != expected_identity:
        raise _SkipUpdate("remote URL does not exactly match the configured repository")
    return _Upstream(remote, source_ref, tracking_ref, raw_urls[0], effective_url)


def _snapshot(target: Path, expected_url: str, hooks_path: Path) -> _UpdateSnapshot:
    target_abs = Path(os.path.abspath(os.fspath(target)))
    marker = target_abs / ".git"
    if not _present(marker):
        raise _SkipUpdate("directory is not a Git worktree")
    inside = _single_line(_git_required(target_abs, ["rev-parse", "--is-inside-work-tree"], hooks_path))
    if inside != "true":
        raise _SkipUpdate("directory is not a non-bare Git worktree")
    top = _single_line(_git_required(target_abs, ["rev-parse", "--show-toplevel"], hooks_path))
    if top is None:
        raise ClonerError("Git did not return the worktree root")
    if _normalize_path(top) != _normalize_path(target_abs):
        raise _SkipUpdate("directory is inside another Git worktree")
    branch_ref = _single_line(
        _git_optional(
            target_abs,
            ["symbolic-ref", "-q", "HEAD"],
            hooks_path,
            expected_exit_codes=(1,),
        )
    )
    if branch_ref is None or not _safe_ref(branch_ref, _REF_RE):
        raise _SkipUpdate("HEAD is detached or unborn")
    head_oid = _oid(target_abs, "HEAD", hooks_path, optional=True)
    if head_oid is None:
        raise _SkipUpdate("HEAD has no commit")
    _progress_marker_paths(target_abs, hooks_path)
    status = _git_required(
        target_abs,
        ["status", "--porcelain=v1", "-z", "--untracked-files=all", "--ignore-submodules=none"],
        hooks_path,
    )
    if status:
        raise _SkipUpdate("working tree or index has local changes")
    hidden_index = _hidden_index_entries(target_abs, hooks_path)
    upstream = _read_upstream(target_abs, branch_ref, expected_url, hooks_path)
    return _UpdateSnapshot(head_oid, branch_ref, upstream, status, hidden_index)


def _assert_same(before: _UpdateSnapshot, after: _UpdateSnapshot) -> None:
    if before != after:
        raise _SkipUpdate("repository state changed during update checks")


def _ref_counts(target: Path, left: str, right: str, hooks_path: Path) -> tuple[int, int]:
    value = _single_line(
        _git_required(target, ["rev-list", "--left-right", "--count", f"{left}...{right}"], hooks_path)
    )
    if value is None:
        raise ClonerError("Git returned an invalid ancestry comparison")
    fields = value.split()
    if len(fields) != 2:
        raise ClonerError("Git returned an invalid ancestry comparison")
    try:
        counts = tuple(int(field) for field in fields)
    except ValueError:
        raise ClonerError("Git returned an invalid ancestry comparison") from None
    if any(count < 0 for count in counts):
        raise ClonerError("Git returned an invalid ancestry comparison")
    return counts  # type: ignore[return-value]


def _prepare_hooks(target: Path) -> tuple[tempfile.TemporaryDirectory, Path]:
    temporary = tempfile.TemporaryDirectory(prefix="repo cloner hooks-")
    hooks = Path(os.path.abspath(temporary.name))
    target_abs = Path(os.path.abspath(os.fspath(target)))
    try:
        if not hooks.is_dir() or any(hooks.iterdir()):
            raise OSError("temporary hooks directory is not empty")
        if _normalize_path(hooks) == _normalize_path(target_abs):
            raise OSError("temporary hooks directory is the worktree")
        try:
            if os.path.commonpath((_normalize_path(hooks), _normalize_path(target_abs))) == _normalize_path(target_abs):
                raise OSError("temporary hooks directory is inside the worktree")
        except ValueError:
            pass
    except BaseException:
        cleanup_error: BaseException | None = None
        try:
            temporary.cleanup()
        except BaseException as exc:
            cleanup_error = exc
        if cleanup_error is not None:
            print(
                f"Temporary hooks directory cleanup failed ({hooks}): {cleanup_error}",
                file=sys.stderr,
            )
        raise
    return temporary, hooks


def _update_existing(repo: Repository, target: Path) -> str:
    """Fetch the configured upstream and fast-forward one existing worktree."""
    target_abs = Path(os.path.abspath(os.fspath(target)))
    if not _present(target_abs / ".git"):
        print(f"SKIP  {target} (directory is not a Git worktree)")
        return "skipped"
    if _remote_identity(repo.url) is None:
        print(f"SKIP  {target} (configured remote URL is not safely identifiable)")
        return "skipped"
    try:
        temporary, hooks_path = _prepare_hooks(target_abs)
    except KeyboardInterrupt:
        raise
    except (OSError, ClonerError) as exc:
        raise ClonerError(f"Cannot prepare temporary hooks directory: {exc}") from None

    result: str | None = None
    message: str | None = None
    operation_error: BaseException | None = None
    cleanup_error: BaseException | None = None
    try:
        try:
            initial = _snapshot(target, repo.url, hooks_path)
            old_tracking_oid = _direct_ref_oid(target, initial.upstream.tracking_ref, hooks_path)
            _git(
                target,
                [
                    "fetch",
                    "--no-tags",
                    "--no-recurse-submodules",
                    "--no-prune",
                    "--refmap=",
                    "--",
                    initial.upstream.remote,
                    f"{initial.upstream.source_ref}:",
                ],
                hooks_path,
            )
            fetched_oid = _fetched_commit(target, hooks_path)
            after_fetch = _snapshot(target, repo.url, hooks_path)
            _assert_same(initial, after_fetch)
            if _fetched_commit(target, hooks_path) != fetched_oid:
                raise _SkipUpdate("FETCH_HEAD changed after fetch")
            _publish_tracking(
                target, initial.upstream.tracking_ref, old_tracking_oid, fetched_oid, hooks_path,
            )
            _assert_same(initial, _snapshot(target, repo.url, hooks_path))
            left, right = _ref_counts(target, initial.head_oid, fetched_oid, hooks_path)
            if left:
                result = "skipped"
                message = f"SKIP  {target} (local branch is ahead of or diverged from upstream)"
            elif right == 0:
                result = "unchanged"
                message = f"OK    {target} (already up to date)"
            else:
                before_merge = _snapshot(target, repo.url, hooks_path)
                _assert_same(initial, before_merge)
                if _direct_ref_oid(target, initial.upstream.tracking_ref, hooks_path) != fetched_oid:
                    raise _SkipUpdate("tracking ref changed before fast-forward")
                if _fetched_commit(target, hooks_path) != fetched_oid:
                    raise _SkipUpdate("FETCH_HEAD changed before fast-forward")
                _git(
                    target,
                    [
                        "merge",
                        "--ff-only",
                        "--no-autostash",
                        "--no-overwrite-ignore",
                        fetched_oid,
                    ],
                    hooks_path,
                    extra_config=("-c", "submodule.recurse=false"),
                )
                final_branch = _single_line(
                    _git_optional(
                        target,
                        ["symbolic-ref", "-q", "HEAD"],
                        hooks_path,
                        expected_exit_codes=(1,),
                    )
                )
                final_head = _oid(target, "HEAD", hooks_path)
                if final_branch != initial.branch_ref or final_head != fetched_oid:
                    raise ClonerError("Git fast-forward completed with an unexpected HEAD")
                result = "updated"
                message = f"UPDATE {target}"
        except _SkipUpdate as exc:
            result = "skipped"
            message = f"SKIP  {target} ({exc})"
        except BaseException as exc:
            operation_error = exc
    finally:
        try:
            temporary.cleanup()
            if hooks_path.exists() or hooks_path.is_symlink():
                raise OSError("temporary hooks directory still exists")
        except BaseException as exc:
            cleanup_error = exc
    if cleanup_error is not None:
        print(
            f"Temporary hooks directory cleanup failed ({hooks_path}): {cleanup_error}",
            file=sys.stderr,
        )
    if operation_error is not None:
        raise operation_error
    if cleanup_error is not None:
        if isinstance(cleanup_error, KeyboardInterrupt):
            raise cleanup_error
        raise ClonerError(f"Temporary hooks directory cleanup failed: {hooks_path}") from None
    if result is None:
        raise ClonerError("Existing repository update produced no result")
    if message is not None:
        print(message)
    return result


class Api:
    def __init__(self, base: str, source: dict):
        self.base = base.rstrip("/")
        self.headers = {"Accept": "application/json", "User-Agent": "project-repo-cloner"}
        self.opener = build_opener(NoRedirect())
        if source.get("tokenEnv"):
            token = os.environ.get(source["tokenEnv"])
            if not token:
                raise ClonerError(f"Empty environment variable: {source['tokenEnv']}")
            if source.get("usernameEnv"):
                username = os.environ.get(source["usernameEnv"])
                if not username:
                    raise ClonerError(f"Empty environment variable: {source['usernameEnv']}")
                encoded = base64.b64encode(f"{username}:{token}".encode()).decode()
                self.headers["Authorization"] = f"Basic {encoded}"
            else:
                self.headers["Authorization"] = f"Bearer {token}"

    def get(self, url: str):
        parsed, origin = urlsplit(url), urlsplit(self.base)
        if (parsed.scheme != "https" or parsed.netloc != origin.netloc
                or parsed.username or parsed.password):
            raise ClonerError("API URL must use HTTPS and the configured API host")
        try:
            with self.opener.open(Request(url, headers=self.headers), timeout=60) as response:
                return json.load(response)
        except HTTPError as exc:
            raise ClonerError(
                f"API HTTP {exc.code}: check credentials, permissions, URL and rate limit"
            ) from None
        except (URLError, TimeoutError, ValueError):
            raise ClonerError("API request failed: check connectivity and JSON response") from None


def clone_link(item: dict, protocol: str, server: bool = False) -> Repository:
    name = "http" if server and protocol == "https" else protocol
    for link in item["links"]["clone"]:
        if link["name"] == name:
            return Repository(item["slug"], link["href"])
    raise ClonerError(f"Missing {protocol} clone URL for {item['slug']}")


def repositories(source: dict, protocol: str) -> Iterator[Repository]:
    provider = required(source, "provider")
    if provider == "github":
        api = Api(source.get("apiUrl", "https://api.github.com"), source)
        org = quote(required(source, "organization"), safe="")
        page = 1
        while True:
            items = api.get(f"{api.base}/orgs/{org}/repos?type=all&per_page=100&page={page}")
            for item in items:
                yield Repository(item["name"], item["ssh_url" if protocol == "ssh" else "clone_url"])
            if len(items) < 100:
                break
            page += 1
    elif provider == "bitbucket-cloud":
        api = Api("https://api.bitbucket.org/2.0", source)
        workspace = quote(required(source, "workspace"), safe="")
        query = urlencode({"pagelen": 100, "q": "project.key=" + json.dumps(required(source, "project"))})
        url = f"{api.base}/repositories/{workspace}?{query}"
        visited = set()
        while url:
            if url in visited:
                raise ClonerError("API returned a repeated pagination URL")
            visited.add(url)
            data = api.get(url)
            for item in data["values"]:
                yield clone_link(item, protocol)
            url = data.get("next")
    elif provider == "bitbucket-server":
        api = Api(required(source, "baseUrl"), source)
        project = quote(required(source, "project"), safe="")
        start = 0
        while True:
            data = api.get(f"{api.base}/rest/api/1.0/projects/{project}/repos?limit=100&start={start}")
            for item in data["values"]:
                yield clone_link(item, protocol, server=True)
            if data["isLastPage"]:
                break
            next_start = data["nextPageStart"]
            if not isinstance(next_start, int) or next_start <= start:
                raise ClonerError("Invalid API pagination offset")
            start = next_start
    else:
        raise ClonerError(f"Unsupported provider: {provider}")


def _is_reparse_point(path: Path) -> bool:
    if not sys.platform.startswith("win"):
        return False
    try:
        import stat

        attributes = path.lstat().st_file_attributes
    except (AttributeError, OSError, TypeError):
        return False
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def clone(repo: Repository, parent: Path, dry_run: bool) -> str:
    target = parent / folder_name(repo.name)
    if target.exists() or target.is_symlink() or _is_reparse_point(target):
        if not target.is_dir() or target.is_symlink() or _is_reparse_point(target):
            print(f"SKIP  {target} (existing path is not a regular directory)")
            return "skipped"
        if dry_run:
            print(f"PLAN  {target}")
            return "planned"
        return _update_existing(repo, target)
    # Never allow local paths or executable Git remote helpers from API responses.
    if _remote_identity(repo.url) is None:
        raise ClonerError("Unsupported clone URL")
    if dry_run:
        print(f"PLAN  {target}")
        return "planned"
    parent.mkdir(parents=True, exist_ok=True)
    temporary = parent / f".clone-{uuid4().hex}"
    print(f"CLONE {target}", flush=True)
    try:
        subprocess.run(["git", "clone", "--", repo.url, str(temporary)], check=True)
        # Reserve the destination atomically; do not overwrite a concurrent clone.
        target.mkdir()
        try:
            # Git creates the worktree in temporary; move its contents into the reserved directory.
            for child in temporary.iterdir():
                child.rename(target / child.name)
            temporary.rmdir()
        except BaseException:
            print(f"Incomplete destination requires inspection: {target}", file=sys.stderr)
            raise
    except (OSError, subprocess.CalledProcessError) as exc:
        if temporary.exists():
            print(f"Partial clone retained: {temporary}", file=sys.stderr)
        raise ClonerError(f"Clone failed ({type(exc).__name__})") from None
    return "cloned"


def run(config_path: Path, dry_run: bool = False) -> int:
    config = json.loads(config_path.read_text(encoding="utf-8-sig"))
    load_env(config_path.resolve().parent / ".env")
    protocol = config.get("protocol", "ssh")
    if protocol not in {"ssh", "https"}:
        raise ClonerError("protocol must be ssh or https")
    sources = config.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ClonerError("sources must be a nonempty list")
    names = set()
    for source in sources:
        name = folder_name(required(source, "name"))
        if name.casefold() in names:
            raise ClonerError(f"Duplicate source name: {name}")
        names.add(name.casefold())
    root = Path(config.get("destination", "./clones")).expanduser()
    if not root.is_absolute():
        root = config_path.resolve().parent / root
    if not dry_run and not shutil.which("git"):
        raise ClonerError("Git was not found in PATH. Install Git first.")
    counts = dict.fromkeys(("cloned", "updated", "unchanged", "skipped", "planned", "failed"), 0)
    for source in sources:
        print(f"[{source['name']}] Fetching repositories...", flush=True)
        try:
            repos = list(repositories(source, protocol))
        except (ClonerError, KeyError, TypeError, ValueError) as exc:
            print(f"[{source['name']}] Listing failed: {exc}", file=sys.stderr)
            counts["failed"] += 1
            continue
        print(f"[{source['name']}] Found {len(repos)} repositories")
        for repo in repos:
            try:
                counts[clone(repo, root / source["name"], dry_run)] += 1
            except (ClonerError, OSError) as exc:
                print(f"[{source['name']}/{repo.name}] {exc}", file=sys.stderr)
                counts["failed"] += 1
    print("Done: " + " ".join(f"{key}={value}" for key, value in counts.items()))
    return 1 if counts["failed"] else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("repositories.json"))
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List clone/update candidates without Git or temporary directories",
    )
    args = parser.parse_args()
    try:
        return run(args.config, args.dry_run)
    except (ClonerError, OSError, ValueError, TypeError, KeyError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted. No successful result is reported; inspect any partial clone.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
