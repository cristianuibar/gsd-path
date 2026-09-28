import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import lean_verification
import tests.test_lean_verification as lean_tests

ROOT = Path(__file__).resolve().parents[1]
MEMBERS = ROOT / "scripts" / "members.py"
COMMAND = "test -f ../web/lib.py && python3 -m unittest -q test_hello"


def git(repo: Path, *arguments: str, check: bool = True) -> str:
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *arguments], cwd=repo,
                          text=True, capture_output=True, check=check).stdout.strip()


class MemberProjectVerifyTests(unittest.TestCase):
    fixture = lean_tests.LeanVerificationTests.fixture

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name).resolve()
        environment = mock.patch.dict(os.environ, {"GSD_PATH_WORKTREE_ROOT": str(base / "workspace")})
        environment.start()
        self.addCleanup(environment.stop)
        self.root = base / "acme"
        self.root.mkdir()
        self.fixture(self.root)
        self.member = base / "web"
        self.member.mkdir()
        git(self.member, "init", "-q", "-b", "main")
        (self.member / "README.md").write_text("web\n", encoding="utf-8")
        git(self.member, "add", "-A")
        git(self.member, "commit", "-q", "-m", "init")
        git(self.member, "remote", "add", "origin", "https://github.com/acme/web.git")
        git(self.member, "update-ref", "refs/remotes/origin/main", "HEAD")
        git(self.member, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
        state = self.root / ".project" / "STATE.md"
        shipping = state.read_text(encoding="utf-8")
        state.write_text(shipping.replace("phase: ship", "phase: plan"), encoding="utf-8")
        joined = subprocess.run([sys.executable, str(MEMBERS), "add", "--repo", str(self.root), "--name", "web",
                                 "--checkout", str(self.member)], text=True, capture_output=True)
        self.assertEqual(joined.returncode, 0, joined.stderr)
        state.write_text(shipping, encoding="utf-8")
        git(self.member, "checkout", "-q", "-b", "gsd-path/demo-M001")
        (self.member / "lib.py").write_text("landed = True\n", encoding="utf-8")
        git(self.member, "add", "-A")
        git(self.member, "commit", "-q", "-m", "member landing")
        self.member_tip = git(self.member, "rev-parse", "HEAD")
        git(self.member, "checkout", "-q", "main")
        lock = self.root / ".project" / "build" / "members.json"
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text(json.dumps({"schema": "gsd-path/member-lock/v1", "members": [
            {"name": "web", "branch": "gsd-path/demo-M001", "base": git(self.member, "rev-parse", "main")}]}),
            encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "member milestone")
        self.head = git(self.root, "rev-parse", "HEAD")

    def use_member_verify_command(self) -> None:
        plan = self.root / ".project" / "plan" / "PLAN.md"
        text = plan.read_text(encoding="utf-8")
        start = text.index("Project verify:")
        end = text.index("\n", start)
        plan.write_text(text[:start] + f"Project verify: {COMMAND}" + text[end:], encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "project verify uses the member")
        self.head = git(self.root, "rev-parse", "HEAD")

    def ledger_rows(self) -> list:
        ledger = self.root / ".project" / "build" / "verify-ledger.jsonl"
        return [json.loads(line) for line in ledger.read_text().splitlines()] if ledger.exists() else []

    def test_project_verify_sees_member_sidecars_beside_the_coordinator(self) -> None:
        self.use_member_verify_command()
        result = lean_verification.verify_project(self.root, self.head)
        self.assertTrue(result["passed"], result["execution"])
        self.assertEqual(result["execution"]["members"], {"web": self.member_tip})
        self.assertEqual(git(self.member, "worktree", "list", "--porcelain").count("worktree "), 1)
        self.assertEqual(git(self.member, "branch", "--list", "gsd-path-verify/*"), "")

    def test_stale_member_marker_leaves_no_verify_sidecar(self) -> None:
        self.use_member_verify_command()
        marker = Path(git(self.member, "rev-parse", "--path-format=absolute", "--git-common-dir")) / "gsd-path" / "member.json"
        marker.unlink()
        with self.assertRaisesRegex(Exception, "member marker for web"):
            lean_verification.verify_project(self.root, self.head)
        self.assertEqual(git(self.root, "branch", "--list", "gsd-path-verify/*"), "")
        self.assertEqual(git(self.root, "worktree", "list", "--porcelain").count("worktree "), 1)

    def test_member_milestone_verify_is_never_reused_from_the_ledger(self) -> None:
        self.use_member_verify_command()
        first = lean_verification.verify_project(self.root, self.head)
        second = lean_verification.verify_project(self.root, self.head)
        self.assertFalse(first["reused"])
        self.assertFalse(second["reused"])
        self.assertEqual([row for row in self.ledger_rows() if row["command"] == COMMAND], [])

    def test_final_review_is_not_reused_for_a_member_milestone(self) -> None:
        wave = next((self.root / ".project" / "review").glob("wave-1.cycle*.md"))
        text = wave.read_text(encoding="utf-8")
        start = text.index("Reviewed HEAD:")
        end = text.index("\n", start)
        wave.write_text(text[:start] + f"Reviewed HEAD: {self.head}" + text[end:], encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "review covers the member milestone")
        head = git(self.root, "rev-parse", "HEAD")
        result = lean_verification.reuse_final(self.root, head)
        self.assertFalse(result["reused"])
        self.assertIn("member", result["reason"])


if __name__ == "__main__":
    unittest.main()
