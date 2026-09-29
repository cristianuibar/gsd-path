import subprocess
import tempfile
import unittest
from pathlib import Path

from tests import evaluate_host


def git(repo: Path, *arguments: str) -> str:
    return subprocess.run(["git", *arguments], cwd=repo, text=True, capture_output=True, check=True).stdout.strip()


class MemberFixtureTests(unittest.TestCase):
    """The two-repo host scenario's member keeps a GitHub origin but pushes to a local bare remote."""

    def test_member_fixture_has_a_github_origin_that_pushes_locally(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            arm = Path(temporary).resolve()
            member = evaluate_host.member_fixture(arm)
            self.assertTrue((member / "count.py").is_file())
            self.assertEqual(git(member, "config", "--get", "remote.origin.url"), "https://github.com/acme/web.git")
            self.assertEqual(git(member, "symbolic-ref", "refs/remotes/origin/HEAD"), "refs/remotes/origin/main")
            (member / "note.txt").write_text("x\n", encoding="utf-8")
            git(member, "add", "-A")
            git(member, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "note")
            git(member, "push", "-q", "origin", "main")
            self.assertEqual(git(arm / "web-origin.git", "rev-parse", "main"), git(member, "rev-parse", "HEAD"))

    def test_multi_repo_scenario_names_the_member_flow(self) -> None:
        scenario = evaluate_host.SCENARIOS["multi-repo"]
        self.assertEqual(scenario["fixture"], "counter-member")
        request = scenario["request"].format(member="/m", plugin="/p", repo="/r")
        self.assertIn("--member-of /r --project /m", request)

    def test_only_the_release_scenario_carries_the_receipt_addendum(self) -> None:
        if git(evaluate_host.ROOT, "status", "--porcelain"):
            self.skipTest("prepare needs a committed candidate")
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            evaluate_host.prepare("claude", base / "multi", evaluate_host.ROOT, "multi-repo")
            prompt = (base / "multi" / "multi-repo" / "prompt.txt").read_text(encoding="utf-8")
            self.assertIn("close-members", prompt)
            self.assertNotIn("RELEASE-EVIDENCE ADDENDUM", prompt)


if __name__ == "__main__":
    unittest.main()
