#!/usr/bin/env python3
# gsd-path project runtime
"""Record and validate the member repositories of a multi-repo coordinator.

The coordinator's `.project/MEMBERS.md` lists members in ship order
(docs/adr/0002-multi-repo-coordinator.md). `add` only writes the file; the
next approval checkpoint commits it with the other `.project` artifacts.
Each member's shared Git directory holds an untracked marker naming its
coordinator; `member_role` verifies it from any worktree of the member.
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
MARKER_SCHEMA = "gsd-path/member/v1"
MARKER_KEYS = {"schema", "coordinator", "project", "name"}
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
FIELDS = ("Checkout", "Remote", "Integration")
INTEGRATIONS = ("default", "direct", "pull-request")
GITHUB_REMOTE_RE = re.compile(
    r"(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)([^/\s]+)/([^/\s]+)"
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
    if Path(_git(root, "rev-parse", "--show-toplevel")).resolve() != root:
        raise MembersError(f"coordinator is not a Git root: {root}")
    return root, state


def _remote_identity(remote: str) -> Optional[tuple[str, str]]:
    match = GITHUB_REMOTE_RE.fullmatch(remote)
    if match is None:
        return None
    return match.group(1).lower(), match.group(2).removesuffix(".git").lower()


def _common_dir(checkout: Path) -> Path:
    return Path(_git(checkout, "rev-parse", "--path-format=absolute", "--git-common-dir")).resolve()


def _marker_path(checkout: Path) -> Path:
    directory = _common_dir(checkout) / "gsd-path"
    if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
        raise MembersError(f"member marker directory must be real: {directory}")
    path = directory / "member.json"
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise MembersError(
            f"member marker is not a regular file: {path}; "
            "remove it by hand, then run members.py repair --repo <coordinator>"
        )
    return path


def _read_marker(path: Path) -> Optional[dict[str, str]]:
    if not path.exists() and not path.is_symlink():
        return None
    try:
        if path.is_symlink() or not path.is_file():
            raise MembersError(
                f"member marker is not a regular file: {path}; "
                "remove it by hand, then run members.py repair --repo <coordinator>"
            )
        data = json.loads(path.read_text(encoding="utf-8"))
        if (not isinstance(data, dict) or set(data) != MARKER_KEYS
                or any(not isinstance(data[key], str) or not data[key].strip() for key in MARKER_KEYS)
                or data["schema"] != MARKER_SCHEMA
                or not Path(data["coordinator"]).is_absolute()):
            raise ValueError("unexpected content")
    except (OSError, ValueError) as error:
        raise MembersError(
            f"member marker is unreadable: {path}: {error}; "
            "run members.py repair --repo <coordinator>"
        ) from error
    return data


def _write_marker(checkout: Path, coordinator: Path, project: str, name: str) -> None:
    path = _marker_path(checkout)
    path.parent.mkdir(parents=True, exist_ok=True)
    marker = {"schema": MARKER_SCHEMA, "coordinator": str(coordinator), "project": project, "name": name}
    _common.atomic_write(path, json.dumps(marker, sort_keys=True) + "\n")


def _refuse_foreign_marker(checkout: Path, coordinator: Path, project: str, name: str) -> None:
    path = _marker_path(checkout)
    try:
        marker = _read_marker(path)
    except MembersError:
        return
    if marker is not None and (marker["project"], marker["name"]) != (project, name):
        raise MembersError(f"{checkout} is already a member of {marker['project']}")
    if marker is not None:
        try:
            role = member_role(checkout)
        except MembersError:
            return
        if role is not None and role["coordinator"] != coordinator:
            raise MembersError(f"{checkout} is already a member of {role['coordinator']}")


def member_role(checkout: Path) -> Optional[dict[str, object]]:
    """The verified coordinator of a member checkout, or None outside a member."""
    checkout = Path(checkout)
    marker = _read_marker(_marker_path(checkout))
    if marker is None:
        return None
    stale = MembersError(
        f"member marker for {marker['name']} is stale; "
        "run members.py repair --repo <coordinator>"
    )
    try:
        root, state = _coordinator(Path(marker["coordinator"]))
        listed = read_members(root)
        common = _common_dir(checkout)
        for member in listed:
            if member["name"] == marker["name"] and _common_dir(Path(member["checkout"])) == common:
                if state.project != marker["project"]:
                    break
                return {"coordinator": root, "project": state.project, "name": member["name"]}
    except (MembersError, OSError) as error:
        raise stale from error
    raise stale


def read_members(coordinator: Path) -> list[dict[str, str]]:
    """Parse MEMBERS.md; an absent file means a single-repo project."""
    path = coordinator / ".project" / MEMBERS_FILE
    if not path.exists() and not path.is_symlink():
        return []
    if path.is_symlink() or not path.is_file():
        raise MembersError("MEMBERS.md must be a regular file")
    members: list[dict[str, str]] = []
    current: Optional[dict[str, str]] = None
    preamble: list[str] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.startswith("## "):
            name = line[3:].strip()
            if not NAME_RE.fullmatch(name):
                raise MembersError(f"MEMBERS.md line {number}: invalid member name {name!r}")
            current = {"name": name}
            members.append(current)
            continue
        if current is None:
            preamble.append(line)
            continue
        if not line.strip():
            continue
        key, separator, value = line.partition(":")
        if not separator or key not in FIELDS or key.lower() in current:
            raise MembersError(f"MEMBERS.md line {number}: unexpected line {line!r}")
        current[key.lower()] = value.strip()
    if not preamble or preamble[0] != "# Members":
        raise MembersError("MEMBERS.md format error: expected # Members")
    rest = preamble[1:]
    while rest and not rest[0]:
        rest.pop(0)
    comment = HEADER.splitlines()[2:]
    if rest[:len(comment)] == comment:
        rest = rest[len(comment):]
    if any(rest):
        raise MembersError("MEMBERS.md format error: unexpected pre-section content")
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
    if _git(checkout, "status", "--porcelain", "--untracked-files=all"):
        raise MembersError(f"member has uncommitted changes: {checkout}")
    remote = _git(checkout, "remote", "get-url", "origin")
    if not GITHUB_REMOTE_RE.fullmatch(remote):
        raise MembersError(f"member requires a GitHub.com origin: {remote}")
    if recorded_remote is not None and remote != recorded_remote:
        raise MembersError(f"member origin changed: {recorded_remote} -> {remote}")
    default = _common.run_git(checkout, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    if default.returncode != 0 or default.stdout.strip() != "origin/main":
        raise MembersError(f"member remote default must be main: {checkout}")
    member_state = checkout / ".project" / "STATE.md"
    if member_state.exists() or member_state.is_symlink():
        if member_state.is_symlink() or not member_state.is_file():
            raise MembersError("member STATE.md is unreadable")
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
    remote = check_member(root, state.project, checkout)
    common = Path(_git(resolved, "rev-parse", "--path-format=absolute", "--git-common-dir")).resolve()
    identity = _remote_identity(remote)
    for member in members:
        previous = Path(member["checkout"])
        if (member["name"] == name or previous == resolved
                or _remote_identity(member["remote"]) == identity
                or Path(_git(previous, "rev-parse", "--path-format=absolute", "--git-common-dir")).resolve() == common):
            raise MembersError(f"member already recorded: {member['name']}")
    _refuse_foreign_marker(resolved, root, state.project, name)
    members.append(
        {"name": name, "checkout": str(resolved), "remote": remote, "integration": integration}
    )
    _write_marker(resolved, root, state.project, name)
    _common.atomic_write(root / ".project" / MEMBERS_FILE, render(members))
    return members


def validate_members(repo: Path) -> list[dict[str, str]]:
    root, state = _coordinator(repo)
    members = read_members(root)
    for member in members:
        checkout = Path(member["checkout"])
        check_member(root, state.project, checkout, member["remote"])
        try:
            role = member_role(checkout)
        except MembersError as error:
            raise MembersError(f"{error}; run members.py repair --repo {root}") from error
        if role != {"coordinator": root, "project": state.project, "name": member["name"]}:
            raise MembersError(
                f"member marker for {member['name']} is missing or stale; "
                f"run members.py repair --repo {root}"
            )
    return members


def repair_members(repo: Path) -> list[dict[str, str]]:
    """Rewrite missing or stale markers; never take over another coordinator's member."""
    root, state = _coordinator(repo)
    members = read_members(root)
    for member in members:
        checkout = Path(member["checkout"])
        check_member(root, state.project, checkout, member["remote"])
        _refuse_foreign_marker(checkout.resolve(), root, state.project, member["name"])
    for member in members:
        checkout = Path(member["checkout"]).resolve()
        try:
            role = member_role(checkout)
        except MembersError:
            role = None
        if role != {"coordinator": root, "project": state.project, "name": member["name"]}:
            _write_marker(checkout, root, state.project, member["name"])
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
    repair = commands.add_parser("repair", help="rewrite missing or stale member markers")
    repair.add_argument("--repo", required=True, type=Path, help="coordinator Git root")
    return result


def main(argv: Optional[Sequence[str]] = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        if arguments.command == "add":
            members = add_member(
                arguments.repo, arguments.name, arguments.checkout, arguments.integration
            )
        elif arguments.command == "repair":
            members = repair_members(arguments.repo)
        else:
            members = validate_members(arguments.repo)
    except (MembersError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"members": members}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
