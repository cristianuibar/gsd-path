#!/usr/bin/env python3
# gsd-path project runtime
"""Record and validate the member repositories of a multi-repo coordinator.

The coordinator's `.project/MEMBERS.md` lists members in ship order
(docs/adr/0002-multi-repo-coordinator.md). `add` only writes the file; the
next approval checkpoint commits it with the other `.project` artifacts.
"""

from __future__ import annotations

import argparse
import json
import re
import sys

# Runtime helpers must not modify their immutable installation.
sys.dont_write_bytecode = True
from pathlib import Path
from typing import Optional, Sequence

if __package__:
    from . import _common, pipeline_state
else:
    import _common
    import pipeline_state


MEMBERS_FILE = "MEMBERS.md"
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
FIELDS = ("Checkout", "Remote", "Integration")
INTEGRATIONS = ("default", "direct", "pull-request")
GITHUB_REMOTE_RE = re.compile(
    r"(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)[^/\s]+/[^/\s]+"
)
# Member-side Path refs carry the coordinator name, so they cannot collide with
# a member's own Path history.
MEMBER_REF_FORMATS = (
    "refs/heads/gsd-path/{}-",
    "refs/heads/gsd-path-task/{}-",
    "refs/heads/gsd-path-verify/{}-",
    "refs/heads/gsd-path-integrate/{}-",
    "refs/remotes/origin/gsd-path/{}-",
    "refs/remotes/origin/gsd-path-task/{}-",
    "refs/remotes/origin/gsd-path-verify/{}-",
    "refs/remotes/origin/gsd-path-integrate/{}-",
    "refs/tags/milestone/{}-",
)
HEADER = (
    "# Members\n\n"
    "<!-- Written by members.py add. One section per member repository, in\n"
    "     ship order. Fixed format; change it only through members.py. -->\n"
)


class MembersError(RuntimeError):
    pass


def _git(repo: Path, *arguments: str) -> str:
    result = _common.run_git(repo, *arguments)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip() or "git command failed"
        raise MembersError(f"{repo}: git {' '.join(arguments)}: {detail}")
    return result.stdout.strip()


def _coordinator(repo: Path) -> tuple[Path, pipeline_state.PipelineState]:
    try:
        root = pipeline_state._repo_root(Path(repo))
        state, _, _ = pipeline_state.load_state(root)
    except pipeline_state.PipelineStateError as error:
        raise MembersError(f"coordinator: {error}") from error
    return root, state


def read_members(coordinator: Path) -> list[dict[str, str]]:
    """Parse MEMBERS.md; an absent file means a single-repo project."""
    path = coordinator / ".project" / MEMBERS_FILE
    if not path.exists() and not path.is_symlink():
        return []
    if path.is_symlink() or not path.is_file():
        raise MembersError("MEMBERS.md must be a regular file")
    members: list[dict[str, str]] = []
    current: Optional[dict[str, str]] = None
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.startswith("## "):
            name = line[3:].strip()
            if not NAME_RE.fullmatch(name):
                raise MembersError(f"MEMBERS.md line {number}: invalid member name {name!r}")
            current = {"name": name}
            members.append(current)
            continue
        if current is None or not line.strip():
            continue
        key, separator, value = line.partition(":")
        if not separator or key not in FIELDS or key.lower() in current:
            raise MembersError(f"MEMBERS.md line {number}: unexpected line {line!r}")
        current[key.lower()] = value.strip()
    names = [member["name"] for member in members]
    if len(set(names)) != len(names):
        raise MembersError("MEMBERS.md repeats a member name")
    for member in members:
        missing = [field for field in FIELDS if not member.get(field.lower())]
        if missing:
            raise MembersError(f"MEMBERS.md member {member['name']} lacks {', '.join(missing)}")
        if member["integration"] not in INTEGRATIONS:
            raise MembersError(
                f"MEMBERS.md member {member['name']} has invalid Integration: {member['integration']}"
            )
        if not Path(member["checkout"]).is_absolute():
            raise MembersError(f"MEMBERS.md member {member['name']} Checkout must be absolute")
    return members


