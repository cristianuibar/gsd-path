from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

from . import subprocess_platform


def _git(root: str, *args: str) -> Optional[str]:
    try:
        result = subprocess_platform.run(
            ["git", "-C", root, *args],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def git_branch_head_dirty(root) -> dict:
    root = str(root)
    branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
    head = _git(root, "rev-parse", "HEAD")
    porcelain = _git(root, "status", "--porcelain")
    return {
        "branch": branch or None,
        "head": head or None,
        "dirty": bool(porcelain) if porcelain is not None else None,
    }


def project_identity(root) -> dict:
    root = str(root)
    records = _git(root, "worktree", "list", "--porcelain", "-z") or ""
    first = records.split("\0\0", 1)[0].split("\0")
    main = next((field[len("worktree "):] for field in first if field.startswith("worktree ")), None)
    checkout = _git(root, "rev-parse", "--show-toplevel") if main else None
    if not checkout:
        return {"project_root": root, "repository": None, "worktree_root": None}
    is_bare = "bare" in first
    relative = Path(root).resolve().relative_to(Path(checkout).resolve())
    return {
        "project_root": root if is_bare else str(Path(main) / relative),
        "repository": Path(main).name,
        "worktree_root": checkout if is_bare or Path(checkout).resolve() != Path(main).resolve() else None,
    }
