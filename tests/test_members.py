import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import archive_milestone
import check_handoffs
import lean_verification

SCRIPT = ROOT / "scripts" / "members.py"

STATE = """---
pipeline: gsd-path/v2
project: {project}
milestone: {milestone}
phase: {phase}
status: {status}
branch: {branch}
archive: {archive}
---
"""


def git(repo: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments], cwd=repo, text=True, capture_output=True, check=True
    ).stdout.strip()


def write_state(root: Path, project: str, phase: str, status: str = "active",
                milestone: str = "demo", branch: str = "gsd-path/M001",
                archive: str = "null") -> None:
    (root / ".project").mkdir(exist_ok=True)
    (root / ".project" / "STATE.md").write_text(
        STATE.format(project=project, milestone=milestone, phase=phase,
                     status=status, branch=branch, archive=archive),
        encoding="utf-8",
    )


def commit_all(repo: Path, message: str = "init") -> None:
    git(repo, "add", "-A")
    git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", message)


class MemberTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.coordinator = self.root / "acme"
        self.coordinator.mkdir()
        git(self.coordinator, "init", "-q", "-b", "main")
        write_state(self.coordinator, "acme", "plan")
        (self.coordinator / ".project" / "REPOSITORY.md").write_text(
            "# Repository Binding\n\nKind: new-github\n", encoding="utf-8"
        )
        commit_all(self.coordinator)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def make_member(self, name: str, parent: Optional[Path] = None,
                    remote: Optional[str] = None, default: str = "main") -> Path:
        member = (parent or self.root) / name
        member.mkdir()
        git(member, "init", "-q", "-b", "main")
        (member / "README.md").write_text(name, encoding="utf-8")
        commit_all(member)
        git(member, "remote", "add", "origin", remote or f"https://github.com/acme/{name}.git")
        git(member, "update-ref", f"refs/remotes/origin/{default}", "HEAD")
        git(member, "symbolic-ref", "refs/remotes/origin/HEAD", f"refs/remotes/origin/{default}")
        return member

    def run_members(self, *arguments: str):
        return subprocess.run(
            [sys.executable, str(SCRIPT), arguments[0], "--repo", str(self.coordinator),
             *arguments[1:]],
            text=True, capture_output=True, check=False,
        )

    def add(self, name: str, checkout: Path, *extra: str):
        return self.run_members("add", "--name", name, "--checkout", str(checkout), *extra)

    def assert_refused(self, result, reason: str) -> None:
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(reason, result.stderr)
        self.assertFalse((self.coordinator / ".project" / "MEMBERS.md").exists())

    def test_add_records_members_in_order_without_touching_repository_binding(self) -> None:
        binding = (self.coordinator / ".project" / "REPOSITORY.md").read_bytes()
        web = self.make_member("web")
        sdk = self.make_member("sdk")
        self.assertEqual(self.add("web", web).returncode, 0)
        added = self.add("sdk", sdk, "--integration", "pull-request")
        self.assertEqual(added.returncode, 0, added.stderr)

        validated = self.run_members("validate")
        self.assertEqual(validated.returncode, 0, validated.stderr)
        members = json.loads(validated.stdout)["members"]
        self.assertEqual(
            members,
            [
                {"name": "web", "checkout": str(web), "remote": "https://github.com/acme/web.git",
                 "integration": "default"},
                {"name": "sdk", "checkout": str(sdk), "remote": "https://github.com/acme/sdk.git",
                 "integration": "pull-request"},
            ],
        )
        self.assertEqual((self.coordinator / ".project" / "REPOSITORY.md").read_bytes(), binding)

    def test_validate_without_members_file_reports_no_members(self) -> None:
        result = self.run_members("validate")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"members": []})
        self.assertFalse((self.coordinator / ".project" / "MEMBERS.md").exists())

    def test_add_refuses_remote_default_other_than_main(self) -> None:
        self.assert_refused(self.add("web", self.make_member("web", default="develop")),
                            "remote default must be main")

    def test_add_refuses_origin_outside_github(self) -> None:
        member = self.make_member("web", remote="https://gitlab.com/acme/web.git")
        self.assert_refused(self.add("web", member), "GitHub.com origin")

    def test_add_refuses_dirty_member_worktree(self) -> None:
        member = self.make_member("web")
        (member / "README.md").write_text("changed", encoding="utf-8")
        self.assert_refused(self.add("web", member), "uncommitted changes")

    def test_add_refuses_untracked_files_hidden_by_git_config(self) -> None:
        member = self.make_member("web")
        git(member, "config", "status.showUntrackedFiles", "no")
        (member / "untracked.txt").write_text("hidden", encoding="utf-8")
        self.assert_refused(self.add("web", member), "uncommitted changes")

    def test_add_refuses_member_nested_in_coordinator(self) -> None:
        member = self.make_member("web", parent=self.coordinator)
        self.assert_refused(self.add("web", member), "nested")

    def test_add_refuses_submodule_checkout(self) -> None:
        source = self.make_member("web-source")
        parent = self.make_member("host")
        git(parent, "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(source), "web")
        commit_all(parent, "add submodule")
        submodule = parent / "web"
        git(submodule, "remote", "set-url", "origin", "https://github.com/acme/web.git")
        git(submodule, "update-ref", "refs/remotes/origin/main", "HEAD")
        git(submodule, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
        self.assert_refused(self.add("web", submodule), "submodule")

    def test_add_refuses_member_with_active_milestone(self) -> None:
        member = self.make_member("web")
        write_state(member, "web", "build")
        commit_all(member, "path state")
        self.assert_refused(self.add("web", member), "active milestone")

    def test_add_and_validate_refuse_unreadable_member_state(self) -> None:
        for kind in ("broken symlink", "live symlink", "directory"):
            with self.subTest(kind):
                member = self.make_member(kind.replace(" ", "-"))
                state = member / ".project" / "STATE.md"
                state.parent.mkdir()
                if kind == "directory":
                    state.mkdir()
                else:
                    if kind == "live symlink":
                        write_state(member, "web", "shipped", status="done")
                        state.rename(member / ".project" / "saved-state.md")
                        state.symlink_to("saved-state.md")
                    else:
                        state.symlink_to("missing-state.md")
                    commit_all(member, "state link")
                self.assert_refused(self.add("web", member), "member STATE.md is unreadable")

        member = self.make_member("valid")
        self.assertEqual(self.add("valid", member).returncode, 0)
        state = member / ".project" / "STATE.md"
        state.parent.mkdir()
        state.symlink_to("missing-state.md")
        commit_all(member, "state link")
        result = self.run_members("validate")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("member STATE.md is unreadable", result.stderr)

    def test_add_accepts_member_whose_own_milestone_shipped(self) -> None:
        member = self.make_member("web")
        write_state(member, "web", "shipped", status="done", milestone="demo",
                    archive=".project/archive/001-demo")
        commit_all(member, "path state")
        result = self.add("web", member)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_add_refuses_colliding_member_branch_or_tag(self) -> None:
        cases = {
            "branch": ("branch", "gsd-path/acme-M001"),
            "task": ("branch", "gsd-path-task/acme-T001"),
            "remote": ("update-ref", "refs/remotes/origin/gsd-path/acme-M002"),
            "tag": ("tag", "milestone/acme-001-demo"),
        }
        for label, (command, ref) in cases.items():
            with self.subTest(label):
                member = self.make_member(f"web-{label}")
                if command == "update-ref":
                    git(member, "update-ref", ref, "HEAD")
                else:
                    git(member, command, ref)
                self.assert_refused(self.add(f"web-{label}", member), "collide with coordinator")

    def test_add_ignores_member_refs_named_for_other_coordinators(self) -> None:
        member = self.make_member("web")
        git(member, "branch", "gsd-path/M001")
        git(member, "tag", "milestone/001-demo")
        git(member, "branch", "gsd-path/acmex-M001")
        result = self.add("web", member)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_add_refuses_during_build_and_ship(self) -> None:
        member = self.make_member("web")
        for phase in ("build", "ship"):
            with self.subTest(phase):
                write_state(self.coordinator, "acme", phase)
                self.assert_refused(self.add("web", member), "milestone boundary")

    def test_add_refuses_duplicate_name_or_checkout(self) -> None:
        web = self.make_member("web")
        self.assertEqual(self.add("web", web).returncode, 0)
        before = (self.coordinator / ".project" / "MEMBERS.md").read_bytes()
        for name, checkout in (("web", self.make_member("other")), ("web2", web)):
            with self.subTest(name):
                result = self.add(name, checkout)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("already", result.stderr)
                self.assertEqual((self.coordinator / ".project" / "MEMBERS.md").read_bytes(), before)

    def test_add_refuses_duplicate_github_origin_across_url_forms(self) -> None:
        web = self.make_member("web")
        self.assertEqual(self.add("web", web).returncode, 0)
        before = (self.coordinator / ".project" / "MEMBERS.md").read_bytes()
        for name, remote in (("clone", "git@github.com:Acme/Web"),
                             ("clone2", "ssh://git@github.com/acme/web.git")):
            with self.subTest(remote):
                clone = self.make_member(name, remote=remote)
                result = self.add(name, clone)
                self.assertIn("member already recorded", result.stderr)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual((self.coordinator / ".project" / "MEMBERS.md").read_bytes(), before)

    def test_add_refuses_duplicate_git_common_dir(self) -> None:
        web = self.make_member("web")
        self.assertEqual(self.add("web", web).returncode, 0)
        linked = self.root / "linked"
        git(web, "worktree", "add", "-q", "-b", "linked", str(linked))
        path = self.coordinator / ".project" / "MEMBERS.md"
        path.write_text(path.read_text(encoding="utf-8").replace(
            "https://github.com/acme/web.git", "https://github.com/acme/other.git"
        ), encoding="utf-8")
        before = path.read_bytes()
        result = self.add("linked", linked)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("member already recorded", result.stderr)
        self.assertEqual(path.read_bytes(), before)

    def test_add_refuses_coordinator_as_its_own_member(self) -> None:
        self.assert_refused(self.add("acme", self.coordinator), "coordinator")

    def test_validate_rechecks_members_after_add(self) -> None:
        web = self.make_member("web")
        self.assertEqual(self.add("web", web).returncode, 0)
        (web / "README.md").write_text("changed", encoding="utf-8")
        result = self.run_members("validate")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("uncommitted changes", result.stderr)

    def test_validate_refuses_member_whose_origin_changed(self) -> None:
        web = self.make_member("web")
        self.assertEqual(self.add("web", web).returncode, 0)
        git(web, "remote", "set-url", "origin", "https://github.com/acme/other.git")
        result = self.run_members("validate")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("origin changed", result.stderr)

    def test_validate_refuses_malformed_members_file(self) -> None:
        path = self.coordinator / ".project" / "MEMBERS.md"
        for label, body in {
            "unknown field": "## web\nCheckout: /x\nRemote: https://github.com/a/b\nIntegration: default\nColor: red\n",
            "bad name": "## Web App\nCheckout: /x\nRemote: https://github.com/a/b\nIntegration: default\n",
            "bad mode": "## web\nCheckout: /x\nRemote: https://github.com/a/b\nIntegration: squash\n",
            "section heading changed": "# web\nCheckout: /x\nRemote: https://github.com/a/b\nIntegration: default\n",
            "unexpected preamble": "extra\n## web\nCheckout: /x\nRemote: https://github.com/a/b\nIntegration: default\n",
        }.items():
            with self.subTest(label):
                path.write_text("# Members\n\n" + body, encoding="utf-8")
                result = self.run_members("validate")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("MEMBERS.md", result.stderr)


class MembersArtifactTests(unittest.TestCase):
    def test_ship_verification_accepts_members_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary).resolve()
            git(repo, "init", "-q", "-b", "gsd-path/M001")
            write_state(repo, "acme", "ship")
            (repo / ".project" / "MEMBERS.md").write_text("# Members\n", encoding="utf-8")
            commit_all(repo)
            head = git(repo, "rev-parse", "HEAD")
            lean_verification._require_ship_inputs(repo, head)
            (repo / ".project" / "STRAY.md").write_text("x", encoding="utf-8")
            with self.assertRaisesRegex(check_handoffs.HandoffError, "STRAY.md"):
                lean_verification._require_ship_inputs(repo, head)

    def test_milestone_close_keeps_members_file_active(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            active = Path(temporary) / ".project"
            archive = active / "archive" / "001-demo"
            archive.mkdir(parents=True)
            (active / "STATE.md").write_text("state", encoding="utf-8")
            (active / "MEMBERS.md").write_text("# Members\n", encoding="utf-8")
            archive_milestone.require_clean_active_root(active, archive)
            (active / "STRAY.md").write_text("x", encoding="utf-8")
            with self.assertRaisesRegex(archive_milestone.ArchiveError, "STRAY.md"):
                archive_milestone.require_clean_active_root(active, archive)


if __name__ == "__main__":
    unittest.main()
