#!/usr/bin/env python3
# gsd-path project runtime
"""Helpers shared by the gsd-path scripts.

Every consuming script binds the names it used before (for example
``run_git = _common.run_git``) so callers and tests that patch the name on the
consuming module keep working.
"""

from __future__ import annotations

import sys

# Runtime helpers must not modify their immutable installation.
sys.dont_write_bytecode = True

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Optional

PIPELINE_MARKER = "gsd-path/v2"
BOUND_BRANCH_RE = re.compile(r"^gsd-path/M(\d{3,})$")

FIELD_PATTERN = re.compile(r"^(?P<key>[a-z_]+):\s*(?P<value>.*)$")
INLINE_LIST_PATTERN = re.compile(r"^\[(?P<body>.*)\]$")
LIST_ITEM_PATTERN = re.compile(r"^\s*-\s+(?P<value>.*)$")
VERIFY_LEDGER_PATH = ".project/build/verify-ledger.jsonl"
VERIFY_RESULTS = ("pass", "fail")
VERIFY_LEDGER_SCHEMA = "gsd-path/verify-ledger/v2"
VERIFY_BLOCK_PATTERN = re.compile(r"```bash[ \t]*\n(?P<block>.*?)```", re.DOTALL)


# Sample paths the pipeline must commit. A product rule such as an unanchored
# `build/` would otherwise drop them silently from every commit.
PROJECT_PROBE_PATHS = (
    ".project/STATE.md",
    ".project/LESSONS.md",
    ".project/REPOSITORY.md",
    ".project/MEMBERS.md",
    ".project/CHARTER.md",
    ".project/ROADMAP.md",
    ".project/SYNTHESIS.md",
    VERIFY_LEDGER_PATH,
    ".project/build/members.json",
    ".project/build/evidence.json",
    ".project/archive/001-probe/build/evidence.json",
    ".project/archive/001-probe/build/verify-ledger.jsonl",
    ".project/intent/probe.md",
    ".project/research/probe.md",
    ".project/plan/probe.md",
    ".project/plan/PLAN.md",
    ".project/tasks/probe.md",
    ".project/review/probe.md",
    ".project/discuss/probe.md",
    ".project/next/probe.md",
)


def project_ignore_error(repo: Path) -> Optional[str]:
    """Why ignore rules would drop pipeline state from commits, or None."""
    result = subprocess.run(
        ("git", "-C", str(repo), "check-ignore", "-v", "-n", "-z", "--no-index", "--stdin"),
        input="\0".join(PROJECT_PROBE_PATHS) + "\0",
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode not in (0, 1):
        return f"could not check ignore rules: {result.stderr.strip()}"
    fields = result.stdout.split("\0")
    hits = []
    for index in range(0, len(fields) - 3, 4):
        source, line, pattern, path = fields[index:index + 4]
        # A `!` match re-includes the path; only a plain match excludes it.
        if pattern and not pattern.startswith("!"):
            hits.append(f"{source}:{line}:{pattern} excludes {path}")
    if not hits:
        return None
    return ("ignore rules exclude GSD Path state that must be committed: "
            + "; ".join(hits)
            + ". Anchor the product rule (for example `/build/`) in a task that owns it.")


def section_body(text: str, heading: str) -> Optional[str]:
    """The text under `## <heading>` up to the next `## `, or None when absent."""
    match = re.search(
        rf"(?ms)^## {re.escape(heading)}\s*\n(?P<body>.*?)(?=^## |\Z)", text
    )
    return match.group("body") if match else None


def task_verify_command(task_text: str) -> str:
    """The Verify shell text, excluding the closing fence's separator newline."""
    body = section_body(task_text, "Verify")
    block = VERIFY_BLOCK_PATTERN.search(body) if body is not None else None
    return block.group("block").removesuffix("\n") if block else ""


def latest_verify_entry(entries: list, command: str, commit: str,
                        repo: Optional[str] = None) -> Optional[dict]:
    """Rows are keyed by (command, repo, commit); a row without `repo` is a coordinator row."""
    for entry in reversed(entries):
        if (entry.get("schema") == VERIFY_LEDGER_SCHEMA and entry.get("repo") == repo
                and entry["command"] == command and entry["commit"] == commit):
            return entry
    return None


def verify_ledger_entries(path: Path) -> list:
    """Parsed verify-ledger rows; raises ValueError on a malformed line."""
    if not path.exists():
        return []
    return parse_verify_ledger(path.read_text(encoding="utf-8"))


def parse_verify_ledger(text: str) -> list:
    entries = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"{VERIFY_LEDGER_PATH} line {number} is not JSON: {error}") from error
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("command"), str)
            or not isinstance(entry.get("commit"), str)
            or entry.get("result") not in VERIFY_RESULTS
            or not isinstance(entry.get("recorded_at"), str)
            or ("repo" in entry and not isinstance(entry["repo"], str))
        ):
            raise ValueError(f"{VERIFY_LEDGER_PATH} line {number} has invalid fields")
        entries.append(entry)
    return entries


