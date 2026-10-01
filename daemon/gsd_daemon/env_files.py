"""Read and change a project's ``.env`` files for the native app.

The app lists names only. A value leaves this module in one place, ``reveal``,
for one name. A save changes only the named lines and keeps every other byte.
No message or log made here holds a value.
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import subprocess_platform

FILES = (".env", ".env.local", ".env.development", ".env.production")
NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
LINE = re.compile(r"(?P<prefix>\s*(?:export\s+)?)(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?P<value>.*)\Z", re.S)
# A value made of these characters needs no quotes in any dotenv reader.
PLAIN = re.compile(r"[A-Za-z0-9_./:@%+,-]*\Z")
ESCAPES = {"n": "\n", "r": "\r", "t": "\t", '"': '"', "\\": "\\", "$": "$"}


def _path(root, name: str) -> Path:
    if name not in FILES:
        raise ValueError(f"the file must be one of: {', '.join(FILES)}")
    path = Path(root) / name
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError(f"{name} is a link or not a regular file; it is not opened")
    return path


def _lines(path: Path) -> List[str]:
    try:
        return path.read_bytes().decode("utf-8").splitlines(keepends=True)
    except FileNotFoundError:
        return []
    except UnicodeDecodeError:
        raise ValueError(f"{path.name} is not UTF-8 text") from None


def _decode(raw: str) -> str:
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == raw[-1] == "'":
        return raw[1:-1]
    if len(raw) >= 2 and raw[0] == raw[-1] == '"':
        return re.sub(r"\\(.)", lambda found: ESCAPES.get(found.group(1), found.group(0)), raw[1:-1], flags=re.S)
    return re.split(r"\s+#", raw, maxsplit=1)[0]  # an unquoted value ends at " #"


def _encode(value: str) -> str:
    if PLAIN.match(value):
        return value
    if "'" not in value and "\n" not in value and "\r" not in value:
        return f"'{value}'"  # single quotes: every reader takes the text as it is
    escaped = value
    for char, code in (("\\", "\\\\"), ('"', '\\"'), ("$", "\\$"), ("\n", "\\n"), ("\r", "\\r"), ("\t", "\\t")):
        escaped = escaped.replace(char, code)
    return f'"{escaped}"'


def _parse(lines: List[str]) -> List[Tuple[int, str, str, str]]:
    """(line index, prefix, name, raw value) for each variable line."""
    found = []
    for index, line in enumerate(lines):
        match = LINE.match(line.rstrip("\r\n"))
        if match and not line.lstrip().startswith("#"):
            found.append((index, match.group("prefix"), match.group("name"), match.group("value")))
    return found


def _git_state(root, name: str) -> str:
    def git(*args) -> Optional[int]:
        try:
            return subprocess_platform.run(["git", "-C", str(root), *args], check=False,
                                           capture_output=True, text=True).returncode
        except (OSError, subprocess.SubprocessError):
            return None
    if git("ls-files", "--error-unmatch", "--", name) == 0:
        return "tracked"
    return "ignored" if git("check-ignore", "-q", "--", name) == 0 else "untracked"


def list_file(root, name: str) -> dict:
    path = _path(root, name)
    values: Dict[str, str] = {}
    for _index, _prefix, variable, raw in _parse(_lines(path)):
        values[variable] = raw  # a repeated name: the last line wins, as in a shell
    return {"file": name, "exists": path.exists(), "git": _git_state(root, name),
            "vars": [{"name": variable, "empty": _decode(raw) == ""} for variable, raw in values.items()]}


def reveal(root, name: str, variable: str) -> str:
    for _index, _prefix, found, raw in reversed(_parse(_lines(_path(root, name)))):
        if found == variable:
            return _decode(raw)
    raise ValueError(f"{name} has no variable with that name")


def save(root, name: str, changes, dry_run: bool = False) -> dict:
    """Apply ``[{"name", "value"} | {"name", "remove": true}]``. Returns the diff by name."""
    path = _path(root, name)
    if not isinstance(changes, list) or not all(isinstance(change, dict) for change in changes):
        raise ValueError("changes must be a list")
    names = [change.get("name") for change in changes]
    if not all(isinstance(variable, str) and NAME.match(variable) for variable in names):
        raise ValueError("a variable name has letters, digits, and _ only, and does not start with a digit")
    if len(set(names)) != len(names):
        raise ValueError("a variable is named more than once")

    lines = _lines(path)
    ending = "\r\n" if any(line.endswith("\r\n") for line in lines) else "\n"
    parsed = _parse(lines)
    diff = []
    for change in changes:
        variable = change["name"]
        at = [(index, prefix, raw) for index, prefix, found, raw in parsed if found == variable]
        if change.get("remove") is True:
            if not at:
                raise ValueError(f"{name} has no variable {variable} to remove")
            for index, _prefix, _raw in at:
                lines[index] = ""
            diff.append({"name": variable, "change": "remove"})
            continue
        value = change.get("value")
        if not isinstance(value, str):
            raise ValueError(f"{variable} needs a text value, or remove: true")
        if at:
            index, prefix, raw = at[-1]
            if _decode(raw) == value:
                continue
            lines[index] = f"{prefix}{variable}={_encode(value)}{ending}"
            diff.append({"name": variable, "change": "change"})
        else:
            if lines and not lines[-1].endswith(("\n", "\r")):
                lines[-1] += ending
            lines.append(f"{variable}={_encode(value)}{ending}")
            diff.append({"name": variable, "change": "add"})
    if dry_run or not diff:
        return {"written": False, "diff": diff}

    mode = (path.stat().st_mode & 0o777) if path.exists() else 0o600
    handle, temporary = tempfile.mkstemp(prefix=name + ".", dir=str(path.parent))
    try:
        with os.fdopen(handle, "wb") as out:
            out.write("".join(lines).encode("utf-8"))
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    return {"written": True, "diff": diff}
