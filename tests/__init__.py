"""Test-suite process setup, applied on the first import of the ``tests`` package.

Git 2.47+ runs ``git maintenance run --auto --detach`` after commit, merge, and
receive-pack. The detached child takes ``objects/maintenance.lock`` inside a
temporary repository while ``TemporaryDirectory`` cleanup removes it, which
fails intermittently with ``Directory not empty``. Keeping auto maintenance in
the foreground makes each git command finish its own maintenance before it
exits.

The settings live in a per-run global config file named by
``GIT_CONFIG_GLOBAL``. ``GIT_CONFIG_COUNT`` would not reach far enough: git
clears it for the receive-pack it starts when pushing to a local path, which is
how tests push to their bare origins. The file first includes the developer's
usual global config, through ``~`` paths git expands when it runs, so tests
that point ``HOME`` elsewhere still see what they saw before. No git config
file of the developer's is written.

``unittest discover -s tests`` imports test modules as top-level names, not
through this package, but it imports every module before running any test, and
suite modules import ``tests.*`` helpers, so this runs before the first git call.
"""

import atexit
import os
import tempfile
from pathlib import Path
from typing import List, MutableMapping

GIT_TEST_CONFIG = {
    "maintenance.autoDetach": "false",
    "gc.autoDetach": "false",
}
MARKER = "GSD_PATH_TEST_GIT_CONFIG"


def _quoted(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _user_global_configs(env: MutableMapping[str, str]) -> List[str]:
    """The files git reads as global config, in git's order, under this environment."""
    if env.get("GIT_CONFIG_GLOBAL"):
        return [env["GIT_CONFIG_GLOBAL"]]
    xdg = env.get("XDG_CONFIG_HOME")
    xdg_config = (Path(xdg) / "git/config").as_posix() if xdg else "~/.config/git/config"
    return [xdg_config, "~/.gitconfig"]


def git_test_config_text(env: MutableMapping[str, str]) -> str:
    lines = ["[include]"]
    lines += [f"\tpath = {_quoted(path)}" for path in _user_global_configs(env)]
    for name, value in GIT_TEST_CONFIG.items():
        section, key = name.rsplit(".", 1)
        lines += [f"[{section}]", f"\t{key} = {value}"]
    return "\n".join(lines) + "\n"


def _pin_git_config(env: MutableMapping[str, str]) -> None:
    # A child Python process that imports this package inherits the file.
    if env.get(MARKER) and env.get(MARKER) == env.get("GIT_CONFIG_GLOBAL"):
        return
    descriptor, name = tempfile.mkstemp(prefix="gsd-path-test-", suffix=".gitconfig")
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(git_test_config_text(env))
    atexit.register(lambda: Path(name).unlink(missing_ok=True))
    env["GIT_CONFIG_GLOBAL"] = env[MARKER] = name


_pin_git_config(os.environ)
