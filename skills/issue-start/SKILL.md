---
name: issue-start
description: Start work on a GitLab issue — pick it, sync the default branch, cut a feature branch, load context, then plan or build. Use when beginning work, e.g. "/issue-start 35", "/issue-start" (pick the best next issue), or "/issue-start 35 now" to skip the plan gate.
---

# issue-start (lite, GitLab)

**Goal:** Go from "issue exists" to "correct branch, context loaded, building"
with zero manual git bookkeeping.

## Arguments

- A number → that issue (`/issue-start 35`).
- Bare → list open issues (`glab issue list --assignee @me`), pick the most
  actionable small one, confirm the pick in one line, proceed.
- `now` anywhere → skip the plan gate even for enhancements.
- `plan` anywhere → force the plan gate.

## Steps

### 1. Load the issue

`glab issue view <N>` — read title, body, labels. If it doesn't exist, stop.

### 2. Sync the default branch

```
git checkout main 2>nul || git checkout master
git pull --ff-only
```

A dirty tree stops here: report the dirty files and let the user decide.

### 3. Cut the branch

`<type>/<N>-<short-slug>` where `<type>` mirrors the issue's type label
(`bug` → `fix`, `enhancement` → `feat`, `documentation` → `docs`, else the
label itself), e.g. `fix/28-terminal-reconnect`:

```
git checkout -b <type>/<N>-<slug>
```

### 4. Mode

- `bug` / `chore` / `documentation` label (or `now`): build straight away.
- `enhancement` (or `plan`): present a short plan (files to touch, approach,
  risks) and wait for a go-ahead before editing.

### 5. Build

Work the issue to a verified state: run the project's own checks (tests,
lint, byte-compile — whatever the README declares). Report failures honestly.
When done, suggest `/issue-finish`.
