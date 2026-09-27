"""Attacks on the Windows handle-anchored STATE.md creation (detect_project)."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import detect_project
from _platform import can_symlink, windows_only

TEMPLATE = ROOT / "skills" / "gsd-path" / "templates" / "state.md"


def make_junction(target: Path, link: Path) -> None:
    import _winapi

    _winapi.CreateJunction(str(target), str(link))


@windows_only
class WindowsAnchoredStateTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.base = Path(directory.name).resolve()
        self.repo = self.base / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        self.outside = self.base / "outside"
        self.outside.mkdir()

    def snapshots(self):
        root = detect_project.lstat_evidence(self.repo, missing_ok=False)
        project = detect_project.lstat_evidence(self.repo / ".project", missing_ok=True)
        return root, project

    def write(self, root_status, project_status, content: str = "state\n") -> None:
        detect_project.write_state_anchored(self.repo, content, root_status, project_status)

    def test_initialize_writes_exact_lf_state(self) -> None:
        payload = detect_project.initialize(self.repo, TEMPLATE)
        self.assertTrue(payload["wrote_state"])
        data = (self.repo / ".project" / "STATE.md").read_bytes()
        self.assertNotIn(b"\r", data)
        self.assertIn(b"pipeline: gsd-path/v2", data)
        self.assertEqual(os.listdir(self.repo / ".project"), ["STATE.md"])
        self.assertEqual(detect_project.classify(self.repo)["verdict"], "owned")

    def test_refuses_a_junction_planted_at_project(self) -> None:
        root_status, _ = self.snapshots()
        make_junction(self.outside, self.repo / ".project")
        with self.assertRaises(detect_project.DetectError):
            self.write(root_status, None)
        with self.assertRaises(detect_project.DetectError):
            self.write(root_status, detect_project.lstat_evidence(self.repo / ".project", missing_ok=False))
        self.assertEqual(os.listdir(self.outside), [])

    def test_project_cannot_be_swapped_while_writing(self) -> None:
        root_status, project_status = self.snapshots()
        attempts = []
        original = detect_project.write_all

        def swap_then_write(descriptor, payload):
            try:
                os.rename(self.repo / ".project", self.base / "moved")
                attempts.append("renamed")
            except OSError as error:
                attempts.append(type(error).__name__)
            original(descriptor, payload)

        with mock.patch.object(detect_project, "write_all", side_effect=swap_then_write):
            self.write(root_status, project_status)
        self.assertEqual(attempts, ["PermissionError"])
        self.assertEqual((self.repo / ".project" / "STATE.md").read_bytes(), b"state\n")

    @unittest.skipUnless(can_symlink(), "symlinks unavailable on this host")
    def test_never_writes_through_a_state_symlink(self) -> None:
        (self.repo / ".project").mkdir()
        target = self.outside / "target.md"
        target.write_bytes(b"outside\n")
        root_status, project_status = self.snapshots()
        (self.repo / ".project" / "STATE.md").symlink_to(target)
        with self.assertRaises(detect_project.DetectError):
            self.write(root_status, project_status)
        self.assertEqual(target.read_bytes(), b"outside\n")
        self.assertEqual(sorted(os.listdir(self.repo / ".project")), ["STATE.md"])

    def test_failure_rolls_back_the_temporary_file(self) -> None:
        root_status, project_status = self.snapshots()
        with mock.patch.object(detect_project, "write_all", side_effect=OSError("disk full")):
            with self.assertRaises(detect_project.DetectError):
                self.write(root_status, project_status)
        self.assertEqual(os.listdir(self.repo / ".project"), [])

    def test_reuses_a_leftover_temporary_file(self) -> None:
        (self.repo / ".project").mkdir()
        (self.repo / ".project" / detect_project.STATE_TEMP_NAME).write_bytes(b"partial")
        self.assertEqual(detect_project.classify(self.repo)["verdict"], "greenfield")
        root_status, project_status = self.snapshots()
        self.write(root_status, project_status, "fresh\n")
        self.assertEqual(os.listdir(self.repo / ".project"), ["STATE.md"])
        self.assertEqual((self.repo / ".project" / "STATE.md").read_bytes(), b"fresh\n")

    def test_refuses_when_state_already_exists(self) -> None:
        (self.repo / ".project").mkdir()
        root_status, project_status = self.snapshots()
        (self.repo / ".project" / "STATE.md").write_bytes(b"existing\n")
        with self.assertRaises(detect_project.DetectError):
            self.write(root_status, project_status)
        self.assertEqual((self.repo / ".project" / "STATE.md").read_bytes(), b"existing\n")


if __name__ == "__main__":
    unittest.main()
