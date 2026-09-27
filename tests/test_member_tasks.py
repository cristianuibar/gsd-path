import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts import build_state, check_handoffs, check_task_briefs
from tests.test_build_state import BRANCH, plan_text, run_git, task_text
from tests.test_task_briefs import CONTRACT, TASK_TEMPLATE

ROOT = Path(__file__).resolve().parents[1]
MEMBERS = ROOT / "scripts" / "members.py"
STATE = (
    "---\npipeline: gsd-path/v2\nproject: acme\nmilestone: demo\nphase: {phase}\n"
    "status: active\nbranch: {branch}\narchive: null\n---\n"
)


def git(repo: Path, *arguments: str) -> str:
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *arguments],
                          cwd=repo, text=True, capture_output=True, check=True).stdout.strip()


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
        (self.coordinator / ".project" / "STATE.md").write_text(
            STATE.format(phase="plan", branch="gsd-path/M001"), encoding="utf-8")
        (self.coordinator / "lib").mkdir()
        (self.coordinator / "lib" / "server.py").write_text("coordinator only\n", encoding="utf-8")
        git(self.coordinator, "add", "-A")
        git(self.coordinator, "commit", "-q", "-m", "init")
        self.member = root / "web"
        self.member.mkdir()
        git(self.member, "init", "-q", "-b", "main")
        (self.member / "src").mkdir()
        (self.member / "src" / "app.py").write_text("member only\n", encoding="utf-8")
        git(self.member, "add", "-A")
        git(self.member, "commit", "-q", "-m", "init")
        git(self.member, "remote", "add", "origin", "https://github.com/acme/web.git")
        git(self.member, "update-ref", "refs/remotes/origin/main", "HEAD")
        git(self.member, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
        subprocess.run([sys.executable, str(MEMBERS), "add", "--repo", str(self.coordinator),
                        "--name", "web", "--checkout", str(self.member)],
                       text=True, capture_output=True, check=True)
        self.head = git(self.coordinator, "rev-parse", "HEAD")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write(self, task_id: str, text: str) -> None:
        (self.coordinator / ".project" / "tasks" / f"{task_id}-task.md").write_text(text, encoding="utf-8")

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

    def test_repo_must_name_a_member(self) -> None:
        self.write("T001", member_task("T001", "src/app.py", "Edit `src/app.py`.", repo="sdk"))
        self.assertIn("repo: names no member in MEMBERS.md: sdk", self.problems())


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
    def test_build_refuses_member_tasks_until_member_landing_exists(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            run_git(repo, "init", "-q")
            run_git(repo, "config", "user.email", "t@t")
            run_git(repo, "config", "user.name", "t")
            run_git(repo, "switch", "-q", "-c", BRANCH)
            (repo / ".project" / "plan").mkdir(parents=True)
            (repo / ".project" / "tasks").mkdir()
            (repo / ".project" / "STATE.md").write_text(
                STATE.format(phase="build", branch=BRANCH), encoding="utf-8")
            (repo / ".project" / "plan" / "PLAN.md").write_text(
                plan_text(((("T001", "Member", (), ("app.py",)),),)), encoding="utf-8")
            text = task_text("T001", "Member", 1, (), ("app.py",))
            (repo / ".project" / "tasks" / "T001-task.md").write_text(
                text.replace("files:", "repo: web\nfiles:", 1), encoding="utf-8")
            run_git(repo, "add", "-A")
            run_git(repo, "commit", "-q", "-m", "plan")
            with self.assertRaisesRegex(build_state.BuildStateError, "member task"):
                build_state.ready(str(repo))


if __name__ == "__main__":
    unittest.main()
