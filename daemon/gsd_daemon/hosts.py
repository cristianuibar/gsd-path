"""Which coding agents (hosts) are installed on this computer.

A host is found when its command is on PATH or in the folder its own installer
uses. The commands are the ones the host runners in ``tests/hosts`` start,
except for Zed (see ``KNOWN``).
"""
from __future__ import annotations

import shutil
from typing import Callable, List, Optional

from .plugin import HOSTS, PluginManager

# id: (name shown in the app, commands, install paths under the user's home)
KNOWN = {
    "codex": ("Codex", ("codex",), ()),
    "claude": ("Claude Code", ("claude",), ()),
    "grok": ("Grok", ("grok",), (".grok/bin/grok",)),
    "opencode": ("OpenCode", ("opencode",), ()),
    "copilot": ("Copilot CLI", ("copilot",), ()),
    "qwen": ("Qwen Code", ("qwen",), ()),
    "antigravity": ("Antigravity", ("agy",), ()),
    # The agent commands only: "cursor" and "kiro" are the IDE launchers.
    "cursor": ("Cursor", ("cursor-agent",), ()),
    # The runner starts eval-cli, which is only the test harness binary. A user has the editor's own command.
    "zed": ("Zed", ("zed",), ()),
    "kiro": ("Kiro", ("kiro-cli",), ()),
    "kimi": ("Kimi Code", ("kimi",), (".kimi-code/bin/kimi",)),
    "muse": ("Muse Code", ("muse",), ()),
}


def detect(plugin: PluginManager, which: Callable[[str], Optional[str]] = shutil.which) -> List[dict]:
    rows = []
    for host in HOSTS:
        name, commands, places = KNOWN[host]
        path = next((found for found in map(which, commands) if found), None)
        if path is None:
            path = next((str(place) for place in (plugin.user_home / item for item in places) if place.exists()), None)
        rows.append({"id": host, "name": name, "found": path is not None, "path": path,
                     "skills_root": str(plugin.global_root(host))})
    return rows
