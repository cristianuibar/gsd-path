import json
import subprocess
import sys
import unittest
from pathlib import Path

import tests.test_member_landing as landing

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
git = landing.git


def run(script: str, *arguments: str) -> dict:
    result = subprocess.run([sys.executable, "-B", str(SCRIPTS / script), *arguments], text=True,
                            capture_output=True)
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
            "## Log", "## Verify\n\n```bash\ngrep -q v2 app.py\n```\n\n## Log"), encoding="utf-8")
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


if __name__ == "__main__":
    unittest.main()
