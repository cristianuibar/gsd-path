import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts import pipeline_git, state_checkpoint, state_promote
from tests.test_pipeline_state import PLAN_WAVE, roadmap_text, run_git, state_text, task_text

MEMBERS = Path(__file__).resolve().parents[1] / "scripts" / "members.py"


class MemberDriftTests(unittest.TestCase):
    """Lookahead member tasks are checked against the member merge the shipped milestone made."""

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name).resolve()
        self.member = base / "web"
        run_git(base, "init", "-b", "main", str(self.member))
        for key, value in (("user.name", "t"), ("user.email", "t@t")):
            run_git(self.member, "config", key, value)
        (self.member / "app.py").write_text("approved = True\n", encoding="utf-8")
        (self.member / "other.py").write_text("other = True\n", encoding="utf-8")
        run_git(self.member, "add", "-A")
        run_git(self.member, "commit", "-m", "member base")
        run_git(self.member, "remote", "add", "origin", "https://github.com/acme/web.git")
        run_git(self.member, "update-ref", "refs/remotes/origin/main", "HEAD")
        run_git(self.member, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
        self.repo = base / "repo"
        run_git(base, "init", "-b", "main", str(self.repo))
        for key, value in (("user.name", "t"), ("user.email", "t@t")):
            run_git(self.repo, "config", key, value)
        (self.repo / "README.md").write_text("coordinator\n", encoding="utf-8")
        run_git(self.repo, "add", "-A")
        run_git(self.repo, "commit", "-m", "base")
        run_git(self.repo, "switch", "-c", "gsd-path/M001")
        project = self.repo / ".project"
        (project / "next" / "tasks").mkdir(parents=True)
        (project / "next" / "plan").mkdir()
        (project / "next" / "review").mkdir()
        (project / "STATE.md").write_text(state_text(milestone="first", phase="plan", status="active",
                                                     branch="gsd-path/M001"), encoding="utf-8")
        joined = subprocess.run([sys.executable, str(MEMBERS), "add", "--repo", str(self.repo), "--name", "web",
                                 "--checkout", str(self.member)], text=True, capture_output=True)
        self.assertEqual(joined.returncode, 0, joined.stderr)
        (project / "STATE.md").write_text(state_text(milestone="first", phase="build", status="active",
                                                     branch="gsd-path/M001"), encoding="utf-8")
        (project / "ROADMAP.md").write_text(roadmap_text(), encoding="utf-8")
        (project / "next" / "STATE.md").write_text(state_text(status="active"), encoding="utf-8")
        (project / "next" / "tasks" / "T001-change-app.md").write_text(
            task_text().replace("T002", "T001").replace("files:", "repo: web\nfiles:", 1), encoding="utf-8")
        (project / "next" / "plan" / "PLAN.md").write_text(
            PLAN_WAVE.format(title="second").replace("T002", "T001"), encoding="utf-8")
        (project / "next" / "review" / "PLAN-PANEL.md").write_text("# Plan review panel\n\nStatus: ready\n",
                                                                    encoding="utf-8")
        self.approval_base = run_git(self.member, "rev-parse", "HEAD").stdout.strip()
        state_checkpoint.checkpoint_approval(self.repo, "plan", run_git(self.repo, "rev-parse", "HEAD").stdout.strip(),
                                             ".project/next")

    def ship(self, changed: str) -> str:
        """The shipped milestone merged a member change to `changed` into the member's main."""
        run_git(self.member, "switch", "-c", "gsd-path/demo-M001")
        (self.member / changed).write_text("changed = True\n", encoding="utf-8")
        run_git(self.member, "commit", "-am", "member landing")
        reviewed = run_git(self.member, "rev-parse", "HEAD").stdout.strip()
        run_git(self.member, "switch", "main")
        run_git(self.member, "merge", "--no-ff", "-m", "integrate", "gsd-path/demo-M001")
        merge = run_git(self.member, "rev-parse", "HEAD").stdout.strip()
        project = self.repo / ".project"
        (project / "STATE.md").write_text(state_text(milestone="first", phase="shipped", status="done",
                                                     branch="gsd-path/M001", archive=".project/archive/001-first/"),
                                          encoding="utf-8")
        run_git(self.repo, "add", "-A")
        rows = [{"name": "web", "reviewed_head": reviewed, "merge": merge, "tag": "milestone/demo-001-first"}]
        run_git(self.repo, "commit", "-m", "ship: M001 — first", "-m",
                pipeline_git.ship_commit_body(".project/archive/001-first", "d" * 40, rows))
        run_git(self.repo, "switch", "main")
        run_git(self.repo, "merge", "--no-ff", "gsd-path/M001", "-m", "integrate: M001 — merge gsd-path/M001 into main")
        integrate = run_git(self.repo, "rev-parse", "HEAD").stdout.strip()
        run_git(self.repo, "tag", "-a", "-m", "milestone 001-first", "milestone/001-first", integrate)
        tag = run_git(self.repo, "rev-parse", "refs/tags/milestone/001-first").stdout.strip()
        run_git(self.repo, "update-ref", "refs/remotes/origin/tags/milestone/001-first", tag)
        run_git(self.repo, "update-ref", "refs/remotes/origin/main", integrate)
        run_git(self.repo, "switch", "-c", "gsd-path/M002")
        return integrate

    def test_approval_records_the_member_base_the_brief_was_checked_at(self) -> None:
        common = Path(run_git(self.repo, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip())
        recorded = json.loads((common / "gsd-path" / "lookahead-member-bases" / "second.json").read_text())
        self.assertEqual(recorded["bases"], {"web": self.approval_base})

    def test_member_change_to_a_declared_path_flags_the_task(self) -> None:
        integrate = self.ship("app.py")
        result = state_promote.promote_next(self.repo, "second", "gsd-path/M002", integrate)
        self.assertEqual(result["drift"]["class"], "changed")
        self.assertEqual(result["drift"]["task_ids"], ["T001"])
        self.assertIn("web:app.py", result["drift"]["changed_paths"])
        again = state_promote.promote_next(self.repo, "second", "gsd-path/M002", integrate)
        self.assertEqual(again["drift"], result["drift"])

    def test_member_change_elsewhere_keeps_the_plan_clean(self) -> None:
        integrate = self.ship("other.py")
        result = state_promote.promote_next(self.repo, "second", "gsd-path/M002", integrate)
        self.assertEqual(result["drift"]["class"], "clean")

    def test_missing_member_bases_stay_unverifiable(self) -> None:
        common = Path(run_git(self.repo, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip())
        (common / "gsd-path" / "lookahead-member-bases" / "second.json").unlink()
        integrate = self.ship("other.py")
        result = state_promote.promote_next(self.repo, "second", "gsd-path/M002", integrate)
        self.assertEqual(result["drift"]["class"], "unverifiable")


if __name__ == "__main__":
    unittest.main()
