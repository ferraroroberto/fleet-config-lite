"""The one place lite runs `glab`: spawn, error ladder, JSON read, merge-request listing.

Every forge read in the lite chief and the owner check goes through here, so a glab that
is missing, slow, signed out or answering with something that is not JSON reads the same
everywhere: one `GlabError` naming which of those it was, never an empty answer. Callers
keep their own verdict on top (`UNKNOWN`, an `error` row, `None`); tests inject the runner.

Stdlib-only; it imports `no_window` as the other `skills/_lib` modules do.
"""

from __future__ import annotations

import json
import subprocess
from typing import Any, Callable, Dict, List, Optional, Sequence

from no_window import NO_WINDOW

Glab = Callable[[List[str]], "subprocess.CompletedProcess[str]"]

# glab spawns its own API calls; one issue view is well under this on a working network.
GLAB_TIMEOUT = 30.0

_BANNERS = frozenset({"ERROR", "WARNING", "WARN", "INFO"})
_DETAIL_CHARS = 200


class GlabError(RuntimeError):
    """A glab call that did not establish its answer (missing, timed out, failed, unreadable)."""


def run_glab(args: Sequence[str], timeout: float = GLAB_TIMEOUT) -> "subprocess.CompletedProcess[str]":
    """`glab <args>`, UTF-8 decoded, no console window, stdin closed.

    Raises `FileNotFoundError` when glab is not installed and `subprocess.TimeoutExpired`
    past `timeout`; `glab_output` turns both into `GlabError`.
    """
    return subprocess.run(  # noqa: S603 -- fixed executable, argv built by the callers
        ["glab", *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout, creationflags=NO_WINDOW, stdin=subprocess.DEVNULL,
    )


def first_message(text: str) -> str:
    """The first useful line of glab's output.

    glab boxes a failure under a banner line that is only the level word (`ERROR`), so the
    first non-empty line carries no information.
    """
    for line in (text or "").splitlines():
        line = line.strip()
        if line and line.upper() not in _BANNERS:
            return line
    return ""


def _verb(args: Sequence[str]) -> str:
    return " ".join(args[:2])


def glab_output(args: Sequence[str], glab: Optional[Glab] = None) -> "subprocess.CompletedProcess[str]":
    """The finished process for `glab <args>`; a missing glab or a timeout is a `GlabError`.

    The exit status is the caller's: `glab mr merge` can be refused and still carry an answer.
    """
    run = glab or run_glab
    try:
        return run(list(args))
    except FileNotFoundError as exc:
        raise GlabError("glab not installed") from exc
    except subprocess.TimeoutExpired as exc:
        waited = f" after {exc.timeout:g}s" if exc.timeout else ""
        raise GlabError(f"glab timed out{waited}") from exc


def glab_text(args: Sequence[str], glab: Optional[Glab] = None) -> str:
    """Stdout of a successful `glab <args>`; a non-zero exit is a `GlabError` carrying glab's own message."""
    res = glab_output(args, glab)
    if res.returncode != 0:
        detail = first_message(res.stderr or res.stdout)[:_DETAIL_CHARS] or "no detail"
        raise GlabError(f"glab {_verb(args)} failed: {detail}")
    return res.stdout or ""


def glab_json(args: Sequence[str], glab: Optional[Glab] = None, expect: Optional[type] = None) -> Any:
    """`glab <args>` stdout parsed as JSON; `expect` (`list` or `dict`) names the shape a caller needs.

    Blank output is unparseable, not an empty list: a glab that said nothing has not said "none".
    """
    out = glab_text(args, glab)
    try:
        data = json.loads(out)
    except ValueError as exc:
        raise GlabError(f"unparseable glab {_verb(args)} output") from exc
    if expect is not None and not isinstance(data, expect):
        shape = "a list" if expect is list else "an object"
        raise GlabError(f"glab {_verb(args)} output was not {shape}")
    return data


def merge_requests(project: str, branch: str, glab: Optional[Glab] = None) -> List[Dict[str, Any]]:
    """Every merge request from `branch` in any state (`glab mr list` rows)."""
    rows = glab_json(["mr", "list", "--repo", project, "--source-branch", branch, "--all", "--output", "json"],
                     glab, expect=list)
    return [row for row in rows if isinstance(row, dict)]