def run_command(
    *arguments: str, cwd: Optional[Path] = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        arguments,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )


def run_git(
    repo: Path, *arguments: str, input: Optional[str] = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ("git", "-C", str(repo), *arguments),
        input=input,
        text=True,
        capture_output=True,
        check=False,
    )


# OS files that are never pipeline artifacts when git ignores them.
# ponytail: .DS_Store only (#149); add Thumbs.db and the like when reported.
OS_JUNK_NAMES = frozenset({".DS_Store"})


def is_ignored_junk(path: Path) -> bool:
    """True for an OS junk file that git ignores and does not track."""
    if path.name not in OS_JUNK_NAMES or path.is_symlink() or not path.is_file():
        return False
    return run_git(path.parent, "check-ignore", "-q", "--", path.name).returncode == 0


def git_visible_entries(directory: Path) -> set:
    """Top-level names under directory that git tracks or would add (not ignored)."""
    result = run_git(directory, "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", ".")
    if result.returncode != 0:
        raise RuntimeError(f"git ls-files failed in {directory}: {result.stderr.strip()}")
    return {path.split("/", 1)[0] for path in result.stdout.split("\0") if path}


def atomic_replace(path: Path, temporary_path: Path, content: str) -> None:
    temporary_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = None
    try:
        if temporary_path.exists() or temporary_path.is_symlink():
            temporary_path.unlink()
        descriptor = os.open(
            temporary_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o666,
        )
        handle = os.fdopen(descriptor, "w", encoding="utf-8")
        descriptor = None
        with handle:
            handle.write(content)
        os.replace(temporary_path, path)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary_path.exists() or temporary_path.is_symlink():
            temporary_path.unlink()


def atomic_write(path: Path, content: str) -> None:
    atomic_replace(path, path.parent / f".{path.name}.gsd-path-tmp", content)


def strip_yaml_comment(value: str) -> str:
    quote = None
    previous_significant = None
    inline_list = value.lstrip().startswith("[")
    index = 0
    while index < len(value):
        character = value[index]
        if quote == '"':
            if character == "\\" and index + 1 < len(value):
                index += 2
                continue
            if character == quote:
                quote = None
        elif quote == "'":
            if (
                character == quote
                and index + 1 < len(value)
                and value[index + 1] == quote
            ):
                index += 2
                continue
            if character == quote:
                quote = None
        else:
            if character in {"'", '"'} and (
                previous_significant is None
                or (inline_list and previous_significant in {"[", ","})
            ):
                quote = character
            elif character == "#" and (
                index == 0 or value[index - 1].isspace()
            ):
                return value[:index].rstrip()
        if quote is None and not character.isspace():
            previous_significant = character
        index += 1
    return value.strip()


def unquote(value: str) -> str:
    cleaned = strip_yaml_comment(value).strip()
    if (
        len(cleaned) >= 2
        and cleaned[0] == cleaned[-1]
        and cleaned[0] in {"'", '"'}
    ):
        return cleaned[1:-1]
    return cleaned
