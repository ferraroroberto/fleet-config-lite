"""Shared `git` subprocess wrapper for skills/_lib helpers.

Every helper here needs the same three lines — shell out to `git`, capture
stdout/stderr as UTF-8, never crash on an undecodable byte (`errors="replace"`,
so a non-ASCII commit message cannot raise `UnicodeDecodeError` mid-run), so
one place owns the subprocess plumbing; each call site keeps whatever return
shape (`str` vs `CompletedProcess`) and failure behavior (raise vs swallow) it
needs on top.

stdlib only (plus the sibling `no_window` constant).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Mapping, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))
from no_window import NO_WINDOW  # noqa: E402


def git_env(base: Optional[dict] = None) -> dict:
    """`base` (default `os.environ`) plus `GIT_OPTIONAL_LOCKS=0`.

    **Do not "clean up" this variable.** `git status` takes
    `.git/index.lock` purely to write back a refreshed stat
    cache — an optimisation, not part of producing the output. Kill such a
    process mid-refresh and it leaves exactly a 0-byte `index.lock` and
    nothing else touched. Done fleet-wide, that strands a 0-byte lock in
    every repo swept, all stamped the same second, and each is silently unable
    to `git add`/`commit`/`pull`/`stash` for days.

    Days, because a stale lock is invisible to a read: `git status
    --porcelain`, `git fetch`, `git rev-list`, and an up-to-date `git pull
    --ff-only` **all exit 0 and print the right answer** with the lock
    sitting there — so the raise-on-non-zero guard never fires and no sweep
    ever reports `UNKNOWN`. Detection is `index_lock.py`'s job; this is the
    half that stops them being created at all.

    Measured, and narrower than "and friends" suggested:
    of `status --porcelain=v2 --branch`, `diff --name-only HEAD`,
    `diff --name-only --cached HEAD`, `ls-files --others`,
    `rev-parse --verify` and `symbolic-ref`, **only `status` takes the
    optional lock**. A helper that never runs `status` cannot strand one —
    which lets a hunt for stranded locks rule call sites in and out instead
    of suspecting every `git` spawn equally.

    `GIT_OPTIONAL_LOCKS=0` suppresses only *optional* locks — a requested
    write still takes the real index lock, and still refuses when one is
    already held.
    """
    env = dict(os.environ if base is None else base)
    env["GIT_OPTIONAL_LOCKS"] = "0"
    return env


def run_git(
    args: Sequence[str], *, check: bool = False, timeout: Optional[float] = None,
    extra_env: Optional[Mapping[str, str]] = None,
) -> subprocess.CompletedProcess:
    """Run `git <args>`, UTF-8 decoded with undecodable bytes replaced.

    Pass `-C <repo>` as part of `args` to target a specific working tree —
    the convention every call site in this repo uses. `check=True` raises
    `subprocess.CalledProcessError` on a non-zero exit (matching
    `subprocess.run`'s own contract); the default `check=False` leaves the
    caller to inspect `.returncode`/`.stdout`/`.stderr`. `timeout` is passed
    straight through (raising `subprocess.TimeoutExpired`) for the call sites
    that bound a crawl over an unknown tree.

    `creationflags=NO_WINDOW` is what makes this the *only* place most helpers
    need to think about console suppression: a scheduled `claude -p` job has no
    console of its own, so every unsuppressed `git` spawn beneath it flashes a
    window on screen. `env=git_env()` is the same
    one-place-fix argument for optional index locks — see that function.

    `stdin=DEVNULL` because git is never fed input and a hidden, detached
    parent leaves an invalid inherited handle (`OSError: [WinError 6]`).

    `extra_env` layers variables that have no `-c` equivalent (e.g.
    `GIT_INDEX_FILE`) over the ambient environment;
    `git_env()` is applied last, so no caller can drop `GIT_OPTIONAL_LOCKS=0`.
    """
    base = {**os.environ, **extra_env} if extra_env else None
    return subprocess.run(
        ["git", *args], capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=check, timeout=timeout,
        creationflags=NO_WINDOW, env=git_env(base), stdin=subprocess.DEVNULL,
    )
