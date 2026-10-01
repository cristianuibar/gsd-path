"""Project setup actions for the native app.

Each action runs one helper from the plugin source (``install.py`` or
``members.py``) and returns its output. The helper owns every rule; this
module only chooses the command and refuses a project the daemon does not watch.
"""
from __future__ import annotations

import json
import sys
from typing import List

from .plugin import OP_LOCK, _tail

# op -> installer flag. Each takes "--project <root>".
INSTALLER_OPS = {
    "hooks-init": "--hooks-init",
    "hooks-refresh": "--hooks-refresh",
    "hooks-refresh-full": "--hooks-refresh-full",
    "runtime-restore": "--runtime-restore",
    "doctor": "--doctor",
}
OPS = (*INSTALLER_OPS, "members", "member-hooks", "member-repair")



class Busy(Exception):
    status = 409


def _members_helper(plugin, *args: str):
    plugin.ensure_source()
    return plugin.runner([sys.executable, str(plugin.src_dir / "scripts" / "members.py"), *args])


def _validated(plugin, root: str) -> dict:
    rc, stdout, stderr = _members_helper(plugin, "validate", "--repo", root)
    if rc != 0:
        return {"ok": False, "members": [], "error": _tail(stderr) or _tail(stdout)}
    return {"ok": True, "members": json.loads(stdout)["members"], "error": None}


def _members(plugin, root: str) -> dict:
    result = _validated(plugin, root)
    for member in result["members"]:
        rc, stdout, _stderr = _members_helper(plugin, "detect", "--checkout", member["checkout"])
        detected = json.loads(stdout) if rc == 0 else {}
        member["marker"] = {"current": detected.get("current") is True, "reason": detected.get("reason")}
        member["hooks"] = plugin.detect_project(member["checkout"])["hooks"]
    return result


def _dispatch(plugin, root: str, op: str, body: dict) -> dict:
    preview: List[str] = ["--dry-run"] if body.get("dry_run") else []
    if op in INSTALLER_OPS:
        return plugin._run_installer(op, [INSTALLER_OPS[op], "--project", root, *preview])
    if op == "members":
        return _members(plugin, root)
    if op == "member-repair":
        if preview:
            raise ValueError("member repair has no preview; it rewrites only missing or stale markers")
        rc, stdout, stderr = _members_helper(plugin, "repair", "--repo", root)
        return {"ok": rc == 0, "stdout_tail": _tail(stdout), "error": (_tail(stderr) or _tail(stdout)) if rc else None}
    # member-hooks: only into a repository the coordinator records as its member.
    recorded = _validated(plugin, root)
    if body.get("member") not in [member["checkout"] for member in recorded["members"]]:
        raise ValueError(recorded["error"] or "member is not a recorded member of this project")
    return plugin._run_installer(op, ["--member-of", root, "--project", body["member"], *preview])


def run(handler, body: dict) -> dict:
    """POST /api/project/op ``{root, op, dry_run?, member?}``."""
    root, op = body.get("root"), body.get("op")
    if not isinstance(root, str) or root not in handler.watcher.projects:
        raise ValueError("root is not a watched project")
    if op not in OPS:
        raise ValueError(f"op must be one of: {', '.join(OPS)}")
    if not OP_LOCK.acquire(blocking=False):
        raise Busy("operation in progress")
    try:
        return _dispatch(handler.plugin, root, op, body)
    finally:
        OP_LOCK.release()
