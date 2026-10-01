"""Muse Code host module tests.

The envelopes mirror the live ``muse exec --json`` stream recorded on 2026-09-30 with
the echo provider (see ``tests/hosts/muse.py``).
"""

import json
import tempfile
import unittest
from pathlib import Path

from tests.hosts import muse

SESSION = "01a0f32e-7bbb-7642-b987-4f19fdc05f74"


def envelope(payload_type, payload, kind="session", stream_id=SESSION):
    return json.dumps({"schema_version": 1, "stream": {"kind": kind, "id": stream_id}, "payload_type": payload_type, "payload": payload})


STARTED = envelope("run.lifecycle.started", {"kind": "run_started", "prompt": "hello"})
TERMINAL = envelope("run.terminal.completed", {"kind": "run_terminal", "terminal": "completed", "text": "shipped"})


class MuseHostTests(unittest.TestCase):
    def test_spec_matches_manifest_facts(self):
        spec = muse.SPEC
        self.assertEqual((spec.name, spec.install_flag, spec.skill_root, spec.invocation, spec.child_api, spec.guard_tier),
                         ("muse", "--muse", ".agents/skills", "/gsd-path", "muse.subagent_spawn", "git-only"))
        self.assertFalse(spec.verified_live)

    def test_command_reads_prompt_file_and_resumes_by_session(self):
        prompt = Path("/runs/run-1/prompt.txt")
        self.assertEqual(muse.command(prompt), ["muse", "exec", "--json", "--yolo", "--prompt-file", str(prompt)])
        self.assertEqual(muse.command(prompt, "s-1")[-2:], ["--session-id", "s-1"])

    def test_parse_events_reads_session_and_terminal_text(self):
        lines = [STARTED, "not json", envelope("run.output.delta", {"text": "partial"}), TERMINAL]
        self.assertEqual(muse.parse_events(lines), {"session_id": SESSION, "final_message": "shipped", "usage": None})

    def test_parse_events_ignores_non_session_streams_and_never_invents(self):
        self.assertEqual(muse.parse_events([]), {"session_id": None, "final_message": None, "usage": None})
        parsed = muse.parse_events([envelope("task.stream.linked", {}, kind="task", stream_id="task-1")])
        self.assertIsNone(parsed["session_id"])
        failed = envelope("run.terminal.completed", {"terminal": "failed", "text": "boom"})
        self.assertIsNone(muse.parse_events([STARTED, failed])["final_message"])

    def test_bind_child_never_fabricates_evidence(self):
        with tempfile.TemporaryDirectory() as root, self.assertRaisesRegex(LookupError, "build_T001"):
            muse.bind_child(Path(root), "build_T001")


if __name__ == "__main__":
    unittest.main()
