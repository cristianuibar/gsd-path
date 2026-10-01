"""Which coding agents (hosts) are installed on this computer.

A host is found when its command is on PATH or in the folder its own installer
uses. The commands are the ones the host runners in ``tests/hosts`` start.
"""
from __future__ import annotations

import shutil
from pathlib import Path
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
    "cursor": ("Cursor", ("cursor-agent", "cursor"), ()),
    "zed": ("Zed", ("zed",), ()),
    "kiro": ("Kiro", ("kiro-cli", "kiro"), ()),
    "kimi": ("Kimi Code", ("kimi",), (".kimi-code/bin/kimi",)),
    "muse": ("Muse Code", ("muse",), ()),
}


def detect(plugin: PluginManager, which: Callable[[str], Optional[str]] = shutil.which) -> List[dict]:
    rows = []
    for host in HOSTS:
        # A host added to the plugin before this table: its id is its name and its command.
        name, commands, places = KNOWN.get(host, (host.capitalize(), (host,), ()))
        path = next((found for found in map(which, commands) if found), None)
        if path is None:
            path = next((str(place) for place in (plugin.user_home / item for item in places) if place.exists()), None)
        rows.append({"id": host, "name": name, "found": path is not None, "path": path,
                     "skills_root": str(plugin.global_root(host))})
    return rows
