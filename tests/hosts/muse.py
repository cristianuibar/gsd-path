"""Muse Code (``muse``) headless runner (verified against muse 1.4.1, 2026-09-30).

``muse exec --json --yolo --prompt-file <path>`` prints one JSONL envelope per line
(``schema_version``, ``stream``, ``payload_type``, ``payload``). ``--yolo`` trusts the
workspace: in an untrusted workspace Muse hides its delegation tools ("Agent delegation:
auto unavailable: workspace is untrusted") and GSD Path must stop instead of delegating.

Live observations (echo provider, no model call): the session id is ``stream.id`` of a
``stream.kind == "session"`` envelope; the final message is ``payload.text`` of the
``run.terminal.completed`` payload (``payload.terminal == "completed"``). ``muse resume
<session-ref>`` resumes a session by UUID.

Not verified: the envelopes a ``muse.subagent_spawn`` child emits, and token usage. The
tool schemas were read from a live trusted session, but no child was recorded through
``exec --json``, so ``bind_child`` refuses to invent a binding and always raises.
"""

import json

from tests.hosts import HostSpec


def command(prompt_path, resume=None):
    """``muse exec --json --yolo --prompt-file <prompt>``; ``resume`` becomes ``--session-id``."""
    args = ["muse", "exec", "--json", "--yolo", "--prompt-file", str(prompt_path)]
    if resume:
        args += ["--session-id", resume]
    return args


def _envelopes(lines):
    for line in lines:
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if isinstance(ev, dict) and isinstance(ev.get("payload"), dict):
            yield ev


def parse_events(lines):
    session = final = None
    for ev in _envelopes(lines):
        stream = ev.get("stream") if isinstance(ev.get("stream"), dict) else {}
        if stream.get("kind") == "session" and stream.get("id"):
            session = session or stream["id"]
        if ev.get("payload_type") == "run.terminal.completed" and ev["payload"].get("terminal") == "completed":
            final = ev["payload"].get("text")
    return {"session_id": session, "final_message": final, "usage": None}


def bind_child(run_root, child_id):
    raise LookupError(
        f"Muse child evidence for {child_id!r} in {run_root}: the muse.subagent_spawn event schema recorded by "
        "`muse exec --json` has not been verified, so no child can be bound to a completed spawn"
    )


SPEC = HostSpec(
    name="muse", install_flag="--muse", skill_root=".agents/skills", invocation="/gsd-path",
    child_api="muse.subagent_spawn", guard_tier="git-only", command=command, parse_events=parse_events,
    child_name_key="task_name", bind_child=bind_child, prompt_on_stdin=True, verified_live=False,
    notes="Session id and final message verified against muse 1.4.1 with the echo provider only. bind_child is "
          "unimplemented (spawn envelopes unverified), so no release receipt can bind a Muse child yet. Requires a "
          "trusted workspace for delegation; --yolo also disables approval and the sandbox.",
)
