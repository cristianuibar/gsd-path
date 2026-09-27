import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts import members, pipeline_state

ROOT = Path(__file__).resolve().parents[1]
MEMBERS = ROOT / "scripts" / "members.py"
STATE = (
    "---\npipeline: gsd-path/v2\nproject: acme\nmilestone: demo\nphase: plan\nstatus: done\n"
    "branch: gsd-path/M001\narchive: null\n---\n\n# Project State\n\n## Log\n\n- 2026-09-27 — plan — plan approved\n"
)
TASK = "---\nid: {id}\ntitle: T\nwave: 1\ndeps: []\nstatus: pending\n{repo}files:\n  - {path}\n---\n# {id}\n"
EXPECT = {"phase": "plan", "status": "done", "branch": "gsd-path/M001", "archive": None}
CHANGES = {"phase": "build", "status": "active"}


def git(repo: Path, *arguments: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *arguments],
                          cwd=repo, text=True, capture_output=True, check=check)


class MemberBuildStartTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.coordinator = self.root / "acme"
        (self.coordinator / ".project" / "tasks").mkdir(parents=True)
        git(self.root, "init", "-q", "-b", "gsd-path/M001", str(self.coordinator))
        (self.coordinator / ".project" / "STATE.md").write_text(STATE, encoding="utf-8")
        git(self.coordinator, "add", "-A")
        git(self.coordinator, "commit", "-q", "-m", "init")
        self.repos = {}
        for name in ("sdk", "web", "docs"):
            member = self.root / name
            member.mkdir()
            git(member, "init", "-q", "-b", "main")
            (member / "README.md").write_text(name, encoding="utf-8")
            git(member, "add", "-A")
            git(member, "commit", "-q", "-m", "init")
            git(member, "remote", "add", "origin", f"https://github.com/acme/{name}.git")
            git(member, "update-ref", "refs/remotes/origin/main", "HEAD")
            git(member, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
            subprocess.run([sys.executable, str(MEMBERS), "add", "--repo", str(self.coordinator),
                            "--name", name, "--checkout", str(member)],
                           text=True, capture_output=True, check=True)
            self.repos[name] = member

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def tasks(self, *repos: str) -> None:
        for number, repo in enumerate(repos, 1):
            task_id = f"T{number:03d}"
            line = f"repo: {repo}\n" if repo else ""
            (self.coordinator / ".project" / "tasks" / f"{task_id}-t.md").write_text(
                TASK.format(id=task_id, repo=line, path=f"f{number}.py"), encoding="utf-8")

    def start(self):
        return pipeline_state.transition_state(self.coordinator, EXPECT, CHANGES, "build started")

    def phase(self) -> str:
        state, _, _ = pipeline_state.load_state(self.coordinator)
        return f"{state.phase}/{state.status}"

    def branch(self, name: str):
        found = git(self.repos[name], "rev-parse", "--verify", "--quiet",
                    "refs/heads/gsd-path/acme-M001", check=False)
        return found.stdout.strip() or None

    def origin_main(self, name: str) -> str:
        return git(self.repos[name], "rev-parse", "refs/remotes/origin/main").stdout.strip()

    def lock(self):
        return json.loads((self.coordinator / members.LOCK_PATH).read_text(encoding="utf-8"))

    def test_build_start_locks_named_members_in_members_order(self) -> None:
        self.tasks("docs", "", "sdk", "docs")
        self.start()
        self.assertEqual(self.phase(), "build/active")
        self.assertEqual(self.lock(), {
            "schema": "gsd-path/member-lock/v1",
            "members": [
                {"name": "sdk", "branch": "gsd-path/acme-M001", "base": self.origin_main("sdk")},
                {"name": "docs", "branch": "gsd-path/acme-M001", "base": self.origin_main("docs")},
            ],
        })
        self.assertEqual(self.branch("sdk"), self.origin_main("sdk"))
        self.assertEqual(self.branch("docs"), self.origin_main("docs"))
        self.assertIsNone(self.branch("web"))

    def test_coordinator_only_plan_writes_no_lock_and_no_branches(self) -> None:
        self.tasks("", "")
        self.start()
        self.assertEqual(self.phase(), "build/active")
        self.assertFalse((self.coordinator / members.LOCK_PATH).exists())
        self.assertIsNone(self.branch("web"))

    def test_reentry_removes_lock_when_member_tasks_are_removed(self) -> None:
        self.tasks("web")
        self.start()
        self.assertEqual([entry["name"] for entry in self.lock()["members"]], ["web"])
        branch = self.branch("web")
        self.assertIsNotNone(branch)

        self.tasks("")
        self.assertIsNone(members.lock_build_members(self.coordinator))
        self.assertFalse((self.coordinator / members.LOCK_PATH).exists())
        self.assertEqual(self.branch("web"), branch)

    def test_existing_unused_member_branch_is_reused(self) -> None:
        self.tasks("web")
        git(self.repos["web"], "branch", "gsd-path/acme-M001", "refs/remotes/origin/main")
        self.start()
        self.assertEqual(self.lock()["members"][0]["base"], self.origin_main("web"))

    def test_member_branch_with_unlocked_work_blocks_build_start(self) -> None:
        self.tasks("web")
        web = self.repos["web"]
        git(web, "checkout", "-q", "-b", "gsd-path/acme-M001")
        (web / "stray.py").write_text("x", encoding="utf-8")
        git(web, "add", "-A")
        git(web, "commit", "-q", "--no-verify", "-m", "stray")
        git(web, "checkout", "-q", "main")
        with self.assertRaisesRegex(pipeline_state.PipelineStateError, "commits not on origin/main"):
            self.start()
        self.assertEqual(self.phase(), "plan/done")
        self.assertFalse((self.coordinator / members.LOCK_PATH).exists())

    def test_recovery_reentry_keeps_the_locked_base_and_landed_work(self) -> None:
        self.tasks("web")
        self.start()
        base = self.lock()["members"][0]["base"]
        web = self.repos["web"]
        git(web, "checkout", "-q", "gsd-path/acme-M001")
        (web / "landed.py").write_text("x", encoding="utf-8")
        git(web, "add", "-A")
        git(web, "commit", "-q", "--no-verify", "-m", "landed")
        git(web, "checkout", "-q", "main")
        git(web, "commit", "-q", "--allow-empty", "-m", "upstream moved")
        git(web, "update-ref", "refs/remotes/origin/main", "HEAD")
        entries = members.lock_build_members(self.coordinator)
        self.assertEqual(entries[0]["base"], base)

    def test_stale_or_unknown_member_blocks_build_start(self) -> None:
        self.tasks("web")
        members_file = self.coordinator / ".project" / "MEMBERS.md"
        saved = members_file.read_text(encoding="utf-8")
        members_file.write_text(saved.replace("## web\n", "## gone\n"), encoding="utf-8")
        with self.assertRaisesRegex(pipeline_state.PipelineStateError, "web"):
            self.start()
        self.assertEqual(self.phase(), "plan/done")
        members_file.write_text(saved, encoding="utf-8")
        self.assertIsNone(self.branch("web"))
        marker = Path(git(self.repos["web"], "rev-parse", "--path-format=absolute",
                          "--git-common-dir").stdout.strip()) / "gsd-path" / "member.json"
        marker.unlink()
        with self.assertRaisesRegex(pipeline_state.PipelineStateError, "members.py repair"):
            self.start()
        self.assertEqual(self.phase(), "plan/done")
        self.assertIsNone(self.branch("web"))

    def test_changed_later_member_origin_creates_no_refs(self) -> None:
        self.tasks("sdk", "web")
        git(self.repos["web"], "remote", "set-url", "origin", "https://github.com/other/web.git")
        with self.assertRaisesRegex(pipeline_state.PipelineStateError, "member origin changed"):
            self.start()
        self.assertEqual(self.phase(), "plan/done")
        self.assertIsNone(self.branch("sdk"))
        self.assertIsNone(self.branch("web"))
        self.assertFalse((self.coordinator / members.LOCK_PATH).exists())

    def test_ignored_member_lock_blocks_build_start(self) -> None:
        self.tasks("web")
        (self.coordinator / ".gitignore").write_text("/.project/build/members.json\n", encoding="utf-8")
        with self.assertRaisesRegex(pipeline_state.PipelineStateError, "members.json"):
            self.start()
        self.assertEqual(self.phase(), "plan/done")
        self.assertIsNone(self.branch("web"))
        self.assertFalse((self.coordinator / members.LOCK_PATH).exists())

    def test_pending_discussion_creates_no_refs_or_lock(self) -> None:
        self.tasks("web")
        discussion = self.coordinator / ".project" / "discuss"
        discussion.mkdir()
        (discussion / "DIALOGUE.md").write_text(
            "# GSD Path Discussion — Dialogue\n\n## Turns\n\n"
            "### D001 — 2026-09-27 — plan/done — Review\n",
            encoding="utf-8",
        )
        (discussion / "ANSWERS.md").write_text(
            "# GSD Path Discussion — Answers\n\n"
            "## Answer A001 — 2026-09-27 — Review\n\n"
            "- **Status**: final\n- **Follow-up**: required\n"
            "- **Next owner**: gsd-path-plan\n"
            "- **Target artifact**: .project/plan/PLAN.md\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(pipeline_state.PipelineStateError, "pending discussion"):
            self.start()
        self.assertEqual(self.phase(), "plan/done")
        self.assertIsNone(self.branch("web"))
        self.assertFalse((self.coordinator / members.LOCK_PATH).exists())


if __name__ == "__main__":
    unittest.main()
