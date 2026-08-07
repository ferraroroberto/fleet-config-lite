---
name: issue-finish
description: Finish the current issue branch — confirm acceptance, update docs, run the verification gate, push, open a merge request that closes the issue, merge when the pipeline passes, and clean up. Use "/issue-finish" on a feature branch; pairs with /issue-start.
---

# issue-finish (lite, GitLab)

**Goal:** Take the current feature branch from "code done" to "merged, branch
deleted, issue closed, back on an updated default branch".

## Preconditions

- On a `<type>/<N>-<slug>` branch (not the default branch) — else stop.
- Parse `<N>` from the branch name; `glab issue view <N>` to reload the
  acceptance checklist.

## Steps

### 1. Acceptance + docs

- Walk the issue's acceptance checkboxes against the actual diff; anything
  unmet → report and stop.
- Update `README.md` if usage, config, or output changed.

### 2. Verification gate

Run the project's declared gate (README/AGENTS.md — e.g. tests + lint +
byte-compile). Red gate → stop and report; never ship on red.

### 2b. E2e leg (delegated to `/e2e`)

Run the `/e2e` skill — the evaluation is mandatory before any MR, the
execution proportionate: it routes the branch diff to a tier
(`skip`/`static`/`full`, fail-safe `full`), runs the routed slice, and keeps
the suite right-sized. If the gate above already ran that slice, `/e2e`
carries the result. A red slice stops the finish like a red gate; the tier +
reason go in the final report even when the answer is `skip` or `n/a`.

### 3. Commit + push

Conventional message (`<type>: <subject>`, ≤72-char first line, body bullets
explaining *why*). Then:

```
git push -u origin HEAD
```

### 4. Merge request

```
glab mr create --fill --description "Closes #<N>" --assignee @me --remove-source-branch --squash-before-merge
glab mr merge --auto-merge
```

`Closes #<N>` in the MR description auto-closes the issue on merge to the
default branch. If the project has no pipeline, merge directly
(`glab mr merge --squash --remove-source-branch --yes`).

### 5. Land

Resolve the default branch rather than guessing it — `git symbolic-ref --short
refs/remotes/origin/HEAD` prints `origin/<branch>`; check out the part after
`origin/` (fallback `git checkout main || git checkout master`). **Never write
`2>nul`**: it's cmd.exe-only, and a POSIX shell (Git Bash) treats `nul` as a
filename and leaves an untracked `nul` behind that blocks the next run's
dirty-tree check.

```
git symbolic-ref --short refs/remotes/origin/HEAD
git checkout <default-branch>
git pull --ff-only
git branch -d <branch>
git fetch --prune
```

Confirm the MR merged and the issue closed (`glab issue view <N>` shows
closed). Report the MR URL and the one-line outcome.
