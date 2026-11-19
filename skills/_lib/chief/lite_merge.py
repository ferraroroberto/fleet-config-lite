"""`chief_ops.py merge`: the lite merge path, and a refused merge as a Board question.

A lite lane ships through a GitLab merge request. This verb asks GitLab to merge
the request from `--branch`, squashed and with the source branch removed, as
soon as its pipeline passes (`glab mr merge --auto-merge`; a project with no
pipeline merges at once). It then reads the request back, so the verdict is
GitLab's state and not the command's exit code:

  MERGE=merged   GitLab shows the request merged.
  MERGE=queued   auto-merge is set; GitLab merges it when the pipeline passes.
  MERGE=refused  GitLab refused (a failed pipeline, a conflict, a missing
                 approval, a closed request) and the `reason=` says why.
  MERGE=unknown  glab is missing, signed out, or its answer could not be read.

With `--ask`, a refusal also becomes a question on the chief's plan (`plan ask`,
id `merge-<repo>-<N>`), so it reaches Roberto's Board instead of dying in a
lane's terminal. The chief and chief-managed lanes pass `--ask`. A repeat
refusal for the same item reuses the open question.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

import chief_plan

from . import journal, launcher, rails

Glab = Callable[[List[str]], subprocess.CompletedProcess]


class Unknown(Exception):
    """glab could not answer."""


def _glab(glab: Glab, args: List[str]) -> subprocess.CompletedProcess:
    try:
        return glab(args)
    except FileNotFoundError as exc:
        raise Unknown("glab not installed") from exc
    except subprocess.TimeoutExpired as exc:
        raise Unknown("glab timed out") from exc


def mr_state(project: str, branch: str, glab: Glab) -> Dict[str, Any]:
    """The merge request from `branch` as glab shows it (`state`, `iid`, `web_url`)."""
    res = _glab(glab, ["mr", "view", branch, "--repo", project, "--output", "json"])
    if res.returncode != 0:
        raise Unknown(f"glab mr view failed: {(res.stderr or '').strip()[:200] or 'no detail'}")
    try:
        data = json.loads(res.stdout or "")
    except ValueError as exc:
        raise Unknown("unparseable glab mr view output") from exc
    if not isinstance(data, dict):
        raise Unknown("glab mr view output was not an object")
    return data


def merge(project: str, branch: str, glab: Glab) -> Tuple[str, Dict[str, Any], str]:
    """`(verdict, merge request, reason)` for one merge attempt."""
    res = _glab(glab, ["mr", "merge", branch, "--repo", project, "--auto-merge", "--squash",
                       "--remove-source-branch", "--yes"])
    refusal = next((line.strip() for line in (res.stderr or res.stdout or "").splitlines() if line.strip()), "")
    mr = mr_state(project, branch, glab)
    state = str(mr.get("state") or "")
    if state == "merged":
        return "merged", mr, ""
    if res.returncode != 0:
        return "refused", mr, refusal or f"glab mr merge exited {res.returncode}"
    if state == "opened":
        return "queued", mr, ""
    return "refused", mr, f"merge request is {state or 'in an unknown state'}"


def question_id(repo: str, number: int) -> str:
    return f"merge-{repo}-{number}"


def ask_on_refusal(plan_path: Path, repo: str, number: int, iid: Any, reason: str) -> str:
    """File (or reuse) the plan question for a refused merge; returns its id."""
    ref = f"{repo}#{number}"
    qid = question_id(repo, number)
    question = f"GitLab refused to merge {ref} (merge request !{iid or '?'}): {reason}"

    def mutate(doc: Dict[str, Any]) -> None:
        if any(item.get("id") == qid for item in doc.get("waiting_on_roberto") or []):
            return
        chief_plan.add_question(
            doc, question, ref=ref, item_id=qid,
            detail="The lane's merge request did not merge. GitLab's reason is quoted above.",
            recommendation="Fix in the lane: the refusal usually names something the lane can repair.",
            options=["Fix in the lane::send the lane the refusal to repair and push",
                     "Retry::merge again once the cause is gone",
                     "Leave it::park the item with the reason"],
            recommended=["Fix in the lane"],
        )

    chief_plan.update(plan_path, mutate)
    journal.log_transition(journal.journal_for_plan(plan_path), "asked", f"asked: {question}", ref)
    return qid


def cmd_merge(args: argparse.Namespace, glab: Glab = launcher.run_glab) -> int:
    repo, number = rails.parse_issue_ref(args.ref)
    owner, why = (None, "") if args.project else launcher.resolve_owner(repo, args.owner)
    if owner is None and not args.project:
        print(f"MERGE=unknown reason={launcher.OWNER_UNKNOWN} ({why})")
        return 1
    project = args.project or f"{owner}/{repo}"
    try:
        verdict, mr, reason = merge(project, args.branch, glab)
    except Unknown as exc:
        print(f"MERGE=unknown reason={exc}")
        return 1
    tail = f" mr=!{mr.get('iid')}" + (f" url={mr['web_url']}" if mr.get("web_url") else "")
    print(f"MERGE={verdict}{tail}" + (f" reason={reason}" if reason else ""))
    if verdict == "refused" and args.ask:
        plan_path = Path(args.plan_file) if args.plan_file else chief_plan.plan_file()
        print(f"MERGE_ASKED={ask_on_refusal(plan_path, repo, number, mr.get('iid'), reason)}")
    return 0 if verdict in ("merged", "queued") else 1


def add_parser(sub: argparse._SubParsersAction) -> None:
    m = sub.add_parser("merge", help="merge a lane's GitLab merge request when its pipeline passes")
    m.add_argument("ref", help="<repo>#<N> the merge request closes")
    m.add_argument("--branch", required=True, help="the merge request's source branch")
    m.add_argument("--ask", action="store_true", help="on a refusal, add a Board question to the chief's plan")
    m.add_argument("--owner", default=None, help="GitLab namespace (default: the launcher's gitlab_group)")
    m.add_argument("--project", default=None, help="full GitLab path; overrides <owner>/<repo>")
    m.add_argument("--plan-file", default=None)
    m.set_defaults(func=cmd_merge)
