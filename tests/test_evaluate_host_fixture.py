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

    def test_multi_repo_prepare_delivers_the_member_flow(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            candidate = base / "candidate"
            subprocess.run(["git", "clone", "--quiet", "--no-hardlinks", str(evaluate_host.ROOT), str(candidate)],
                           check=True, capture_output=True)
            evaluate_host.prepare("claude", base / "multi", candidate, "multi-repo")
            arm = base / "multi" / "multi-repo"
            prompt = (arm / "prompt.txt").read_text(encoding="utf-8")
            self.assertIn(f"--member-of {arm / 'repo'} --project {arm / 'web'}", prompt)
            self.assertIn(str(arm / "web"), prompt)
            self.assertIn("close-members", prompt)
            self.assertNotIn("RELEASE-EVIDENCE ADDENDUM", prompt)

    def test_older_evaluator_rejects_host_only_scenario(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            result = subprocess.run(["python3", "-B", str(evaluate_host.ROOT / "tests/evaluate_features.py"),
                                     "prepare", "--directory", str(base / "unused"), "--scenario", "multi-repo"],
                                    text=True, capture_output=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn("invalid choice", result.stderr)
            self.assertFalse((base / "unused").exists())


if __name__ == "__main__":
    unittest.main()
