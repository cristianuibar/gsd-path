import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts import build_state, check_handoffs, check_task_briefs, pipeline_state, state_checkpoint
from tests.test_build_state import BRANCH, plan_text, run_git, task_text
from tests.test_task_briefs import CONTRACT, PLAN_WAVE, TASK_TEMPLATE

ROOT = Path(__file__).resolve().parents[1]
MEMBERS = ROOT / "scripts" / "members.py"
STATE = (
    "---\npipeline: gsd-path/v2\nproject: acme\nmilestone: demo\nphase: {phase}\n"
    "status: active\nbranch: {branch}\narchive: null\n---\n"
)


def git(repo: Path, *arguments: str) -> str:
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *arguments],
                          cwd=repo, encoding="utf-8", errors="replace", capture_output=True, check=True).stdout.strip()


def member_task(task_id: str, files: str, context: str, repo: str = "web",
                contract: str = "- None", verify: str = "test -f src/app.py") -> str:
    text = TASK_TEMPLATE.format(
        task_id=task_id, files_block=f"  - {files}", context=context,
        approach="- Keep the change small.", contract=contract, verify=verify,
    )
    return text.replace("files:\n", f"repo: {repo}\nfiles:\n", 1) if repo else text


class MemberTaskBriefTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name).resolve()
        self.coordinator = root / "acme"
        (self.coordinator / ".project" / "tasks").mkdir(parents=True)
        git(root, "init", "-q", "-b", "main", str(self.coordinator))
        (self.coordinator / ".project" / "STATE.md").write_bytes(
            STATE.format(phase="plan", branch="gsd-path/M001").encode("utf-8"))
        (self.coordinator / "lib").mkdir()
        (self.coordinator / "lib" / "server.py").write_bytes("coordinator only\n".encode("utf-8"))
        git(self.coordinator, "add", "-A")
        git(self.coordinator, "commit", "-q", "-m", "init")
        self.member = root / "web"
        self.member.mkdir()
        git(self.member, "init", "-q", "-b", "main")
        (self.member / "src").mkdir()
        (self.member / "src" / "app.py").write_bytes("member only\n".encode("utf-8"))
        git(self.member, "add", "-A")
        git(self.member, "commit", "-q", "-m", "init")
        git(self.member, "remote", "add", "origin", "https://github.com/acme/web.git")
        git(self.member, "update-ref", "refs/remotes/origin/main", "HEAD")
        git(self.member, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
        subprocess.run([sys.executable, str(MEMBERS), "add", "--repo", str(self.coordinator),
                        "--name", "web", "--checkout", str(self.member)],
                       encoding="utf-8", errors="replace", capture_output=True, check=True)
        self.head = git(self.coordinator, "rev-parse", "HEAD")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write(self, task_id: str, text: str) -> None:
        (self.coordinator / ".project" / "tasks" / f"{task_id}-task.md").write_bytes(text.encode("utf-8"))

    def problems(self) -> str:
        try:
            check_task_briefs.validate_task_briefs(self.coordinator, self.head)
        except check_task_briefs.BriefError as error:
            return str(error)
        return ""

    def test_member_task_paths_resolve_in_the_member(self) -> None:
        self.write("T001", member_task("T001", "src/new.py", "Follow `src/app.py` in the member.",
                                       verify="test -f src/app.py"))
        self.assertEqual(self.problems(), "")

    def test_member_task_paths_do_not_resolve_in_the_coordinator(self) -> None:
        self.write("T001", member_task("T001", "src/app.py", "Read `lib/server.py` first.",
                                       verify="test -f lib/server.py"))
        problems = self.problems()
        self.assertIn("## Context names a path missing at the layer base: lib/server.py", problems)
        self.assertIn("## Verify names a path missing at the layer base: lib/server.py", problems)

    def test_coordinator_task_is_unchanged(self) -> None:
        self.write("T001", member_task("T001", "lib/server.py", "Edit `lib/server.py`.", repo="",
                                       verify="test -f lib/server.py"))
        self.assertEqual(self.problems(), "")
        self.write("T001", member_task("T001", "lib/server.py", "Read `src/app.py`.", repo=""))
        self.assertIn("path missing at the layer base: src/app.py", self.problems())

    def test_landed_member_task_checks_its_recorded_member_base(self) -> None:
        old = git(self.member, "rev-parse", "HEAD")
        git(self.member, "rm", "-q", "src/app.py")
        git(self.member, "commit", "-q", "-m", "drop app")
        git(self.member, "update-ref", "refs/remotes/origin/main", "HEAD")
        self.write("T001", member_task("T001", "src/new.py", "Follow `src/app.py`.",
                                       verify="test -f src/app.py"))
        self.assertIn("path missing at the layer base: src/app.py", self.problems())
        check_task_briefs.validate_task_briefs(self.coordinator, self.head, landed_bases={"T001": old})

    def test_plan_approval_resolves_landed_base_in_member(self) -> None:
        old = git(self.member, "rev-parse", "HEAD")
        self.assertNotEqual(subprocess.run(
            ["git", "cat-file", "-e", f"{old}^{{commit}}"], cwd=self.coordinator,
            capture_output=True, check=False,
        ).returncode, 0)
        git(self.member, "rm", "-q", "src/app.py")
        git(self.member, "commit", "-q", "-m", "drop app")
        git(self.member, "update-ref", "refs/remotes/origin/main", "HEAD")
        (self.coordinator / ".project" / "plan").mkdir()
        (self.coordinator / ".project" / "plan" / "PLAN.md").write_bytes(
            PLAN_WAVE.format(title="demo").encode("utf-8"))
        task = member_task("T001", "src/new.py", "Follow `src/app.py`.",
                           verify="test -f src/app.py")
        task = task.replace("status: pending", "status: done").replace(
            "agent: null", "agent: coder").replace("base: null", f"base: {old}")
        self.write("T001", task)

        state_checkpoint._validate_plan_briefs(self.coordinator, "plan", ".project")

        self.write("T001", task.replace(f"base: {old}", f"base: {'0' * 40}"))
        with self.assertRaisesRegex(pipeline_state.PipelineStateError,
                                    "landed task has invalid historical base"):
            state_checkpoint._validate_plan_briefs(self.coordinator, "plan", ".project")

    def test_member_brief_during_build_resolves_at_the_bound_branch_tip(self) -> None:
        git(self.member, "checkout", "-q", "-b", "gsd-path/acme-M001")
        (self.member / "src" / "landed.py").write_text("earlier landing\n", encoding="utf-8")
        git(self.member, "add", "-A")
        git(self.member, "commit", "-q", "-m", "earlier landing")
        git(self.member, "checkout", "-q", "main")
        self.write("T001", member_task("T001", "src/new.py", "Follow `src/landed.py`.",
                                       verify="test -f src/landed.py"))
        self.assertIn("path missing at the layer base: src/landed.py", self.problems())
        lock = self.coordinator / ".project" / "build" / "members.json"
        lock.parent.mkdir(parents=True)
        lock.write_text('{"schema": "gsd-path/member-lock/v1", "members": [{"name": "web", '
                        '"branch": "gsd-path/acme-M001", "base": "x"}]}', encoding="utf-8")
        self.assertEqual(self.problems(), "")

    def test_plan_recovery_brief_uses_the_existing_build_lock(self) -> None:
        git(self.member, "checkout", "-q", "-b", "gsd-path/acme-M001")
        (self.member / "src" / "landed.py").write_text("earlier landing\n", encoding="utf-8")
        git(self.member, "add", "-A")
        git(self.member, "commit", "-q", "-m", "earlier landing")
        git(self.member, "checkout", "-q", "main")
        (self.coordinator / ".project" / "plan").mkdir()
        (self.coordinator / ".project" / "plan" / "PLAN.md").write_text(
            PLAN_WAVE.format(title="demo"), encoding="utf-8")
        self.write("T001", member_task("T001", "src/new.py", "Follow `src/landed.py`.",
                                       verify="test -f src/landed.py"))
        with self.assertRaisesRegex(pipeline_state.PipelineStateError, "src/landed.py"):
            state_checkpoint._validate_plan_briefs(self.coordinator, "plan", ".project")
        lock = self.coordinator / ".project" / "build" / "members.json"
        lock.parent.mkdir(parents=True)
        lock.write_text('{"schema": "gsd-path/member-lock/v1", "members": [{"name": "web", '
                        '"branch": "gsd-path/acme-M001", "base": "x"}]}', encoding="utf-8")
        state_checkpoint._validate_plan_briefs(self.coordinator, "plan", ".project")

    def test_repo_must_name_a_member(self) -> None:
        self.write("T001", member_task("T001", "src/app.py", "Edit `src/app.py`.", repo="sdk"))
        self.assertIn("repo: names no member in MEMBERS.md: sdk", self.problems())


class MemberTaskReadyTests(unittest.TestCase):
    def test_same_path_in_different_repos_is_ready_together(self) -> None:
        from unittest import mock
        with tempfile.TemporaryDirectory() as temporary, \
                mock.patch.dict(os.environ, {build_state.MEMBER_EXECUTION_GATE: "1"}):
            repo = Path(temporary)
            run_git(repo, "init", "-q")
            run_git(repo, "config", "user.email", "t@t")
            run_git(repo, "config", "user.name", "t")
            run_git(repo, "switch", "-q", "-c", BRANCH)
            (repo / ".project" / "plan").mkdir(parents=True)
            (repo / ".project" / "tasks").mkdir()
            (repo / ".project" / "STATE.md").write_text(STATE.format(phase="build", branch=BRANCH), encoding="utf-8")
            (repo / ".project" / "plan" / "PLAN.md").write_text(plan_text(((
                ("T001", "One", (), ("app.py",)), ("T002", "Two", (), ("app.py",))),)), encoding="utf-8")
            (repo / ".project" / "tasks" / "T001-task.md").write_text(
                task_text("T001", "One", 1, (), ("app.py",)), encoding="utf-8")
            (repo / ".project" / "tasks" / "T002-task.md").write_text(
                task_text("T002", "Two", 1, (), ("app.py",)).replace("files:", "repo: web\nfiles:", 1), encoding="utf-8")
            run_git(repo, "add", "-A")
            run_git(repo, "commit", "-q", "-m", "plan")
            ready = build_state.ready(str(repo))
            self.assertEqual(sorted(task["id"] for task in ready["ready"]), ["T001", "T002"])
            self.assertEqual({task["id"]: task.get("repo") for task in ready["ready"]}, {"T001": None, "T002": "web"})


class MemberTaskGraphTests(unittest.TestCase):
    def graph(self, *tasks):
        texts = {task_id: text for task_id, text in tasks}
        return check_handoffs._validate_task_graph({1: "Deliver", 2: "Next"}, texts, initial=True)

    def task(self, task_id: str, files: str, repo: str = "", deps: str = "[]", wave: int = 1) -> tuple:
        text = member_task(task_id, files, "Change the module.", repo=repo)
        text = text.replace("deps: []", f"deps: {deps}").replace("wave: 1", f"wave: {wave}")
        return task_id, text

    def test_same_path_in_different_repos_does_not_overlap(self) -> None:
        self.graph(self.task("T001", "app.py"), self.task("T002", "app.py", repo="web"))
        with self.assertRaisesRegex(check_handoffs.HandoffError, "same-wave file overlap"):
            self.graph(self.task("T001", "app.py", repo="web"), self.task("T002", "app.py", repo="web"))

    def test_dependency_files_stay_in_their_repo(self) -> None:
        supplied = self.graph(
            self.task("T001", "shared.py"),
            self.task("T002", "client.py", repo="web", deps="[T001]", wave=2),
            self.task("T003", "server.py", deps="[T001]", wave=2),
        )
        self.assertEqual(supplied["T002"], set())
        self.assertEqual(supplied["T003"], {"shared.py"})


class MemberTaskBuildTests(unittest.TestCase):
    def test_build_refuses_member_tasks_without_the_member_execution_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            run_git(repo, "init", "-q")
            run_git(repo, "config", "user.email", "t@t")
            run_git(repo, "config", "user.name", "t")
            run_git(repo, "switch", "-q", "-c", BRANCH)
            (repo / ".project" / "plan").mkdir(parents=True)
            (repo / ".project" / "tasks").mkdir()
            (repo / ".project" / "STATE.md").write_bytes(
                STATE.format(phase="build", branch=BRANCH).encode("utf-8"))
            (repo / ".project" / "plan" / "PLAN.md").write_bytes(
                plan_text(((("T001", "Member", (), ("app.py",)),),)).encode("utf-8"))
            text = task_text("T001", "Member", 1, (), ("app.py",))
            (repo / ".project" / "tasks" / "T001-task.md").write_bytes(
                text.replace("files:", "repo: web\nfiles:", 1).encode("utf-8"))
            run_git(repo, "add", "-A")
            run_git(repo, "commit", "-q", "-m", "plan")
            with self.assertRaisesRegex(build_state.BuildStateError, "member task"):
                build_state.ready(str(repo))


if __name__ == "__main__":
    unittest.main()
