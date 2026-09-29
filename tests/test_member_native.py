import json
import subprocess
import sys
import unittest
from pathlib import Path

import tests.test_member_landing as landing

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
git = landing.git


def call(script: str, *arguments: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-B", str(SCRIPTS / script), *arguments], text=True,
                          capture_output=True)


def run(script: str, *arguments: str) -> dict:
    result = call(script, *arguments)
    if result.returncode != 0:
        raise AssertionError(f"{script} {arguments}: {result.stdout}{result.stderr}")
    return json.loads(result.stdout)


class NativeMemberDispatchTests(unittest.TestCase):
    """Hosts that dispatch coders with native child tools build member tasks through the CLIs."""

    def setUp(self) -> None:
        landing.MemberLandingTests.setUp(self)
        # MemberLandingTests isolates and activates T001 through the API; start from a clean slate.
        from scripts import isolation
        isolation.deactivate_member_task(self.coordinator, "web", "T001")
        isolation.retire_member_task(self.coordinator, "web", "T001")
        task = self.coordinator / landing.TASK_FILE
        task.write_text(task.read_text(encoding="utf-8").replace(
            "## Log", "## Verify\n\n```bash\ngrep -q v2 app.py\n```\n\n## Log").replace(
            "repo: web", 'repo: "web"'), encoding="utf-8")
        git(self.coordinator, "add", "-A")
        git(self.coordinator, "commit", "-q", "-m", "plan: T001 Verify")
        self.base = git(self.coordinator, "rev-parse", "HEAD")

    tearDown = landing.MemberLandingTests.tearDown

    def test_native_prepare_activate_and_finish_land_a_member_task(self) -> None:
        prepared = run("workflow_run.py", "prepare-task", "--repo", str(self.coordinator),
                       "--expected-head", self.base, "--task-id", "T001", "--round-size", "1")
        isolate = prepared["steps"][0]["result"]
        self.assertEqual((isolate["mode"], isolate["member"]), ("member", "web"))
        self.assertEqual(len(prepared["steps"]), 1)
        active = run("isolation.py", "activate-member-task", "--repo", str(self.coordinator), "--member", "web",
                     "--task-id", "T001", "--agent", "build_t001", "--task-file", landing.TASK_FILE,
                     "--base", self.base)
        sidecar = Path(active["worktree"])
        (sidecar / "app.py").write_text("v2\n", encoding="utf-8")
        with Path(active["copy"]).open("a", encoding="utf-8") as copy:
            copy.write("- coder: changed app.py\n")
        finished = run("dispatch_driver.py", "finish", "--repo", str(self.coordinator), "--task-id", "T001")
        self.assertEqual(finished["landed"][0]["mode"], "member")
        bound = git(self.member, "rev-parse", "gsd-path/acme-M001")
        self.assertEqual(git(self.member, "show", f"{bound}:app.py"), "v2")
        self.assertIn("Member: web", git(self.coordinator, "log", "-1", "--format=%B"))

    def attempt(self, content: str) -> dict:
        head = git(self.coordinator, "rev-parse", "HEAD")
        run("workflow_run.py", "prepare-task", "--repo", str(self.coordinator),
            "--expected-head", head, "--task-id", "T001", "--round-size", "1")
        active = run("isolation.py", "activate-member-task", "--repo", str(self.coordinator), "--member", "web",
                     "--task-id", "T001", "--agent", "build_t001", "--task-file", landing.TASK_FILE,
                     "--base", head)
        (Path(active["worktree"]) / "app.py").write_text(content, encoding="utf-8")
        with Path(active["copy"]).open("a", encoding="utf-8") as copy:
            copy.write(f"- coder: wrote {content.strip()}\n")
        return active

    def retire(self, *extra: str) -> subprocess.CompletedProcess:
        return call("isolation.py", "retire-member-task", "--repo", str(self.coordinator), "--member", "web",
                    "--task-id", "T001", "--task-file", landing.TASK_FILE, *extra)

    def record_rejection(self, active: dict) -> None:
        """The parent copies the failed attempt's Log delta into the pending coordinator task and checkpoints."""
        task = self.coordinator / landing.TASK_FILE
        contract = git(self.coordinator, "show", f"HEAD:{landing.TASK_FILE}") + "\n"
        delta = Path(active["copy"]).read_text(encoding="utf-8")[len(contract):]
        task.write_text(task.read_text(encoding="utf-8") + delta, encoding="utf-8")
        git(self.coordinator, "add", "-A")
        git(self.coordinator, "commit", "-q", "-m", "build: record T001 rejection")

    def test_failed_native_member_task_retries_in_a_fresh_sidecar(self) -> None:
        first = self.attempt("wrong\n")
        failed = call("dispatch_driver.py", "finish", "--repo", str(self.coordinator), "--task-id", "T001")
        self.assertNotEqual(failed.returncode, 0, failed.stdout)
        sidecar = Path(first["worktree"])
        self.assertTrue((sidecar / "app.py").read_text(encoding="utf-8") == "wrong\n")
        # The rejected dirty sidecar blocks a new prepare until the parent retires it.
        self.assertNotEqual(call("workflow_run.py", "prepare-task", "--repo", str(self.coordinator),
                                 "--expected-head", git(self.coordinator, "rev-parse", "HEAD"),
                                 "--task-id", "T001", "--round-size", "1").returncode, 0)
        self.assertEqual(self.retire().returncode, 1)  # dirty: never without --force
        self.record_rejection(first)
        retired = self.retire("--force")
        self.assertEqual(retired.returncode, 0, retired.stderr)
        self.assertFalse(sidecar.exists())
        self.assertEqual(git(self.member, "branch", "--list", "gsd-path-task/acme-T001"), "")
        second = self.attempt("v2\n")
        self.assertNotIn("wrong", Path(second["worktree"]).joinpath("app.py").read_text(encoding="utf-8"))
        finished = run("dispatch_driver.py", "finish", "--repo", str(self.coordinator), "--task-id", "T001")
        self.assertEqual(finished["landed"][0]["mode"], "member")
        bound = git(self.member, "rev-parse", "gsd-path/acme-M001")
        self.assertEqual(git(self.member, "show", f"{bound}:app.py"), "v2")
        record = git(self.coordinator, "show", f"HEAD:{landing.TASK_FILE}")
        self.assertIn("coder: wrote wrong", record)
        self.assertIn("orchestrator Verify (isolate gsd-path-task/acme-T001): fail", record)

    def test_forced_retire_refuses_until_the_rejection_is_recorded(self) -> None:
        active = self.attempt("wrong\n")
        call("dispatch_driver.py", "finish", "--repo", str(self.coordinator), "--task-id", "T001")
        sidecar = Path(active["worktree"])
        refused = self.retire("--force")
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("Log", refused.stderr)
        self.assertEqual((sidecar / "app.py").read_text(encoding="utf-8"), "wrong\n")
        self.record_rejection(active)
        task = self.coordinator / landing.TASK_FILE
        task.write_text(task.read_text(encoding="utf-8").replace("status: pending", "status: failed"),
                        encoding="utf-8")
        git(self.coordinator, "commit", "-q", "-am", "build: mark failed")
        refused = self.retire("--force")
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("pending", refused.stderr)
        self.assertTrue(sidecar.is_dir())


if __name__ == "__main__":
    unittest.main()
