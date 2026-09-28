import json
import unittest
from pathlib import Path

import tests.test_member_landing as landing
from scripts import isolation

TASK_FILE = landing.TASK_FILE
git = landing.git
AUTH = "refs/gsd-path/task-authorizations/acme-T001"
MANAGED = {
    ".claude/settings.json": {"hooks": {"PreToolUse": [{"matcher": ".*", "hooks": [
        {"type": "command", "command": 'python3 "$CLAUDE_PROJECT_DIR/.gsd-path/guard_hook.py"'}]}]}},
    ".cursor/hooks.json": {"version": 1, "hooks": {"preToolUse": [
        {"command": 'python3 ".gsd-path/guard_hook.py"', "matcher": ".*", "failClosed": True}]}},
}


class MemberSidecarHookTests(unittest.TestCase):
    setUp_landing = landing.MemberLandingTests.setUp
    tearDown = landing.MemberLandingTests.tearDown

    def setUp(self) -> None:
        self.setUp_landing()
        # The fixture activates T001; start over from an isolated, unactivated task.
        isolation.retire_member_task(self.coordinator, "web", "T001")
        for relative, content in MANAGED.items():
            path = self.coordinator / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(content), encoding="utf-8")
        git(self.coordinator, "add", "-A")
        git(self.coordinator, "commit", "-q", "-m", "install host guards")
        self.base = git(self.coordinator, "rev-parse", "HEAD")
        self.sidecar = Path(isolation.isolate_member_task(self.coordinator, "web", "T001")["worktree"])

    def activate(self):
        return isolation.activate_member_task(self.coordinator, "web", "T001", "coder", TASK_FILE, self.base)

    def guard_commands(self, relative: str) -> list:
        data = json.loads((self.sidecar / relative).read_text(encoding="utf-8"))
        entries = data["hooks"]["PreToolUse" if "PreToolUse" in data["hooks"] else "preToolUse"]
        return [hook["command"] for entry in entries for hook in entry.get("hooks", [entry])]

    def test_sidecar_gets_host_hooks_that_call_the_coordinator_guard(self) -> None:
        self.activate()
        guard = str(self.coordinator / ".gsd-path" / "guard_hook.py")
        for relative in MANAGED:
            commands = self.guard_commands(relative)
            self.assertEqual(len(commands), 1)
            self.assertIn(f'"{guard}"', commands[0])
        self.assertFalse((self.sidecar / ".codex" / "hooks.json").exists())
        self.assertEqual(git(self.sidecar, "status", "--porcelain", "--untracked-files=all"), "")
        isolation.retire_member_task(self.coordinator, "web", "T001")
        self.assertFalse(self.sidecar.exists())

    def test_member_that_tracks_a_host_config_refuses_activation(self) -> None:
        isolation.retire_member_task(self.coordinator, "web", "T001")
        bound = Path(isolation.member_bound_checkout(self.coordinator, "web")["checkout"])
        (bound / ".claude").mkdir()
        (bound / ".claude" / "settings.json").write_text('{"team": true}', encoding="utf-8")
        git(bound, "add", "-A")
        git(bound, "commit", "-q", "--no-verify", "-m", "team settings")
        self.sidecar = Path(isolation.isolate_member_task(self.coordinator, "web", "T001")["worktree"])
        with self.assertRaisesRegex(isolation.IsolationError, ".claude/settings.json"):
            self.activate()
        self.assertEqual((self.sidecar / ".claude" / "settings.json").read_text(encoding="utf-8"), '{"team": true}')
        self.assertFalse((self.sidecar / ".gsd-path-coordinator").exists())
        self.assertEqual(git(self.member, "rev-parse", "--verify", "--quiet", AUTH, check=False), "")

    def test_untracked_local_host_config_is_never_overwritten(self) -> None:
        local = self.sidecar / ".cursor" / "hooks.json"
        local.parent.mkdir()
        local.write_text('{"mine": true}', encoding="utf-8")
        exclude = Path(git(self.member, "rev-parse", "--path-format=absolute", "--git-common-dir")) / "info" / "exclude"
        exclude.parent.mkdir(parents=True, exist_ok=True)
        exclude.write_text("/.cursor/\n", encoding="utf-8")
        with self.assertRaisesRegex(isolation.IsolationError, ".cursor/hooks.json"):
            self.activate()
        self.assertEqual(local.read_text(encoding="utf-8"), '{"mine": true}')
        self.assertEqual(git(self.member, "rev-parse", "--verify", "--quiet", AUTH, check=False), "")

    def test_reactivation_keeps_the_generated_hooks(self) -> None:
        self.activate()
        before = (self.sidecar / ".claude" / "settings.json").read_bytes()
        self.activate()
        self.assertEqual((self.sidecar / ".claude" / "settings.json").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
