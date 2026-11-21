"""The guarded writers, under the flat import name the skill scripts use.

The skills write into a folder the operator passes on the command line (a deck dir,
an --out-dir, the repo an e2e bootstrap targets). `fleet_core.runtime_files` owns the
guard that refuses such a path at runtime when it resolves under a code folder; this
module only re-exports it so a script that puts `skills/_lib` on `sys.path` can write
`from runtime_files import ...` and still get the one definition of the guarded-folder
set and of every writer's signature (`make_dirs` takes `Path.mkdir`'s arguments, and
`save_text` defaults to the locale encoding, so callers pass `encoding="utf-8"`).

Stdlib-only, so any skill can use it.
"""

from __future__ import annotations

from fleet_core.runtime_files import (
    CODE_FOLDERS,
    REPO_ROOT,
    PathLike,
    checked,
    copy_file,
    copy_tree,
    copy_with_metadata,
    file_handler,
    make_dirs,
    move,
    open_for_write,
    save_bytes,
    save_text,
    touch_file,
)

__all__ = [
    "CODE_FOLDERS",
    "REPO_ROOT",
    "PathLike",
    "checked",
    "copy_file",
    "copy_tree",
    "copy_with_metadata",
    "file_handler",
    "make_dirs",
    "move",
    "open_for_write",
    "save_bytes",
    "save_text",
    "touch_file",
]
