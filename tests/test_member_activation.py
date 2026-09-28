import unittest
from pathlib import Path

import tests.test_member_landing as landing
from scripts import isolation

TASK_FILE = landing.TASK_FILE
git = landing.git
AUTH = "refs/gsd-path/task-authorizations/acme-T001"


class MemberActivationTests(unittest.TestCase):
    setUp = landing.MemberLandingTests.setUp
    tearDown = landing.MemberLandingTests.tearDown
    land = landing.MemberLandingTests.land
    edit = landing.MemberLandingTests.edit

    def copy(self) -> Path:
        return self.sidecar / ".gsd-path-coordinator" / TASK_FILE

    def test_activation_writes_an_excluded_live_copy_and_authorization(self) -> None:
        text = self.copy().read_text(encoding="utf-8")
        for line in ("status: in-progress", "agent: coder", f"base: {self.base}",
                     f"member_base: {self.member_base}", f"worktree: {self.sidecar}",
                     "task_branch: gsd-path-task/acme-T001"):
            self.assertIn(line + "\n", text)
        self.assertEqual(git(self.sidecar, "status", "--porcelain", "--untracked-files=all"), "")
        self.assertEqual(git(self.member, "rev-parse", AUTH), self.member_base)
        self.assertEqual(git(self.coordinator, "status", "--porcelain"), "")
        self.assertIn("status: pending\n", (self.coordinator / TASK_FILE).read_text(encoding="utf-8"))

    def test_activation_is_idempotent_for_the_same_agent(self) -> None:
        before = self.copy().read_bytes()
        isolation.activate_member_task(self.coordinator, "web", "T001", "coder", TASK_FILE, self.base)
        self.assertEqual(self.copy().read_bytes(), before)

    def test_activation_requires_the_sidecar_at_its_member_base(self) -> None:
        self.copy().unlink()
        git(self.member, "update-ref", "-d", AUTH)
        self.edit()
        git(self.sidecar, "commit", "-q", "--no-verify", "-am", "early")
        with self.assertRaisesRegex(isolation.IsolationError, "member base"):
            isolation.activate_member_task(self.coordinator, "web", "T001", "coder", TASK_FILE, self.base)

    def test_landing_requires_activation_and_its_authorization(self) -> None:
        self.edit()
        git(self.member, "update-ref", "-d", AUTH)
        with self.assertRaisesRegex(isolation.IsolationError, "authoriz"):
            self.land()
        git(self.member, "update-ref", AUTH, self.member_base)
        self.copy().unlink()
        with self.assertRaisesRegex(isolation.IsolationError, "activ"):
            self.land()
        self.assertEqual(git(self.bound, "rev-parse", "HEAD"), self.member_base)

    def test_coder_log_lands_in_the_coordinator_record(self) -> None:
        self.edit()
        path = self.copy()
        path.write_text(path.read_text(encoding="utf-8") + "- coder: changed app\n", encoding="utf-8")
        self.land()
        record = (self.coordinator / TASK_FILE).read_text(encoding="utf-8")
        self.assertIn("- coder: changed app\n", record)
        self.assertIn("status: done\n", record)
        self.assertEqual(git(self.coordinator, "show", f"HEAD:{TASK_FILE}"), record.rstrip("\n"))

    def test_copy_must_keep_the_contract_and_only_grow_its_log(self) -> None:
        self.edit()
        path = self.copy()
        original = path.read_text(encoding="utf-8")
        path.write_text(original.replace("  - app.py", "  - app.py\n  - extra.py"), encoding="utf-8")
        with self.assertRaisesRegex(isolation.IsolationError, "contract"):
            self.land()
        path.write_text(original.replace("- created\n", "- rewritten\n"), encoding="utf-8")
        with self.assertRaisesRegex(isolation.IsolationError, "append-only"):
            self.land()
        self.assertEqual(git(self.bound, "rev-parse", "HEAD"), self.member_base)

    def test_unstaged_bookkeeping_may_stay_dirty_while_landing(self) -> None:
        ledger = self.coordinator / ".project" / "build" / "verify-ledger.jsonl"
        ledger.write_text("{}\n", encoding="utf-8")
        self.edit()
        self.land()
        self.assertEqual(git(self.coordinator, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"),
                         TASK_FILE)

    def test_staged_bookkeeping_never_enters_the_record(self) -> None:
        ledger = self.coordinator / ".project" / "build" / "verify-ledger.jsonl"
        ledger.write_text("{}\n", encoding="utf-8")
        git(self.coordinator, "add", "-f", str(ledger))
        self.edit()
        with self.assertRaisesRegex(isolation.IsolationError, "verify-ledger"):
            self.land()
        self.assertEqual(git(self.bound, "rev-parse", "HEAD"), self.member_base)

    def test_retire_clears_the_authorization(self) -> None:
        self.edit()
        self.land()
        isolation.retire_member_task(self.coordinator, "web", "T001")
        self.assertEqual(git(self.member, "rev-parse", "--verify", "--quiet", AUTH, check=False), "")


if __name__ == "__main__":
    unittest.main()
