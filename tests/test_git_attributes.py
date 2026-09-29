"""The installer's local LF rule for .project (issue #200)."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import install


def git(repo: Path, *arguments: str) -> str:
    # The dev runner pins core.autocrlf=false through GIT_CONFIG_*, which would
    # override the repository setting these tests exercise.
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_CONFIG_")}
    return subprocess.run(["git", "-C", str(repo), *arguments], check=True, env=env,
                          capture_output=True, encoding="utf-8", errors="replace").stdout


class MergedAttributesTests(unittest.TestCase):
    path = Path("attributes")

    def test_new_file_is_the_block(self) -> None:
        self.assertEqual(install._merged_git_attributes(None, self.path),
                         install.GIT_ATTRIBUTES_BLOCK.encode("utf-8"))

    def test_owner_rules_are_kept_and_the_block_appended(self) -> None:
        merged = install._merged_git_attributes(b"*.png binary", self.path)
        self.assertEqual(merged, b"*.png binary\n" + install.GIT_ATTRIBUTES_BLOCK.encode("utf-8"))

    def test_existing_block_is_replaced_in_place_and_idempotent(self) -> None:
        stale = (b"*.png binary\n# gsd-path:begin\n/.project/** -text\n# gsd-path:end\n"
                 b"*.md text\n")
        merged = install._merged_git_attributes(stale, self.path)
        self.assertEqual(merged, b"*.png binary\n" + install.GIT_ATTRIBUTES_BLOCK.encode("utf-8")
                         + b"*.md text\n")
        self.assertEqual(install._merged_git_attributes(merged, self.path), merged)

    def test_unbalanced_markers_are_refused(self) -> None:
        with self.assertRaises(install.InstallerError):
            install._merged_git_attributes(b"# gsd-path:begin\n", self.path)


class ApplyAttributesTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.base = Path(directory.name).resolve()
        self.repo = self.base / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.email", "test@example.invalid")
        git(self.repo, "config", "user.name", "Test")

    def attributes(self) -> Path:
        return install._git_attributes_path(self.repo)

    def test_writes_the_common_attributes_file_and_rolls_back(self) -> None:
        transaction = install.ProjectTransaction()
        install._apply_git_attributes(self.repo, transaction)
        self.assertEqual(self.attributes().read_bytes(), install.GIT_ATTRIBUTES_BLOCK.encode("utf-8"))
        install._rollback_project(transaction)
        self.assertFalse(self.attributes().exists())

    def test_keeps_owner_rules_on_rollback(self) -> None:
        self.attributes().parent.mkdir(parents=True, exist_ok=True)
        self.attributes().write_bytes(b"*.png binary\n")
        transaction = install.ProjectTransaction()
        install._apply_git_attributes(self.repo, transaction)
        self.assertIn(b"/.project/** text eol=lf", self.attributes().read_bytes())
        install._rollback_project(transaction)
        self.assertEqual(self.attributes().read_bytes(), b"*.png binary\n")

    def test_pipeline_state_stays_lf_under_autocrlf_in_new_worktrees(self) -> None:
        (self.repo / ".project").mkdir()
        (self.repo / ".project" / "STATE.md").write_bytes(b"phase: build\nstatus: active\n")
        (self.repo / "app.txt").write_bytes(b"one\ntwo\n")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-qm", "fixture")
        git(self.repo, "config", "core.autocrlf", "true")
        install._apply_git_attributes(self.repo, install.ProjectTransaction())
        worktree = self.base / "task"
        git(self.repo, "worktree", "add", "-q", "-b", "task", str(worktree))
        self.assertEqual((worktree / ".project" / "STATE.md").read_bytes(),
                         b"phase: build\nstatus: active\n")
        # Product files still follow the user's autocrlf setting.
        self.assertEqual((worktree / "app.txt").read_bytes(), b"one\r\ntwo\r\n")

    def test_doctor_reports_the_rule(self) -> None:
        texts = lambda: [f["text"] for f in install.doctor(ROOT, [], lambda _: self.base, self.repo)]
        self.assertTrue(any("lacks the GSD Path LF rule" in text for text in texts()))
        install._apply_git_attributes(self.repo, install.ProjectTransaction())
        self.assertTrue(any(".project is checked out LF" in text for text in texts()))


if __name__ == "__main__":
    unittest.main()