def check_member(
    coordinator: Path,
    coordinator_name: str,
    checkout: Path,
    recorded_remote: Optional[str] = None,
) -> str:
    """Refuse a checkout that cannot join; return its origin URL."""
    if checkout.is_symlink() or not checkout.is_dir():
        raise MembersError(f"member checkout is not a real directory: {checkout}")
    checkout = checkout.resolve()
    if coordinator in checkout.parents or checkout in coordinator.parents:
        raise MembersError(f"member checkout is nested with the coordinator: {checkout}")
    if Path(_git(checkout, "rev-parse", "--show-toplevel")).resolve() != checkout:
        raise MembersError(f"member checkout must be its Git root: {checkout}")
    if _git(checkout, "rev-parse", "--show-superproject-working-tree"):
        raise MembersError(f"member checkout is a submodule: {checkout}")
    common = Path(_git(checkout, "rev-parse", "--path-format=absolute", "--git-common-dir"))
    coordinator_common = Path(
        _git(coordinator, "rev-parse", "--path-format=absolute", "--git-common-dir")
    )
    if common.resolve() == coordinator_common.resolve():
        raise MembersError("the coordinator cannot be its own member")
    if _git(checkout, "status", "--porcelain"):
        raise MembersError(f"member has uncommitted changes: {checkout}")
    remote = _git(checkout, "remote", "get-url", "origin")
    if not GITHUB_REMOTE_RE.fullmatch(remote):
        raise MembersError(f"member requires a GitHub.com origin: {remote}")
    if recorded_remote is not None and remote != recorded_remote:
        raise MembersError(f"member origin changed: {recorded_remote} -> {remote}")
    default = _common.run_git(checkout, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    if default.returncode != 0 or default.stdout.strip() != "origin/main":
        raise MembersError(f"member remote default must be main: {checkout}")
    if (checkout / ".project" / "STATE.md").exists():
        try:
            state, _, _ = pipeline_state.load_state(checkout)
        except pipeline_state.PipelineStateError as error:
            raise MembersError(f"member STATE.md is unreadable: {error}") from error
        if state.milestone is not None and (state.phase, state.status) != ("shipped", "done"):
            raise MembersError(f"member has an active milestone: {state.milestone}")
    prefixes = tuple(pattern.format(coordinator_name) for pattern in MEMBER_REF_FORMATS)
    refs = _git(checkout, "for-each-ref", "--format=%(refname)").splitlines()
    colliding = [ref for ref in refs if ref.startswith(prefixes)]
    if colliding:
        raise MembersError("member refs collide with coordinator names: " + ", ".join(colliding))
    return remote


def render(members: Sequence[dict[str, str]]) -> str:
    sections = [
        f"## {member['name']}\n"
        f"Checkout: {member['checkout']}\n"
        f"Remote: {member['remote']}\n"
        f"Integration: {member['integration']}\n"
        for member in members
    ]
    return "\n".join([HEADER, *sections])


def add_member(repo: Path, name: str, checkout: Path, integration: str) -> list[dict[str, str]]:
    root, state = _coordinator(repo)
    if state.phase in {"build", "ship"}:
        raise MembersError("members change only at a milestone boundary, not during build or ship")
    if not NAME_RE.fullmatch(name):
        raise MembersError(f"invalid member name: {name!r}")
    members = read_members(root)
    resolved = checkout.resolve()
    for member in members:
        if member["name"] == name or Path(member["checkout"]) == resolved:
            raise MembersError(f"member already recorded: {member['name']}")
    remote = check_member(root, state.project, checkout)
    members.append(
        {"name": name, "checkout": str(resolved), "remote": remote, "integration": integration}
    )
    _common.atomic_write(root / ".project" / MEMBERS_FILE, render(members))
    return members


def validate_members(repo: Path) -> list[dict[str, str]]:
    root, state = _coordinator(repo)
    members = read_members(root)
    for member in members:
        check_member(root, state.project, Path(member["checkout"]), member["remote"])
    return members


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    add = commands.add_parser("add", help="record one member repository")
    add.add_argument("--repo", required=True, type=Path, help="coordinator Git root")
    add.add_argument("--name", required=True)
    add.add_argument("--checkout", required=True, type=Path)
    add.add_argument("--integration", choices=INTEGRATIONS, default="default")
    validate = commands.add_parser("validate", help="check MEMBERS.md and every member")
    validate.add_argument("--repo", required=True, type=Path, help="coordinator Git root")
    return result


def main(argv: Optional[Sequence[str]] = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        if arguments.command == "add":
            members = add_member(
                arguments.repo, arguments.name, arguments.checkout, arguments.integration
            )
        else:
            members = validate_members(arguments.repo)
    except (MembersError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"members": members}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
