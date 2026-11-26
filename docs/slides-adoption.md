# Bringing the slides skill to a computer that already has decks

A computer with older decks usually holds one-off CSS in each of them. This is the way to move those decks onto the shared catalog without losing a look worth keeping, and without any client material reaching a tracked path.

In the commands, `<repo>` is the folder this repository is cloned into and `<deck-dir>` is one deck's folder. `install.ps1` creates the `.venv` they use; the scripts need only the standard library.

## Keep private material untracked

- **Decks live outside every git work tree.** Pick a folder such as a documents folder that no repository covers. A deck that must sit inside a work tree has to be ignored there, or the inventory and request scripts refuse to write beside it.
- **Brand tokens live in your own untracked file**, one per client, outside this repository. The skill asks for it; its values go into a deck's `--brand` and `--brand-dark` and nowhere else.
- **Never edit the skill's folder to suit one deck.** A change that every deck should have goes through a component request.
- The only thing that leaves your computer is a component request you have read.

## 1. Update the skill

```powershell
git -C <repo> pull --ff-only
powershell -NoProfile -ExecutionPolicy Bypass -File <repo>\install.ps1
```

The installer links the skill folders, so a later `git pull` is enough to update them; run it again when a pull adds a new skill. If you kept another copy of the slides skill elsewhere, remove it from the agent's skills folder so only this one answers.

## 2. Inventory each deck

```powershell
<repo>\.venv\Scripts\python.exe <repo>\skills\slides\scripts\lint_deck.py <deck-dir> --inventory
```

Exit 2 is expected for an old deck. The report, `lint-inventory.md`, is written beside the deck and lists the unanchored rules grouped by the classes they style.

A deck built before the shared zones existed also reports `shared zone 'tokens'` and `'base'` findings. Move such a slide onto `skills/slides/assets/template.html` first: keep its markup and per-slide CSS, take the zones from the template, and set only `--brand` and `--brand-dark`.

## 3. Decide, group by group

Each group in the report carries a verdict from the class and property overlap. The verdict is a starting point; look at the slide before you decide.

| Decision | When | What to do in the deck |
|---|---|---|
| Map to an existing component | `likely catalog match`, and the catalog look is good enough | Replace the rules with the component's anchored block from `skills/slides/assets/components.md` and rename the markup's classes to the component's |
| Turn into a variant | `near match`, and the difference is worth keeping | Use the component's block, and wrap only the difference in a local block that `extends` that component |
| Request a new component | `no match`, and you would use it again | Wrap the rules in a local block with `extends: none` |
| Drop | One-off decoration, or a look you would not repeat | Delete the rules and the markup that only served them |

A local block looks like this. Its name is the name the catalog will take, so choose a generic one: no client, product or project names.

```css
/* ==slides:local:big-states== */
/* purpose: state cards with a larger count · extends: states */
.states.big-states .count { font-size: 4cqw; }
/* ==/slides:local:big-states== */
```

Build it on the design tokens (`var(--accent)`, `var(--soft)`, …): a request with a literal colour, font, image or quoted text is refused. After each group, run the lint again; the deck is ready for the next step when it exits 1 (local blocks only) or 0 (catalog only).

## 4. File the component requests

```powershell
<repo>\.venv\Scripts\python.exe <repo>\skills\slides\scripts\component_request.py <deck-dir>
```

One `component-request-<name>.md` appears beside the deck per local block. Fill its `Use when` and `Don't use when` lines in general terms, then check it:

```powershell
<repo>\.venv\Scripts\python.exe <repo>\skills\slides\scripts\component_request.py <deck-dir> --check
```

The check refuses an unfilled line, a literal colour, and any word or figure from the deck's slides that the skill's own documentation does not use. It cannot know that an ordinary word is sensitive, so read each file before filing it. File it as an issue in the skill's repository:

```powershell
gh issue create --repo <owner>/<repo-name> --title "slides: component request <name>" --body-file <deck-dir>\component-request-<name>.md --label enhancement
```

An existing request file is never overwritten. Delete it to regenerate it after changing the block.

## 5. Re-base and lint clean

Once the requests are merged into the catalog:

```powershell
git -C <repo> pull --ff-only
<repo>\.venv\Scripts\python.exe <repo>\skills\slides\scripts\lint_deck.py <deck-dir> --session-start
<repo>\.venv\Scripts\python.exe <repo>\skills\slides\scripts\rebase_deck.py <deck-dir>
<repo>\.venv\Scripts\python.exe <repo>\skills\slides\scripts\lint_deck.py <deck-dir>
```

The last command exits 0 and the deck is final. Check it in the browser as any new deck: the catalog version may differ slightly from your local one.

`rebase_deck.py` writes nothing when it refuses, and says why:

| Refusal | Fix |
|---|---|
| `missing catalog entry` | The request is not merged yet, or was merged under another name. Wait for it, rename the local block, or drop it |
| `mismatched catalog entry` | The catalog took it as a variant of another component, or as a new component, or renamed a class. Correct the block's `extends:` line, or rename the class in the markup |
| `differs from` an older catalog block | The component's look changed. Replace the old block with the current one from `components.md` and check the slide |

Every local block must have its catalog entry before the run goes through. To re-base part of a deck while a request is still open, wait, or remove that block and add it back afterwards.

## Pulling later catalog updates

Run the same four commands as in step 5 on any deck you reopen. A component whose version moved without its CSS changing is re-stamped by `rebase_deck.py`; one whose CSS changed is reported, and you replace it by hand. A change to the shared zones of the template is stamped by copying the new zone into one slide and running `skills/slides/scripts/propagate.py <that-slide> <deck-dir>`.
